"""The six FCI import CSVs: headers from the templates, values from the product record."""

import csv
from pathlib import Path

import pytest

from fci.exporters import CSV_FILES, write_csvs
from fci.model import Attribute, Option, ProductOptions
from fci.naming import Naming
from fci.record import ProductRecord

TEMPLATES = Path(__file__).parent.parent.parent / "templates"


@pytest.fixture
def record() -> ProductRecord:
    size = Attribute(
        "Size", 1, True, [Option("A - W.221 X D.228 X H.103 cm"), Option("B - W.228 X D.228 X H.103 cm")]
    )
    cover = Attribute(
        "Cover",
        2,
        True,
        [
            Option(
                "ECP01 BIANCO",
                "/product-images/cattelan-italia/swatches/synthetic-leather/ecp01-bianco.jpg",
                "Synthetic Leather",
            ),
        ],
    )
    feet = Attribute("Structure", 2, False, [Option("GFM18 Bronze Embossed", "/x/gfm18.jpg", "Metal")])
    combos = {
        ("A - W.221 X D.228 X H.103 cm", "ECP01 BIANCO"): 4002,
        ("B - W.228 X D.228 X H.103 cm", "ECP01 BIANCO"): 4017,
    }
    return ProductRecord(
        naming=Naming("Thomas", "Double Bed", "Cattelan Italia", "cattelan-italia"),
        sku="cattelan-italia-806",
        category_code="FUR-BED-DB",
        options=ProductOptions([size, cover, feet], combos),
        meta_description="The Thomas Bed features a sculptural quilted headboard.",
        long_description="The Thomas Double Bed is a harmonious fusion.",
        image_count=3,
    )


def read(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def test_writes_six_files_with_template_headers(record: ProductRecord, tmp_path: Path) -> None:
    paths = write_csvs(record, tmp_path, TEMPLATES)
    assert set(paths) == set(CSV_FILES)
    for kind, path in paths.items():
        assert read(path)[0] == read(TEMPLATES / CSV_FILES[kind])[0], kind


def test_product_row(record: ProductRecord, tmp_path: Path) -> None:
    rows = read(write_csvs(record, tmp_path, TEMPLATES)["product"])
    row = dict(zip(rows[0], rows[1], strict=True))
    assert row == {
        "name": "Thomas Double Bed",
        "code": "cattelan-italia-806",
        "brand": "Cattelan Italia",
        "price": "4002",
        "onsale": "0",
        "sellable": "1",
        "url": "/thomas-double-bed-by-cattelan-italia.html",
        "title": "Thomas Double Bed by Cattelan Italia",
        "keywords": "Thomas, Double Bed, Cattelan Italia",
        "description": "The Thomas Bed features a sculptural quilted headboard.",
        "published": "1",
        "nositemap": "1",
        "priority": "200",
        "img": "/site-assets/product-images/cattelan-italia/thomas-double-bed-by-cattelan-italia-1.jpg",
    }


def test_images_and_categories(record: ProductRecord, tmp_path: Path) -> None:
    paths = write_csvs(record, tmp_path, TEMPLATES)
    images = read(paths["images"])
    assert len(images) == 1 + 3
    assert images[2] == [
        "cattelan-italia-806",
        "/cattelan-italia/thomas-double-bed-by-cattelan-italia-2.jpg",
        "Thomas Double Bed by Cattelan Italia| By FCI London",
        "Thomas Double Bed By FCI London",
    ]
    assert read(paths["categories"])[1] == ["cattelan-italia-806", "FUR-BED-DB"]


def test_attributes_rows(record: ProductRecord, tmp_path: Path) -> None:
    rows = read(write_csvs(record, tmp_path, TEMPLATES)["attributes"])
    assert rows[1] == ["cattelan-italia-806", "Size", "1", "1", "A - W.221 X D.228 X H.103 cm", "", "", ""]
    assert rows[3] == [
        "cattelan-italia-806",
        "Cover",
        "2",
        "1",
        "ECP01 BIANCO",
        "/product-images/cattelan-italia/swatches/synthetic-leather/ecp01-bianco.jpg",
        "Synthetic Leather",
        "",
    ]
    assert rows[4][1:4] == ["Structure", "2", "0"]


def test_prices_rows_use_plus_separator(record: ProductRecord, tmp_path: Path) -> None:
    rows = read(write_csvs(record, tmp_path, TEMPLATES)["prices"])
    assert rows[1] == ["cattelan-italia-806", "A - W.221 X D.228 X H.103 cm [+] ECP01 BIANCO", "4002"]
    assert len(rows) == 3


def test_details_keep_template_keys(record: ProductRecord, tmp_path: Path) -> None:
    rows = read(write_csvs(record, tmp_path, TEMPLATES)["details"])
    template = read(TEMPLATES / CSV_FILES["details"])
    assert [r[1] for r in rows] == [r[1] for r in template]
    data = {r[1]: r[2] for r in rows[1:]}
    assert data["SHORT-DESCRIPTION"] == "The Thomas Double Bed is a harmonious fusion."
    assert data["NOTES"] == ""


def test_unknown_template_column_is_left_blank_and_flagged(record: ProductRecord, tmp_path: Path) -> None:
    custom = tmp_path / "templates"
    custom.mkdir()
    for kind, name in CSV_FILES.items():
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        if kind == "categories":
            text = "code,catcode,newcolumn\n"
        (custom / name).write_text(text, encoding="utf-8")
    rows = read(write_csvs(record, tmp_path / "out", custom)["categories"])
    assert rows[1] == ["cattelan-italia-806", "FUR-BED-DB", ""]
    assert any("newcolumn" in f.message for f in record.flags)


def test_files_use_plain_line_endings_like_the_templates(record: ProductRecord, tmp_path: Path) -> None:
    for path in write_csvs(record, tmp_path, TEMPLATES).values():
        assert b"\r" not in path.read_bytes(), path.name
