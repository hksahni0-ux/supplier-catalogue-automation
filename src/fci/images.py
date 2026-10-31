"""Square, web-ready product and swatch images that keep the supplier's full quality.

By default nothing is resampled: room shots are centre-cropped to a square at native
resolution, and studio cut-outs are trimmed and padded onto white without scaling the
product. Every output pixel is therefore a source pixel, so zooming shows the same detail as
the supplier's original. JPEGs are written at quality 95 with 4:4:4 chroma and the source
colour profile, and `fidelity_db` measures each result against its source. A fixed size
(e.g. FCI's previous 1000 px) remains available through `ImageSpec(size=...)`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from io import BytesIO

import imagehash
import numpy as np
from PIL import Image, ImageChops, ImageOps

WHITE = (255, 255, 255)
BLOCK = 8  # JPEG block size: crops and offsets on this grid recompress almost losslessly
Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class ImageSpec:
    size: int | None = None  # None = native resolution (no resampling)
    margin: float = 0.05  # cut-out padding on each side
    quality: int = 95
    subsampling: int = 0  # 0 = 4:4:4, no chroma loss
    min_source_side: int = 500  # smaller sources look soft on a product page
    swatch_size: int | None = None  # None = native resolution
    duplicate_distance: int = 8  # perceptual-hash bits
    min_fidelity_db: float = 40.0  # PSNR treated as visually lossless

    def encode(self, result: Processed) -> bytes:
        buffer = BytesIO()
        options: dict[str, object] = {
            "quality": self.quality,
            "subsampling": self.subsampling,
            "optimize": True,
            "progressive": True,
        }
        if result.icc_profile:
            options["icc_profile"] = result.icc_profile
        if result.qtables:  # re-save at the supplier's own JPEG quality
            options.pop("quality")
            options["qtables"] = result.qtables
        result.image.save(buffer, "JPEG", **options)
        return buffer.getvalue()


@dataclass
class Processed:
    image: Image.Image
    icc_profile: bytes | None = None
    qtables: dict[int, list[int]] | None = None  # source JPEG quantisation tables
    source_box: Box = (0, 0, 0, 0)  # region of the source image that was used
    offset: tuple[int, int] = (0, 0)  # where that region sits in the output
    scale: float = 1.0  # 1.0 = no resampling
    notes: list[str] = field(default_factory=list)


DEFAULT_SPEC = ImageSpec()


def to_rgb(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, WHITE)
        background.paste(img, mask=img.getchannel("A"))
        return background
    return img.convert("RGB")


def _darkest(pixel: object) -> float:
    if isinstance(pixel, tuple):
        return float(min(pixel))
    return float(pixel) if isinstance(pixel, int | float) else 0.0


def is_cutout(img: Image.Image, threshold: int = 240, share: float = 0.9) -> bool:
    """True when the outer frame of the image is (almost) all white: a studio shot."""
    rgb = to_rgb(img)
    small = rgb.resize((200, max(1, int(200 * rgb.height / rgb.width))))
    w, h = small.size
    border = [(x, y) for x in range(w) for y in (0, 1, h - 2, h - 1)]
    border += [(x, y) for y in range(h) for x in (0, 1, w - 2, w - 1)]
    white = sum(1 for p in border if _darkest(small.getpixel(p)) >= threshold)
    return white / len(border) >= share


def _white_bbox(img: Image.Image, threshold: int = 235) -> Box:
    diff = ImageChops.difference(img, Image.new("RGB", img.size, WHITE)).convert("L")
    bbox = diff.point(lambda p: 255 if p > 255 - threshold else 0).getbbox()
    return bbox or (0, 0, img.width, img.height)


def _down(value: int) -> int:
    return value - value % BLOCK


def _centre_square(width: int, height: int) -> Box:
    side = min(width, height)
    left, top = _down((width - side) // 2), _down((height - side) // 2)
    return (left, top, left + side, top + side)


def _qtables(img: Image.Image) -> dict[int, list[int]] | None:
    tables = getattr(img, "quantization", None)
    return {k: list(v) for k, v in tables.items()} if tables else None


def process_product_image(img: Image.Image, spec: ImageSpec = DEFAULT_SPEC) -> Processed:
    result = _process_product_image(img, spec)
    if result.scale == 1.0:  # tables only make sense when pixels are not resampled
        result.qtables = _qtables(img)
    return result


def _process_product_image(img: Image.Image, spec: ImageSpec) -> Processed:
    icc = img.info.get("icc_profile")
    rgb = to_rgb(img)
    if not is_cutout(rgb):
        box = _centre_square(*rgb.size)
        square = rgb.crop(box)
        if spec.size and spec.size != square.width:
            scale = spec.size / square.width
            return Processed(
                square.resize((spec.size, spec.size), Image.Resampling.LANCZOS),
                icc_profile=icc,
                source_box=box,
                scale=scale,
            )
        return Processed(square, icc_profile=icc, source_box=box)

    x0, y0, x1, y1 = _white_bbox(rgb)
    box = (_down(x0), _down(y0), x1, y1)  # widen to the block grid; the extra is white
    product = rgb.crop(box)
    longest = max(product.size)
    if spec.size:
        scale = spec.size * (1 - 2 * spec.margin) / longest
        side = spec.size
        product = product.resize(
            (max(1, round(product.width * scale)), max(1, round(product.height * scale))),
            Image.Resampling.LANCZOS,
        )
    else:
        scale = 1.0
        side = math.ceil(longest / (1 - 2 * spec.margin))
    if scale == 1.0:
        side += -side % BLOCK
        offset = (_down((side - product.width) // 2), _down((side - product.height) // 2))
    else:
        offset = ((side - product.width) // 2, (side - product.height) // 2)
    canvas = Image.new("RGB", (side, side), WHITE)
    canvas.paste(product, offset)
    return Processed(canvas, icc_profile=icc, source_box=box, offset=offset, scale=scale)


def process_swatch(img: Image.Image, spec: ImageSpec = DEFAULT_SPEC) -> Processed:
    icc = img.info.get("icc_profile")
    rgb = to_rgb(img)
    box = _centre_square(*rgb.size)
    square = rgb.crop(box)
    if spec.swatch_size and spec.swatch_size != square.width:
        return Processed(
            square.resize((spec.swatch_size,) * 2, Image.Resampling.LANCZOS),
            icc,
            None,
            box,
            scale=spec.swatch_size / square.width,
        )
    return Processed(square, icc, _qtables(img), box)


def fidelity_db(source: Image.Image, result: Processed, encoded: bytes) -> float:
    """PSNR (dB) of the encoded output against the source pixels it came from.

    Only meaningful at native resolution (scale 1.0); 40 dB and above is visually lossless.
    """
    if result.scale != 1.0:
        return float("nan")
    decoded = to_rgb(Image.open(BytesIO(encoded)))
    x0, y0, x1, y1 = result.source_box
    ox, oy = result.offset
    original = np.asarray(to_rgb(source).crop(result.source_box), dtype=np.float64)
    output = np.asarray(decoded.crop((ox, oy, ox + x1 - x0, oy + y1 - y0)), dtype=np.float64)
    mse = float(np.mean((original - output) ** 2))
    return float("inf") if mse == 0 else 10 * math.log10(255**2 / mse)


def order_and_dedupe(
    images: list[tuple[str, Image.Image]], spec: ImageSpec = DEFAULT_SPEC
) -> tuple[list[tuple[str, Image.Image]], list[tuple[str, str]]]:
    """Drop sources that are too small or duplicate another; keep the larger of two duplicates;
    put cut-outs first."""
    kept: list[tuple[str, Image.Image, imagehash.ImageHash]] = []
    dropped: list[tuple[str, str]] = []
    for key, img in images:
        if min(img.size) < spec.min_source_side:
            dropped.append((key, f"too small ({img.width}x{img.height})"))
            continue
        fingerprint = imagehash.phash(to_rgb(img))
        index = next((i for i, k in enumerate(kept) if k[2] - fingerprint <= spec.duplicate_distance), None)
        if index is None:
            kept.append((key, img, fingerprint))
            continue
        other_key, other_img, _ = kept[index]
        if img.width * img.height > other_img.width * other_img.height:
            kept[index] = (key, img, fingerprint)
            dropped.append((other_key, f"duplicate of {key}, which is larger"))
        else:
            dropped.append((key, f"duplicate of {other_key}"))
    cutouts = [(k, i) for k, i, _ in kept if is_cutout(i)]
    others = [(k, i) for k, i, _ in kept if not is_cutout(i)]
    return cutouts + others, dropped
