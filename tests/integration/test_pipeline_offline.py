"""Both jobs end to end, offline: saved pages, generated images, fixture price lists."""

import csv
import json
import shutil
from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
import yaml
from PIL import Image, ImageDraw

from fci.pipeline import run_job

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def jpeg(seed: int, cutout: bool = False) -> bytes:
    image = Image.new("RGB", (1400, 900), "white" if cutout else (40 + seed * 20, 60, 90))
    ImageDraw.Draw(image).ellipse((200 + seed * 30, 150, 1100, 750), fill=(150, 90 + seed * 10, 60))
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


def pdf_sheet() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "BERTE' technical sheet")
    page.draw_rect(pymupdf.Rect(72, 100, 400, 300))
    return document.tobytes()


class FakeHttp:
    def __init__(self) -> None:
        self.pages = {
            "https://www.cattelanitalia.com/en/products/C742E2EA-1F88-45F9-B990-EAE58E5347CF?c=30": (
                FIXTURES / "cattelan_richard.html"
            ).read_bytes(),
            "https://francoferri.it/en/berte/": (FIXTURES / "francoferri_berte.html").read_bytes(),
            "https://www.fcilondon.co.uk/products/burt-corner-sofa-by-fiera-collection.html": (
                FIXTURES / "fci_burt.html"
            ).read_bytes(),
            "https://francoferri.it/pdf/berte.pdf": pdf_sheet(),
        }
        self.requested: list[str] = []

    def get(self, url: str) -> bytes:
        self.requested.append(url)
        if url in self.pages:
            return self.pages[url]
        if "/wp-content/uploads/" in url or "/multimedia/" in url or "colorizoom" in url:
            return jpeg(len(self.requested) % 7, cutout=url.endswith("Berte2.jpg"))
        raise ConnectionError(f"unexpected URL in test: {url}")

    def post_json(self, url: str, data: dict) -> dict:
        return json.loads((FIXTURES / f"cattelan_finishes_{data['idCategory']}.json").read_text())

    def exists(self, url: str) -> bool:
        return False


@pytest.fixture
def workspace(tmp_path: Path) -> dict[str, Path]:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    shutil.copy(FIXTURES / "cattelan_beds.pdf", inputs / "CATTELAN ITALIA p.list 05-26 EUR Vat excl.pdf")
    shutil.copy(FIXTURES / "franco_ferri_berte.xlsx", inputs / "ff-prices.xlsx")
    shutil.copy(FIXTURES / "franco_ferri_swatches.xlsx", inputs / "ff-swatches.xlsx")
    config = tmp_path / "config"
    shutil.copytree(ROOT / "config", config)
    fiera = config / "brands" / "fiera-collection.yaml"
    data = yaml.safe_load(fiera.read_text())
    data["price_list"]["file"] = "ff-prices.xlsx"
    data["swatches"]["file"] = "ff-swatches.xlsx"
    fiera.write_text(yaml.safe_dump(data))
    return {"inputs": inputs, "config": config, "out": tmp_path / "out"}


def run(job: str, ws: dict[str, Path]):
    return run_job(
        ROOT / "jobs" / job,
        inputs=ws["inputs"],
        config=ws["config"],
        templates=ROOT / "templates",
        out_root=ws["out"],
        http=FakeHttp(),
        client=None,
    )


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_richard_end_to_end(workspace) -> None:
    result = run("richard-double-bed.yaml", workspace)
    product = read(result.csvs["product"])[0]
    assert product["price"] == "4121"
    assert product["url"] == "/richard-double-bed-by-cattelan-italia.html"
    assert len(read(result.csvs["prices"])) == 2340
    images = read(result.csvs["images"])
    assert len(images) == result.record.image_count >= 2
    for row in images:
        file = result.out_dir / "images" / row["name"].lstrip("/")
        width, height = Image.open(file).size
        assert width == height >= 900  # square, native resolution (generated sources are 1400x900)
    photos = [m for m in result.images if m.get("fidelity_db")]
    assert photos and all(float(m["fidelity_db"]) >= 40 for m in photos)
    assert (result.out_dir / "originals" / images[0]["name"].lstrip("/")).exists()
    swatch_rows = [r for r in read(result.csvs["attributes"]) if r["display"] == "2"]
    for row in swatch_rows[:20]:
        assert (result.out_dir / "swatches" / row["image"].removeprefix("/product-images/")).exists()
    assert (result.out_dir / "report.md").exists()
    assert not [f for f in result.record.flags if f.severity == "error"]


def test_burt_end_to_end(workspace) -> None:
    result = run("burt-corner-sofa.yaml", workspace)
    product = read(result.csvs["product"])[0]
    assert product["price"] == "1650"
    assert product["brand"] == "Naustro Fiera Collection"
    assert product["url"] == "/burt-corner-sofa-by-fiera-collection.html"
    attributes = {r["attribute"] for r in read(result.csvs["attributes"])}
    assert attributes == {"Size", "Cover", "Orientation", "Feet", "Contrast Stitching", "Comfort"}
    prices = read(result.csvs["prices"])
    assert all(" [+] " in p["combo"] for p in prices)
    reused = [r for r in read(result.csvs["attributes"]) if r["image"].startswith("/product-images/fiera")]
    assert len(reused) > 100
    report = json.loads((result.out_dir / "report.json").read_text())
    assert report["base_price"] == 1650
    # the supplier's sheet carries Franco Ferri's logo and address; FCI sells this as Naustro Fiera
    assert not any("technical" in m["source"] for m in report["images"])
    assert any(f["field"] == "images" and "branding" in f["message"] for f in report["flags"])
    assert any(f["field"] == "catcode" for f in report["flags"])
    # every web call is listed, including FCI's page used for swatch reuse
    fci_page = "https://www.fcilondon.co.uk/products/burt-corner-sofa-by-fiera-collection.html"
    assert fci_page in report["sources"]
