"""Command line: `fci run jobs/richard-double-bed.yaml`, `fci run jobs/`, or `fci grid <prices.csv>`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from fci.content import select_backend
from fci.grid import format_grid, read_grid
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
    ws = sub.add_parser("workspace", help="run the products in the Google Drive workspace (Products sheet)")
    ws.add_argument("--only", nargs="*", help="SKUs to run (default: every active product)")
    ws.add_argument("--publish", action="store_true", help="save results to Drive Outputs/<date>/<sku>/")
    ws.add_argument("--no-images", action="store_true")
    ws.add_argument("--no-ai", action="store_true")
    ws.add_argument("--inputs", type=Path, default=ROOT / ".workspace" / "inputs")
    ws.add_argument("--out", type=Path, default=ROOT / "output")
    serve = sub.add_parser("serve", help="start the catalogue web app")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--base-url", default=None, help="public address used in sign-in links")
    ask = sub.add_parser("ask", help="ask the catalogue assistant a question about the run outputs")
    ask.add_argument("question")
    ask.add_argument("--out", type=Path, default=ROOT / "output")
    grid = sub.add_parser("grid", help="collapse a prices CSV to one price per size and cover group")
    grid.add_argument("prices_csv", type=Path)
    args = parser.parse_args(argv)
    if args.command == "grid":
        print(format_grid(read_grid(args.prices_csv)))
        return 0
    if args.command == "serve":
        load_env(ROOT / ".env")
        import uvicorn

        from fci.web.serve import build

        base_url = args.base_url or f"http://localhost:{args.port}"
        uvicorn.run(build(ROOT, base_url), host="127.0.0.1", port=args.port)
        return 0
    if args.command == "ask":
        load_env(ROOT / ".env")
        return ask_command(args)
    if args.command == "workspace":
        load_env(ROOT / ".env")
        return run_workspace_command(args)

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


def ask_command(args: argparse.Namespace) -> int:
    from fci.assistant.agent import Assistant, NvidiaChat
    from fci.assistant.catalogue import Catalogue
    from fci.assistant.tools import Tools

    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        print("NVIDIA_API_KEY is not set (add it to .env)")
        return 1
    tools = Tools(Catalogue(args.out, ROOT / "config"))
    reply = Assistant(NvidiaChat(key), tools).reply([{"role": "user", "content": args.question}])
    print(reply.text)
    print(f"\n[tools: {', '.join(reply.tools_used) or 'none'} | verified: {reply.verified}]")
    for proposal in reply.proposals:
        print(f"[proposed, not run: {proposal}]")
    return 0


def run_workspace_command(args: argparse.Namespace) -> int:
    from datetime import date

    from fci.workflow import run_workspace
    from fci.workspace import connect, load_workspace

    workspace = load_workspace(ROOT / "config" / "drive.yaml")
    client = None if args.no_ai else select_backend()
    print(f"copy: {client.model if client else 'supplier text (no AI key)'}")
    runs = run_workspace(
        connect(workspace),
        workspace,
        inputs=args.inputs,
        config=ROOT / "config",
        templates=ROOT / "templates",
        out_root=args.out,
        http=Http(ROOT / ".cache" / "http"),
        client=client,
        publish=args.publish,
        date=date.today().isoformat(),
        images=not args.no_images,
        only=set(args.only) if args.only else None,
    )
    failures = 0
    for run in runs:
        print(f"\n== {run.sku}")
        if run.error:
            failures += 1
            print(f"   FAILED: {run.error}")
            continue
        flags = run.flags or {}
        print(f"   {run.name}: base price {run.base_price}, {run.combinations} combinations")
        counts = ", ".join(
            f"{flags.get(s, 0)} {s}{'s' if s != 'info' else ''}" for s in ("error", "warning", "info")
        )
        print(f"   flags: {counts}")
        print(f"   prices: {run.changes.summary() if run.changes else 'first run, nothing to compare'}")
        if run.drive_folder:
            print(f"   Drive: https://drive.google.com/drive/folders/{run.drive_folder}")
        failures += bool(flags.get("error"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
