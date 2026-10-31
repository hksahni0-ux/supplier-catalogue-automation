"""Modular suppliers (Franco Ferri): a sellable layout is a list of modules, and its price
for a material is the sum of the module prices in that material's price category."""

from __future__ import annotations

from dataclasses import dataclass

from fci.adapters.franco_ferri_swatches import FrancoFerriSwatchCard
from fci.adapters.franco_ferri_xlsm import ModelEntry
from fci.model import Attribute, Flag, Option, ProductOptions, Swatch
from fci.naming import Naming


@dataclass(frozen=True)
class Layout:
    name: str
    modules: list[str]


def _mirror(modules: list[str], pairs: list[tuple[str, str]]) -> list[str]:
    swap = {a: b for a, b in pairs} | {b: a for a, b in pairs}
    return [swap.get(m, m) for m in modules]


def _layout_prices(entry: ModelEntry, modules: list[str]) -> dict[str, int] | None:
    if any(m not in entry.modules for m in modules):
        return None
    return {
        category: sum(entry.modules[m].prices[category] for m in modules)
        for category in entry.categories
        if all(category in entry.modules[m].prices for m in modules)
    }


def build_modular_options(
    entry: ModelEntry,
    card: FrancoFerriSwatchCard,
    layouts: list[Layout],
    *,
    brand_slug: str,
    model: str = "",
    mirror_pairs: list[tuple[str, str]] | None = None,
    feet_codes: list[str] | None = None,
    extra_dropdowns: dict[str, list[str]] | None = None,
    swatch_folder: str = "",
) -> ProductOptions:
    naming = Naming(model, "", "", brand_slug)
    source = f"price list block '{entry.name}' (row {entry.source_row})"
    flags: list[Flag] = []

    size = Attribute("Size", display=1, changes_price=True)
    layout_prices: dict[str, dict[str, int]] = {}
    for layout in layouts:
        prices = _layout_prices(entry, layout.modules)
        if prices is None:
            missing = [m for m in layout.modules if m not in entry.modules]
            flags.append(
                Flag("error", "Size", f"layout '{layout.name}' uses unknown modules {missing}", source)
            )
            continue
        size.add(Option(f"{layout.name}"))
        layout_prices[layout.name] = prices

    cover = Attribute("Cover", display=2, changes_price=True)
    combinations: dict[tuple[str, ...], int] = {}
    priced_categories = set()
    for article in card.articles:
        if article.category not in entry.categories:
            flags.append(
                Flag(
                    "warning",
                    "Cover",
                    f"{article.name} is {article.category or 'uncategorised'}, not priced for {entry.name}",
                    card.path.name,
                )
            )
            continue
        if not article.colours:
            flags.append(
                Flag(
                    "warning",
                    "Cover",
                    f"{article.name} ({article.category}) lists no colours ('{article.note}'); "
                    "add them from the supplier's sample book",
                    card.path.name,
                )
            )
            continue
        priced_categories.add(article.category)
        for code, colour in article.colours:
            name = f"{code}-{colour}-{article.name}".upper().replace(" ", "-")
            swatch = Swatch(name, article.category, article.material, swatch_folder, "")
            cover.add(Option(name, naming.swatch_path(swatch_folder, name), article.material, swatch))
            for layout_name, prices in layout_prices.items():
                combinations[(layout_name, name)] = prices[article.category]
    for category in entry.categories:
        if category not in priced_categories:
            flags.append(
                Flag(
                    "info",
                    "Cover",
                    f"{category} is priced in the list but the swatch card has no materials for it",
                    source,
                )
            )

    attributes = [size, cover]

    if mirror_pairs:
        orientation = Attribute(
            "Orientation", display=1, changes_price=False, options=[Option("As Shown"), Option("Mirrored")]
        )
        for layout in layouts:
            if layout.name not in layout_prices:
                continue
            mirrored = _layout_prices(entry, _mirror(layout.modules, mirror_pairs))
            if mirrored != layout_prices[layout.name]:
                flags.append(
                    Flag(
                        "warning",
                        "Orientation",
                        f"mirrored '{layout.name}' is priced differently or has missing modules",
                        source,
                    )
                )
        attributes.append(orientation)

    if feet_codes:
        available = dict(card.feet("Metal", model=model))
        feet = Attribute("Feet", display=2, changes_price=False)
        for code in feet_codes:
            if code not in available:
                flags.append(
                    Flag("warning", "Feet", f"feet finish {code} is not on the swatch card", card.path.name)
                )
                continue
            name = f"{code} {available[code]}"
            feet.add(Option(name, naming.swatch_path(swatch_folder, name), "Metal"))
        attributes.append(feet)

    stitching = card.stitching()
    if stitching:
        attributes.append(
            Attribute(
                "Contrast Stitching",
                display=1,
                changes_price=False,
                options=[Option(f"{c} {n}") for c, n in stitching],
            )
        )

    for name, values in (extra_dropdowns or {}).items():
        attributes.append(
            Attribute(name, display=1, changes_price=False, options=[Option(v) for v in values])
        )

    return ProductOptions(attributes, combinations, flags)
