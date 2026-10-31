"""Cattelan price list + finishes catalogue -> attributes and price combinations."""

import json
from pathlib import Path

import pytest

from fci.adapters.cattelan_finishes import CattelanFinishes
from fci.adapters.cattelan_pdf import CattelanPriceList
from fci.brands import load_brand
from fci.mapping import build_options

FIXTURES = Path(__file__).parent.parent / "fixtures"
CONFIG = Path(__file__).parent.parent.parent / "config"


@pytest.fixture(scope="module")
def brand():
    return load_brand(CONFIG / "brands" / "cattelan-italia.yaml")


@pytest.fixture(scope="module")
def finishes(brand) -> CattelanFinishes:
    def fetch(category: int) -> dict:
        return json.loads((FIXTURES / f"cattelan_finishes_{category}.json").read_text())

    return CattelanFinishes(brand.swatch_groups, fetch)


@pytest.fixture(scope="module")
def richard(brand, finishes):
    entry = CattelanPriceList(FIXTURES / "cattelan_beds.pdf").find("RICHARD")
    return build_options(entry, brand, finishes.group)


def test_swatch_groups_follow_catalogue(finishes: CattelanFinishes) -> None:
    synthetic = finishes.group("synthetic-leather")
    assert "ECP01 BIANCO" in [s.name for s in synthetic]
    assert all(s.label == "Synthetic Leather" for s in synthetic)
    sofa_a = finishes.group("sofa-fabric-a")
    assert sofa_a and all(s.name.startswith("A") for s in sofa_a)
    glove = finishes.group("sofa-glove")
    assert glove and all(s.name.startswith("GLW") for s in glove)


def test_swatch_has_supplier_image(finishes: CattelanFinishes) -> None:
    swatch = finishes.group("synthetic-leather")[0]
    assert swatch.source_image.startswith("https://")


def test_unknown_group_raises(finishes: CattelanFinishes) -> None:
    with pytest.raises(KeyError):
        finishes.group("no-such-group")


def test_size_attribute_folds_slats_variant_into_size(richard) -> None:
    sizes = [o.name for o in richard.attribute("Size").options]
    assert sizes[:5] == [
        "A - W.245 X D.234 X H.102 cm",
        "B - W.245 X D.234 X H.102 cm",
        "D - W.265 X D.234 X H.102 cm",
        "E - W.285 X D.234 X H.102 cm",
        "G - W.285 X D.237 X H.102 cm",
    ]
    assert sizes[5] == "A - W.245 X D.234 X H.102 cm Pull-up slats with container"
    assert len(sizes) == 10
    size = richard.attribute("Size")
    assert (size.display, size.changes_price) == (1, True)


def test_cover_attribute_is_swatch_and_changes_price(richard) -> None:
    cover = richard.attribute("Cover")
    assert (cover.display, cover.changes_price) == (2, True)
    groupings = {o.grouping for o in cover.options}
    assert {
        "Synthetic Leather",
        "Fabric",
        "Micro Nubuck",
        "Soft Leather",
        "Soft Leather Glove",
        "Sofa Fabric A",
        "Sofa Fabric B",
        "Sofa Fabric D",
        "Sofa Fabric F",
    } <= groupings


def test_combination_prices_come_from_the_right_column(richard) -> None:
    prices = richard.price_map()
    assert prices[("A - W.245 X D.234 X H.102 cm", "ECP01 BIANCO")] == 4121
    assert prices[("G - W.285 X D.237 X H.102 cm", "MN103 WHITE")] == 5020  # fabric / micro nubuck column
    sofa_a = next(o.name for o in richard.attribute("Cover").options if o.grouping == "Sofa Fabric A")
    assert prices[("A - W.245 X D.234 X H.102 cm", sofa_a)] == 4233
    assert prices[("E - W.285 X D.234 X H.102 cm Pull-up slats with container", "ECP01 BIANCO")] == 5617


def test_base_price_is_cheapest_combination(richard) -> None:
    assert richard.base_price == 4121


def test_unpriced_combinations_are_flagged_not_invented(richard) -> None:
    prices = richard.price_map()
    sofa_a = next(o.name for o in richard.attribute("Cover").options if o.grouping == "Sofa Fabric A")
    assert ("A - W.245 X D.234 X H.102 cm Pull-up slats with container", sofa_a) not in prices
    assert any("not priced" in f.message for f in richard.flags)


@pytest.fixture(scope="module")
def thomas(brand, finishes):
    entry = CattelanPriceList(FIXTURES / "cattelan_beds.pdf").find("THOMAS")
    return build_options(entry, brand, finishes.group, finishes.find)


def test_table_note_with_finish_codes_becomes_a_swatch_attribute(thomas) -> None:
    structure = thomas.attribute("Structure")
    assert (structure.display, structure.changes_price) == (2, False)
    assert [o.name for o in structure.options] == ["GFM18 Bronze Embossed", "GFM69 Graphite Embossed"]
    assert all(o.grouping == "Metal" for o in structure.options)
    assert (
        structure.options[0].image == "/product-images/cattelan-italia/swatches/gfm18-bronze-embossed.jpg"
    )  # as in FCI's sample
    assert structure.options[0].swatch and structure.options[0].swatch.source_image.startswith("https://")


def test_feet_do_not_multiply_price_combinations(thomas) -> None:
    assert all(len(key) == 2 for key in thomas.combinations)
    assert len(thomas.combinations) == 5 * len(thomas.attribute("Cover").options)


def test_unknown_finish_code_is_flagged(brand, finishes) -> None:
    entry = CattelanPriceList(FIXTURES / "cattelan_beds.pdf").find("THOMAS")
    entry.tables[0].qualifiers["Feet"] = "GFM18 / GFM99"
    options = build_options(entry, brand, finishes.group, finishes.find)
    assert [o.name for o in options.attribute("Structure").options] == ["GFM18 Bronze Embossed"]
    assert any("GFM99" in f.message for f in options.flags)


def test_sizes_with_identical_printed_dimensions_are_flagged(richard) -> None:
    flagged = [f for f in richard.flags if f.field == "Size" and "identical" in f.message]
    assert len(flagged) == 2  # A/B standard and A/B pull-up
    assert "A" in flagged[0].message and "B" in flagged[0].message
