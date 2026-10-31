"""The Nemotron backend (NVIDIA API catalog, OpenAI-compatible) and how copy uses it."""

import json
from types import SimpleNamespace

import pytest

from fci.content import CopyError, NvidiaBackend, ProductFacts, extract_json, select_backend, write_copy

FACTS = ProductFacts(
    name="Burt Corner Sofa",
    brand="Naustro Fiera Collection",
    product_type="Corner Sofa",
    supplier_texts=["Characterized by sartorial elegance, with crisscross stitching on the headrest."],
)
GOOD = {
    "meta_description": "Burt Corner Sofa by Naustro Fiera Collection, a tailored recliner "
    "with crisscross stitching on the headrest.",
    "long_description": "The Burt Corner Sofa brings sartorial detail to the living room. " * 4,
}


class FakePost:
    def __init__(self, bodies: list[dict], status: int = 200) -> None:
        self.bodies = bodies
        self.status = status
        self.calls: list[dict] = []

    def __call__(self, url: str, headers: dict, json: dict, timeout: float):  # noqa: A002
        self.calls.append({"url": url, "headers": headers, "json": json})
        body = self.bodies[min(len(self.calls) - 1, len(self.bodies) - 1)]
        return SimpleNamespace(status_code=self.status, json=lambda: body, text=str(body))


def completion(content: str, finish: str = "stop", model: str = "nvidia/nemotron-3.5-super-vl-120b-a12b"):
    return {"model": model, "choices": [{"message": {"content": content}, "finish_reason": finish}]}


def test_request_shape() -> None:
    post = FakePost([completion(json.dumps(GOOD))])
    backend = NvidiaBackend("nvapi-test", post=post)
    reply = backend.complete("system text", "user text")
    call = post.calls[0]
    assert call["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer nvapi-test"
    body = call["json"]
    assert body["model"] == "nvidia/nemotron-3.5-super-vl-120b-a12b"
    assert body["messages"][0] == {"role": "system", "content": "system text"}
    assert body["messages"][1]["role"] == "user"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["stream"] is False
    assert json.loads(reply.text) == GOOD
    assert reply.model == "nvidia/nemotron-3.5-super-vl-120b-a12b"


def test_nemotron_copy_is_accepted_and_model_recorded() -> None:
    post = FakePost([completion("```json\n" + json.dumps(GOOD) + "\n```", model="private/nvidia/x")])
    copy = write_copy(FACTS, NvidiaBackend("k", post=post))
    assert copy.source == "ai"
    assert copy.meta_description.startswith("Burt Corner Sofa")
    assert any("private/nvidia/x" in f.source for f in copy.flags)


def test_http_error_falls_back_to_supplier_text() -> None:
    post = FakePost([{"detail": "unauthorised"}], status=401)
    copy = write_copy(FACTS, NvidiaBackend("bad", post=post))
    assert copy.source == "supplier"
    assert any("401" in f.message for f in copy.flags)


def test_content_filter_counts_as_declined() -> None:
    post = FakePost([completion("", finish="content_filter")])
    copy = write_copy(FACTS, NvidiaBackend("k", post=post))
    assert copy.source == "supplier"
    assert len(post.calls) == 1


@pytest.mark.parametrize(
    "text",
    [
        json.dumps(GOOD),
        "```json\n" + json.dumps(GOOD) + "\n```",
        "<think>planning...</think>\n" + json.dumps(GOOD),
        "Here is the copy:\n" + json.dumps(GOOD) + "\nHope this helps.",
    ],
)
def test_extract_json_tolerates_wrappers(text: str) -> None:
    assert extract_json(text) == GOOD


def test_extract_json_rejects_non_json() -> None:
    with pytest.raises(CopyError):
        extract_json("no json here")


def test_backend_selection(monkeypatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("FCI_COPY_MODEL", raising=False)
    assert select_backend() is None
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    backend = select_backend()
    assert isinstance(backend, NvidiaBackend)
    monkeypatch.setenv("FCI_COPY_MODEL", "nvidia/other-model")
    assert select_backend().model == "nvidia/other-model"  # type: ignore[union-attr]
