"""Supplier-neutral product model shared by every adapter and exporter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Flag:
    severity: Severity
    field: str
    message: str
    source: str = ""


@dataclass(frozen=True)
class Swatch:
    name: str  # as the supplier names it, e.g. "ECP01 BIANCO"
    group: str  # config key, e.g. "synthetic-leather"
    label: str  # attributes CSV "grouping", e.g. "Synthetic Leather"
    folder: str  # FCI swatch folder
    source_image: str  # supplier image URL (or "" when the supplier has none)


@dataclass
class Option:
    name: str
    image: str = ""  # FCI server path for swatch display
    grouping: str = ""
    swatch: Swatch | None = None


@dataclass
class Attribute:
    name: str
    display: int  # 1 = dropdown, 2 = swatch
    changes_price: bool
    options: list[Option] = field(default_factory=list)

    def add(self, option: Option) -> None:
        if all(o.name != option.name for o in self.options):
            self.options.append(option)


@dataclass
class ProductOptions:
    attributes: list[Attribute]
    combinations: dict[tuple[str, ...], int]  # option names, in price-attribute order -> price
    flags: list[Flag] = field(default_factory=list)

    def attribute(self, name: str) -> Attribute:
        return next(a for a in self.attributes if a.name == name)

    def price_map(self) -> dict[tuple[str, ...], int]:
        return self.combinations

    @property
    def base_price(self) -> int:
        return min(self.combinations.values())
