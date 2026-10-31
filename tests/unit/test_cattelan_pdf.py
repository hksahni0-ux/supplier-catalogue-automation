"""Cattelan price-list parser. Expected values are read off pages 358 (Richard) and 361 (Thomas)."""

from pathlib import Path

import pytest

from fci.adapters.cattelan_pdf import CattelanPriceList

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cattelan_beds.pdf"


@pytest.fixture(scope="module")
def price_list() -> CattelanPriceList:
    return CattelanPriceList(FIXTURE)


def test_finds_product_by_title(price_list: CattelanPriceList) -> None:
    assert price_list.find("RICHARD").page_number == 1
    assert price_list.find("Thomas").page_number == 2


def test_unknown_product_raises(price_list: CattelanPriceList) -> None:
    with pytest.raises(LookupError):
        price_list.find("NOT A PRODUCT")


def test_richard_has_three_tables(price_list: CattelanPriceList) -> None:
    tables = price_list.find("RICHARD").tables
    assert len(tables) == 3
    assert tables[0].columns == [
        "Synthetic leather / C.O.M.",
        "Fabric / Micro nubuck / C.O.L",
        "Soft leather",
        "Soft leather Glove",
    ]
    assert tables[1].columns == [
        "Fabric A Sofas",
        "Fabric B Sofas",
        "Fabric D Sofas",
        "Fabric F Sofas",
        "Soft leather Glove / Perfetto Sofas",
        "Soft leather Nabuk / Magnifica Sofas",
    ]


def test_richard_table_qualifiers(price_list: CattelanPriceList) -> None:
    tables = price_list.find("RICHARD").tables
    assert tables[0].qualifiers == {}
    assert tables[2].qualifiers == {"Slats": "Pull-up slats with container"}


def test_richard_rows_and_prices(price_list: CattelanPriceList) -> None:
    standard, sofa, pull_up = price_list.find("RICHARD").tables
    assert [r.code for r in standard.rows] == ["A", "B", "D", "E", "G"]
    a = standard.rows[0]
    assert (a.width, a.depth, a.height) == (245, 234, 102)
    assert a.prices == {
        "Synthetic leather / C.O.M.": 4121,
        "Fabric / Micro nubuck / C.O.L": 4498,
        "Soft leather": 6216,
        "Soft leather Glove": 6673,
    }
    g = sofa.rows[-1]
    assert (g.width, g.depth) == (285, 237)
    assert g.prices["Soft leather Nabuk / Magnifica Sofas"] == 8730
    assert g.prices["Fabric A Sofas"] == 4729
    assert pull_up.rows[3].prices["Synthetic leather / C.O.M."] == 5617


def test_thomas_ignores_inches_volume_and_parcels(price_list: CattelanPriceList) -> None:
    product = price_list.find("THOMAS")
    (table,) = product.tables
    assert table.qualifiers == {"Feet": "GFM18 / GFM69"}
    assert [r.code for r in table.rows] == ["A", "B", "D", "E", "G"]
    assert table.rows[0].prices == {
        "Synthetic leather / C.O.M.": 4002,
        "Fabric / Micro nubuck / C.O.L": 4129,
        "Soft leather": 5211,
        "Soft leather Glove": 5640,
    }
    assert (table.rows[4].width, table.rows[4].depth, table.rows[4].height) == (261, 231, 103)
    assert table.rows[4].prices["Soft leather Glove"] == 6641


def test_extracts_description_and_designer(price_list: CattelanPriceList) -> None:
    richard = price_list.find("RICHARD")
    assert richard.description.startswith("Upholstered bed covered in fabric, micro nubuck")
    assert richard.description.endswith("Optional: pull-up slats with container.")
    assert richard.designer is None
    thomas = price_list.find("THOMAS")
    assert thomas.designer == "Maurizio Manzoni"
    assert "bronze (GFM18) or graphite" in thomas.description


def test_every_row_has_a_price_for_every_column(price_list: CattelanPriceList) -> None:
    for name in ("RICHARD", "THOMAS"):
        for table in price_list.find(name).tables:
            for row in table.rows:
                assert set(row.prices) == set(table.columns), (name, row.code)


def test_page_with_two_products_keeps_them_apart(price_list: CattelanPriceList) -> None:
    # Fixture page 3 is the outdoor page: BISHOP and GRETA share it.
    bishop = price_list.find("BISHOP")
    assert [r.code for r in bishop.tables[0].rows] == ["A", "B", "C"]
    assert bishop.tables[0].rows[0].prices == {"Cobalto / Etrusco / Smeraldo": 1121}
    greta = price_list.find("GRETA")
    assert greta.tables[0].rows[0].prices == {"Outdoor Fabric": 1415}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("245x234x102h", (245, 234, 102)),
        ("Ø36x45h", (36, 36, 45)),
        ("ø140x73,5h", (140, 140, 73.5)),
        ("62x62x78h", (62, 62, 78)),
    ],
)
def test_parse_dims(raw: str, expected: tuple[float, float, float]) -> None:
    from fci.adapters.cattelan_pdf import parse_dims

    assert parse_dims(raw) == expected
