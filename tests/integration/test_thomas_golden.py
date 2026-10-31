"""Golden test against FCI's own hand-made Thomas bed CSVs (templates/).

FCI built the Thomas sample manually from an earlier price list. Rebuilding it from the
current list must give the same structure, the same size labels, and, for every cover FCI
listed, the same price column: FCI's price / current price is one constant list-update ratio.
"""

import csv
import json
from pathlib import Path

import pytest

from fci.adapters.cattelan_finishes import CattelanFinishes
from fci.adapters.cattelan_pdf import CattelanPriceList
from fci.brands import load_brand
from fci.mapping import build_options

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def rows(name: str) -> list[dict[str, str]]:
    with (ROOT / "templates" / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def thomas():
    brand = load_brand(ROOT / "config" / "brands" / "cattelan-italia.yaml")
    finishes = CattelanFinishes(
        brand.swatch_groups,
        lambda c: json.loads((FIXTURES / f"cattelan_finishes_{c}.json").read_text()),
    )
    entry = CattelanPriceList(FIXTURES / "cattelan_beds.pdf").find("THOMAS")
    return build_options(entry, brand, finishes.group, finishes.find)


def code(name: str) -> str:
    return name.split()[0].upper().replace("-", "")


def test_size_labels_match_fci_exactly(thomas) -> None:
    fci_sizes = [r["name"] for r in rows("attributes.csv") if r["attribute"] == "Size"]
    assert [o.name for o in thomas.attribute("Size").options] == fci_sizes


def test_attribute_flags_match_fci(thomas) -> None:
    fci = {r["attribute"]: (int(r["display"]), r["changesprice"] == "1") for r in rows("attributes.csv")}
    for name in ("Size", "Cover", "Structure"):
        attribute = thomas.attribute(name)
        assert (attribute.display, attribute.changes_price) == fci[name]


def test_every_fci_cover_lands_in_the_same_price_column(thomas) -> None:
    ours = {(size, code(cover)): price for (size, cover), price in thomas.combinations.items()}
    ratios = []
    unmatched = []
    for row in rows("prices.csv"):
        size, cover = row["combo"].split(" [+] ")
        current = ours.get((size, code(cover)))
        if current is None:
            unmatched.append(cover)
            continue
        ratios.append(int(row["price"]) / current)
    # Every cover FCI listed that Cattelan still offers is matched; the rest are withdrawn codes.
    catalogue = set()
    for category in (70, 119):
        data = json.loads((FIXTURES / f"cattelan_finishes_{category}.json").read_text())
        catalogue |= {code(e["sNomeColore"]) for v in data["productsList"].values() for e in v}
    assert not {code(c) for c in unmatched} & catalogue
    assert max(ratios) - min(ratios) < 0.001, "a cover was mapped to a different price column"
    assert 0.95 < ratios[0] < 0.97  # FCI's sample predates a ~4% list increase


def test_withdrawn_covers_in_fci_listing_are_detectable(thomas) -> None:
    """41 of FCI's 118 Thomas covers are gone from Cattelan's catalogue (mostly old B2xx/B4xx fabrics)."""
    ours = {code(o.name) for o in thomas.attribute("Cover").options}
    fci = {code(r["name"]) for r in rows("attributes.csv") if r["attribute"] == "Cover"}
    withdrawn = fci - ours
    assert len(withdrawn) == 41
    assert "B401" in withdrawn and "ECP28" in withdrawn


def test_feet_finishes_match_fci_codes(thomas) -> None:
    fci = sorted(code(r["name"]) for r in rows("attributes.csv") if r["attribute"] == "Structure")
    ours = sorted(code(o.name) for o in thomas.attribute("Structure").options)
    assert ours == fci == ["GFM18", "GFM69"]
