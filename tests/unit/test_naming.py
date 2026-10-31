"""Derived-column rules, reverse-engineered from FCI's Thomas bed sample CSVs and Rajesh's video."""

import pytest

from fci.naming import Naming, parse_supplier_price, size_label, slugify


@pytest.fixture
def thomas() -> Naming:
    return Naming(
        model="Thomas",
        product_type="Double Bed",
        brand="Cattelan Italia",
        brand_slug="cattelan-italia",
    )


def test_name_joins_model_and_product_type(thomas: Naming) -> None:
    assert thomas.name == "Thomas Double Bed"


def test_url_title_keywords_match_sample(thomas: Naming) -> None:
    assert thomas.url == "/thomas-double-bed-by-cattelan-italia.html"
    assert thomas.title == "Thomas Double Bed by Cattelan Italia"
    assert thomas.keywords == "Thomas, Double Bed, Cattelan Italia"


def test_image_paths_match_sample(thomas: Naming) -> None:
    assert thomas.image_file(1) == "thomas-double-bed-by-cattelan-italia-1.jpg"
    assert thomas.image_csv_name(3) == "/cattelan-italia/thomas-double-bed-by-cattelan-italia-3.jpg"
    assert (
        thomas.main_image_url
        == "/site-assets/product-images/cattelan-italia/thomas-double-bed-by-cattelan-italia-1.jpg"
    )


def test_image_title_and_alt_match_sample(thomas: Naming) -> None:
    assert thomas.image_title == "Thomas Double Bed by Cattelan Italia| By FCI London"
    assert thomas.image_alt == "Thomas Double Bed By FCI London"


def test_url_brand_can_differ_from_display_brand() -> None:
    # Live FCI page: brand "Naustro Fiera Collection", URL ".../burt-corner-sofa-by-fiera-collection.html"
    burt = Naming(
        model="Burt",
        product_type="Corner Sofa",
        brand="Naustro Fiera Collection",
        brand_slug="fiera-collection",
        url_brand="Fiera Collection",
    )
    assert burt.url == "/burt-corner-sofa-by-fiera-collection.html"
    assert burt.title == "Burt Corner Sofa by Fiera Collection"
    assert burt.keywords == "Burt, Corner Sofa, Naustro Fiera Collection"


def test_swatch_path_without_folder_has_no_double_slash(thomas: Naming) -> None:
    assert (
        thomas.swatch_path("", "38 Anodic Black")
        == "/product-images/cattelan-italia/swatches/38-anodic-black.jpg"
    )


def test_swatch_path(thomas: Naming) -> None:
    assert (
        thomas.swatch_path("synthetic-leather", "ECP01 BIANCO")
        == "/product-images/cattelan-italia/swatches/synthetic-leather/ecp01-bianco.jpg"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("4.121", 4121), ("4.002", 4002), ("975", 975), ("12.345", 12345)],
)
def test_parse_supplier_price_treats_dot_as_thousands(raw: str, expected: int) -> None:
    assert parse_supplier_price(raw) == expected


@pytest.mark.parametrize("raw", ["", "EUR", "0,83", "1,25", "n/a"])
def test_parse_supplier_price_rejects_non_prices(raw: str) -> None:
    assert parse_supplier_price(raw) is None


def test_size_label_matches_sample_format() -> None:
    assert size_label("A", 221, 228, 103) == "A - W.221 X D.228 X H.103 cm"


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("ECP13 ROSSO CORSA", "ecp13-rosso-corsa"),
        ("GLV03 ECRÙ", "glv03-ecru"),
        ("995 Nardò", "995-nardo"),
        ("Berte' FF", "berte-ff"),
    ],
)
def test_slugify(text: str, slug: str) -> None:
    assert slugify(text) == slug
