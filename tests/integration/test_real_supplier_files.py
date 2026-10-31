"""Checks against the full supplier documents. Skipped when supplier_inputs/ is absent (e.g. CI)."""

from pathlib import Path

import pytest

from fci.adapters.cattelan_pdf import CattelanPriceList
from fci.adapters.franco_ferri_swatches import FrancoFerriSwatchCard
from fci.adapters.franco_ferri_xlsm import FrancoFerriPriceList

INPUTS = Path(__file__).resolve().parents[2] / "supplier_inputs"
CATTELAN = INPUTS / "CATTELAN ITALIA p.list 05-26 EUR Vat excl.pdf"
FF_PRICES = INPUTS / "2026 - Franco Ferri GBP Price List IW - FCI Clipper Design - June 2026.xlsm"
FF_CARD = (
    INPUTS / "Leather and Fabric Swatches - Feet Finish - Contrast Stitching - Franco Ferri Italia 2025.xls"
)

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not CATTELAN.exists(), reason="supplier PDF not present")
def test_full_cattelan_list_finds_richard_on_page_358() -> None:
    richard = CattelanPriceList(CATTELAN).find("RICHARD")
    assert richard.page_number == 358
    assert richard.tables[0].rows[0].prices["Synthetic leather / C.O.M."] == 4121


@pytest.mark.skipif(not CATTELAN.exists(), reason="supplier PDF not present")
def test_generic_parser_reads_most_of_the_catalogue() -> None:
    """No product-specific code: the same parser should read the large majority of the list."""
    price_list = CattelanPriceList(CATTELAN)
    titles = price_list.titles()[40:]  # skip the index pages
    complete = 0
    for title in titles:
        entry = price_list.find(title)
        tables = [t for t in entry.tables if t.rows]
        if tables and all(set(r.prices) == set(t.columns) for t in tables for r in t.rows):
            complete += 1
    assert complete / len(titles) > 0.7


@pytest.mark.skipif(not FF_PRICES.exists(), reason="supplier workbook not present")
def test_full_franco_ferri_list() -> None:
    price_list = FrancoFerriPriceList(FF_PRICES)
    assert len(price_list.models) > 300
    berte = price_list.find("BERTE' FF")
    assert berte.modules["0401"].prices["Cat.70"] == 564
    assert berte.currency == "GBP"


@pytest.mark.skipif(not FF_CARD.exists(), reason="swatch card not present")
def test_original_xls_swatch_card() -> None:
    card = FrancoFerriSwatchCard(FF_CARD)
    assert card.article("Boston").stated_count == 16
    assert len(card.stitching()) == 11
