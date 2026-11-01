import os
from datetime import UTC, datetime

import pytest

from fci.drive import ComposioDrive, DriveFile, publish_outputs, sync_folder
from fci.inputs import resolve_input
from tests.fakes import FakeDrive


# ---------------------------------------------------------------- sync
def test_sync_downloads_new_files_and_keeps_drive_dates(tmp_path) -> None:
    drive = FakeDrive()
    drive.put("cat", "CATTELAN ITALIA p.list 05-26.pdf", b"old list", "2026-05-01T09:00:00.000Z")
    paths = sync_folder(drive, "cat", tmp_path)
    assert [p.name for p in paths] == ["CATTELAN ITALIA p.list 05-26.pdf"]
    assert paths[0].read_bytes() == b"old list"
    assert datetime.fromtimestamp(os.stat(paths[0]).st_mtime, UTC) == datetime(2026, 5, 1, 9, tzinfo=UTC)


def test_sync_skips_files_that_are_already_identical(tmp_path) -> None:
    drive = FakeDrive()
    drive.put("cat", "list.pdf", b"same", "2026-05-01T09:00:00.000Z")
    sync_folder(drive, "cat", tmp_path)
    sync_folder(drive, "cat", tmp_path)
    assert len(drive.downloads) == 1


def test_sync_refuses_names_that_would_escape_the_folder(tmp_path) -> None:
    drive = FakeDrive()
    drive.put("cat", "../evil.pdf", b"x", "2026-05-01T09:00:00.000Z")
    with pytest.raises(ValueError, match="unsafe file name"):
        sync_folder(drive, "cat", tmp_path / "inputs")


# ---------------------------------------------------------------- choosing the price list
def test_newest_matching_file_wins_so_a_new_catalogue_needs_no_config_change(tmp_path) -> None:
    for name, day in [("CATTELAN ITALIA p.list 05-26.pdf", 1), ("CATTELAN ITALIA p.list 11-26.pdf", 20),
                      ("Copy of Materials-2023.pdf", 30)]:  # fmt: skip
        path = tmp_path / name
        path.write_bytes(b"x")
        stamp = datetime(2026, 11, day, tzinfo=UTC).timestamp()
        os.utime(path, (stamp, stamp))
    spec = {"file": "CATTELAN ITALIA p.list 05-26.pdf", "match": "CATTELAN ITALIA p.list*.pdf"}
    assert resolve_input(tmp_path, spec).name == "CATTELAN ITALIA p.list 11-26.pdf"


def test_without_a_pattern_the_named_file_is_used(tmp_path) -> None:
    (tmp_path / "list.pdf").write_bytes(b"x")
    assert resolve_input(tmp_path, {"file": "list.pdf"}) == tmp_path / "list.pdf"


def test_no_match_is_a_clear_error(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match=r"no file matching 'X\*\.pdf'"):
        resolve_input(tmp_path, {"match": "X*.pdf"})


# ---------------------------------------------------------------- publishing a run
def test_publish_mirrors_the_output_folder_under_a_dated_folder(tmp_path) -> None:
    out = tmp_path / "cattelan-italia-889"
    (out / "csv").mkdir(parents=True)
    (out / "csv" / "x-prices.csv").write_text("code,combo,price\n")
    (out / "report.md").write_text("# report")
    (out / "originals").mkdir()
    (out / "originals" / "big.jpg").write_bytes(b"raw")  # archive copies stay local
    drive = FakeDrive()
    folder = publish_outputs(drive, out, "outputs", "2026-11-02")
    names = sorted(name for _, name in drive.uploads)
    assert names == ["report.md", "x-prices.csv"]
    assert folder == drive.folders["folder-0/cattelan-italia-889"]


def test_publishing_again_replaces_changed_files_and_skips_identical_ones(tmp_path) -> None:
    out = tmp_path / "cattelan-italia-889"
    (out / "csv").mkdir(parents=True)
    (out / "csv" / "x-prices.csv").write_text("code,combo,price\n")
    (out / "report.md").write_text("# report")
    drive = FakeDrive()
    publish_outputs(drive, out, "outputs", "2026-11-02")
    (out / "report.md").write_text("# report, second run")
    publish_outputs(drive, out, "outputs", "2026-11-02")
    assert sorted(name for _, name in drive.uploads) == ["report.md", "x-prices.csv"]  # no duplicates
    assert drive.replaced == ["report.md"]  # x-prices.csv was identical, so skipped


# ---------------------------------------------------------------- Composio adapter
class FakeComposio:
    def __init__(self, replies: dict[str, dict]) -> None:
        self.replies, self.calls = replies, []

    def execute(self, slug: str, arguments: dict) -> dict:
        self.calls.append((slug, arguments))
        return self.replies[slug]


def test_composio_lists_a_folder_with_checksums() -> None:
    files = [{"id": "a", "name": "list.pdf", "size": "10", "md5Checksum": "m", "modifiedTime": "t"}]
    api = FakeComposio({"GOOGLEDRIVE_FIND_FILE": {"successful": True, "data": {"files": files}}})
    assert ComposioDrive(api.execute).list_folder("cat") == [DriveFile("a", "list.pdf", 10, "m", "t")]
    slug, args = api.calls[0]
    assert "'cat' in parents" in args["q"] and "trashed = false" in args["q"]


def test_composio_finds_a_subfolder_by_name() -> None:
    folder = {"id": "f1", "name": "Poltrona Frau", "mimeType": "application/vnd.google-apps.folder"}
    api = FakeComposio({"GOOGLEDRIVE_FIND_FILE": {"successful": True, "data": {"files": [folder]}}})
    assert ComposioDrive(api.execute).find_folder("Poltrona Frau", "lists") == "f1"
    _, args = api.calls[0]
    assert "name = 'Poltrona Frau'" in args["q"] and "'lists' in parents" in args["q"]


def test_composio_reports_a_missing_subfolder_as_none() -> None:
    api = FakeComposio({"GOOGLEDRIVE_FIND_FILE": {"successful": True, "data": {"files": []}}})
    assert ComposioDrive(api.execute).find_folder("Nobody", "lists") is None


def test_composio_failures_are_raised_not_swallowed() -> None:
    api = FakeComposio({"GOOGLEDRIVE_FIND_FILE": {"successful": False, "error": "403 forbidden"}})
    with pytest.raises(ConnectionError, match="GOOGLEDRIVE_FIND_FILE: 403 forbidden"):
        ComposioDrive(api.execute).list_folder("cat")


def test_composio_reads_a_sheet_tab() -> None:
    reply = {
        "successful": True,
        "data": {"valueRanges": [{"range": "Products!A1:K4", "values": [["sku"], ["a"]]}]},
    }
    api = FakeComposio({"GOOGLESHEETS_BATCH_GET": reply})
    assert ComposioDrive(api.execute).read_tab("sheet", "Products") == [["sku"], ["a"]]
