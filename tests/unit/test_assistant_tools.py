import csv
import json
from pathlib import Path

import pytest

from fci.assistant.catalogue import Catalogue
from fci.assistant.tools import Tools

ROOT = Path(__file__).resolve().parents[2]
SIZE_A, SIZE_D = "A - W.245 X D.234 X H.102 cm", "D - W.265 X D.234 X H.102 cm"


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def catalogue(tmp_path) -> Catalogue:
    out = tmp_path / "cattelan-italia-889"
    report = {
        "product": "Richard Double Bed", "sku": "cattelan-italia-889", "base_price": 4121,
        "price_range": [4121, 7192], "combinations": 4, "generated": "2026-11-01 22:58 UTC",
        "manual_inputs": {"brand": "cattelan-italia"},
        "flags": [
            {"severity": "warning", "field": "Size", "message": "A and B look identical", "source": "p.358"},
            {"severity": "info", "field": "Cover", "message": "unpriced pairs omitted", "source": "p.358"},
        ],
    }  # fmt: skip
    out.mkdir(parents=True)
    (out / "report.json").write_text(json.dumps(report))
    write_csv(out / "csv" / "cattelan-italia-889-prices.csv", ["code", "combo", "price"], [
        ["cattelan-italia-889", f"{SIZE_A} [+] ECP01 BIANCO", "4121"],
        ["cattelan-italia-889", f"{SIZE_A} [+] GLV02 DOVER", "6673"],
        ["cattelan-italia-889", f"{SIZE_D} [+] GLV02 DOVER", "7192"],
        ["cattelan-italia-889", f"{SIZE_D} [+] GLV03 ECRU", "7192"],
    ])  # fmt: skip
    attributes = [
        "code",
        "attribute",
        "display",
        "changesprice",
        "name",
        "image",
        "grouping",
        "specifications",
    ]
    write_csv(out / "csv" / "cattelan-italia-889-attributes.csv", attributes, [
        ["cattelan-italia-889", "Size", "1", "1", SIZE_A, "", "", ""],
        ["cattelan-italia-889", "Size", "1", "1", SIZE_D, "", "", ""],
        ["cattelan-italia-889", "Cover", "2", "1", "ECP01 BIANCO", "/x.jpg", "Synthetic Leather", ""],
        ["cattelan-italia-889", "Cover", "2", "1", "GLV02 DOVER", "/y.jpg", "Soft Leather Glove", ""],
        ["cattelan-italia-889", "Cover", "2", "1", "GLV03 ECRU", "/z.jpg", "Soft Leather Glove", ""],
    ])  # fmt: skip
    (out / "price-changes.md").write_text("# Price changes\n\n1 prices changed (avg +4.0%), 3 unchanged\n")
    (out / "published.json").write_text(json.dumps({"folder": "abc123", "date": "2026-11-02"}))
    return Catalogue(tmp_path, ROOT / "config")


def test_products_are_listed_with_currency_and_review_counts(catalogue) -> None:
    (product,) = Tools(catalogue).list_products()
    assert product["name"] == "Richard Double Bed" and product["currency"] == "EUR"
    assert product["needs_review"] == 1 and product["base_price"] == 4121


def test_price_lookup_matches_size_letter_and_material_words(catalogue) -> None:
    reply = Tools(catalogue).get_price("richard", size="D", cover="glove leather")
    assert reply["currency"] == "EUR"
    assert reply["prices"] == [
        {
            "price": 7192,
            "size": SIZE_D,
            "cover_groups": ["Soft Leather Glove"],
            "covers": ["GLV02 DOVER", "GLV03 ECRU"],
        }
    ]


def test_price_lookup_by_cover_code(catalogue) -> None:
    reply = Tools(catalogue).get_price("cattelan-italia-889", cover="ECP01")
    assert [p["price"] for p in reply["prices"]] == [4121]


def test_unknown_product_says_so_and_lists_what_exists(catalogue) -> None:
    reply = Tools(catalogue).get_price("sofa that does not exist")
    assert "error" in reply and "Richard Double Bed" in reply["known_products"]


def test_no_matching_price_is_an_explicit_empty_answer(catalogue) -> None:
    reply = Tools(catalogue).get_price("richard", size="Z")
    assert reply["prices"] == [] and "no price" in reply["note"]


def test_options_group_covers_with_counts_and_price_ranges(catalogue) -> None:
    reply = Tools(catalogue).list_options("richard")
    assert reply["sizes"] == [SIZE_A, SIZE_D]
    glove = next(g for g in reply["cover_groups"] if g["group"] == "Soft Leather Glove")
    assert glove == {
        "group": "Soft Leather Glove",
        "count": 2,
        "from": 6673,
        "to": 7192,
        "examples": ["GLV02 DOVER", "GLV03 ECRU"],
    }  # noqa: E501


def test_review_items_leave_out_info_by_default(catalogue) -> None:
    items = Tools(catalogue).get_review_items("richard")["items"]
    assert [i["severity"] for i in items] == ["warning"]


def test_price_changes_and_drive_link(catalogue) -> None:
    tools = Tools(catalogue)
    assert "1 prices changed" in tools.get_price_changes("richard")["summary"]
    assert tools.get_drive_link("richard")["url"] == "https://drive.google.com/drive/folders/abc123"


def test_run_requests_are_proposals_that_do_nothing(catalogue) -> None:
    proposal = Tools(catalogue).propose_run(["richard"], publish=True)
    assert proposal == {
        "proposal": {"action": "run", "skus": ["cattelan-italia-889"], "publish": True},
        "note": "Nothing has run yet. The user must press Confirm.",
    }


def test_every_tool_has_a_schema_for_the_model(catalogue) -> None:
    names = {s["function"]["name"] for s in Tools(catalogue).schemas()}
    assert names == {"list_products", "get_price", "list_options", "get_review_items", "get_price_changes",
                     "get_drive_link", "propose_run"}  # fmt: skip
