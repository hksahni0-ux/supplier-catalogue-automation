"""Compare two runs of the same product: which prices moved, which options appeared or went.

Used for re-pricing when a supplier sends a new price list: FCI uploads only the rows that
changed, and a person reads the summary instead of thousands of rows.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PriceChange:
    combo: str
    old: int
    new: int

    @property
    def percent(self) -> float:
        return (self.new - self.old) / self.old * 100 if self.old else 0.0


@dataclass
class Changes:
    changed: list[PriceChange] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0

    def summary(self) -> str:
        if not (self.changed or self.added or self.removed):
            return f"no price changes ({self.unchanged} unchanged)"
        parts = []
        if self.changed:
            average = sum(c.percent for c in self.changed) / len(self.changed)
            parts.append(f"{len(self.changed)} prices changed (avg {average:+.1f}%)")
        if self.added:
            parts.append(f"{len(self.added)} added")
        if self.removed:
            parts.append(f"{len(self.removed)} removed")
        parts.append(f"{self.unchanged} unchanged")
        return ", ".join(parts)


def _prices(rows: Iterable[dict[str, str]]) -> dict[str, int]:
    return {row["combo"]: int(row["price"]) for row in rows}


def compare_prices(old_rows: Iterable[dict[str, str]], new_rows: Iterable[dict[str, str]]) -> Changes:
    old, new = _prices(old_rows), _prices(new_rows)
    changes = Changes()
    for combo, price in new.items():
        if combo not in old:
            changes.added.append(combo)
        elif old[combo] != price:
            changes.changed.append(PriceChange(combo, old[combo], price))
        else:
            changes.unchanged += 1
    changes.removed = [combo for combo in old if combo not in new]
    return changes


def write_changed_rows(changes: Changes, new_rows: Iterable[dict[str, str]], path: Path) -> Path:
    """A prices CSV with only the rows to upload: changed and newly added combinations."""
    wanted = {c.combo for c in changes.changed} | set(changes.added)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["code", "combo", "price"], lineterminator="\n")
        writer.writeheader()
        for row in new_rows:
            if row["combo"] in wanted:
                writer.writerow({"code": row["code"], "combo": row["combo"], "price": row["price"]})
    return path
