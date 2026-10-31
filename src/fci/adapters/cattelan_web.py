"""cattelanitalia.com product page: description, year and gallery originals."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from fci.adapters.web_common import SupplierPage, clean_text, unique

UUID_RE = re.compile(r"/multimedia/\w+/([0-9a-f-]{36})\.")


def parse_cattelan_page(html: str) -> SupplierPage:
    soup = BeautifulSoup(html, "html.parser")
    name_tag = soup.select_one(".col-dx .name p")
    name = clean_text(name_tag.get_text()) if name_tag else ""

    text_tag = soup.select_one(".text-scheda")
    description = clean_text(text_tag.get_text(" ")) if text_tag else ""
    description = re.sub(r"^model\s+", "", description)  # stray label the page renders before the text
    description = re.sub(r"\s+([.,;:])", r"\1", description)

    year_tag = soup.select_one(".anno p")
    year_match = re.search(r"\d{4}", year_tag.get_text()) if year_tag else None

    # Main view, then the gallery. Prefer the "generic" (original) file over the hd/ld renditions.
    candidates: list[str] = []
    for img in soup.select("img[data-download], img.cGalleryImg"):
        url = img.get("data-download") or img.get("data-full") or img.get("src") or ""
        if "/multimedia/" in str(url):
            candidates.append(str(url))
    by_uuid: dict[str, str] = {}
    for url in candidates:
        match = UUID_RE.search(url)
        if match and match.group(1) not in by_uuid:
            by_uuid[match.group(1)] = url
    return SupplierPage(
        name=name,
        description=description,
        images=unique(list(by_uuid.values())),
        year=int(year_match.group(0)) if year_match else None,
    )
