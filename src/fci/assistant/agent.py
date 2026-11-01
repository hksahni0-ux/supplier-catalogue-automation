"""The chat loop: Nemotron decides which tools to call; the answer must rest on their results.

Guard against made-up figures: every price-like number in the final answer (100 and above,
or any decimal or percentage) must appear in this turn's tool results or in the user's own
messages. If not, the model is told which numbers failed and gets one more try; a second
failure is replaced by a plain "couldn't verify" message, so an invented price never shows.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests

from fci.content import NVIDIA_MODEL, NVIDIA_URL

SYSTEM = """You are the FCI London catalogue assistant for the back-office team.
You answer questions about supplier products that the automation has processed, and you can
propose re-running products from the latest price lists in Google Drive.

Rules:
- Use the tools for every fact. Never answer a price, count or date from memory.
- Quote numbers exactly as the tools give them, with the currency the tool reports. Prices are
  the supplier's list prices (FCI's website applies its own uplift); say so if asked about retail.
- When several prices match, give every one, each with its size and cover group; don't pick one.
- If a tool finds nothing, say what you looked for and suggest how to narrow or widen it.
- To run or re-price products, call propose_run and tell the user to press Confirm. Never say
  a run has happened.
- Be brief and plain: one or two sentences, or a short list. British English."""

NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)(\s*%)?")
FALLBACK = (
    "I couldn't verify that answer against the catalogue data, so I won't guess. "
    "Try asking about one product, size or cover."
)
CORRECTION = (
    "Your answer used numbers that are not in the tool results: {numbers}. Answer again using only "
    "numbers from tool results; call a tool if you need more data."
)
STUCK = "I couldn't finish looking that up. Try a narrower question, e.g. one product and one size."


def numbers_in(text: str) -> set[str]:
    """Price-like numbers: 100 and above, decimals and percentages (small counts are left alone)."""
    found = set()
    for digits, percent in NUMBER.findall(text):
        value = digits.replace(",", "").rstrip(".")
        if not value:
            continue
        if percent or "." in value or float(value) >= 100:
            found.add(value)
    return found


class ChatModel(Protocol):
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]: ...


class ToolBox(Protocol):
    def schemas(self) -> list[dict[str, Any]]: ...
    def call(self, name: str, arguments: str) -> Any: ...


@dataclass
class AssistantReply:
    text: str
    verified: bool
    proposals: list[dict[str, Any]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)


class NvidiaChat:
    """Nemotron on the NVIDIA API (OpenAI-compatible), with tool calling and reasoning off."""

    def __init__(
        self,
        api_key: str,
        model: str = NVIDIA_MODEL,
        post: Callable[..., Any] = requests.post,
        url: str = NVIDIA_URL,
    ) -> None:
        self.api_key, self.model, self._post, self._url = api_key, model, post, url

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        response = self._post(
            self._url,
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
            json={
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.2,
                "max_tokens": 900,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=120,
        )
        if response.status_code >= 400:
            raise ConnectionError(f"NVIDIA API returned {response.status_code}")
        message: dict[str, Any] = response.json()["choices"][0]["message"]
        return message


class Assistant:
    def __init__(self, model: ChatModel, tools: ToolBox, max_rounds: int = 5) -> None:
        self.model, self.tools, self.max_rounds = model, tools, max_rounds

    def reply(self, history: list[dict[str, Any]]) -> AssistantReply:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}, *history]
        allowed = set().union(
            *(numbers_in(str(m.get("content") or "")) for m in history if m["role"] == "user")
        )
        proposals: list[dict[str, Any]] = []
        used: list[str] = []
        corrected = False
        rounds = 0
        while True:
            message = self.model.chat(messages, self.tools.schemas())
            calls = message.get("tool_calls") or []
            if calls:
                rounds += 1
                if rounds > self.max_rounds:
                    return AssistantReply(STUCK, False, proposals, used)
                messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
                for call in calls:
                    name, arguments = call["function"]["name"], call["function"].get("arguments") or "{}"
                    result = self.tools.call(name, arguments)
                    used.append(name)
                    if isinstance(result, dict) and "proposal" in result:
                        proposals.append(result["proposal"])
                    payload = json.dumps(result, ensure_ascii=False)
                    allowed |= numbers_in(payload)
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": payload})
                continue
            text = (message.get("content") or "").strip()
            unverified = sorted(numbers_in(text) - allowed)
            if not unverified:
                return AssistantReply(text, True, proposals, used)
            if corrected:
                return AssistantReply(FALLBACK, False, proposals, used)
            corrected = True
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": CORRECTION.format(numbers=", ".join(unverified))})
