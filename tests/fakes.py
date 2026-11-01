"""Test doubles shared by unit and integration tests."""

import hashlib
from pathlib import Path

from fci.drive import DriveFile


class FakeDrive:
    """In-memory Drive: folders hold files; uploads and folders are recorded."""

    def __init__(self) -> None:
        self.files: dict[str, list[tuple[DriveFile, bytes]]] = {}
        self.downloads: list[str] = []
        self.folders: dict[str, str] = {}
        self.uploads: list[tuple[str, str]] = []
        self.replaced: list[str] = []
        self.tabs: dict[str, list[list[str]]] = {}

    def put(self, folder: str, name: str, content: bytes, modified: str) -> None:
        md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
        meta = DriveFile(f"id-{name}", name, len(content), md5, modified)
        self.files.setdefault(folder, []).append((meta, content))

    def list_folder(self, folder_id: str) -> list[DriveFile]:
        return [meta for meta, _ in self.files.get(folder_id, [])]

    def download(self, file_id: str, dest: Path) -> None:
        self.downloads.append(file_id)
        for entries in self.files.values():
            for meta, content in entries:
                if meta.id == file_id:
                    dest.write_bytes(content)

    def find_folder(self, name: str, parent_id: str) -> str | None:
        return self.folders.get(f"{parent_id}/{name}")

    def ensure_folder(self, name: str, parent_id: str) -> str:
        return self.folders.setdefault(f"{parent_id}/{name}", f"folder-{len(self.folders)}")

    def upload(self, path: Path, folder_id: str) -> str:
        self.uploads.append((folder_id, path.name))
        self.put(folder_id, path.name, path.read_bytes(), "2026-11-02T00:00:00.000Z")
        return f"id-{path.name}"

    def replace(self, file_id: str, path: Path) -> None:
        self.replaced.append(path.name)
        for folder, entries in self.files.items():
            self.files[folder] = [(m, c) for m, c in entries if m.id != file_id]
            if len(self.files[folder]) != len(entries):
                self.put(folder, path.name, path.read_bytes(), "2026-11-02T00:00:00.000Z")

    def read_tab(self, sheet_id: str, tab: str) -> list[list[str]]:
        return self.tabs.get(tab, [])
