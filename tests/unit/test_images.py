"""Image processing: square, web-ready images with the supplier's full quality kept.

No resampling by default: every output pixel is a source pixel, so zooming shows the same
detail as the supplier's original. Fidelity is measured (PSNR) against the source.
"""

from io import BytesIO

from PIL import Image, ImageCms, ImageDraw

from fci.images import (
    ImageSpec,
    fidelity_db,
    is_cutout,
    order_and_dedupe,
    process_product_image,
    process_swatch,
)

SPEC = ImageSpec()


def cutout(width: int = 1600, height: int = 1000) -> Image.Image:
    """A dark 'sofa' on a white studio background."""
    img = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(img).rectangle((300, 300, width - 300, height - 200), fill=(90, 80, 70))
    return img


def lifestyle(width: int = 1600, height: int = 980, shade: int = 60) -> Image.Image:
    img = Image.new("RGB", (width, height), (shade, shade + 20, shade + 40))
    ImageDraw.Draw(img).rectangle((100, 500, 1500, 900), fill=(200, 150, 100))
    return img


def photo_like(width: int = 1800, height: int = 1200) -> Image.Image:
    """Smooth gradients plus fine detail, roughly like a product photo."""
    base = Image.linear_gradient("L").resize((width, height)).convert("RGB")
    noise = Image.effect_noise((width, height), 12).convert("RGB")
    return Image.blend(base, noise, 0.15)


def with_srgb_profile(img: Image.Image) -> Image.Image:
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    buffer = BytesIO()
    img.save(buffer, "JPEG", quality=95, icc_profile=profile)
    return Image.open(BytesIO(buffer.getvalue()))


def test_detects_cutout_vs_lifestyle() -> None:
    assert is_cutout(cutout())
    assert not is_cutout(lifestyle())


def test_lifestyle_is_cropped_square_at_native_resolution() -> None:
    result = process_product_image(lifestyle())
    assert result.image.size == (980, 980)  # shorter side kept, nothing scaled
    assert result.scale == 1.0
    assert result.image.getpixel((2, 2)) != (255, 255, 255)


def test_cutout_is_trimmed_and_padded_without_scaling_the_product() -> None:
    result = process_product_image(cutout())
    out = result.image
    assert out.size[0] == out.size[1]
    assert out.getpixel((3, 3)) == (255, 255, 255)
    bbox = Image.eval(out.convert("L"), lambda p: 255 if p < 200 else 0).getbbox()
    assert bbox is not None
    assert bbox[2] - bbox[0] == 1000 + 1  # product keeps its source width: x 300..1300 inclusive
    assert result.scale == 1.0


def test_fixed_size_is_still_available() -> None:
    result = process_product_image(lifestyle(), ImageSpec(size=1000))
    assert result.image.size == (1000, 1000)


def test_converts_transparent_png_onto_white() -> None:
    rgba = Image.new("RGBA", (1200, 1200), (0, 0, 0, 0))
    ImageDraw.Draw(rgba).ellipse((200, 200, 1000, 1000), fill=(20, 20, 20, 255))
    result = process_product_image(rgba)
    assert result.image.mode == "RGB"
    assert result.image.getpixel((3, 3)) == (255, 255, 255)


def test_encoding_keeps_full_colour_detail_and_the_colour_profile() -> None:
    source = with_srgb_profile(photo_like())
    result = process_product_image(source)
    encoded = Image.open(BytesIO(SPEC.encode(result)))
    assert encoded.info.get("icc_profile") == source.info["icc_profile"]
    assert [layer[1:3] for layer in encoded.layer] == [(1, 1), (1, 1), (1, 1)]  # 4:4:4, no chroma loss


def test_output_is_visually_lossless_against_the_source() -> None:
    source = photo_like()
    result = process_product_image(source)
    assert fidelity_db(source, result, SPEC.encode(result)) >= 40


def test_dedupe_drops_resized_copies_and_puts_cutouts_first() -> None:
    a = lifestyle()
    a_small = a.resize((900, 551))
    b = cutout()
    c = lifestyle(shade=150)
    kept, dropped = order_and_dedupe([("a", a), ("b", b), ("a-small", a_small), ("c", c)])
    assert [k for k, _ in kept] == ["b", "a", "c"]
    assert dropped == [("a-small", "duplicate of a")]


def test_duplicate_keeps_the_higher_resolution_copy() -> None:
    big = lifestyle()
    small = big.resize((900, 551))
    kept, dropped = order_and_dedupe([("small", small), ("big", big)])
    assert [(k, i.size) for k, i in kept] == [("big", (1600, 980))]
    assert dropped == [("small", "duplicate of big, which is larger")]


def test_rejects_images_too_small_for_web() -> None:
    kept, dropped = order_and_dedupe([("tiny", lifestyle(300, 200)), ("ok", lifestyle())])
    assert [k for k, _ in kept] == ["ok"]
    assert dropped[0][0] == "tiny"
    assert "too small" in dropped[0][1]


def test_swatch_is_square_at_native_resolution() -> None:
    result = process_swatch(Image.new("RGB", (640, 480), (120, 30, 30)))
    assert result.image.size == (480, 480)


def jpeg_source(img: Image.Image, quality: int) -> Image.Image:
    buffer = BytesIO()
    img.save(buffer, "JPEG", quality=quality, subsampling=0)
    return Image.open(BytesIO(buffer.getvalue()))


def test_jpeg_sources_are_saved_with_their_own_quality_tables() -> None:
    source = jpeg_source(photo_like(), quality=80)
    result = process_product_image(source)
    encoded = Image.open(BytesIO(SPEC.encode(result)))
    assert encoded.quantization == source.quantization  # same quality as the supplier's file
    assert fidelity_db(source, result, SPEC.encode(result)) >= 40


def test_non_jpeg_sources_use_high_quality_default() -> None:
    result = process_product_image(photo_like())  # not a JPEG: no tables to reuse
    encoded = Image.open(BytesIO(SPEC.encode(result)))
    assert encoded.quantization != jpeg_source(photo_like(), quality=80).quantization


def test_crops_align_to_the_jpeg_block_grid_so_recompression_is_near_lossless() -> None:
    source = jpeg_source(photo_like(1803, 1201), quality=90)  # centred crop would start at x=301
    result = process_product_image(source)
    assert result.source_box[0] % 8 == 0 and result.source_box[1] % 8 == 0
    assert result.offset[0] % 8 == 0 and result.offset[1] % 8 == 0
    assert fidelity_db(source, result, SPEC.encode(result)) >= 45


def test_aligned_cutout_padding_keeps_blocks_aligned() -> None:
    img = Image.new("RGB", (1603, 1003), "white")
    ImageDraw.Draw(img).rectangle((301, 299, 1297, 801), fill=(90, 80, 70))
    result = process_product_image(jpeg_source(img, quality=90))
    assert result.source_box[0] % 8 == 0 and result.source_box[1] % 8 == 0
    assert result.image.width % 8 == 0
    assert result.offset[0] % 8 == 0 and result.offset[1] % 8 == 0
