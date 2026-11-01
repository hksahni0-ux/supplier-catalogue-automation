"""What the assistant can do. Every answer is read from the run outputs; nothing is estimated.

Read-only tools return facts. The single action, `propose_run`, only describes a run: the web
page asks the user to Confirm before anything happens.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fci.assistant.catalogue import Catalogue, Product, words
from fci.exporters import COMBO_SEPARATOR

MAX_GROUPS = 15


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


DESCRIPTIONS = {
    "list_products": "Every product with its latest run: SKU, base price, currency, review count.",
    "get_price": (
        "Supplier prices for a product, filtered by size and/or cover. Size is a letter ('D') or layout "
        "words ('maxi chaise'); cover is a code ('GLV02') or material words ('glove leather')."
    ),
    "list_options": "Sizes, cover groups (with counts and price ranges) and other options.",
    "get_review_items": "Warnings and errors a person should check, for one product or all.",
    "get_price_changes": "What changed in prices since the previous run.",
    "get_drive_link": "The Google Drive folder with a product's latest published results.",
    "propose_run": (
        "Propose re-running products from the latest Drive price lists. Does NOT run anything: "
        "the user must press Confirm."
    ),
}
PRODUCT = {
    "type": "string",
    "description": "Product name words or SKU, e.g. 'Richard' or 'fiera-collection-043'",
}


class Tools:
    def __init__(self, catalogue: Catalogue) -> None:
        self.catalogue = catalogue

    # ------------------------------------------------------------ helpers
    def _product(self, query: str) -> Product | dict[str, Any]:
        product = self.catalogue.find(query)
        if product is None:
            return {
                "error": f"no single product matches '{query}'",
                "known_products": [p.name for p in self.catalogue.products()],
            }
        return product

    def _groups(self, product: Product) -> dict[str, str]:
        return {r["name"]: r["grouping"] for r in product.attributes if r["attribute"] == "Cover"}

    # ------------------------------------------------------------ read-only tools
    def list_products(self) -> list[dict[str, Any]]:
        out = []
        for p in self.catalogue.products():
            flags = p.report.get("flags", [])
            out.append(
                {
                    "sku": p.sku,
                    "name": p.name,
                    "currency": p.currency,
                    "base_price": p.report.get("base_price"),
                    "price_range": p.report.get("price_range"),
                    "price_rows": p.report.get("combinations"),
                    "needs_review": sum(1 for f in flags if f["severity"] in ("error", "warning")),
                    "last_run": p.report.get("generated"),
                }
            )
        return out

    def get_price(self, product: str, size: str = "", cover: str = "") -> dict[str, Any]:
        found = self._product(product)
        if isinstance(found, dict):
            return found
        groups = self._groups(found)
        size_words, cover_words = words(size), words(cover)
        letter = size.strip().upper() if len(size.strip()) <= 2 else ""
        matched: dict[tuple[str, int], list[str]] = {}
        for row in found.prices:
            option, _, chosen = row["combo"].partition(COMBO_SEPARATOR)
            if letter and not option.startswith(f"{letter} - "):
                continue
            if size_words and not letter and not set(size_words) <= set(words(option)):
                continue
            if cover_words and not set(cover_words) <= set(words(f"{chosen} {groups.get(chosen, '')}")):
                continue
            matched.setdefault((option, int(row["price"])), []).append(chosen)
        prices = [
            {
                "price": price,
                "size": option,
                "cover_groups": sorted({groups.get(c, "") for c in covers} - {""}),
                "covers": covers,
            }
            for (option, price), covers in matched.items()
        ]
        reply: dict[str, Any] = {
            "product": found.name,
            "currency": found.currency,
            "prices": prices[:MAX_GROUPS],
        }
        if not prices:
            reply["note"] = (
                "no price matches those words; call list_options to see the sizes and cover groups"
            )
        elif len(prices) > MAX_GROUPS:
            reply["note"] = (
                f"{len(prices)} groups match; showing {MAX_GROUPS}. Ask for a size or cover to narrow it."
            )
        return reply

    def list_options(self, product: str) -> dict[str, Any]:
        found = self._product(product)
        if isinstance(found, dict):
            return found
        sizes = [r["name"] for r in found.attributes if r["attribute"] == "Size"]
        groups = self._groups(found)
        by_group: dict[str, list[str]] = {}
        for name, group in groups.items():
            by_group.setdefault(group or "Other", []).append(name)
        prices: dict[str, list[int]] = {}
        for row in found.prices:
            chosen = row["combo"].partition(COMBO_SEPARATOR)[2]
            prices.setdefault(groups.get(chosen, "") or "Other", []).append(int(row["price"]))
        cover_groups = [
            {"group": g, "count": len(names), "from": min(prices.get(g, [0])), "to": max(prices.get(g, [0])),
             "examples": names[:3]}
            for g, names in by_group.items()
        ]  # fmt: skip
        others = sorted({r["attribute"] for r in found.attributes} - {"Size", "Cover"})
        return {
            "product": found.name,
            "currency": found.currency,
            "sizes": sizes,
            "cover_groups": cover_groups,
            "other_options": others,
        }

    def get_review_items(self, product: str = "", include_info: bool = False) -> dict[str, Any]:
        targets = self.catalogue.products()
        if product:
            found = self._product(product)
            if isinstance(found, dict):
                return found
            targets = [found]
        levels = ("error", "warning", "info") if include_info else ("error", "warning")
        items = [
            {"product": p.name, "severity": f["severity"], "about": f["field"], "message": f["message"]}
            for p in targets
            for f in p.report.get("flags", [])
            if f["severity"] in levels
        ]
        return {"items": items}

    def get_price_changes(self, product: str = "") -> dict[str, Any]:
        targets = self.catalogue.products()
        if product:
            found = self._product(product)
            if isinstance(found, dict):
                return found
            targets = [found]
        summaries = []
        for p in targets:
            path = p.out_dir / "price-changes.md"
            text = path.read_text() if path.exists() else ""
            line = next((ln for ln in text.splitlines()[1:] if ln.strip()), "no comparison yet (first run)")
            summaries.append(f"{p.name}: {line}")
        return {"summary": "\n".join(summaries)}

    def get_drive_link(self, product: str) -> dict[str, Any]:
        found = self._product(product)
        if isinstance(found, dict):
            return found
        path = found.out_dir / "published.json"
        if not path.exists():
            return {"product": found.name, "note": "not published to Drive yet"}
        data = json.loads(path.read_text())
        return {"product": found.name, "date": data["date"],
                "url": f"https://drive.google.com/drive/folders/{data['folder']}"}  # fmt: skip

    def propose_run(self, products: list[str], publish: bool = True) -> dict[str, Any]:
        skus = []
        for query in products:
            if query.strip().lower() == "all":
                skus = [p.sku for p in self.catalogue.products()]
                break
            found = self._product(query)
            if isinstance(found, dict):
                return found
            skus.append(found.sku)
        return {
            "proposal": {"action": "run", "skus": skus, "publish": publish},
            "note": "Nothing has run yet. The user must press Confirm.",
        }

    # ------------------------------------------------------------ for the model
    def handlers(self) -> dict[str, Callable[..., Any]]:
        return {
            "list_products": self.list_products,
            "get_price": self.get_price,
            "list_options": self.list_options,
            "get_review_items": self.get_review_items,
            "get_price_changes": self.get_price_changes,
            "get_drive_link": self.get_drive_link,
            "propose_run": self.propose_run,
        }

    def call(self, name: str, arguments: str | dict[str, Any]) -> dict[str, Any] | list[Any]:
        handler = self.handlers().get(name)
        if handler is None:
            return {"error": f"unknown tool '{name}'"}
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            result: dict[str, Any] | list[Any] = handler(**(args or {}))
            return result
        except (TypeError, ValueError) as error:
            return {"error": f"bad arguments for {name}: {error}"}

    def schemas(self) -> list[dict[str, Any]]:
        text = {"type": "string"}
        flag = {"type": "boolean"}
        products = {"type": "array", "items": text, "description": "names, SKUs or 'all'"}
        publish = {"type": "boolean", "description": "save results to Drive (default true)"}
        return [
            _schema("list_products", DESCRIPTIONS["list_products"], {}, []),
            _schema(
                "get_price",
                DESCRIPTIONS["get_price"],
                {"product": PRODUCT, "size": text, "cover": text},
                ["product"],
            ),
            _schema("list_options", DESCRIPTIONS["list_options"], {"product": PRODUCT}, ["product"]),
            _schema(
                "get_review_items",
                DESCRIPTIONS["get_review_items"],
                {"product": PRODUCT, "include_info": flag},
                [],
            ),
            _schema("get_price_changes", DESCRIPTIONS["get_price_changes"], {"product": PRODUCT}, []),
            _schema("get_drive_link", DESCRIPTIONS["get_drive_link"], {"product": PRODUCT}, ["product"]),
            _schema(
                "propose_run",
                DESCRIPTIONS["propose_run"],
                {"products": products, "publish": publish},
                ["products"],
            ),
        ]
