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


KNOWN = {
    "brand",
    "model",
    "supplier_name",
    "product_type",
    "category_code",
    "sku",
    "supplier_url",
    "category_confirmed",
}


def job_from_dict(data: dict[str, Any], source: str, path: Path | None = None) -> Job:
    """Build a job from its fields, wherever they were written (a YAML file or a sheet row)."""
    missing = sorted(k for k in KNOWN - {"category_confirmed"} if not data.get(k))
    if missing:
        raise ValueError(f"{source}: missing required fields {missing}")
    return Job(
        **{k: data[k] for k in KNOWN if k in data},
        options={k: v for k, v in data.items() if k not in KNOWN},
        path=path,
    )


def load_job(path: Path | str) -> Job:
    path = Path(path)
    return job_from_dict(yaml.safe_load(path.read_text()), path.name, path)
