"""Matching supplier swatch codes to swatch images already on FCI's server."""

from fci.swatch_reuse import index_existing, match_swatch

EXISTING = index_existing(
    [
        "/product-images/fiera-collection/swatches/05-lightgrey-boston.jpg",
        "/product-images/fiera-collection/swatches/16-sky-boston.jpg",
        "/product-images/fiera-collection/swatches/001-giotto.jpg",
        "/product-images/fiera-collection/swatches/40180-newbuck.jpg",
        "/product-images/fiera-collection/swatches/20650_gioioso.jpg",
    ]
)


def test_matches_on_code_and_article_ignoring_spelling() -> None:
    path, note = match_swatch("05-LIGHT-GREY-BOSTON", EXISTING)
    assert path == "/product-images/fiera-collection/swatches/05-lightgrey-boston.jpg"
    assert note == ""


def test_matches_zero_padded_codes_without_colour() -> None:
    assert match_swatch("01-ORANGE-GIOTTO", EXISTING)[0].endswith("001-giotto.jpg")
    assert match_swatch("40180-COCONUT-NEWBUCK", EXISTING)[0].endswith("40180-newbuck.jpg")
    assert match_swatch("20650-WHITE-GIOIOSO", EXISTING)[0].endswith("20650_gioioso.jpg")


def test_colour_change_is_not_reused_and_is_reported() -> None:
    path, note = match_swatch("16-LIGHT-TEAL-BOSTON", EXISTING)
    assert path is None  # the code now means a different colour; FCI's image may be wrong
    assert "sky" in note and "light teal" in note


def test_no_match() -> None:
    assert match_swatch("99-NEW-BOSTON", EXISTING) == (None, "")
    assert match_swatch("05-LIGHT-GREY-BRUTUS", EXISTING) == (None, "")
