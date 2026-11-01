import csv

from fci.changes import compare_prices, write_changed_rows

OLD = [
    {"code": "x-1", "combo": "A [+] ECP01 BIANCO", "price": "4121"},
    {"code": "x-1", "combo": "A [+] ECP05 TORTORA", "price": "4121"},
    {"code": "x-1", "combo": "A [+] B240", "price": "4498"},
    {"code": "x-1", "combo": "A [+] B999 GONE", "price": "4498"},
]
NEW = [
    {"code": "x-1", "combo": "A [+] ECP01 BIANCO", "price": "4286"},
    {"code": "x-1", "combo": "A [+] ECP05 TORTORA", "price": "4286"},
    {"code": "x-1", "combo": "A [+] B240", "price": "4498"},
    {"code": "x-1", "combo": "A [+] B300 NEW", "price": "4498"},
]


def test_compare_finds_changed_added_and_removed_combinations() -> None:
    changes = compare_prices(OLD, NEW)
    assert [(c.combo, c.old, c.new) for c in changes.changed] == [
        ("A [+] ECP01 BIANCO", 4121, 4286),
        ("A [+] ECP05 TORTORA", 4121, 4286),
    ]
    assert changes.added == ["A [+] B300 NEW"]
    assert changes.removed == ["A [+] B999 GONE"]
    assert changes.unchanged == 1


def test_change_reports_percentage_and_summary() -> None:
    changes = compare_prices(OLD, NEW)
    assert round(changes.changed[0].percent, 1) == 4.0
    assert changes.summary() == "2 prices changed (avg +4.0%), 1 added, 1 removed, 1 unchanged"


def test_no_differences_is_reported_plainly() -> None:
    assert compare_prices(OLD, OLD).summary() == "no price changes (4 unchanged)"


def test_changed_rows_csv_holds_only_rows_to_upload(tmp_path) -> None:
    path = write_changed_rows(compare_prices(OLD, NEW), NEW, tmp_path / "x-1-prices-changed.csv")
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    # changed and added rows are uploaded; removed ones are listed in the report instead
    assert [r["combo"] for r in rows] == ["A [+] ECP01 BIANCO", "A [+] ECP05 TORTORA", "A [+] B300 NEW"]
    assert list(rows[0]) == ["code", "combo", "price"]
