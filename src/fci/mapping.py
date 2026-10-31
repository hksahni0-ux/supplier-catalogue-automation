"""Turn a parsed grid price list into FCI attributes and price combinations.

Grid suppliers (Cattelan) price each size against material groups. Every material group
expands into its swatches, so each (size, swatch) pair gets the price of its column.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from fci.adapters.cattelan_pdf import ProductEntry, SizeRow
from fci.brands import Brand
from fci.model import Attribute, Flag, Option, ProductOptions, Swatch
from fci.naming import Naming, size_label

GroupLookup = Callable[[str], list[Swatch]]
FinishLookup = Callable[[int, str, str, str], Swatch | None]
FINISH_CODE_RE = re.compile(r"\b[A-Z]{2,}\d+\b")


def _size_name(row: SizeRow, qualifiers: dict[str, str], variant_keys: list[str]) -> str:
    base = (
        size_label(row.code, row.width, row.depth, row.height)
        if row.code and row.depth is not None and row.height is not None
        else row.raw
    )
    suffix = " ".join(qualifiers[k] for k in variant_keys if k in qualifiers)
    return f"{base} {suffix}" if suffix else base


def _qualifier_attributes(
    entry: ProductEntry, brand: Brand, find: FinishLookup | None, naming: Naming, source: str
) -> tuple[list[Attribute], list[Flag]]:
    """Table notes that list finish codes (e.g. 'Feet: GFM18 / GFM69') -> swatch attributes."""
    attributes: dict[str, Attribute] = {}
    flags: list[Flag] = []
    for table in entry.tables:
        for key, value in table.qualifiers.items():
            spec = brand.qualifier_attributes.get(key)
            if spec is None or find is None:
                continue
            attribute = attributes.setdefault(spec["attribute"], Attribute(spec["attribute"], 2, False))
            for code in FINISH_CODE_RE.findall(value):
                swatch = find(int(spec["category"]), code, spec["grouping"], spec["folder"])
                if swatch is None:
                    flags.append(
                        Flag("warning", spec["attribute"], f"finish {code} not in the catalogue", source)
                    )
                    continue
                attribute.add(
                    Option(swatch.name, naming.swatch_path(swatch.folder, swatch.name), swatch.label, swatch)
                )
    return list(attributes.values()), flags


def build_options(
    entry: ProductEntry, brand: Brand, groups: GroupLookup, find: FinishLookup | None = None
) -> ProductOptions:
    naming = Naming(entry.title.title(), "", brand.name, brand.slug)
    variant_keys = brand.size_variant_qualifiers or ["Slats"]
    size = Attribute("Size", display=1, changes_price=True)
    cover = Attribute("Cover", display=2, changes_price=True)
    combinations: dict[tuple[str, ...], int] = {}
    flags: list[Flag] = []
    source = f"{brand.price_list.get('file', 'price list')} p.{entry.page_number}"

    for table in entry.tables:
        for column in table.columns:
            group_keys = brand.groups_for_column(column)
            if group_keys is None:
                flags.append(
                    Flag("error", "Cover", f"price column '{column}' has no material mapping", source)
                )
                continue
            swatches = [s for key in group_keys for s in groups(key)]
            if not swatches:
                flags.append(Flag("warning", "Cover", f"no swatches found for '{column}'", source))
            for row in table.rows:
                size_name = _size_name(row, table.qualifiers, variant_keys)
                size.add(Option(size_name))
                price = row.prices.get(column)
                if price is None:
                    flags.append(
                        Flag("warning", "price", f"{size_name} / {column}: blank in price list", source)
                    )
                    continue
                for swatch in swatches:
                    key = (size_name, swatch.name)
                    if key in combinations and combinations[key] != price:
                        flags.append(
                            Flag(
                                "warning",
                                "price",
                                f"{swatch.name} priced twice for {size_name}; kept {combinations[key]}",
                                source,
                            )
                        )
                        continue
                    combinations.setdefault(key, price)
                    cover.add(
                        Option(
                            swatch.name, naming.swatch_path(swatch.folder, swatch.name), swatch.label, swatch
                        )
                    )

    for table in entry.tables:
        seen: dict[tuple[object, ...], str] = {}
        for row in table.rows:
            dims = (row.width, row.depth, row.height)
            if dims in seen:
                label = " ".join(table.qualifiers.values()) or "standard"
                message = (
                    f"sizes {seen[dims]} and {row.code} ({label}) have identical printed dimensions; "
                    "they differ only in the drawing (e.g. mattress size), "
                    "so add that to the option name by hand"
                )
                if any(f.message == message for f in flags):
                    continue
                flags.append(
                    Flag(
                        "warning",
                        "Size",
                        message,
                        source,
                    )
                )
            else:
                seen[dims] = row.code or row.raw

    missing: dict[str, int] = {}
    for size_option in size.options:
        for cover_option in cover.options:
            if (size_option.name, cover_option.name) not in combinations:
                missing[size_option.name] = missing.get(size_option.name, 0) + 1
    for size_name, count in missing.items():
        flags.append(
            Flag(
                "info",
                "price",
                f"{count} covers not priced for '{size_name}' in the price list; "
                "those combinations are left out, not estimated",
                source,
            )
        )
    extra, extra_flags = _qualifier_attributes(entry, brand, find, naming, source)
    return ProductOptions([size, cover, *extra], combinations, flags + extra_flags)
