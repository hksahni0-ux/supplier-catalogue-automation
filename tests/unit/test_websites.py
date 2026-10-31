"""Supplier product pages -> description, image originals, documents. Saved HTML, no network."""

from pathlib import Path

from fci.adapters.cattelan_web import parse_cattelan_page
from fci.adapters.franco_ferri_web import parse_franco_ferri_page

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_cattelan_description() -> None:
    page = parse_cattelan_page((FIXTURES / "cattelan_richard.html").read_text(encoding="utf-8"))
    assert page.name == "RICHARD"
    assert page.description.startswith("The Richard is a double storage bed")
    assert "rolled effect" in page.description
    assert page.year == 2026


def test_cattelan_images_are_full_size_originals_without_duplicates() -> None:
    page = parse_cattelan_page((FIXTURES / "cattelan_richard.html").read_text(encoding="utf-8"))
    assert len(page.images) == 6  # main view + 5 gallery images
    assert all("/multimedia/generic/" in url for url in page.images)
    assert len(set(page.images)) == len(page.images)


def test_franco_ferri_page() -> None:
    page = parse_franco_ferri_page((FIXTURES / "francoferri_berte.html").read_text(encoding="utf-8"))
    assert page.name == "BERTE'"
    assert page.description.startswith("Characterized by sartorial elegance")
    assert page.collection == "RELAX COLLECTION"
    assert page.documents == {"technical_sheet": "https://francoferri.it/pdf/berte.pdf"}


def test_franco_ferri_images_collapse_wordpress_sizes() -> None:
    page = parse_franco_ferri_page((FIXTURES / "francoferri_berte.html").read_text(encoding="utf-8"))
    assert page.images == [
        "https://francoferri.it/wp-content/uploads/2025/10/berte1.jpg",
        "https://francoferri.it/wp-content/uploads/2025/10/Berte2.jpg",
        "https://francoferri.it/wp-content/uploads/2025/10/Berte3.jpg",
    ]
