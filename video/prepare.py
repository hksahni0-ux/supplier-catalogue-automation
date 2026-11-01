"""Collect every real asset and number the video shows, from the supplier files and the pipeline output.

    uv run python video/prepare.py      # writes video/assets/ and video/assets/data.json

Nothing in the video is typed in by hand: prices, counts, text and images all come from here.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pymupdf
import requests
from PIL import Image

from fci.adapters.franco_ferri_xlsm import FrancoFerriPriceList

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
ASSETS = ROOT / "video" / "assets"
PDF = ROOT / "supplier_inputs" / "CATTELAN ITALIA p.list 05-26 EUR Vat excl.pdf"
XLSM = next((ROOT / "supplier_inputs").glob("*Franco Ferri GBP*.xlsm"))
SKUS = {"richard": "cattelan-italia-889", "burt": "fiera-collection-043", "thomas": "cattelan-italia-806"}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def csv_of(key: str, kind: str) -> Path:
    sku = SKUS[key]
    return OUT / sku / "csv" / f"{sku}-{kind}.csv"


def save_small(src: Path, dest: Path, side: int) -> None:
    image = Image.open(src).convert("RGB")
    image.thumbnail((side, side), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, quality=90)


def product_images() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for key, sku in SKUS.items():
        files = sorted((OUT / sku / "images").glob("*/*.jpg"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
        found[key] = []
        for path in files:
            name = f"products/{key}-{path.stem.rsplit('-', 1)[1]}.jpg"
            save_small(path, ASSETS / name, 1400)
            found[key].append(name)
    return found


def price_page() -> dict[str, object]:
    """p.358 rendered for the screen, with the box of every printed price."""
    page = pymupdf.open(PDF)[357]
    scale = 1400 / page.rect.height
    page.get_pixmap(matrix=pymupdf.Matrix(scale, scale)).save(ASSETS / "p358.png")
    cells = [
        {
            "x": w[0] / page.rect.width,
            "y": w[1] / page.rect.height,
            "w": (w[2] - w[0]) / page.rect.width,
            "h": (w[3] - w[1]) / page.rect.height,
            "text": w[4],
        }
        for w in page.get_text("words")
        if re.fullmatch(r"\d\.\d{3}", w[4])
    ]
    return {"aspect": page.rect.width / page.rect.height, "cells": cells, "page_count": len(page.parent)}


def burt_modules() -> list[dict[str, object]]:
    entry = FrancoFerriPriceList(XLSM).find("BERTE' FF")
    return [
        {
            "code": code,
            "description": entry.modules[code].description,
            "cat70": entry.modules[code].prices["Cat.70"],
        }
        for code in ("0168", "0125", "0401", "0145")
    ] + [{"source_row": entry.source_row}]


def swatches() -> dict[str, list[str]]:
    root = OUT / SKUS["richard"] / "swatches" / "cattelan-italia" / "swatches"
    ecp = sorted((root / "synthetic-leather").glob("ecp*.jpg"))
    mixed = [
        p
        for folder in ("fabrics", "soft-leather", "sofa-fabrics", "sofa-leathers", "micro-nubuck")
        for p in sorted((root / folder).glob("*.jpg"))[:8]
    ]
    result: dict[str, list[str]] = {"ecp": [], "richard": [], "burt": [], "burt_missing": []}
    for kind, paths in (("ecp", ecp), ("richard", ecp[:6] + mixed)):
        for path in paths:
            name = f"swatches/richard/{path.parent.name}-{path.name}"
            save_small(path, ASSETS / name, 240)
            result[kind].append(name)
    cover_rows = [r for r in rows(csv_of("burt", "attributes")) if r["attribute"] == "Cover"]
    planned = {r["name"] for r in cover_rows}
    report = json.loads((OUT / SKUS["burt"] / "report.json").read_text())
    needed = set()
    for flag in report["flags"]:
        if flag["field"] == "swatches":
            needed |= {n for n in planned if n in flag["message"]}
    for row in cover_rows:
        if row["name"] in needed:
            result["burt_missing"].append(row["name"])
            continue
        if len(result["burt"]) >= 30:
            continue
        dest = ASSETS / "swatches" / "burt" / Path(row["image"]).name
        if not dest.exists():
            reply = requests.get(f"https://www.fcilondon.co.uk/site-assets{row['image']}", timeout=30)
            if reply.status_code != 200:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(reply.content)
            save_small(dest, dest, 240)
        result["burt"].append(f"swatches/burt/{dest.name}")
    return result


def fidelity_pair() -> dict[str, object]:
    """The same detail from the supplier's original and from the processed file, for a zoom comparison."""
    name = "richard-double-bed-by-cattelan-italia-2.jpg"
    original = np.asarray(
        Image.open(OUT / SKUS["richard"] / "originals" / "cattelan-italia" / name).convert("L"),
        dtype=np.float32,
    )
    processed = Image.open(OUT / SKUS["richard"] / "images" / "cattelan-italia" / name).convert("RGB")
    small = np.asarray(processed.convert("L"), dtype=np.float32)
    dy_range = range(0, original.shape[0] - small.shape[0] + 1, 8)
    dx_range = range(0, original.shape[1] - small.shape[1] + 1, 8)
    probe = small[::16, ::16]
    best = min(
        (
            float(
                np.mean(
                    np.abs(original[dy : dy + small.shape[0] : 16, dx : dx + small.shape[1] : 16] - probe)
                )
            ),
            dx,
            dy,
        )
        for dy in dy_range
        for dx in dx_range
    )
    _, dx, dy = best
    box = (1300, 1480, 1540, 1660)  # headboard fabric, in processed-image pixels
    source = Image.open(OUT / SKUS["richard"] / "originals" / "cattelan-italia" / name).convert("RGB")
    source.crop((box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)).save(ASSETS / "zoom-original.png")
    processed.crop(box).save(ASSETS / "zoom-processed.png")
    report = json.loads((OUT / SKUS["richard"] / "report.json").read_text())
    entry = next(m for m in report["images"] if m.get("file", "").endswith(name))
    save_small(OUT / SKUS["richard"] / "images" / "cattelan-italia" / name, ASSETS / "zoom-full.jpg", 1200)
    save_small(
        OUT / SKUS["richard"] / "originals" / "cattelan-italia" / name, ASSETS / "zoom-source.jpg", 1600
    )
    return {
        "offset": [dx, dy],
        "box": box,
        "fidelity_db": entry["fidelity_db"],
        "size": entry["size"],
        "source_size": entry["source_size"],
    }


def contacts() -> list[dict[str, str]]:
    """Contact cards (label, handle, colour, icon) from the creator's standard outro, same details."""
    source = Path.home() / "Documents" / "B2B_CRM" / "marketing" / "demo-video" / "video.html"
    html = source.read_text()
    cards = json.loads(re.search(r'<script[^>]*id="contacts"[^>]*>(.*?)</script>', html, re.S).group(1))  # type: ignore[union-attr]
    handles = dict(
        re.findall(
            r"'?([A-Za-z ()]+)'?: '([^']+)'",
            re.search(r"const SHORT = \{(.*?)\};", (source.parent / "common.js").read_text()).group(1),
        )
    )  # type: ignore[union-attr]  # noqa: E501
    handles = {k.strip(): v for k, v in handles.items()}
    return [
        {"label": c["label"], "handle": handles[c["label"]], "bg": c["bg"], "svg": c["svg"]} for c in cards
    ]


def thomas() -> dict[str, object]:
    template = [r["name"] for r in rows(ROOT / "templates" / "attributes.csv") if r["attribute"] == "Size"]
    ours = [r["name"] for r in rows(csv_of("thomas", "attributes")) if r["attribute"] == "Size"]
    return {"fci_sizes": template, "our_sizes": ours}


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    creator = Path.home() / "Documents" / "B2B_CRM" / "marketing" / "demo-video" / "assets"
    (ASSETS / "creator").mkdir(exist_ok=True)
    for name in ("prateek.jpg", "qr-site.png"):  # the person's photo and website QR, not styling
        (ASSETS / "creator" / name).write_bytes((creator / name).read_bytes())
    reports = {k: json.loads((OUT / s / "report.json").read_text()) for k, s in SKUS.items()}
    details = {r["name"]: r["data"] for r in rows(csv_of("richard", "details"))}
    product = rows(csv_of("richard", "product-upload"))[0]
    grid = subprocess.run(
        ["uv", "run", "fci", "grid", str(csv_of("richard", "prices"))],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout
    tests = subprocess.run(
        ["uv", "run", "pytest", "-q", "--co"], capture_output=True, text=True, cwd=ROOT
    ).stdout
    data = {
        "products": {
            k: {
                "name": r["product"],
                "sku": r["sku"],
                "base_price": r["base_price"],
                "price_range": r["price_range"],
                "combinations": r["combinations"],
                "images": r["images_kept"],
                "swatches": r["swatches"],
                "fidelity": [float(m["fidelity_db"]) for m in r["images"] if m.get("fidelity_db")],
                "warnings": [f["message"] for f in r["flags"] if f["severity"] == "warning"],
            }
            for k, r in reports.items()
        },
        "images": product_images(),
        "page": price_page(),
        "burt_modules": burt_modules(),
        "swatches": swatches(),
        "zoom": fidelity_pair(),
        "thomas": thomas(),
        "copy": {"meta": product["description"], "short": details.get("SHORT-DESCRIPTION", "")},
        "run": (ASSETS / "run.txt").read_text(),
        "grid": grid,
        "price_rows": rows(csv_of("richard", "prices"))[:40],
        "tests": int(re.search(r"(\d+) tests collected", tests).group(1))  # type: ignore[union-attr]
        + sum(
            len(re.findall(r"^test\(", f.read_text(), re.M))
            for f in (ROOT / "web" / "src").glob("*.test.tsx")
        ),
        "contacts": contacts(),
        "drive": json.loads((ASSETS / "app" / "drive.json").read_text()),  # from capture_app.py
        "changes": {
            k: (OUT / s / "price-changes.md").read_text().splitlines()[2]
            for k, s in SKUS.items()
            if (OUT / s / "price-changes.md").exists()
        },
        "job": (ROOT / "jobs" / "richard-double-bed.yaml").read_text(),
        "burt_job": (ROOT / "jobs" / "burt-corner-sofa.yaml").read_text(),
    }
    (ASSETS / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(json.dumps({k: data[k] for k in ("tests", "zoom")}, indent=1))
    print("price cells on p.358:", len(data["page"]["cells"]))
    print("swatches:", {k: len(v) for k, v in data["swatches"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
