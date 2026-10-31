"""francoferri.it (WordPress/Elementor) product page: description, images, technical sheet."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from fci.adapters.web_common import SupplierPage, clean_text, unique
from fci.naming import slugify

WP_SIZE_RE = re.compile(r"-\d+x\d+(?=\.\w+$)")
UPLOAD_RE = re.compile(
    r"https?://[^\"'\s)]+/wp-content/uploads/[^\"'\s)]+\.(?:jpe?g|png|webp)", re.IGNORECASE
)


def parse_franco_ferri_page(html: str, product_slug: str | None = None) -> SupplierPage:
    soup = BeautifulSoup(html, "html.parser")
    # The product heading is the h2 that matches the page title ("Berté – Franco Ferri Italia").
    page_title = soup.title.get_text() if soup.title else ""
    title_key = slugify(re.split(r"\s[–|-]\s", page_title)[0])
    headings = soup.select("h2.elementor-heading-title")
    heading = next((h for h in headings if slugify(h.get_text()) == title_key), None)
    name = clean_text(heading.get_text()) if heading else ""

    description = ""
    collection = ""
    if heading:
        previous = heading.find_previous("p", class_="elementor-heading-title")
        collection = clean_text(previous.get_text()) if previous else ""
        paragraph = heading.find_next("p")
        description = clean_text(paragraph.get_text(" ")) if paragraph else ""
    description = re.sub(r"\s+([.,;:])", r"\1", description)

    # Product images: WordPress originals (size suffix removed) whose filename names the product.
    key = (product_slug or re.sub(r"[^a-z]", "", name.lower()))[:5]
    images = []
    for url in UPLOAD_RE.findall(html):
        original = WP_SIZE_RE.sub("", url)
        if key and key in urlparse(original).path.rsplit("/", 1)[-1].lower():
            images.append(original)

    documents = {}
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        if href.lower().endswith(".pdf") and "/pdf/" in href:
            documents["technical_sheet"] = href
            break
    return SupplierPage(
        name=name, description=description, images=unique(images), documents=documents, collection=collection
    )
