"""Copy rules: what Nemotron's answer must satisfy, and the supplier-text fallback."""

import json
from types import SimpleNamespace

from fci.content import NvidiaBackend, ProductFacts, write_copy

FACTS = ProductFacts(
    name="Richard Double Bed",
    brand="Cattelan Italia",
    product_type="Double Bed",
    supplier_texts=[
        "The Richard is a double storage bed with no visible feet and a thick low-to-the-floor bed "
        "surround. The edges are curved outwards, expanding the supporting base at the bottom.",
        "Upholstered bed covered in fabric, micro nubuck, synthetic leather or soft leather as per "
        "sample card. Slats included. Optional: pull-up slats with container.",
    ],
    specs=["Sizes: A - W.245 X D.234 X H.102 cm"],
)


def nemotron(answers: list[dict]) -> tuple[NvidiaBackend, list[dict]]:
    calls: list[dict] = []

    def post(url, headers, json, timeout):  # noqa: A002
        calls.append(json)
        answer = answers[min(len(calls) - 1, len(answers) - 1)]
        body = {"model": "nvidia/x", "choices": [{"message": {"content": _dumps(answer)}}]}
        return SimpleNamespace(status_code=200, json=lambda: body, text="")

    return NvidiaBackend("k", post=post), calls


def _dumps(answer: dict) -> str:
    return json.dumps(answer)


def test_without_backend_uses_supplier_text_and_flags_for_review() -> None:
    copy = write_copy(FACTS, None)
    assert copy.source == "supplier"
    assert len(copy.meta_description) <= 160
    assert copy.meta_description.startswith("The Richard is a double storage bed")
    assert "Slats included" in copy.long_description
    assert any("review" in f.message for f in copy.flags)


def test_valid_copy_is_used_and_prompt_carries_supplier_facts() -> None:
    backend, calls = nemotron(
        [
            {
                "meta_description": "Richard Double Bed by Cattelan Italia: a sculptural storage bed "
                "with a softly curved base and rolled headboard.",
                "long_description": "The Richard Double Bed is a sculptural storage bed. " * 5,
            }
        ]
    )
    copy = write_copy(FACTS, backend)
    assert copy.source == "ai"
    assert copy.meta_description.startswith("Richard Double Bed by Cattelan Italia")
    prompt = calls[0]["messages"][1]["content"]
    assert "Slats included" in prompt and "W.245" in prompt


def test_overlong_meta_is_retried_then_falls_back() -> None:
    backend, calls = nemotron([{"meta_description": "x" * 200, "long_description": "fine " * 30}])
    copy = write_copy(FACTS, backend)
    assert len(calls) == 2
    assert copy.source == "supplier"
    assert len(copy.meta_description) <= 160


def test_copy_mentioning_a_price_is_rejected() -> None:
    backend, _ = nemotron(
        [{"meta_description": "From £4,121 - the Richard bed.", "long_description": "ok " * 30}]
    )
    copy = write_copy(FACTS, backend)
    assert copy.source == "supplier"
    assert any("price" in f.message for f in copy.flags)


def test_bland_short_meta_is_retried_then_falls_back() -> None:
    backend, calls = nemotron(
        [
            {
                "meta_description": "Richard Double Bed by Cattelan Italia at FCI London",
                "long_description": "The Richard Double Bed is a sculptural storage bed. " * 5,
            }
        ]
    )
    copy = write_copy(FACTS, backend)
    assert len(calls) == 2
    assert copy.source == "supplier"
    assert any("too short" in f.message for f in copy.flags)
