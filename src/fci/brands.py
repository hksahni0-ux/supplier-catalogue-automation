"""Brand configuration: everything supplier-specific that is data, not code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PriceColumn:
    pattern: re.Pattern[str]
    groups: tuple[str, ...]


@dataclass
class Brand:
    name: str
    slug: str
    currency: str
    url_brand: str | None
    price_list: dict[str, Any]
    website: dict[str, Any]
    swatches: dict[str, Any]
    swatch_groups: dict[str, dict[str, Any]]
    price_columns: list[PriceColumn]
    size_variant_qualifiers: list[str] = field(default_factory=list)
    qualifier_attributes: dict[str, dict[str, Any]] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def drive_folder(self) -> str:
        """Its subfolder of Price lists in Drive: `drive_folder:` if set, else the brand name."""
        return str(self.raw.get("drive_folder") or self.name)

    def groups_for_column(self, header: str) -> tuple[str, ...] | None:
        normalised = re.sub(r"\s+", " ", header).strip().lower()
        for column in self.price_columns:
            if column.pattern.search(normalised):
                return column.groups
        return None


def load_brand(path: Path | str) -> Brand:
    data = yaml.safe_load(Path(path).read_text())
    swatches = data.get("swatches", {})
    return Brand(
        name=data["brand"],
        slug=data["brand_slug"],
        currency=data.get("currency", "GBP"),
        url_brand=data.get("url_brand"),
        price_list=data.get("price_list", {}),
        website=data.get("website", {}),
        swatches=swatches,
        swatch_groups=swatches.get("groups", {}),
        price_columns=[
            PriceColumn(re.compile(c["header"], re.IGNORECASE), tuple(c["groups"]))
            for c in data.get("price_columns", [])
        ],
        size_variant_qualifiers=data.get("size_variant_qualifiers", []),
        qualifier_attributes=data.get("qualifier_attributes", {}),
        raw=data,
    )
