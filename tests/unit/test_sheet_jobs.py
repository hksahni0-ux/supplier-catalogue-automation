from pathlib import Path

import pytest

from fci.jobs import load_job
from fci.sheet_jobs import jobs_from_sheet

JOBS = Path(__file__).resolve().parents[2] / "jobs"
PRODUCTS = [
    ["active", "sku", "brand", "model", "supplier_name", "product_type", "category_code",
     "category_confirmed", "supplier_url", "fci_url", "notes"],
    ["yes", "fiera-collection-043", "fiera-collection", "Burt", "BERTE' FF", "Corner Sofa", "FUR-SEA-SOF",
     "no", "https://francoferri.it/en/berte/",
     "https://www.fcilondon.co.uk/products/burt-corner-sofa-by-fiera-collection.html", ""],
    ["yes", "cattelan-italia-889", "cattelan-italia", "Richard", "RICHARD", "Double Bed", "FUR-BED-DB", "yes",
     "https://www.cattelanitalia.com/en/products/C742E2EA-1F88-45F9-B990-EAE58E5347CF?c=30",
     "https://www.fcilondon.co.uk/products/richard-double-bed-by-cattelan-italia.html", ""],
    ["no", "cattelan-italia-806", "cattelan-italia", "Thomas", "THOMAS", "Double Bed", "FUR-BED-DB", "yes",
     "https://example.com", "", "paused"],
]  # fmt: skip
LAYOUTS = [
    ["sku", "layout", "modules"],
    ["fiera-collection-043", "Corner - W.305 X D.305 X H.95 cm", "0168, 0125, 0401, 0125, 0169"],
    ["fiera-collection-043", "Corner with Terminal - W.305 X D.281 X H.95 cm", "0168, 0125, 0401, 0145"],
    ["fiera-collection-043", "Maxi Chaise - W.324 X D.161 X H.95 cm", "0172, A138, 0285"],
    ["fiera-collection-043", "Chaise - W.300 X D.161 X H.95 cm", "0246, 0125, 0169"],
]
OPTIONS = [
    ["sku", "option", "values"],
    ["fiera-collection-043", "mirror_pairs", "0168/0169, 0171/0172, 0285/0286, 0245/0246, 0145/0146"],
    ["fiera-collection-043", "feet", "38, 42, 47, 71"],
    ["fiera-collection-043", "dropdown:Comfort", "Soft, Hard"],
]


def comparable(job):
    return (job.brand, job.model, job.supplier_name, job.product_type, job.category_code, job.sku,
            job.supplier_url, job.category_confirmed, job.options)  # fmt: skip


def test_sheet_rows_give_the_same_jobs_as_the_yaml_files() -> None:
    jobs = {j.sku: j for j in jobs_from_sheet(PRODUCTS, LAYOUTS, OPTIONS)}
    assert comparable(jobs["fiera-collection-043"]) == comparable(load_job(JOBS / "burt-corner-sofa.yaml"))
    assert comparable(jobs["cattelan-italia-889"]) == comparable(load_job(JOBS / "richard-double-bed.yaml"))


def test_inactive_rows_are_skipped() -> None:
    assert "cattelan-italia-806" not in {j.sku for j in jobs_from_sheet(PRODUCTS, LAYOUTS, OPTIONS)}


def test_short_rows_from_the_sheets_api_are_padded() -> None:
    # the Sheets API drops trailing empty cells, so rows can be shorter than the header
    rows = [PRODUCTS[0], PRODUCTS[2][:9]]
    (job,) = jobs_from_sheet(rows, [], [])
    assert job.options == {}


def test_a_missing_required_field_names_the_row() -> None:
    rows = [PRODUCTS[0], ["yes", "cattelan-italia-889", "cattelan-italia", "", "RICHARD"]]
    with pytest.raises(ValueError, match=r"Products row 2.*model"):
        jobs_from_sheet(rows, [], [])
