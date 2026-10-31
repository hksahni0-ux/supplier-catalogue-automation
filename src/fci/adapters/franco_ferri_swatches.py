"""Franco Ferri swatch card (.xls or .xlsx): fabrics and leathers by price category,
feet finishes and contrast stitching. Text only: the card has no swatch images."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ARTICLE_RE = re.compile(r"^art\.\s*(.+)$", re.IGNORECASE)
CATEGORY_RE = re.compile(r"^cat\.?\s*(\d+)$", re.IGNORECASE)
COLOUR_RE = re.compile(r"^(\d+)\s+(.+?)\s*(?:\(only model\s+(\w+)\))?$", re.IGNORECASE)
SUMMARY_RE = re.compile(r"^([\d/]+)\s+colou?rs?$", re.IGNORECASE)
FOOTER_RE = re.compile(r"^(total\b|up ?dated\b)", re.IGNORECASE)

Colour = tuple[str, str]


@dataclass
class Article:
    name: str
    material: str  # "Fabric" or "Leather"
    category: str  # "Cat.70"
    colours: list[Colour] = field(default_factory=list)
    note: str = ""
    stated_count: int | None = None  # the card's own "16 Colours" total


def _clean(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _read_sheets(path: Path) -> dict[str, list[list[str]]]:
    if path.suffix.lower() == ".xls":
        import xlrd

        book = xlrd.open_workbook(path)
        return {s.name: [[_clean(v) for v in s.row_values(r)] for r in range(s.nrows)] for s in book.sheets()}
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    return {ws.title: [[_clean(v) for v in row] for row in ws.iter_rows(values_only=True)] for ws in workbook}


class FrancoFerriSwatchCard:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._sheets = _read_sheets(self.path)
        self.articles: list[Article] = []
        for sheet_name, material in (("Fabrics", "Fabric"), ("Leathers", "Leather")):
            self.articles += self._articles(self._sheet(sheet_name), material)

    def _sheet(self, name: str) -> list[list[str]]:
        for title, rows in self._sheets.items():
            if title.strip().lower() == name.lower():
                return rows
        raise KeyError(f"sheet '{name}' not in {self.path.name}")

    @staticmethod
    def _articles(rows: list[list[str]], material: str) -> list[Article]:
        header_index = next(i for i, r in enumerate(rows) if any(ARTICLE_RE.match(c) for c in r))
        articles: dict[int, Article] = {}
        for col, cell in enumerate(rows[header_index]):
            match = ARTICLE_RE.match(cell)
            if match:
                category = CATEGORY_RE.match(rows[header_index + 1][col].replace(" ", ""))
                cat = f"Cat.{category.group(1)}" if category else ""
                articles[col] = Article(match.group(1).strip().title(), material, cat)
        for row in rows[header_index + 2 :]:
            for col, article in articles.items():
                cell = row[col] if col < len(row) else ""
                if not cell or FOOTER_RE.match(cell):
                    continue
                summary = SUMMARY_RE.match(cell)
                if summary:
                    if summary.group(1).isdigit():
                        article.stated_count = int(summary.group(1))
                    continue
                colour = COLOUR_RE.match(cell)
                if colour:
                    article.colours.append((colour.group(1), colour.group(2).strip()))
                else:
                    article.note = f"{article.note} {cell}".strip()
        return list(articles.values())

    def article(self, name: str) -> Article:
        return next(a for a in self.articles if a.name.lower() == name.lower())

    def feet(self, kind: str, model: str = "") -> list[Colour]:
        rows = self._sheet("Feet finish")
        header_index = next(i for i, r in enumerate(rows) if any(kind.lower() in c.lower() for c in r))
        col = next(i for i, c in enumerate(rows[header_index]) if kind.lower() in c.lower())
        finishes: list[Colour] = []
        for row in rows[header_index + 1 :]:
            match = COLOUR_RE.match(row[col] if col < len(row) else "")
            if not match:
                continue
            only = match.group(3)
            if only and only.upper() != model.upper():
                continue
            finishes.append((match.group(1), match.group(2).strip()))
        return finishes

    def stitching(self) -> list[Colour]:
        rows = self._sheet("Contrast Stitching")
        return [
            (m.group(1), m.group(2).strip())
            for row in rows
            for cell in row
            if (m := COLOUR_RE.match(cell)) and not SUMMARY_RE.match(cell)
        ]
