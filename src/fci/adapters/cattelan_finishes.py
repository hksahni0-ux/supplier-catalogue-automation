"""Cattelan Italia upholstery swatches, from the public finishes catalogue on cattelanitalia.com.

The catalogue answers a POST with JSON grouped by material. `fetch(category_id)` is
injected so tests run from saved responses and live runs go through the HTTP cache.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fci.model import Swatch

Fetch = Callable[[int], dict[str, Any]]


class CattelanFinishes:
    def __init__(self, groups: dict[str, dict[str, Any]], fetch: Fetch) -> None:
        self._groups = groups
        self._fetch = fetch
        self._catalogue: dict[int, dict[str, Any]] = {}

    def _entries(self, category: int) -> list[dict[str, Any]]:
        if category not in self._catalogue:
            self._catalogue[category] = self._fetch(category)
        products = self._catalogue[category].get("productsList", {})
        return [entry for entries in products.values() for entry in entries]

    def find(self, category: int, code: str, label: str, folder: str) -> Swatch | None:
        """The catalogue entry whose name starts with a finish code such as 'GFM18'."""
        for entry in self._entries(category):
            name = " ".join(entry["sNomeColore"].split())
            if name.upper().split()[0] == code.upper():
                rest = name.split(" ", 1)[1] if " " in name else ""
                thumbs = entry.get("Thumbs") or [{}]
                image = thumbs[0].get("imgHDGalleryProdotto") or thumbs[0].get("imgProdotto") or ""
                return Swatch(f"{code.upper()} {rest.title()}".strip(), code.upper(), label, folder, image)
        return None

    def group(self, key: str) -> list[Swatch]:
        if key not in self._groups:
            raise KeyError(f"swatch group '{key}' is not configured")
        spec = self._groups[key]
        swatches = []
        for entry in self._entries(int(spec["category"])):
            if int(entry.get("sIdMateriale") or 0) != int(spec["material_id"]):
                continue
            if "style" in spec and (entry.get("sNomeMaterialeStile") or "").lower() != spec["style"]:
                continue
            name = " ".join(entry["sNomeColore"].split())
            if "code_prefix" in spec and not name.startswith(spec["code_prefix"]):
                continue
            thumbs = entry.get("Thumbs") or [{}]
            image = thumbs[0].get("imgHDGalleryProdotto") or thumbs[0].get("imgProdotto") or ""
            swatches.append(Swatch(name, key, spec["label"], spec["folder"], image))
        return sorted(swatches, key=lambda s: s.name)
