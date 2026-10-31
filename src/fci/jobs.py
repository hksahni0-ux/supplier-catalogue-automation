"""A job file describes one product: the few facts a person supplies."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Job:
    brand: str
    model: str
    supplier_name: str
    product_type: str
    category_code: str
    sku: str
    supplier_url: str
    category_confirmed: bool = True
    options: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None


def load_job(path: Path | str) -> Job:
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    known = {
        "brand",
        "model",
        "supplier_name",
        "product_type",
        "category_code",
        "sku",
        "supplier_url",
        "category_confirmed",
    }
    missing = sorted(k for k in known - {"category_confirmed"} if not data.get(k))
    if missing:
        raise ValueError(f"{path.name}: missing required fields {missing}")
    return Job(
        **{k: data[k] for k in known if k in data},
        options={k: v for k, v in data.items() if k not in known},
        path=path,
    )
