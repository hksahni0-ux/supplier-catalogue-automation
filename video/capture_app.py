"""Screenshots of the real web app and the real Drive workspace, for the video's app scenes.

    FCI_DEV_LINKS=1 uv run fci serve --port 8000 > server.log &   # links go to the log
    uv run python video/capture_app.py server.log

Every answer on screen is the live assistant's; the Confirm step really re-runs Thomas and
publishes it to Drive. Drive and Sheet contents are read through the app's own Composio connection.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from fci.cli import load_env
from fci.workspace import connect, load_workspace

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "video" / "assets" / "app"
APP = "http://127.0.0.1:8000"
QUESTION = "What does Richard size D cost in glove leather?"
RUN = "Re-run Thomas and save it to Drive"


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"))
    print("captured", name)


def capture_app(log: Path) -> None:
    with sync_playwright() as play:
        browser = play.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.goto(APP)
        page.get_by_label("Work email").fill("sprateek11294@gmail.com")
        page.get_by_role("button", name="Email me a sign-in link").click()
        page.get_by_text("Check your inbox").wait_for()
        shot(page, "login")
        link = re.findall(r"http://localhost:8000/auth\?token=\S+", log.read_text())[-1]
        page.goto(link.replace("localhost", "127.0.0.1"))
        page.get_by_text("Richard Double Bed").first.wait_for()
        time.sleep(0.8)  # fonts
        shot(page, "welcome")
        box = page.get_by_role("textbox", name="Ask the assistant")
        box.fill(QUESTION)
        shot(page, "question")
        page.keyboard.press("Enter")
        page.get_by_text("Checked against the data").first.wait_for(timeout=180000)
        shot(page, "answer")
        box.fill(RUN)
        page.keyboard.press("Enter")
        page.get_by_role("button", name="Confirm").wait_for(timeout=180000)
        shot(page, "proposal")
        page.get_by_role("button", name="Confirm").click()
        page.locator(".pill.running, .pill.queued, .pill.done").first.wait_for(timeout=30000)
        shot(page, "running")
        page.locator(".pill.done").wait_for(timeout=420000)
        page.locator(".run-card").scroll_into_view_if_needed()
        time.sleep(0.5)
        shot(page, "done")
        browser.close()


def capture_drive() -> None:
    load_env(ROOT / ".env")
    workspace = load_workspace(ROOT / "config" / "drive.yaml")
    drive = connect(workspace)

    def tree(folder: str, depth: int = 0) -> list[dict[str, object]]:
        items = []
        for f in sorted(drive._find(f"'{folder}' in parents and trashed = false"), key=lambda f: f["name"]):
            is_folder = str(f.get("mimeType", "")).endswith("folder")
            items.append(
                {"name": f["name"], "folder": is_folder, "size": int(f.get("size") or 0), "depth": depth}
            )
            if is_folder and depth < 2:
                items += tree(f["id"], depth + 1)
        return items

    data = {
        "tree": tree(workspace.root),
        "sheet": {t: drive.read_tab(workspace.products_sheet, t) for t in ("Products", "Layouts", "Options")},
    }
    (SHOTS / "drive.json").write_text(json.dumps(data, indent=1))
    print("captured drive tree", len(data["tree"]), "entries")


if __name__ == "__main__":
    SHOTS.mkdir(parents=True, exist_ok=True)
    capture_app(Path(sys.argv[1]))
    capture_drive()
