"""Read-only view of the run outputs (output/<sku>/), which is all the assistant may quote."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from fci.brands import load_brand


def words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]


@dataclass
class Product:
    sku: str
    out_dir: Path
    report: dict[str, Any]
    currency: str

    @property
    def name(self) -> str:
        return str(self.report.get("product", self.sku))

    def _csv(self, kind: str) -> list[dict[str, str]]:
        path = self.out_dir / "csv" / f"{self.sku}-{kind}.csv"
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    @cached_property
    def prices(self) -> list[dict[str, str]]:
        return self._csv("prices")

    @cached_property
    def attributes(self) -> list[dict[str, str]]:
        return self._csv("attributes")


class Catalogue:
    def __init__(self, out_root: Path, config: Path) -> None:
        self.out_root, self.config = out_root, config

    def products(self) -> list[Product]:
        found = []
        for report_path in sorted(self.out_root.glob("*/report.json")):
            report = json.loads(report_path.read_text())
            brand = (report.get("manual_inputs") or {}).get("brand", "")
            brand_file = self.config / "brands" / f"{brand}.yaml"
            currency = load_brand(brand_file).currency if brand_file.exists() else ""
            found.append(
                Product(report.get("sku", report_path.parent.name), report_path.parent, report, currency)
            )
        return found

    def find(self, query: str) -> Product | None:
        """A product by SKU, or by words of its name ('richard', 'burt sofa')."""
        wanted = words(query)
        products = self.products()
        for product in products:
            if product.sku == query.strip().lower():
                return product
        matches = [p for p in products if wanted and set(wanted) <= set(words(p.name) + words(p.sku))]
        return matches[0] if len(matches) == 1 else None
