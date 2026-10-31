"""Shared types for supplier website adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SupplierPage:
    name: str
    description: str
    images: list[str]  # full-size originals, page order, no duplicates
    documents: dict[str, str] = field(default_factory=dict)
    collection: str = ""
    year: int | None = None


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def unique(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out
