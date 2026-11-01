"""Jobs from the Products Google Sheet, so staff add products in a sheet instead of YAML files.

Three tabs: Products (one row per product), Layouts (modular compositions) and Options
(extra choices such as feet finishes). Rows become exactly the jobs a YAML file would give.
"""

from __future__ import annotations

from typing import Any

from fci.jobs import Job, job_from_dict

Rows = list[list[str]]


def _records(rows: Rows) -> list[tuple[int, dict[str, str]]]:
    """(sheet row number, {header: cell}); the Sheets API drops trailing empty cells, so pad."""
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    return [
        (n, dict(zip(header, [str(c).strip() for c in row] + [""] * (len(header) - len(row)), strict=False)))
        for n, row in enumerate(rows[1:], start=2)
        if any(str(c).strip() for c in row)
    ]


def _split(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _extras(sku: str, layouts: Rows, options: Rows) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    rows = [r for _, r in _records(layouts) if r["sku"] == sku]
    found = [{"name": r["layout"], "modules": _split(r["modules"])} for r in rows]
    if found:
        extra["layouts"] = found
    for _, row in _records(options):
        if row["sku"] != sku:
            continue
        name, values = row["option"], row["values"]
        if name == "mirror_pairs":
            extra["mirror_pairs"] = [pair.split("/") for pair in _split(values)]
        elif name.startswith("dropdown:"):
            extra.setdefault("dropdowns", {})[name.removeprefix("dropdown:")] = _split(values)
        else:
            extra[name] = _split(values)
    return extra


def jobs_from_sheet(products: Rows, layouts: Rows, options: Rows) -> list[Job]:
    jobs = []
    for number, row in _records(products):
        if row.get("active", "yes").lower() not in ("yes", "y", "true", "1"):
            continue
        data: dict[str, Any] = {k: v for k, v in row.items() if k not in ("active", "notes", "fci_url") and v}
        data["category_confirmed"] = row.get("category_confirmed", "yes").lower() in ("yes", "y", "true", "1")
        if row.get("fci_url"):
            data["fci_url"] = row["fci_url"]
        data.update(_extras(row.get("sku", ""), layouts, options))
        jobs.append(job_from_dict(data, f"Products row {number}"))
    return jobs
