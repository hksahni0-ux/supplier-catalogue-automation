"""Polite, cached HTTP. Every response is stored on disk, so re-runs are repeatable and
supplier sites are hit once per resource. `offline=True` serves only from the cache."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

USER_AGENT = "FCI-product-pipeline/0.1 (product data import; contact: hello@fcilondon.co.uk)"


class Http:
    def __init__(self, cache_dir: Path, offline: bool = False, delay: float = 0.3, retries: int = 3) -> None:
        self.cache_dir = cache_dir
        self.offline = offline
        self.delay = delay
        self.retries = retries
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, *parts: str) -> Path:
        return self.cache_dir / hashlib.sha256("\n".join(parts).encode()).hexdigest()

    def _fetch(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self.session.request(method, url, timeout=30, **kwargs)
                if response.status_code < 500:
                    time.sleep(self.delay)
                    return response
                last = requests.HTTPError(f"{response.status_code} for {url}")
            except requests.RequestException as error:
                last = error
            time.sleep(2**attempt)
        raise ConnectionError(f"giving up on {url}: {last}")

    def get(self, url: str) -> bytes:
        path = self._path("GET", url)
        if path.exists():
            return path.read_bytes()
        if self.offline:
            raise ConnectionError(f"offline and not cached: {url}")
        response = self._fetch("GET", url)
        response.raise_for_status()
        path.write_bytes(response.content)
        return response.content

    def post_json(self, url: str, data: dict[str, Any]) -> Any:
        body = json.dumps(data, sort_keys=True)
        path = self._path("POST", url, body)
        if path.exists():
            return json.loads(path.read_bytes())
        if self.offline:
            raise ConnectionError(f"offline and not cached: POST {url}")
        response = self._fetch("POST", url, data=data)
        response.raise_for_status()
        path.write_bytes(response.content)
        return response.json()

    def exists(self, url: str) -> bool:
        path = self._path("HEAD", url)
        if path.exists():
            return path.read_text() == "1"
        if self.offline:
            return False
        ok = self._fetch("HEAD", url, allow_redirects=True).status_code == 200
        path.write_text("1" if ok else "0")
        return ok
