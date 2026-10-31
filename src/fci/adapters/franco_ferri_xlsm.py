"""Franco Ferri (Naustro Fiera) price list: one sheet of model blocks, prices per fabric category.

Each block starts with a 'PREZZO : ...' banner and a header row (Modello, Codice, Versione,
Cat.xx..., L, H, P). The header is read per block, so a model with different categories
still parses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

CATEGORY_RE = re.compile(r"^Cat\.?\s*(\w+)$", re.IGNORECASE)
CURRENCY_RE = re.compile(r"Valuta\s*:\s*([A-Z]{3})")


@dataclass
class Module:
    code: str
    description: str
    prices: dict[str, int]
    width: float | None
    height: float | None
    depth: float | None


@dataclass
class ModelEntry:
    name: str
    currency: str
    categories: list[str]
    modules: dict[str, Module] = field(default_factory=dict)
    source_row: int = 0


def _key(name: str) -> str:
    return re.sub(r"[^A-Z0-9 ]", "", name.upper()).strip()


def _number(value: object) -> float | None:
    if isinstance(value, int | float):
        return int(value) if float(value).is_integer() else float(value)
    return None


class FrancoFerriPriceList:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        workbook = openpyxl.load_workbook(self.path, data_only=True, read_only=True)
        self._rows = [list(r) for r in workbook.worksheets[0].iter_rows(values_only=True)]
        self.models = self._parse()

    def _parse(self) -> list[ModelEntry]:
        models: list[ModelEntry] = []
        currency = "GBP"
        header: list[str] = []
        current: ModelEntry | None = None
        for index, row in enumerate(self._rows):
            first = row[0] if row else None
            if isinstance(first, str) and first.startswith("PREZZO"):
                match = CURRENCY_RE.search(first)
                currency = match.group(1) if match else currency
                current = None
                continue
            if first == "Modello":
                header = [str(c).strip() if c is not None else "" for c in row]
                continue
            if not header or len(row) < 3 or row[1] in (None, ""):
                continue
            if isinstance(first, str) and first.strip():
                categories = [h.replace(" ", "") for h in header if CATEGORY_RE.match(h)]
                current = ModelEntry(first.strip(), currency, categories, source_row=index + 1)
                models.append(current)
            if current is None:
                continue
            values = dict(zip(header, row, strict=False))
            prices = {
                h.replace(" ", ""): int(values[h])
                for h in header
                if CATEGORY_RE.match(h) and isinstance(values.get(h), int | float)
            }
            code = str(row[1]).strip()
            current.modules[code] = Module(
                code,
                str(row[2] or "").strip(),
                prices,
                _number(values.get("L")),
                _number(values.get("H")),
                _number(values.get("P")),
            )
        return models

    def find(self, name: str) -> ModelEntry:
        wanted = _key(name)
        exact = [m for m in self.models if _key(m.name) == wanted]
        prefixed = [m for m in self.models if _key(m.name).startswith(wanted + " ")]
        matches = exact or prefixed
        if not matches:
            raise LookupError(f"'{name}' not found in {self.path.name}")
        return matches[0]
