"""One product, ready for export: naming, options, prices, copy and image count."""

from __future__ import annotations

from dataclasses import dataclass, field

from fci.model import Flag, ProductOptions
from fci.naming import Naming

# Values the Thomas sample uses for every product (template defaults in the master sheet).
DEFAULTS = {"onsale": 0, "sellable": 1, "published": 1, "nositemap": 1, "priority": 200}


@dataclass
class ProductRecord:
    naming: Naming
    sku: str
    category_code: str
    options: ProductOptions
    meta_description: str
    long_description: str
    image_count: int
    details: dict[str, str] = field(default_factory=dict)
    flags: list[Flag] = field(default_factory=list)
    defaults: dict[str, int] = field(default_factory=lambda: dict(DEFAULTS))

    @property
    def base_price(self) -> int:
        return self.options.base_price
