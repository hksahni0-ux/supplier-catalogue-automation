"""Supplier modules. Each one turns a job into supplier-neutral data; a brand's YAML names
the module it uses (`supplier: cattelan`). A new supplier with the same document formats
needs only a YAML file; a new format needs one more `collect_*` function here."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image

from fci.adapters.cattelan_finishes import CattelanFinishes
from fci.adapters.cattelan_pdf import CattelanPriceList
from fci.adapters.cattelan_web import parse_cattelan_page
from fci.adapters.franco_ferri_swatches import FrancoFerriSwatchCard
from fci.adapters.franco_ferri_web import parse_franco_ferri_page
from fci.adapters.franco_ferri_xlsm import FrancoFerriPriceList
from fci.adapters.web_common import SupplierPage
from fci.brands import Brand
from fci.http import Http
from fci.jobs import Job
from fci.mapping import build_options
from fci.model import Flag, ProductOptions
from fci.modular import Layout, build_modular_options
from fci.naming import slugify


@dataclass
class Context:
    inputs: Path
    http: Http


@dataclass
class SupplierData:
    options: ProductOptions
    page: SupplierPage
    supplier_texts: list[str]
    specs: list[str]
    designer: str | None = None
    technical_image: Image.Image | None = None
    sources: list[str] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)


def _check_name(job: Job, page: SupplierPage) -> list[Flag]:
    if slugify(page.name).replace("-", "") not in slugify(job.supplier_name).replace("-", ""):
        return [
            Flag(
                "warning",
                "name",
                f"website calls it '{page.name}', price list '{job.supplier_name}'",
                job.supplier_url,
            )
        ]
    return []


def collect_cattelan(job: Job, brand: Brand, ctx: Context) -> SupplierData:
    price_file = ctx.inputs / brand.price_list["file"]
    price_list = CattelanPriceList(price_file)
    entry = price_list.find(job.supplier_name)
    endpoint = brand.swatches["endpoint"]
    finishes = CattelanFinishes(
        brand.swatch_groups, lambda c: ctx.http.post_json(endpoint, {"idCategory": c})
    )
    options = build_options(entry, brand, finishes.group, finishes.find)
    page = parse_cattelan_page(ctx.http.get(job.supplier_url).decode("utf-8"))
    sizes = [o.name for o in options.attribute("Size").options]
    return SupplierData(
        options=options,
        page=page,
        supplier_texts=[page.description, entry.description],
        specs=[
            f"Sizes: {'; '.join(sizes)}",
            "Covers: " + ", ".join(sorted({o.grouping for o in options.attribute("Cover").options})),
        ],
        designer=entry.designer,
        technical_image=price_list.drawing_image(entry, dpi=300),
        sources=[f"{price_file.name} p.{entry.page_number}", job.supplier_url, endpoint],
        flags=_check_name(job, page),
    )


def collect_franco_ferri(job: Job, brand: Brand, ctx: Context) -> SupplierData:
    price_file = ctx.inputs / brand.price_list["file"]
    card_file = ctx.inputs / brand.swatches["file"]
    entry = FrancoFerriPriceList(price_file).find(job.supplier_name)
    card = FrancoFerriSwatchCard(card_file)
    layouts = [
        Layout(item["name"], [str(m) for m in item["modules"]]) for item in job.options.get("layouts", [])
    ]
    options = build_modular_options(
        entry,
        card,
        layouts,
        brand_slug=brand.slug,
        model=job.supplier_name.split("'")[0].split()[0],
        mirror_pairs=[tuple(p) for p in job.options.get("mirror_pairs", [])],
        feet_codes=[str(c) for c in job.options.get("feet", [])],
        extra_dropdowns=job.options.get("dropdowns", {}),
    )
    page = parse_franco_ferri_page(ctx.http.get(job.supplier_url).decode("utf-8"))
    technical: Image.Image | None = None
    flags = _check_name(job, page)
    sheet_url = page.documents.get("technical_sheet")
    if sheet_url and not brand.website.get("technical_sheet_as_image", True):
        flags.append(
            Flag(
                "info",
                "images",
                "technical sheet not used as an image: it carries the supplier's "
                "branding (logo, model name, address)",
                sheet_url,
            )
        )
    elif sheet_url:
        document = pymupdf.open(stream=ctx.http.get(sheet_url), filetype="pdf")
        pixmap = document[0].get_pixmap(dpi=300)
        technical = Image.open(BytesIO(pixmap.tobytes("png")))
    else:
        flags.append(
            Flag("warning", "images", "no technical sheet linked on the supplier page", job.supplier_url)
        )
    return SupplierData(
        options=options,
        page=page,
        supplier_texts=[page.description],
        specs=[
            f"Layouts: {'; '.join(layout.name for layout in layouts)}",
            "Metal feet; fabric or leather cover",
        ],
        technical_image=technical,
        sources=[f"{price_file.name} (row {entry.source_row})", card_file.name, job.supplier_url]
        + ([sheet_url] if sheet_url else []),
        flags=flags,
    )


SUPPLIERS: dict[str, Callable[[Job, Brand, Context], SupplierData]] = {
    "cattelan": collect_cattelan,
    "franco_ferri": collect_franco_ferri,
}
