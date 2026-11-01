"""Google Drive as the shared workspace: price lists in, results out.

`sync_folder` mirrors a Drive folder into a local one (only changed files are downloaded,
and each keeps its Drive date so "newest price list" means the same thing on both sides).
`publish_outputs` copies a product's results to Outputs/<date>/<sku>/. Drive is reached
through Composio (`ComposioDrive`); tests use an in-memory fake with the same methods.
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import requests

SIMPLE_UPLOAD_LIMIT = 5 * 1024 * 1024  # Composio's plain upload; larger files go resumable
LOCAL_ONLY = {"originals"}  # untouched supplier images stay in the local archive
ZIPPED = {"swatches"}  # hundreds of small files: one zip is quicker to upload and to hand over
FOLDER = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    size: int
    md5: str
    modified: str  # RFC 3339, as Drive reports it


class Drive(Protocol):
    def list_folder(self, folder_id: str) -> list[DriveFile]: ...
    def download(self, file_id: str, dest: Path) -> None: ...
    def find_folder(self, name: str, parent_id: str) -> str | None: ...
    def ensure_folder(self, name: str, parent_id: str) -> str: ...
    def upload(self, path: Path, folder_id: str) -> str: ...
    def replace(self, file_id: str, path: Path) -> None: ...


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sync_folder(drive: Drive, folder_id: str, local: Path) -> list[Path]:
    local.mkdir(parents=True, exist_ok=True)
    paths = []
    for item in drive.list_folder(folder_id):
        target = local / item.name
        if Path(item.name).name != item.name or item.name in ("", ".", ".."):
            raise ValueError(f"unsafe file name from Drive: {item.name!r}")
        if not (target.exists() and _md5(target) == item.md5):
            drive.download(item.id, target)
        stamp = datetime.fromisoformat(item.modified.replace("Z", "+00:00")).timestamp()
        os.utime(target, (stamp, stamp))
        paths.append(target)
    return paths


def publish_outputs(drive: Drive, out_dir: Path, outputs_folder: str, date: str) -> str:
    """Upload one product's results to Outputs/<date>/<sku>/ and return that folder's id."""
    day = drive.ensure_folder(date, outputs_folder)
    root = drive.ensure_folder(out_dir.name, day)
    folders = {Path("."): root}
    existing: dict[str, dict[str, DriveFile]] = {}

    def put(path: Path, folder_id: str) -> None:
        """Re-publishing the same day replaces changed files and skips identical ones (no duplicates)."""
        if folder_id not in existing:
            existing[folder_id] = {f.name: f for f in drive.list_folder(folder_id)}
        current = existing[folder_id].get(path.name)
        if current is None:
            drive.upload(path, folder_id)
        elif current.md5 != _md5(path):
            drive.replace(current.id, path)

    def folder_for(relative: Path) -> str:
        if relative not in folders:
            folders[relative] = drive.ensure_folder(relative.name, folder_for(relative.parent))
        return folders[relative]

    for path in sorted(out_dir.rglob("*")):
        relative = path.relative_to(out_dir)
        top = relative.parts[0]
        if top in LOCAL_ONLY or top in ZIPPED or not path.is_file() or path.name.startswith("."):
            continue
        put(path, folder_for(relative.parent))
    for name in ZIPPED:
        source = out_dir / name
        if source.is_dir():
            archive = out_dir.parent / f".{out_dir.name}-{name}.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:  # JPEGs don't compress
                for file in sorted(source.rglob("*")):
                    if file.is_file():
                        bundle.write(file, file.relative_to(source))
            named = archive.with_name(f"{name}.zip")
            archive.rename(named)
            put(named, root)
            named.unlink()
    return root


# ---------------------------------------------------------------- Composio
Execute = Callable[[str, dict[str, Any]], dict[str, Any]]
Stage = Callable[[Path, str], dict[str, Any]]


def _quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


class ComposioDrive:
    def __init__(self, execute: Execute, stage: Stage | None = None) -> None:
        self._execute = execute
        self._stage = stage

    def _call(self, slug: str, arguments: dict[str, Any]) -> dict[str, Any]:
        reply = self._execute(slug, arguments)
        if not reply.get("successful"):
            raise ConnectionError(f"{slug}: {reply.get('error') or 'failed'}")
        data = reply.get("data") or {}
        return data if isinstance(data, dict) else {}

    def _find(self, query: str) -> list[dict[str, Any]]:
        fields = "files(id,name,size,md5Checksum,modifiedTime,mimeType)"
        files: list[dict[str, Any]] = self._call("GOOGLEDRIVE_FIND_FILE", {"q": query, "fields": fields}).get(
            "files", []
        )
        return files

    def list_folder(self, folder_id: str) -> list[DriveFile]:
        query = f"'{_quote(folder_id)}' in parents and trashed = false and mimeType != '{FOLDER}'"
        return [
            DriveFile(
                f["id"], f["name"], int(f.get("size") or 0), f.get("md5Checksum", ""), f["modifiedTime"]
            )
            for f in self._find(query)
        ]

    def download(self, file_id: str, dest: Path) -> None:
        data = self._call("GOOGLEDRIVE_DOWNLOAD_FILE", {"fileId": file_id})
        url = (data.get("downloaded_file_content") or {}).get("s3url")
        if not url:
            raise ConnectionError(f"GOOGLEDRIVE_DOWNLOAD_FILE: no file link for {file_id}")
        with requests.get(url, stream=True, timeout=120) as reply:
            reply.raise_for_status()
            with dest.open("wb") as handle:
                for block in reply.iter_content(1 << 20):
                    handle.write(block)

    def find_folder(self, name: str, parent_id: str) -> str | None:
        query = (
            f"name = '{_quote(name)}' and '{_quote(parent_id)}' in parents "
            f"and mimeType = '{FOLDER}' and trashed = false"
        )
        existing = self._find(query)
        return str(existing[0]["id"]) if existing else None

    def ensure_folder(self, name: str, parent_id: str) -> str:
        existing = self.find_folder(name, parent_id)
        if existing:
            return existing
        return str(self._call("GOOGLEDRIVE_CREATE_FOLDER", {"name": name, "parent_id": parent_id})["id"])

    def upload(self, path: Path, folder_id: str) -> str:
        if self._stage is None:
            raise RuntimeError("uploads need a staging function")
        if path.stat().st_size <= SIMPLE_UPLOAD_LIMIT:
            staged = self._stage(path, "GOOGLEDRIVE_UPLOAD_FILE")
            data = self._call(
                "GOOGLEDRIVE_UPLOAD_FILE", {"file_to_upload": staged, "folder_to_upload_to": folder_id}
            )
            return str(data.get("id", ""))
        staged = self._stage(path, "GOOGLEDRIVE_RESUMABLE_UPLOAD")
        arguments: dict[str, Any] = {
            "file_to_upload": staged,
            "metadata": {"name": path.name, "parents": [folder_id]},
            "chunkSize": 262144 * 32,  # 8 MB; Drive needs a multiple of 256 KB
        }
        return str(self._call("GOOGLEDRIVE_RESUMABLE_UPLOAD", arguments).get("id", ""))

    def replace(self, file_id: str, path: Path) -> None:
        """New content for an existing file: same id, same link, Drive keeps the old revision."""
        if self._stage is None:
            raise RuntimeError("uploads need a staging function")
        if path.stat().st_size <= SIMPLE_UPLOAD_LIMIT:
            staged = self._stage(path, "GOOGLEDRIVE_UPLOAD_UPDATE_FILE")
            self._call("GOOGLEDRIVE_UPLOAD_UPDATE_FILE", {"fileId": file_id, "file_to_upload": staged})
            return
        staged = self._stage(path, "GOOGLEDRIVE_RESUMABLE_UPLOAD")
        arguments: dict[str, Any] = {"file_to_upload": staged, "file_id": file_id, "chunkSize": 262144 * 32}
        self._call("GOOGLEDRIVE_RESUMABLE_UPLOAD", arguments)

    def read_tab(self, sheet_id: str, tab: str) -> list[list[str]]:
        data = self._call(
            "GOOGLESHEETS_BATCH_GET", {"spreadsheet_id": sheet_id, "ranges": [f"{tab}!A1:Z2000"]}
        )
        ranges = data.get("valueRanges") or [{}]
        return [[str(cell) for cell in row] for row in ranges[0].get("values", [])]
