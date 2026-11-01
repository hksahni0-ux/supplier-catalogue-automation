"""Which supplier file to read: the newest one matching the brand's pattern.

With Drive as the source, a new catalogue arrives under a new name ('p.list 11-26' after
'p.list 05-26'). A pattern in the brand config picks it up with no config change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_input(inputs: Path, spec: dict[str, Any]) -> Path:
    pattern = spec.get("match")
    found = [p for p in inputs.glob(pattern) if p.is_file()] if pattern else []
    if found:
        return max(found, key=lambda p: (p.stat().st_mtime, p.name))
    if spec.get("file"):
        return inputs / spec["file"]  # the file named in the config (offline fixtures, old setups)
    raise FileNotFoundError(f"no file matching '{pattern}' in {inputs}")
