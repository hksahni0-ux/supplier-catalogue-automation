"""One run of the shared workspace: the same steps for the CLI, the web page and the scheduler.

1. read the Products sheet (Products, Layouts, Options tabs) into jobs;
2. mirror each supplier's folder in Price lists (found by name; only changed files download);
3. run every active product;
4. compare its prices with the previous run and write the rows to re-upload;
5. publish the results to Drive: Outputs/<date>/<sku>/.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fci.brands import load_brand
from fci.changes import Changes, compare_prices, write_changed_rows
from fci.drive import Drive, publish_outputs, sync_folder
from fci.http import Http
from fci.pipeline import run_job
from fci.sheet_jobs import jobs_from_sheet
from fci.workspace import Workspace


@dataclass
class ProductRun:
    sku: str
    name: str = ""
    base_price: int = 0
    combinations: int = 0
    flags: dict[str, int] | None = None
    changes: Changes | None = None
    drive_folder: str | None = None
    out_dir: Path | None = None
    error: str | None = None


def _rows(path: Path) -> list[dict[str, str]] | None:
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_changes(changes: Changes, new_rows: list[dict[str, str]], out: Path, sku: str) -> None:
    write_changed_rows(changes, new_rows, out / f"{sku}-prices-changed.csv")
    lines = [f"# Price changes for {sku}", "", changes.summary(), ""]
    if changes.changed:
        lines += ["| Option | Before | After | Change |", "|---|---:|---:|---:|"]
        lines += [f"| {c.combo} | {c.old} | {c.new} | {c.percent:+.1f}% |" for c in changes.changed]
    for title, combos in (("Added", changes.added), ("Removed", changes.removed)):
        if combos:
            lines += ["", f"## {title}", *[f"- {c}" for c in combos]]
    (out / "price-changes.md").write_text("\n".join(lines) + "\n")


def run_workspace(
    drive: Any,
    workspace: Workspace,
    *,
    inputs: Path,
    config: Path,
    templates: Path,
    out_root: Path,
    http: Http,
    client: Any,
    publish: bool,
    date: str,
    images: bool = True,
    only: set[str] | None = None,
) -> list[ProductRun]:
    tabs = {tab: drive.read_tab(workspace.products_sheet, tab) for tab in ("Products", "Layouts", "Options")}
    jobs = jobs_from_sheet(tabs["Products"], tabs["Layouts"], tabs["Options"])
    if only is not None:
        jobs = [j for j in jobs if j.sku in only]

    synced: dict[str, str | None] = {}
    for brand in sorted({j.brand for j in jobs}):
        try:
            sync_folder(drive, _price_list_folder(drive, workspace, config, brand), inputs)
            synced[brand] = None
        except (LookupError, ConnectionError, ValueError) as error:
            synced[brand] = str(error).strip("'\"")

    results = []
    for job in jobs:
        run = ProductRun(job.sku)
        results.append(run)
        if synced[job.brand]:
            run.error = synced[job.brand]
            continue
        prices = out_root / job.sku / "csv" / f"{job.sku}-prices.csv"
        previous = _rows(prices)
        try:
            result = run_job(
                job,
                inputs=inputs,
                config=config,
                templates=templates,
                out_root=out_root,
                http=http,
                client=client,
                images=images,
            )
        except (LookupError, ValueError, ConnectionError, FileNotFoundError) as error:
            run.error = f"{type(error).__name__}: {error}"
            continue
        record = result.record
        run.name, run.base_price = record.naming.name, record.base_price
        run.combinations, run.out_dir = len(record.options.combinations), result.out_dir
        run.flags = {s: sum(1 for f in record.flags if f.severity == s) for s in ("error", "warning", "info")}
        for stale in (result.out_dir / f"{job.sku}-prices-changed.csv", result.out_dir / "price-changes.md"):
            stale.unlink(missing_ok=True)
        if previous is not None:
            current = _rows(prices) or []
            run.changes = compare_prices(previous, current)
            _write_changes(run.changes, current, result.out_dir, job.sku)
        if publish:
            run.drive_folder = publish_outputs(drive, result.out_dir, workspace.outputs, date)
            record_path = result.out_dir / "published.json"
            record_path.write_text(json.dumps({"folder": run.drive_folder, "date": date}))
    return results


def _price_list_folder(drive: Drive, workspace: Workspace, config: Path, brand: str) -> str:
    """A supplier's subfolder of Price lists, so a new supplier needs a folder, not a config id."""
    path = config / "brands" / f"{brand}.yaml"
    if not path.exists():
        raise LookupError(f"no supplier config for brand '{brand}' (config/brands/{brand}.yaml)")
    name = load_brand(path).drive_folder
    folder = drive.find_folder(name, workspace.price_lists)
    if folder is None:
        raise LookupError(f"no folder 'Price lists/{name}' in Drive: create it and add the price list")
    return folder
