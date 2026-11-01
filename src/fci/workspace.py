"""The shared Google Drive workspace, reached through Composio with the app's own connections.

config/drive.yaml holds the folder, sheet and connected-account ids (none of them secret);
the Composio API key comes from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fci.drive import ComposioDrive


@dataclass(frozen=True)
class Workspace:
    root: str
    price_lists: str  # one subfolder per supplier, found by name (see Brand.drive_folder)
    outputs: str
    products_sheet: str
    composio: dict[str, Any]


def load_workspace(path: Path) -> Workspace:
    data = yaml.safe_load(path.read_text())
    return Workspace(
        data["root"], data["price_lists"], data["outputs"], data["products_sheet"], data["composio"]
    )


def connect(workspace: Workspace) -> ComposioDrive:
    """A Drive client on the app's Composio connections. Needs COMPOSIO_API_KEY."""
    if not os.environ.get("COMPOSIO_API_KEY"):
        raise RuntimeError("COMPOSIO_API_KEY is not set (add it to .env)")
    from composio import Composio  # imported here so the pipeline itself needs no Composio
    from composio.core.models._files import FileUploadable

    sdk = Composio()
    user, accounts = workspace.composio["user_id"], workspace.composio["accounts"]

    def execute(slug: str, arguments: dict[str, Any]) -> dict[str, Any]:
        toolkit = slug.split("_", 1)[0].lower()
        reply = sdk.tools.execute(
            slug,
            arguments,
            user_id=user,
            connected_account_id=accounts[toolkit],
            dangerously_skip_version_check=True,  # pinned slugs, checked by the live smoke test
        )
        return dict(reply)

    def stage(path: Path, slug: str) -> dict[str, Any]:
        """Hand one named file to Composio's storage; only paths the app chose are ever sent."""
        staged = FileUploadable.from_path(
            client=sdk.client, file=path, tool=slug, toolkit="googledrive", file_upload_allowlist=None
        )
        return staged.model_dump()

    return ComposioDrive(execute, stage)
