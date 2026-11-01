"""Collapse a prices CSV back to the supplier's table: one line per size and distinct price.

Every cover in a price group shares one supplier price, so thousands of rows reduce to the
handful of cells printed in the price list, which is what a person checks by hand.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from fci.exporters import COMBO_SEPARATOR

Grid = dict[str, dict[int, list[str]]]


def price_grid(rows: Iterable[dict[str, str]]) -> Grid:
    grid: Grid = {}
    for row in rows:
        size, cover = row["combo"].split(COMBO_SEPARATOR, 1)
        grid.setdefault(size, {}).setdefault(int(row["price"]), []).append(cover)
    return grid


def read_grid(path: Path) -> Grid:
    with path.open(newline="") as handle:
        return price_grid(csv.DictReader(handle))


def format_grid(grid: Grid) -> str:
    rows = sum(len(c) for prices in grid.values() for c in prices.values())
    cells = sum(len(prices) for prices in grid.values())
    lines = [f"{rows} rows, {len(grid)} sizes, {cells} distinct prices to check against the price list"]
    for size, prices in grid.items():
        lines.append(f"\n{size}")
        for price, covers in sorted(prices.items()):
            sample = covers[0] if len(covers) == 1 else f"{covers[0]} … {covers[-1]}"
            lines.append(f"  {price:>7}  {len(covers):4} covers  {sample}")
    return "\n".join(lines)
