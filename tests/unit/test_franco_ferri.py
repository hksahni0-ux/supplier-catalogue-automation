"""Franco Ferri / Naustro Fiera: GBP module price list + swatch card -> layouts and combinations."""

from pathlib import Path

import pytest

from fci.adapters.franco_ferri_swatches import FrancoFerriSwatchCard
from fci.adapters.franco_ferri_xlsm import FrancoFerriPriceList
from fci.modular import Layout, build_modular_options

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def price_list() -> FrancoFerriPriceList:
    return FrancoFerriPriceList(FIXTURES / "franco_ferri_berte.xlsx")


@pytest.fixture(scope="module")
def card() -> FrancoFerriSwatchCard:
    return FrancoFerriSwatchCard(FIXTURES / "franco_ferri_swatches.xlsx")


# --- price list -------------------------------------------------------------


def test_finds_model_by_exact_name_not_neighbour(price_list: FrancoFerriPriceList) -> None:
    berte = price_list.find("BERTE' FF")
    assert berte.name == "BERTE' FF"
    assert "0168" in berte.modules
    assert price_list.find("BERTO").modules.keys() == {"0174"}


def test_finds_model_without_suffix(price_list: FrancoFerriPriceList) -> None:
    assert price_list.find("Berte'").name == "BERTE' FF"


def test_module_prices_and_dimensions(price_list: FrancoFerriPriceList) -> None:
    berte = price_list.find("BERTE' FF")
    module = berte.modules["0168"]
    assert module.description == "ARMCHAIR RCL ARM L. TOG.SW."
    assert module.prices == {
        "Cat.70": 698,
        "Cat.80": 739,
        "Cat.84": 786,
        "Cat.20": 905,
        "Cat.25": 945,
        "Cat.30": 970,
        "Cat.35": 1059,
        "Cat.40": 1095,
    }
    assert (module.width, module.height, module.depth) == (108, 95, 101)
    assert berte.categories == [
        "Cat.70",
        "Cat.80",
        "Cat.84",
        "Cat.20",
        "Cat.25",
        "Cat.30",
        "Cat.35",
        "Cat.40",
    ]
    assert berte.currency == "GBP"


def test_unknown_model_raises(price_list: FrancoFerriPriceList) -> None:
    with pytest.raises(LookupError):
        price_list.find("NOPE")


# --- swatch card ------------------------------------------------------------


def test_fabric_articles_with_categories(card: FrancoFerriSwatchCard) -> None:
    boston = card.article("Boston")
    assert boston.category == "Cat.70"
    assert boston.material == "Fabric"
    assert boston.colours[0] == ("01", "Toffee")
    assert len(boston.colours) == 16
    assert boston.stated_count == 16  # the card's own '16 Colours' row
    assert card.article("Universe").category == "Cat.84"


def test_leather_articles_with_categories(card: FrancoFerriSwatchCard) -> None:
    gioioso = card.article("Gioioso")
    assert (gioioso.category, gioioso.material) == ("Cat.20", "Leather")
    assert gioioso.colours[0] == ("20650", "White")
    assert len(gioioso.colours) == 7
    assert card.article("Newbuck").category == "Cat.40"


def test_parsed_counts_match_the_cards_own_totals(card: FrancoFerriSwatchCard) -> None:
    for article in card.articles:
        if article.stated_count is not None and article.colours:
            assert len(article.colours) == article.stated_count, article.name


def test_book_only_articles_are_reported(card: FrancoFerriSwatchCard) -> None:
    aquaclean = card.article("Aquaclean")
    assert aquaclean.colours == []
    assert aquaclean.note == "All colours See Book"


def test_feet_finishes_exclude_summaries_and_other_models(card: FrancoFerriSwatchCard) -> None:
    metal = card.feet("Metal", model="BERTE")
    assert ("42", "Graphite") in metal
    assert ("71", "Titanium Black Gloss") in metal
    assert all(code != "22" for code, _ in metal)  # "Only model BOSE"
    assert len(metal) == 6
    assert [c for c, _ in card.feet("Metal", model="BOSE")].count("22") == 1


def test_contrast_stitching(card: FrancoFerriSwatchCard) -> None:
    stitching = card.stitching()
    assert stitching[0] == ("101", "White")
    assert len(stitching) == 11


# --- layouts and combinations ----------------------------------------------

LAYOUTS = [
    Layout("Corner - W.305 X D.305 X H.95 cm", ["0168", "0125", "0401", "0125", "0169"]),
    Layout("Corner with Terminal - W.305 X D.281 X H.95 cm", ["0168", "0125", "0401", "0145"]),
    Layout("Maxi Chaise - W.324 X D.161 X H.95 cm", ["0172", "A138", "0285"]),
    Layout("Chaise - W.300 X D.161 X H.95 cm", ["0246", "0125", "0169"]),
]
MIRRORS = [("0168", "0169"), ("0171", "0172"), ("0285", "0286"), ("0245", "0246"), ("0145", "0146")]


@pytest.fixture(scope="module")
def burt(price_list, card):
    return build_modular_options(
        price_list.find("BERTE' FF"),
        card,
        LAYOUTS,
        mirror_pairs=MIRRORS,
        feet_codes=["38", "42", "47", "71"],
        extra_dropdowns={"Comfort": ["Soft", "Hard"]},
        brand_slug="fiera-collection",
        model="BERTE",
    )


def test_layout_price_is_sum_of_modules(burt) -> None:
    prices = burt.price_map()
    assert prices[("Corner - W.305 X D.305 X H.95 cm", "03-BLACK-BOSTON")] == 2600
    # 698 + 320 + 564 + 731 (the corner module 0401 sits between the run and the terminal)
    assert prices[("Corner with Terminal - W.305 X D.281 X H.95 cm", "03-BLACK-BOSTON")] == 2313
    assert prices[("Maxi Chaise - W.324 X D.161 X H.95 cm", "03-BLACK-BOSTON")] == 1833
    assert prices[("Chaise - W.300 X D.161 X H.95 cm", "03-BLACK-BOSTON")] == 1650
    # Cat.40 leather: 1095 + 501 + 881 + 501 + 1095
    assert prices[("Corner - W.305 X D.305 X H.95 cm", "40180-COCONUT-NEWBUCK")] == 4073


def test_base_price_is_cheapest(burt) -> None:
    assert burt.base_price == 1650


def test_mirrored_orientation_does_not_change_price(burt) -> None:
    orientation = burt.attribute("Orientation")
    assert [o.name for o in orientation.options] == ["As Shown", "Mirrored"]
    assert orientation.changes_price is False


def test_non_price_attributes(burt) -> None:
    feet = burt.attribute("Feet")
    assert (feet.display, feet.changes_price) == (2, False)
    assert [o.name for o in feet.options] == [
        "38 Anodic Black",
        "42 Graphite",
        "47 Bronze",
        "71 Titanium Black Gloss",
    ]
    assert burt.attribute("Comfort").display == 1
    assert len(burt.attribute("Contrast Stitching").options) == 11


def test_price_categories_without_materials_are_flagged(burt) -> None:
    messages = " ".join(f.message for f in burt.flags)
    for category in ("Cat.80", "Cat.25", "Cat.35"):
        assert category in messages
    assert "Aquaclean" in messages


def test_missing_module_is_an_error(price_list, card) -> None:
    result = build_modular_options(
        price_list.find("BERTE' FF"),
        card,
        [Layout("Bad", ["0168", "9999"])],
        brand_slug="fiera-collection",
        model="BERTE",
    )
    assert not result.combinations
    assert any(f.severity == "error" and "9999" in f.message for f in result.flags)


def test_job_file_layouts_match_the_technical_sheet() -> None:
    """Module codes as drawn on francoferri.it/pdf/berte.pdf (checked against a 300 dpi render)."""
    import yaml

    job = yaml.safe_load((Path(__file__).parents[2] / "jobs" / "burt-corner-sofa.yaml").read_text())
    assert [layout["modules"] for layout in job["layouts"]] == [layout.modules for layout in LAYOUTS]
