"""Command line: `fci run jobs/richard-double-bed.yaml` or `fci run jobs/`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from fci.content import select_backend
from fci.http import Http
from fci.pipeline import run_job

ROOT = Path(__file__).resolve().parents[2]


def load_env(path: Path) -> None:
    """Read KEY=VALUE lines from a .env file; variables already set in the shell win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if value.strip():
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fci", description="Supplier files -> FCI import CSVs and images")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="process one job file, or every job in a folder")
    run.add_argument("jobs", type=Path)
    run.add_argument("--inputs", type=Path, default=ROOT / "supplier_inputs")
    run.add_argument("--out", type=Path, default=ROOT / "output")
    run.add_argument("--config", type=Path, default=ROOT / "config")
    run.add_argument("--templates", type=Path, default=ROOT / "templates")
    run.add_argument("--cache", type=Path, default=ROOT / ".cache" / "http")
    run.add_argument("--offline", action="store_true", help="use only cached web responses")
    run.add_argument("--no-images", action="store_true", help="skip image and swatch processing")
    run.add_argument("--no-ai", action="store_true", help="use supplier wording instead of Nemotron")
    args = parser.parse_args(argv)

    load_env(ROOT / ".env")
    job_files = sorted(args.jobs.glob("*.yaml")) if args.jobs.is_dir() else [args.jobs]
    http = Http(args.cache, offline=args.offline)
    client = None if args.no_ai else select_backend()
    print(f"copy: {client.model if client else 'supplier text (no AI key)'}")
    failures = 0
    for job_file in job_files:
        print(f"\n== {job_file.name}")
        try:
            result = run_job(
                job_file,
                inputs=args.inputs,
                config=args.config,
                templates=args.templates,
                out_root=args.out,
                http=http,
                client=client,
                images=not args.no_images,
            )
        except (LookupError, ValueError, ConnectionError, FileNotFoundError) as error:
            failures += 1
            print(f"   FAILED: {error}")
            continue
        record = result.record
        counts = {s: sum(1 for f in record.flags if f.severity == s) for s in ("error", "warning", "info")}
        print(
            f"   {record.naming.name} ({record.sku}) base price {record.base_price}, "
            f"{len(record.options.combinations)} combinations, {record.image_count} images"
        )
        print(f"   flags: {counts['error']} errors, {counts['warning']} warnings, {counts['info']} info")
        print(f"   output: {result.out_dir}  (see report.md)")
        failures += counts["error"] > 0
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
