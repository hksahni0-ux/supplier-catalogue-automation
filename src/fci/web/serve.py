"""Wire the web app to the real services: Nemotron, the run outputs, Drive and Gmail."""

from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path
from typing import Any

from fci.assistant.agent import Assistant, NvidiaChat
from fci.assistant.catalogue import Catalogue
from fci.assistant.tools import Tools
from fci.content import select_backend
from fci.http import Http
from fci.web.app import Services, WebSettings, create_app
from fci.workflow import ProductRun, run_workspace
from fci.workspace import connect, load_workspace

SIGN_IN_EMAIL = """<p>Hello,</p>
<p>Use this link to sign in to the FCI Catalogue assistant. It works once and expires in 15 minutes.</p>
<p><a href="{link}">Sign in to FCI Catalogue</a></p>
<p>If you didn't ask for this, you can ignore this email.</p>"""


def build(root: Path, base_url: str) -> Any:
    secret = os.environ.get("FCI_SESSION_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("FCI_SESSION_SECRET must be set to a long random string (see .env.example)")
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY is not set")
    out_root, config = root / "output", root / "config"
    workspace = load_workspace(config / "drive.yaml")
    drive = connect(workspace)
    tools = Tools(Catalogue(out_root, config))
    assistant = Assistant(NvidiaChat(key), tools)
    sku_cache: dict[str, Any] = {"at": 0.0, "skus": set()}

    def known_skus() -> set[str]:
        if time.time() - sku_cache["at"] > 60:
            rows = drive.read_tab(workspace.products_sheet, "Products")
            header = rows[0] if rows else []
            column = header.index("sku") if "sku" in header else 1
            sku_cache["skus"] = {r[column].strip() for r in rows[1:] if len(r) > column and r[column].strip()}
            sku_cache["at"] = time.time()
        skus: set[str] = sku_cache["skus"]
        return skus

    def products() -> list[dict[str, Any]]:
        listed = tools.list_products()
        for item in listed:
            item["drive"] = tools.get_drive_link(item["sku"]).get("url")
        return listed

    def runner(skus: list[str], publish: bool, log: Any) -> list[ProductRun]:
        log(f"Syncing price lists from Drive and running {len(skus)} product(s)…")
        results = run_workspace(
            drive,
            workspace,
            inputs=root / ".workspace" / "inputs",
            config=config,
            templates=root / "templates",
            out_root=out_root,
            http=Http(root / ".cache" / "http"),
            client=select_backend(),
            publish=publish,
            date=date.today().isoformat(),
            only=set(skus),
        )
        log("Finished." + (" Results saved to Drive." if publish else ""))
        return results

    def send_link(email: str, link: str) -> None:
        if os.environ.get("FCI_DEV_LINKS") == "1":
            print(f"\n[dev] sign-in link for {email}:\n{link}\n", flush=True)
            return
        reply = drive._execute(  # same Composio session; the gmail connection is picked by slug
            "GMAIL_SEND_EMAIL",
            {"recipient_email": email, "subject": "Your FCI Catalogue sign-in link",
             "body": SIGN_IN_EMAIL.format(link=link), "is_html": True},
        )  # fmt: skip
        if not reply.get("successful"):
            raise ConnectionError(f"could not send the sign-in email: {reply.get('error')}")

    operators = {e.strip().lower() for e in os.environ.get("FCI_OPERATORS", "").split(",") if e.strip()}
    settings = WebSettings(secret=secret, base_url=base_url, operators=operators or "any")
    services = Services(
        assistant=assistant.reply,
        products=products,
        review_items=tools.get_review_items,
        runner=runner,
        send_link=send_link,
        known_skus=known_skus,
    )
    return create_app(settings, services)
