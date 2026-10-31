"""Reuse swatch images FCI already hosts, for suppliers that publish none (Franco Ferri).

FCI's files are named inconsistently ('05-lightgrey-boston.jpg', '001-giotto.jpg',
'20650_gioioso.jpg'), so they are matched on (colour code, article) rather than by name.
When FCI's file names a different colour than the current card, the image is not reused and
the difference is reported: the supplier may have re-used the code for a new colour.
"""

from __future__ import annotations

import re
from pathlib import Path

Key = tuple[int, str]


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def index_existing(paths: list[str]) -> dict[Key, tuple[str, str]]:
    """(code, article) -> (path, colour words in FCI's file name)."""
    index: dict[Key, tuple[str, str]] = {}
    for path in paths:
        tokens = _tokens(Path(path).stem)
        if len(tokens) >= 2 and tokens[0].isdigit():
            index.setdefault((int(tokens[0]), tokens[-1]), (path, " ".join(tokens[1:-1])))
    return index


def match_swatch(option_name: str, index: dict[Key, tuple[str, str]]) -> tuple[str | None, str]:
    tokens = _tokens(option_name)
    if len(tokens) < 2 or not tokens[0].isdigit():
        return None, ""
    hit = index.get((int(tokens[0]), tokens[-1]))
    if hit is None:
        return None, ""
    path, fci_colour = hit
    card_colour = " ".join(tokens[1:-1])
    squash = lambda s: s.replace(" ", "")  # noqa: E731
    if fci_colour and card_colour and squash(fci_colour) != squash(card_colour):
        return None, f"FCI image is '{fci_colour}', card now says '{card_colour}'"
    return path, ""
