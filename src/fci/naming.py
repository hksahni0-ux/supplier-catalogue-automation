"""FCI naming conventions: the columns the master sheet derives from name, category and brand."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SITE_IMAGE_ROOT = "/site-assets/product-images"
SWATCH_ROOT = "/product-images"

_PRICE_RE = re.compile(r"^\d{1,3}(?:\.\d{3})+$|^\d+$")


def slugify(text: str) -> str:
    """Lowercase ASCII, words joined by hyphens: no capitals or special characters (per FCI)."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    ascii_text = ascii_text.replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def parse_supplier_price(raw: str) -> int | None:
    """European price notation: '4.121' is 4121, never 4.121. Returns whole units or None."""
    token = raw.strip()
    if not _PRICE_RE.match(token):
        return None
    return int(token.replace(".", ""))


def size_label(code: str, width: float, depth: float, height: float) -> str:
    return f"{code} - W.{width} X D.{depth} X H.{height} cm"


@dataclass(frozen=True)
class Naming:
    model: str
    product_type: str
    brand: str
    brand_slug: str
    url_brand: str | None = None

    @property
    def name(self) -> str:
        return f"{self.model} {self.product_type}"

    @property
    def _by_brand(self) -> str:
        return self.url_brand or self.brand

    @property
    def slug(self) -> str:
        return f"{slugify(self.name)}-by-{slugify(self._by_brand)}"

    @property
    def url(self) -> str:
        return f"/{self.slug}.html"

    @property
    def title(self) -> str:
        return f"{self.name} by {self._by_brand}"

    @property
    def keywords(self) -> str:
        return f"{self.model}, {self.product_type}, {self.brand}"

    def image_file(self, n: int) -> str:
        return f"{self.slug}-{n}.jpg"

    def image_csv_name(self, n: int) -> str:
        return f"/{self.brand_slug}/{self.image_file(n)}"

    @property
    def main_image_url(self) -> str:
        return f"{SITE_IMAGE_ROOT}/{self.brand_slug}/{self.image_file(1)}"

    @property
    def image_title(self) -> str:
        return f"{self.title}| By FCI London"

    @property
    def image_alt(self) -> str:
        return f"{self.name} By FCI London"

    def swatch_path(self, folder: str, option_name: str) -> str:
        folder_part = f"{folder}/" if folder else ""
        return f"{SWATCH_ROOT}/{self.brand_slug}/swatches/{folder_part}{slugify(option_name)}.jpg"
