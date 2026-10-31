"""Run report: what was produced, from which sources, and everything a person should check."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fci.jobs import Job
    from fci.pipeline import RunResult

ORDER = {"error": 0, "warning": 1, "info": 2}
JOB_FIELDS = ["brand", "model", "supplier_name", "product_type", "category_code", "sku", "supplier_url"]


def _summary(result: RunResult, job: Job, copy_source: str) -> dict[str, Any]:
    record = result.record
    options = record.options
    kept = [m for m in result.images if m["status"] == "kept"]
    combos = options.combinations
    return {
        "product": record.naming.name,
        "sku": record.sku,
        "generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "base_price": record.base_price if combos else None,
        "price_range": [min(combos.values()), max(combos.values())] if combos else None,
        "combinations": len(combos),
        "attributes": {a.name: len(a.options) for a in options.attributes},
        "images_kept": len(kept),
        "images_skipped": len(result.images) - len(kept),
        "swatches": result.swatches,
        "copy_source": copy_source,
        "manual_inputs": {k: getattr(job, k) for k in JOB_FIELDS},
        "flags": Counter(f.severity for f in record.flags),
        "sources": result.sources,
        "csv_files": {k: str(p.relative_to(result.out_dir)) for k, p in result.csvs.items()},
    }


def write_report(result: RunResult, job: Job, copy_source: str) -> None:
    summary = _summary(result, job, copy_source)
    flags = sorted(result.record.flags, key=lambda f: (ORDER[f.severity], f.field))
    payload = {**summary, "flags": [f.__dict__ for f in flags], "images": result.images}
    (result.out_dir / "report.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    lines = [
        f"# {summary['product']} ({summary['sku']})",
        "",
        f"Generated {summary['generated']}.",
        "",
        "## Output",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Base price (cheapest combination) | {summary['base_price']} |",
        f"| Price range | {summary['price_range']} |",
        f"| Price combinations | {summary['combinations']} |",
        *[f"| Attribute: {name} | {count} options |" for name, count in summary["attributes"].items()],
        f"| Product images | {summary['images_kept']} kept, {summary['images_skipped']} skipped |",
        *[f"| Swatches {kind} | {count} |" for kind, count in summary["swatches"].items()],
        f"| Description source | {copy_source} |",
        "",
        "## What a person supplied",
        "",
        "Only the job file. Every other value was extracted, derived or flagged by the pipeline.",
        "",
        *[f"- `{k}`: {v}" for k, v in summary["manual_inputs"].items()],
        "",
        "## Sources",
        "",
        *[f"- {s}" for s in summary["sources"]],
        "",
        f"## Flags ({len(flags)})",
        "",
        "| Severity | Field | Message | Source |",
        "|---|---|---|---|",
        *[f"| {f.severity} | {f.field} | {f.message.replace('|', '/')} | {f.source} |" for f in flags],
        "",
        "## Images",
        "",
        "Output pixels are source pixels (no resampling). Fidelity is PSNR against the source;",
        "40 dB and above is visually lossless. Untouched supplier files are in `originals/`.",
        "",
        "| Status | File | Size | Source size | KB | Fidelity (dB) | Source |",
        "|---|---|---|---|---|---|---|",
        *[
            f"| {m['status']} | {m.get('file', '')} | {m.get('size', '')} | {m.get('source_size', '')} "
            f"| {int(m['bytes']) // 1024 if m.get('bytes') else ''} | {m.get('fidelity_db', '')} "
            f"| {m['source']} |"
            for m in result.images
        ],
        "",
    ]
    (result.out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
