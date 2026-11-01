"""Drive workspace end to end, offline: sheet -> sync price lists -> run -> price changes -> publish."""

import csv
import json
from pathlib import Path

import yaml

from fci.workflow import run_workspace
from fci.workspace import Workspace
from tests.fakes import FakeDrive
from tests.integration.test_pipeline_offline import FIXTURES, ROOT, FakeHttp

HEADER = ["active", "sku", "brand", "model", "supplier_name", "product_type", "category_code",
          "category_confirmed", "supplier_url", "fci_url", "notes"]  # fmt: skip
RICHARD_URL = "https://www.cattelanitalia.com/en/products/C742E2EA-1F88-45F9-B990-EAE58E5347CF?c=30"
RICHARD = ["yes", "cattelan-italia-889", "cattelan-italia", "Richard", "RICHARD", "Double Bed", "FUR-BED-DB",
           "yes", RICHARD_URL]  # fmt: skip
PDF = (FIXTURES / "cattelan_beds.pdf").read_bytes()
MAY = "2026-05-01T09:00:00.000Z"
WORKSPACE = Workspace("root", "price-lists", "outputs", "sheet", {})


def drive_with(pdf: bytes, modified: str) -> FakeDrive:
    drive = FakeDrive()
    drive.folders["price-lists/Cattelan Italia"] = "cat-folder"  # found by the supplier's name
    drive.tabs = {"Products": [HEADER, RICHARD], "Layouts": [["sku", "layout", "modules"]], "Options": []}
    drive.put("cat-folder", "CATTELAN ITALIA p.list 05-26 EUR Vat excl.pdf", pdf, modified)
    return drive


def run(drive: FakeDrive, tmp: Path, publish: bool = True):
    return run_workspace(
        drive,
        WORKSPACE,
        inputs=tmp / "inputs",
        config=ROOT / "config",
        templates=ROOT / "templates",
        out_root=tmp / "out",
        http=FakeHttp(),
        client=None,
        publish=publish,
        date="2026-11-02",
    )


def test_first_run_syncs_runs_and_publishes(tmp_path) -> None:
    drive = drive_with(PDF, MAY)
    (result,) = run(drive, tmp_path)
    assert result.sku == "cattelan-italia-889"
    assert result.base_price == 4121
    assert result.changes is None  # nothing to compare against yet
    assert (tmp_path / "inputs" / "CATTELAN ITALIA p.list 05-26 EUR Vat excl.pdf").exists()
    uploaded = {name for _, name in drive.uploads}
    assert {"cattelan-italia-889-prices.csv", "report.md", "swatches.zip"} <= uploaded
    dated = drive.folders["outputs/2026-11-02"]
    assert result.drive_folder == drive.folders[f"{dated}/cattelan-italia-889"]
    published = json.loads((tmp_path / "out" / "cattelan-italia-889" / "published.json").read_text())
    assert published == {"folder": result.drive_folder, "date": "2026-11-02"}


def test_second_run_reports_only_what_changed(tmp_path) -> None:
    run(drive_with(PDF, MAY), tmp_path, False)
    prices = tmp_path / "out" / "cattelan-italia-889" / "csv" / "cattelan-italia-889-prices.csv"
    with prices.open(newline="") as handle:
        before = list(csv.DictReader(handle))
    # pretend the last published run had a lower price for one combination
    before[0]["price"] = str(int(before[0]["price"]) - 100)
    with prices.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["code", "combo", "price"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(before)
    (result,) = run(drive_with(PDF, MAY), tmp_path)
    assert result.changes is not None
    (change,) = result.changes.changed
    assert change.new - change.old == 100
    changed = tmp_path / "out" / "cattelan-italia-889" / "cattelan-italia-889-prices-changed.csv"
    with changed.open(newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 1


def test_inactive_products_are_not_run(tmp_path) -> None:
    drive = drive_with(PDF, MAY)
    drive.tabs["Products"] = [HEADER, ["no", *RICHARD[1:]]]
    assert run(drive, tmp_path) == []


def test_brands_without_a_drive_folder_are_reported_not_guessed(tmp_path) -> None:
    drive = drive_with(PDF, MAY)
    drive.tabs["Products"] = [HEADER, [*RICHARD[:2], "unknown-brand", *RICHARD[3:]]]
    (result,) = run(drive, tmp_path)
    assert result.error and "unknown-brand" in result.error


def test_a_supplier_folder_is_found_by_name_under_price_lists(tmp_path) -> None:
    drive = drive_with(PDF, MAY)
    del drive.folders["price-lists/Cattelan Italia"]
    (result,) = run(drive, tmp_path)
    assert result.error == (
        "no folder 'Price lists/Cattelan Italia' in Drive: create it and add the price list"
    )


def test_config_is_unchanged_by_runs() -> None:
    # the workflow must never rewrite brand configs (patterns pick the new file instead)
    data = yaml.safe_load((ROOT / "config" / "brands" / "cattelan-italia.yaml").read_text())
    assert data["price_list"]["match"] == "CATTELAN ITALIA p.list*.pdf"
