"""Write the six FCI import CSVs.

Column order comes from the template files, so FCI's structure is never changed here.
A template column the exporter has no value for is written blank and flagged.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from fci.model import Flag
from fci.record import ProductRecord

CSV_FILES = {
    "product": "product-upload.csv",
    "categories": "categories.csv",
    "images": "images.csv",
    "attributes": "attributes.csv",
    "prices": "prices.csv",
    "details": "details.csv",
}
COMBO_SEPARATOR = " [+] "


def _header(template: Path) -> list[str]:
    with template.open(newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle))


def _detail_keys(template: Path) -> list[str]:
    with template.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [row["name"] for row in rows]


def _product_rows(r: ProductRecord) -> Iterable[dict[str, Any]]:
    n = r.naming
    yield {
        "name": n.name,
        "code": r.sku,
        "brand": n.brand,
        "price": r.base_price,
        "url": n.url,
        "title": n.title,
        "keywords": n.keywords,
        "description": r.meta_description,
        "img": n.main_image_url,
        **r.defaults,
    }


def _category_rows(r: ProductRecord) -> Iterable[dict[str, Any]]:
    yield {"code": r.sku, "catcode": r.category_code}


def _image_rows(r: ProductRecord) -> Iterable[dict[str, Any]]:
    for i in range(1, r.image_count + 1):
        yield {
            "code": r.sku,
            "name": r.naming.image_csv_name(i),
            "title": r.naming.image_title,
            "alt": r.naming.image_alt,
        }


def _attribute_rows(r: ProductRecord) -> Iterable[dict[str, Any]]:
    for attribute in r.options.attributes:
        for option in attribute.options:
            yield {
                "code": r.sku,
                "attribute": attribute.name,
                "display": attribute.display,
                "changesprice": int(attribute.changes_price),
                "name": option.name,
                "image": option.image,
                "grouping": option.grouping,
                "specifications": "",
            }


def _price_rows(r: ProductRecord) -> Iterable[dict[str, Any]]:
    for combo, price in r.options.combinations.items():
        yield {"code": r.sku, "combo": COMBO_SEPARATOR.join(combo), "price": price}


ROWS = {
    "product": _product_rows,
    "categories": _category_rows,
    "images": _image_rows,
    "attributes": _attribute_rows,
    "prices": _price_rows,
}


def write_csvs(record: ProductRecord, out_dir: Path, templates: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for kind, filename in CSV_FILES.items():
        template = templates / filename
        header = _header(template)
        if kind == "details":
            data = {"SHORT-DESCRIPTION": record.long_description, **record.details}
            rows: list[dict[str, Any]] = [
                {"code": record.sku, "name": key, "data": data.get(key, "")} for key in _detail_keys(template)
            ]
        else:
            rows = list(ROWS[kind](record))
        known = set().union(*(row.keys() for row in rows)) if rows else set(header)
        for column in header:
            if column not in known:
                record.flags.append(
                    Flag("warning", kind, f"template column '{column}' has no source; left blank", filename)
                )
        path = out_dir / f"{record.sku}-{filename}"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in header})
        written[kind] = path
    return written
