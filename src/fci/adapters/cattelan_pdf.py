"""Cattelan Italia price list (PDF) parser.

Works from word coordinates rather than PDF table detection, which drops columns on
some pages. Each price table has a row of "EUR" labels; their right edges are the
price columns. Header cells sit above that row next to a left-hand label ("Cover",
"Slats", "Feet"...), and size rows sit below it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

from fci.naming import parse_supplier_price

TITLE_MIN_SIZE = 16.0
COLUMN_TOLERANCE = 3.0
LINE_TOLERANCE = 2.5
NUM = r"\d+(?:,\d+)?"
DIMS_RE = re.compile(rf"^([Øø])?({NUM})(?:x({NUM}))?(?:x({NUM}))?h$")
SIZE_CODE_RE = re.compile(r"^[A-Z]{1,2}\d?$")
DESIGNER_RE = re.compile(r"^(.+?)\|(\d{4})$")


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


Number = int | float


def _num(text: str | None) -> Number | None:
    if text is None:
        return None
    value = float(text.replace(",", "."))
    return int(value) if value.is_integer() else value


def parse_dims(raw: str) -> tuple[Number, Number | None, Number | None]:
    """'245x234x102h' -> (245, 234, 102); 'ø140x73,5h' (diameter x height) -> (140, 140, 73.5)."""
    match = DIMS_RE.match(raw)
    if match is None:
        raise ValueError(f"not a size: {raw!r}")
    round_top, a, b, c = match.groups()
    first = _num(a)
    if first is None:
        raise ValueError(f"not a size: {raw!r}")
    if round_top:
        return first, first, _num(b)
    return first, _num(b), _num(c)


@dataclass
class SizeRow:
    code: str | None
    width: Number
    depth: Number | None
    height: Number | None
    raw: str
    prices: dict[str, int] = field(default_factory=dict)


@dataclass
class PriceTable:
    columns: list[str]
    qualifiers: dict[str, str]
    rows: list[SizeRow]


@dataclass
class ProductEntry:
    title: str
    page_number: int  # 1-based, within the document
    designer: str | None
    year: int | None
    description: str
    tables: list[PriceTable]
    drawing_box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # page area above the text


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def _lines(words: list[Word]) -> list[list[Word]]:
    """Group words into visual lines, top to bottom, each sorted left to right."""
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.y0, w.x0)):
        if lines and abs(lines[-1][0].y0 - w.y0) <= LINE_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def _join(words: list[Word]) -> str:
    return _norm(" ".join(w.text for w in sorted(words, key=lambda w: (round(w.y0), w.x0))))


class CattelanPriceList:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._doc = pymupdf.open(self.path)
        self._titles = self._index_titles()

    def _index_titles(self) -> list[tuple[int, float, float, str]]:
        titles = []
        for page_index in range(len(self._doc)):
            page = self._doc[page_index]
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        text = _norm(span["text"])
                        if span["size"] >= TITLE_MIN_SIZE and text:
                            titles.append((page_index, span["bbox"][1], span["bbox"][3], text))
        return titles

    def titles(self) -> list[str]:
        return [t[3] for t in self._titles]

    def find(self, name: str) -> ProductEntry:
        wanted = _norm(name).upper()
        exact = [i for i, t in enumerate(self._titles) if t[3].upper() == wanted]
        prefixed = [i for i, t in enumerate(self._titles) if t[3].upper().startswith(wanted + " ")]
        matches = exact or prefixed
        if not matches:
            raise LookupError(f"'{name}' not found in {self.path.name}")
        return self._parse(matches[0])

    def _parse(self, title_index: int) -> ProductEntry:
        page_index, _top, title_bottom, title = self._titles[title_index]
        page = self._doc[page_index]
        following = [t for t in self._titles if t[0] == page_index and t[1] > title_bottom]
        bottom = min((t[1] for t in following), default=page.rect.height)
        words = [
            Word(x0, y0, x1, y1, _norm(text))
            for x0, y0, x1, y1, text, *_ in page.get_text("words")
            if y0 >= title_bottom - 1 and y1 <= bottom
        ]
        tables, first_header_top = self._tables(words)
        designer, year, description, prose_top, credit_bottom = self._prose(words, first_header_top)
        top = max(title_bottom, credit_bottom) + 2
        box = (0.0, top, page.rect.width, min(prose_top, first_header_top, bottom) - 4)
        return ProductEntry(title, page_index + 1, designer, year, description, tables, box)

    def drawing_image(self, entry: ProductEntry, dpi: int = 200) -> Image.Image | None:
        """Render the product's technical drawings, with photographs painted out.

        Cattelan prints the drawings as wide strips beside a squarish room photo; any raster
        image in the area with photo-like proportions is masked so only the drawings remain.
        """
        page = self._doc[entry.page_number - 1]
        x0, y0, x1, y1 = entry.drawing_box
        if y1 - y0 < 40:
            return None
        clip = pymupdf.Rect(x0, y0, x1, y1)
        pixmap = page.get_pixmap(dpi=dpi, clip=clip)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        scale = dpi / 72
        draw = ImageDraw.Draw(image)
        for info in page.get_image_info():
            bx0, by0, bx1, by1 = info["bbox"]
            width, height = bx1 - bx0, by1 - by0
            inside = by0 >= y0 - 2 and by1 <= y1 + 2
            if inside and height > 0 and 0.6 <= width / height <= 1.8 and width > 80:
                pad = 8  # the photo's frame and shadow lines sit just outside its box
                draw.rectangle(
                    (
                        (bx0 - pad - x0) * scale,
                        (by0 - pad - y0) * scale,
                        (bx1 + pad - x0) * scale,
                        (by1 + pad - y0) * scale,
                    ),
                    fill="white",
                )
        return image

    def _tables(self, words: list[Word]) -> tuple[list[PriceTable], float]:
        eur_rows = [line for line in _lines([w for w in words if w.text == "EUR"])]
        tables: list[PriceTable] = []
        header_tops: list[float] = []
        previous_bottom = min((w.y0 for w in words), default=0.0)
        for i, eur in enumerate(eur_rows):
            eur_y = eur[0].y0
            row_words = [w for w in words if abs(w.y0 - eur_y) <= LINE_TOLERANCE]
            left_of_prices = [w for w in row_words if w.text != "EUR" and w.x1 < eur[0].x0]
            first_col_left = max((w.x1 for w in left_of_prices), default=eur[0].x0 - 40)
            label_left = (
                min((w.x0 for w in left_of_prices if w.text in ("m³", "m3")), default=first_col_left - 45)
                - 15
            )
            col_edges = [w.x1 for w in eur]

            prose_ys = {round(w.y0) for w in words if w.x0 < label_left}
            labels = _lines(
                [
                    w
                    for w in words
                    if previous_bottom < w.y0 < eur_y - 1
                    and w.x0 >= label_left
                    and w.x1 <= first_col_left + 1
                    and not DIMS_RE.match(w.text)
                    # a description line starts at the page margin; a header label does not
                    and not any(abs(round(w.y0) - y) <= LINE_TOLERANCE for y in prose_ys)
                ]
            )
            if not labels:
                continue
            header_top = max(previous_bottom, labels[0][0].y0 - 12)
            header_tops.append(header_top)

            columns, qualifiers = self._header(words, labels, header_top, eur_y, first_col_left, col_edges)
            next_top = self._next_header_guess(words, eur_rows, i)
            rows = self._rows(words, eur_y, next_top, first_col_left, col_edges, columns)
            tables.append(PriceTable(columns, qualifiers, rows))
            previous_bottom = (
                max((r_y for r_y in self._row_ys(words, eur_y, next_top, first_col_left)), default=eur_y) + 3
            )
        return tables, (header_tops[0] if header_tops else float("inf"))

    @staticmethod
    def _next_header_guess(words: list[Word], eur_rows: list[list[Word]], i: int) -> float:
        if i + 1 >= len(eur_rows):
            return float("inf")
        # Rows of this table end before the next table's header block starts (~3 lines up).
        return eur_rows[i + 1][0].y0 - 40

    @staticmethod
    def _header(
        words: list[Word],
        labels: list[list[Word]],
        top: float,
        eur_y: float,
        first_col_left: float,
        col_edges: list[float],
    ) -> tuple[list[str], dict[str, str]]:
        label_ys = [line[0].y0 for line in labels]
        columns: list[str] = []
        qualifiers: dict[str, str] = {}
        for n, line in enumerate(labels):
            band_top = top if n == 0 else (label_ys[n - 1] + label_ys[n]) / 2
            band_bottom = eur_y - 1 if n == len(labels) - 1 else (label_ys[n] + label_ys[n + 1]) / 2
            cells = [w for w in words if band_top <= w.y0 < band_bottom and w.x0 >= first_col_left - 2]
            label = _join(line)
            if n == len(labels) - 1:  # the label nearest the EUR row names the price columns
                lefts = [first_col_left - 2, *col_edges[:-1]]
                for left, right in zip(lefts, col_edges, strict=True):
                    columns.append(_join([w for w in cells if left < w.xc <= right + 2]))
            else:
                qualifiers[label] = _join(cells)
        return columns, qualifiers

    @staticmethod
    def _row_ys(words: list[Word], eur_y: float, next_top: float, first_col_left: float) -> list[float]:
        return [
            w.y0
            for w in words
            if eur_y + 1 < w.y0 < next_top and w.x1 < first_col_left and DIMS_RE.match(w.text)
        ]

    def _rows(
        self,
        words: list[Word],
        eur_y: float,
        next_top: float,
        first_col_left: float,
        col_edges: list[float],
        columns: list[str],
    ) -> list[SizeRow]:
        rows: list[SizeRow] = []
        for y in self._row_ys(words, eur_y, next_top, first_col_left):
            line = sorted((w for w in words if abs(w.y0 - y) <= LINE_TOLERANCE), key=lambda w: w.x0)
            dims_word = next(w for w in line if DIMS_RE.match(w.text) and w.x1 < first_col_left)
            width, depth, height = parse_dims(dims_word.text)
            code_word = next(
                (w for w in line if w.x1 <= dims_word.x0 + 1 and SIZE_CODE_RE.match(w.text)), None
            )
            raw = _join([w for w in line if w.x1 <= dims_word.x1])
            row = SizeRow(code_word.text if code_word else None, width, depth, height, raw)
            for column, edge in zip(columns, col_edges, strict=True):
                price_word = next(
                    (
                        w
                        for w in line
                        if abs(w.x1 - edge) <= COLUMN_TOLERANCE and parse_supplier_price(w.text)
                    ),
                    None,
                )
                if price_word is not None:
                    price = parse_supplier_price(price_word.text)
                    if price is not None:
                        row.prices[column] = price
            rows.append(row)
        return rows

    @staticmethod
    def _prose(
        words: list[Word], first_header_top: float
    ) -> tuple[str | None, int | None, str, float, float]:
        above = [w for w in words if w.y0 < first_header_top]
        designer: str | None = None
        year: int | None = None
        sentences: list[str] = []
        prose_top = float("inf")
        credit_bottom = 0.0
        for line in _lines(above):
            text = _join(line)
            match = DESIGNER_RE.match(text)
            if match and designer is None and not sentences:
                designer, year = match.group(1).strip(), int(match.group(2))
                credit_bottom = max(w.y1 for w in line)
                continue
            alphabetic = [w for w in line if re.search(r"[a-z]{2,}", w.text)]
            if len(alphabetic) >= 4 or (sentences and alphabetic):
                prose_top = min(prose_top, line[0].y0)
                sentences.append(text)
        return designer, year, _norm(" ".join(sentences)), prose_top, credit_bottom
