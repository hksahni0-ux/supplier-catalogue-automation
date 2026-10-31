"""Rebuild the small test fixtures from the full supplier files in supplier_inputs/.

uv run python tests/fixtures/build_fixtures.py
"""

from pathlib import Path

import openpyxl
import pymupdf
import xlrd

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "supplier_inputs"
HERE = Path(__file__).parent


def cattelan_pdf() -> None:
    src = pymupdf.open(INPUTS / "CATTELAN ITALIA p.list 05-26 EUR Vat excl.pdf")
    out = pymupdf.open()
    for page in (357, 360, 361):  # RICHARD, THOMAS, BISHOP + GRETA
        out.insert_pdf(src, from_page=page, to_page=page)
    for page in out:  # drop photos, keep text and lines
        page.add_redact_annot(page.rect)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_NONE,
        )
    out.save(HERE / "cattelan_beds.pdf", garbage=4, deflate=True)


def franco_ferri_price_list() -> None:
    """The BERTE' FF block, plus its neighbour BERTO so name matching is tested."""
    wb = openpyxl.load_workbook(
        INPUTS / "2026 - Franco Ferri GBP Price List IW - FCI Clipper Design - June 2026.xlsm",
        data_only=True,
        read_only=True,
    )
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    start = next(i for i, r in enumerate(rows) if r[0] == "BERTE' FF") - 2
    end = next(i for i, r in enumerate(rows) if r[0] == "BERTO") + 2
    out = openpyxl.Workbook()
    sheet = out.active
    sheet.title = "Collezione_1"
    for row in rows[start:end]:
        sheet.append(list(row[:14]))
    out.save(HERE / "franco_ferri_berte.xlsx")


def franco_ferri_swatches() -> None:
    book = xlrd.open_workbook(
        INPUTS
        / "Leather and Fabric Swatches - Feet Finish - Contrast Stitching - Franco Ferri Italia 2025.xls"
    )
    out = openpyxl.Workbook()
    out.remove(out.active)
    for sheet in book.sheets():
        target = out.create_sheet(sheet.name)
        for r in range(sheet.nrows):
            target.append(sheet.row_values(r))
    out.save(HERE / "franco_ferri_swatches.xlsx")


if __name__ == "__main__":
    cattelan_pdf()
    franco_ferri_price_list()
    franco_ferri_swatches()
    print("fixtures rebuilt")
