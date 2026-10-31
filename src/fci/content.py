"""Product copy: meta description (<= 160 characters) and the long SHORT-DESCRIPTION text.

NVIDIA Nemotron (NVIDIA_API_KEY) rewrites the supplier's own wording into FCI's style.
Everything a model returns is checked (valid JSON, length, no prices) and anything that
fails falls back to the supplier's text with a review flag. Prices never come from a model.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests

from fci.model import Flag

META_LIMIT = 160
META_MIN = 100  # shorter meta descriptions waste the space search results show
PRICE_RE = re.compile(r"[£€$]\s?\d|\d\s?(?:GBP|EUR)\b|\bprice[ds]? (?:from|at)\b", re.IGNORECASE)

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"

SYSTEM = """You write product copy for FCI London, a luxury furniture retailer.
Use British English and a calm, specific tone. Use only the facts supplied: never invent
dimensions, materials, designers or features, and never mention prices or delivery.
meta_description: one sentence of 110-155 characters that names the product and brand and one
distinctive design feature from the supplier text.
long_description: one paragraph of 90-150 words describing design, materials and options.
Reply with only a JSON object with exactly the keys "meta_description" and "long_description"."""


class CopyError(Exception):
    """A provider failed or returned something unusable."""


@dataclass
class Reply:
    text: str
    model: str
    refused: bool = False


class Backend(Protocol):
    model: str

    def complete(self, system: str, prompt: str) -> Reply: ...


@dataclass
class ProductFacts:
    name: str
    brand: str
    product_type: str
    supplier_texts: list[str]
    specs: list[str] = field(default_factory=list)
    designer: str | None = None


@dataclass
class Copy:
    meta_description: str
    long_description: str
    source: str  # "ai" or "supplier"
    flags: list[Flag] = field(default_factory=list)


# --- providers ----------------------------------------------------------------


class NvidiaBackend:
    """NVIDIA API catalog (OpenAI-compatible chat completions), reasoning switched off."""

    def __init__(
        self,
        api_key: str,
        model: str = NVIDIA_MODEL,
        post: Callable[..., Any] = requests.post,
        url: str = NVIDIA_URL,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self._post = post
        self._url = url

    def complete(self, system: str, prompt: str) -> Reply:
        try:
            response = self._post(
                self._url,
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    "temperature": 0.6,
                    "top_p": 0.95,
                    "max_tokens": 2000,
                    "chat_template_kwargs": {"enable_thinking": False},
                    "stream": False,
                },
                timeout=120,
            )
        except requests.RequestException as error:
            raise CopyError(f"NVIDIA request failed: {error}") from error
        if response.status_code >= 400:
            raise CopyError(f"NVIDIA API returned {response.status_code}: {response.text[:200]}")
        body = response.json()
        choice = (body.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        return Reply(
            content, str(body.get("model", self.model)), choice.get("finish_reason") == "content_filter"
        )


def select_backend() -> Backend | None:
    """Nemotron when NVIDIA_API_KEY is set; None means offline (supplier text)."""
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        return None
    return NvidiaBackend(key, os.environ.get("FCI_COPY_MODEL") or NVIDIA_MODEL)


# --- copy -----------------------------------------------------------------------


def extract_json(text: str) -> dict[str, Any]:
    """The JSON object in a reply, ignoring reasoning tags, code fences or chatter around it."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise CopyError("reply contains no JSON object")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as error:
        raise CopyError(f"invalid JSON: {error}") from error
    if not isinstance(data, dict):
        raise CopyError("reply JSON is not an object")
    return data


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "…" if not cut.endswith(".") else cut


def supplier_copy(facts: ProductFacts) -> Copy:
    texts = [t.strip() for t in facts.supplier_texts if t and t.strip()]
    long_description = " ".join(texts)
    first = re.split(r"(?<=[.!?])\s", texts[0])[0] if texts else facts.name
    return Copy(
        _shorten(first, META_LIMIT),
        long_description,
        "supplier",
        [
            Flag(
                "warning",
                "description",
                "copy is the supplier's own wording; review/rewrite for SEO before publishing",
                "supplier website and price list",
            )
        ],
    )


def _prompt(facts: ProductFacts) -> str:
    lines = [f"Product: {facts.name}", f"Brand: {facts.brand}", f"Type: {facts.product_type}"]
    if facts.designer:
        lines.append(f"Designer: {facts.designer}")
    lines += [f"Specification: {s}" for s in facts.specs]
    lines += ["", "Supplier text:"] + [f"- {t}" for t in facts.supplier_texts if t]
    return "\n".join(lines)


def _check(data: dict[str, Any]) -> str | None:
    meta = str(data.get("meta_description", "")).strip()
    long = str(data.get("long_description", "")).strip()
    if not meta or not long:
        return "empty field"
    if len(meta) > META_LIMIT:
        return f"meta description is {len(meta)} characters"
    if PRICE_RE.search(meta) or PRICE_RE.search(long):
        return "copy mentions a price"
    if len(meta) < META_MIN:
        return f"meta description too short ({len(meta)} characters)"
    return None


def write_copy(facts: ProductFacts, backend: Backend | None = None, attempts: int = 2) -> Copy:
    if backend is None:
        return supplier_copy(facts)
    problem = "no response"
    model = backend.model
    for _ in range(attempts):
        try:
            reply = backend.complete(SYSTEM, _prompt(facts))
        except CopyError as error:
            problem = str(error)
            break
        model = reply.model
        if reply.refused:
            problem = "model declined"
            break
        try:
            data = extract_json(reply.text)
        except CopyError as error:
            problem = str(error)
            continue
        problem = _check(data) or ""
        if not problem:
            return Copy(
                str(data["meta_description"]).strip(),
                str(data["long_description"]).strip(),
                "ai",
                [Flag("info", "description", "AI-written copy; spot-check tone before publishing", model)],
            )
    fallback = supplier_copy(facts)
    fallback.flags.append(
        Flag("warning", "description", f"AI copy rejected ({problem}); used supplier text", model)
    )
    return fallback
