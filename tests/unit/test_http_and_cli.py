"""HTTP cache behaviour and the command line, without touching the network."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from fci import cli
from fci.http import Http


class FakeSession:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url))
        return self.responses.pop(0)


def response(status: int = 200, content: bytes = b"ok", json_data=None) -> SimpleNamespace:
    def raise_for_status() -> None:
        if status >= 400:
            raise RuntimeError(status)

    return SimpleNamespace(
        status_code=status, content=content, json=lambda: json_data, raise_for_status=raise_for_status
    )


def test_get_is_cached_after_first_fetch(tmp_path: Path) -> None:
    http = Http(tmp_path, delay=0)
    http.session = FakeSession([response(content=b"page")])  # type: ignore[assignment]
    assert http.get("https://example.com/a") == b"page"
    assert http.get("https://example.com/a") == b"page"
    assert len(http.session.calls) == 1  # type: ignore[attr-defined]


def test_offline_serves_cache_only(tmp_path: Path) -> None:
    online = Http(tmp_path, delay=0)
    online.session = FakeSession([response(content=b"cached")])  # type: ignore[assignment]
    online.get("https://example.com/a")
    offline = Http(tmp_path, offline=True)
    assert offline.get("https://example.com/a") == b"cached"
    with pytest.raises(ConnectionError):
        offline.get("https://example.com/not-cached")
    assert offline.exists("https://example.com/x") is False


def test_post_json_cached_by_body(tmp_path: Path) -> None:
    http = Http(tmp_path, delay=0)
    http.session = FakeSession(
        [
            response(content=b'{"a": 1}', json_data={"a": 1}),  # type: ignore[assignment]
            response(content=b'{"a": 2}', json_data={"a": 2}),
        ]
    )
    assert http.post_json("https://example.com/api", {"id": 1}) == {"a": 1}
    assert http.post_json("https://example.com/api", {"id": 2}) == {"a": 2}
    assert http.post_json("https://example.com/api", {"id": 1}) == {"a": 1}
    assert len(http.session.calls) == 2  # type: ignore[attr-defined]


def test_server_errors_are_retried_then_give_up(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fci.http.time.sleep", lambda s: None)
    http = Http(tmp_path, delay=0, retries=2)
    http.session = FakeSession([response(503), response(503)])  # type: ignore[assignment]
    with pytest.raises(ConnectionError):
        http.get("https://example.com/down")


def test_cli_reports_a_failed_job_and_exits_non_zero(tmp_path: Path, capsys) -> None:
    job = tmp_path / "broken.yaml"
    job.write_text("brand: cattelan-italia\nmodel: X\n")
    code = cli.main(["run", str(job), "--cache", str(tmp_path / "cache"), "--offline", "--no-ai"])
    assert code == 1
    assert "missing required fields" in capsys.readouterr().out
