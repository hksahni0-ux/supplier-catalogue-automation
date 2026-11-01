"""End to end for one job: supplier data -> copy -> images -> swatches -> CSVs -> report."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from fci.brands import load_brand
from fci.content import ProductFacts, write_copy
from fci.exporters import write_csvs
from fci.http import Http
from fci.images import DEFAULT_SPEC, fidelity_db, order_and_dedupe, process_product_image, process_swatch
from fci.jobs import Job, load_job
from fci.model import Flag, Option
from fci.naming import SWATCH_ROOT, Naming
from fci.record import ProductRecord
from fci.report import write_report
from fci.suppliers import SUPPLIERS, Context, SupplierData
from fci.swatch_reuse import index_existing, match_swatch

SKU_RE = re.compile(r"^[a-z0-9-]+-\d{3,}$")


@dataclass
class RunResult:
    record: ProductRecord
    out_dir: Path
    csvs: dict[str, Path]
    images: list[dict[str, str]] = field(default_factory=list)
    swatches: dict[str, int] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)


def _open(data: bytes) -> Image.Image | None:
    try:
        image = Image.open(BytesIO(data))
        image.load()
        return image
    except (UnidentifiedImageError, OSError):
        return None


def _product_images(
    data: SupplierData, naming: Naming, http: Http, out: Path, flags: list[Flag]
) -> list[dict[str, str]]:
    sources: list[tuple[str, Image.Image]] = []
    raw: dict[str, bytes] = {}
    for url in data.page.images:
        try:
            content = http.get(url)
        except ConnectionError as error:
            flags.append(Flag("warning", "images", f"download failed: {error}", url))
            continue
        image = _open(content)
        if image is None:
            flags.append(Flag("warning", "images", "not a readable image", url))
            continue
        sources.append((url, image))
        raw[url] = content
    kept, dropped = order_and_dedupe(sources)
    manifest = [{"source": url, "status": f"skipped: {reason}"} for url, reason in dropped]
    final: list[tuple[str, Image.Image]] = list(kept)
    if data.technical_image is not None:
        final.append(("technical drawing (price list / technical sheet)", data.technical_image))
    folder = out / "images" / naming.brand_slug
    originals = out / "originals" / naming.brand_slug
    folder.mkdir(parents=True, exist_ok=True)
    for n, (source, image) in enumerate(final, start=1):
        processed = process_product_image(image)
        encoded = DEFAULT_SPEC.encode(processed)
        target = folder / naming.image_file(n)
        target.write_bytes(encoded)
        entry = {
            "source": source,
            "status": "kept",
            "file": f"{naming.brand_slug}/{target.name}",
            "size": f"{processed.image.width}x{processed.image.height}",
            "source_size": f"{image.width}x{image.height}",
            "bytes": str(len(encoded)),
        }
        if source in raw:  # keep the supplier's file untouched, for archive or re-processing
            originals.mkdir(parents=True, exist_ok=True)
            (originals / naming.image_file(n)).write_bytes(raw[source])
            fidelity = fidelity_db(image, processed, encoded)
            entry["fidelity_db"] = f"{fidelity:.1f}"
            if fidelity < DEFAULT_SPEC.min_fidelity_db:
                flags.append(
                    Flag(
                        "warning",
                        "images",
                        f"{target.name} is {fidelity:.1f} dB from the source; "
                        "below the visually lossless threshold",
                        source,
                    )
                )
        manifest.append(entry)
    if not final:
        flags.append(Flag("error", "images", "no usable product images found", data.page.name))
    return manifest


def _cattelan_style_swatches(options: list[Option], http: Http, out: Path, flags: list[Flag]) -> int:
    """Download supplier swatch images and save them at the path the attributes CSV points to."""

    def work(option: Option) -> bool:
        if option.swatch is None:
            return False
        target = out / "swatches" / option.image.removeprefix(SWATCH_ROOT + "/")
        if target.exists():
            return True
        image = _open(http.get(option.swatch.source_image))
        if image is None:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(DEFAULT_SPEC.encode(process_swatch(image)))
        return True

    todo = [o for o in options if o.swatch and o.swatch.source_image and o.image]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda o: _safe(work, o), todo))
    failed = [o.name for o, ok in zip(todo, results, strict=True) if not ok]
    if failed:
        flags.append(
            Flag(
                "warning",
                "swatches",
                f"{len(failed)} swatch images could not be fetched: {', '.join(failed[:8])}",
                "supplier finishes catalogue",
            )
        )
    return len(todo) - len(failed)


def _safe(fn: Any, option: Option) -> bool:
    try:
        return bool(fn(option))
    except (ConnectionError, OSError):
        return False


EXISTING_SWATCH_RE = re.compile(r'src="/site-assets(/product-images/[^"]+/swatches/[^"]+\.jpg)"')


def _reuse_fci_swatches(options: list[Option], fci_url: str | None, http: Http, flags: list[Flag]) -> int:
    """Suppliers without swatch images: point at swatches already on FCI's server, matched by code."""
    if not fci_url:
        flags.append(
            Flag("warning", "swatches", "supplier has no swatch images and no FCI page to reuse from", "")
        )
        return 0
    html = http.get(fci_url).decode("utf-8", "ignore")
    existing = index_existing(EXISTING_SWATCH_RE.findall(html))
    matched = 0
    missing: list[str] = []
    changed: list[str] = []
    for option in options:
        if option.swatch is None and not option.image:
            continue
        hit, note = match_swatch(option.name, existing)
        if hit:
            option.image = hit
            matched += 1
        elif note:
            changed.append(f"{option.name} ({note})")
        else:
            missing.append(option.name)
    if changed:
        flags.append(
            Flag(
                "warning",
                "swatches",
                f"{len(changed)} FCI swatch images were not reused because they name a different colour "
                f"than the current card; a new image is needed: {'; '.join(changed)}",
                fci_url,
            )
        )
    if missing:
        flags.append(
            Flag(
                "warning",
                "swatches",
                f"{len(missing)} options have no swatch image on FCI's server or from the supplier; "
                f"image left as planned path: {', '.join(missing[:10])}"
                + (" ..." if len(missing) > 10 else ""),
                fci_url,
            )
        )
    return matched


def _validate(record: ProductRecord, job: Job) -> None:
    flags = record.flags
    if not SKU_RE.match(record.sku):
        flags.append(Flag("error", "code", f"SKU '{record.sku}' does not follow '<brand>-<number>'", "job"))
    if not record.options.combinations:
        flags.append(Flag("error", "price", "no price combinations were produced", "price list"))
    elif record.base_price <= 0:
        flags.append(Flag("error", "price", "base price is zero", "price list"))
    if not job.category_confirmed:
        flags.append(
            Flag(
                "warning",
                "catcode",
                f"category code '{job.category_code}' is inferred from FCI's "
                "naming pattern; confirm it exists in Frame",
                "job",
            )
        )
    names = [o.name for a in record.options.attributes for o in a.options if a.changes_price]
    if len(names) != len(set(names)):
        flags.append(
            Flag("error", "attributes", "duplicate option names would make combinations ambiguous", "")
        )


def run_job(
    job_path: Path | Job,
    *,
    inputs: Path,
    config: Path,
    templates: Path,
    out_root: Path,
    http: Http,
    client: Any = None,
    images: bool = True,
) -> RunResult:
    job = job_path if isinstance(job_path, Job) else load_job(job_path)
    brand = load_brand(config / "brands" / f"{job.brand}.yaml")
    supplier = SUPPLIERS[brand.raw["supplier"]]
    data = supplier(job, brand, Context(inputs, http))
    naming = Naming(job.model, job.product_type, brand.name, brand.slug, brand.url_brand)
    flags: list[Flag] = list(data.flags) + list(data.options.flags)

    copy = write_copy(
        ProductFacts(
            naming.name, brand.name, job.product_type, data.supplier_texts, data.specs, data.designer
        ),
        client,
    )
    flags += copy.flags

    out = out_root / job.sku
    manifest: list[dict[str, str]] = []
    swatch_counts: dict[str, int] = {}
    if images:
        manifest = _product_images(data, naming, http, out, flags)
        swatch_options = [o for a in data.options.attributes if a.display == 2 for o in a.options]
        if any(o.swatch and o.swatch.source_image for o in swatch_options):
            swatch_counts["downloaded"] = _cattelan_style_swatches(swatch_options, http, out, flags)
        else:
            fci_url = job.options.get("fci_url")
            swatch_counts["reused from FCI"] = _reuse_fci_swatches(swatch_options, fci_url, http, flags)
            if fci_url:
                data.sources.append(fci_url)
    image_count = (
        sum(1 for m in manifest if m["status"] == "kept")
        if images
        else int(job.options.get("image_count", 1))
    )

    record = ProductRecord(
        naming=naming,
        sku=job.sku,
        category_code=job.category_code,
        options=data.options,
        meta_description=copy.meta_description,
        long_description=copy.long_description,
        image_count=image_count,
        flags=flags,
    )
    _validate(record, job)
    csvs = write_csvs(record, out / "csv", templates)
    result = RunResult(record, out, csvs, manifest, swatch_counts, data.sources)
    write_report(result, job, copy.source)
    return result
