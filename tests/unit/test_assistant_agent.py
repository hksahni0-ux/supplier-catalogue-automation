import json

from fci.assistant.agent import Assistant, NvidiaChat, numbers_in


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def schemas(self) -> list[dict]:
        return [{"type": "function", "function": {"name": "get_price"}}]

    def call(self, name: str, arguments: str) -> dict:
        args = json.loads(arguments)
        self.calls.append((name, args))
        if name == "propose_run":
            return {"proposal": {"action": "run", "skus": ["cattelan-italia-806"], "publish": True}}
        return {"product": "Richard Double Bed", "currency": "EUR", "prices": [{"price": 7192, "size": "D"}]}


class ScriptedModel:
    """Plays back assistant messages in order and records what it was sent."""

    def __init__(self, *messages: dict) -> None:
        self.messages, self.sent = list(messages), []

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        self.sent.append([dict(m) for m in messages])
        return self.messages.pop(0)


def tool_call(name: str, args: dict, call_id: str = "c1") -> dict:
    function = {"name": name, "arguments": json.dumps(args)}
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": call_id, "type": "function", "function": function}],
    }  # noqa: E501


def say(text: str) -> dict:
    return {"role": "assistant", "content": text}


ASK = [{"role": "user", "content": "What does Richard size D cost in glove leather?"}]


def test_answer_quotes_the_tool_result() -> None:
    model = ScriptedModel(tool_call("get_price", {"product": "Richard", "size": "D"}), say("€7,192 (EUR)."))
    tools = FakeTools()
    reply = Assistant(model, tools).reply(ASK)
    assert reply.text == "€7,192 (EUR)." and reply.verified
    assert tools.calls == [("get_price", {"product": "Richard", "size": "D"})]
    tool_message = model.sent[1][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "c1"


def test_a_number_not_in_any_tool_result_gets_one_correction() -> None:
    model = ScriptedModel(
        tool_call("get_price", {"product": "Richard"}),
        say("It costs €7,500."),  # invented
        say("It costs €7,192."),
    )
    reply = Assistant(model, FakeTools()).reply(ASK)
    assert reply.text == "It costs €7,192." and reply.verified
    correction = model.sent[2][-1]["content"]
    assert "7500" in correction and "tool results" in correction


def test_a_repeated_invented_number_is_never_shown() -> None:
    model = ScriptedModel(
        tool_call("get_price", {"product": "Richard"}), say("€7,500."), say("Still €7,500.")
    )
    reply = Assistant(model, FakeTools()).reply(ASK)
    assert not reply.verified and "7,500" not in reply.text and "couldn't verify" in reply.text


def test_numbers_the_user_gave_may_be_repeated() -> None:
    ask = [{"role": "user", "content": "Is 4121 the Richard base price?"}]
    reply = Assistant(ScriptedModel(say("You asked about 4121; let me check.")), FakeTools()).reply(ask)
    assert reply.verified


def test_proposals_are_returned_for_the_confirm_button_not_run() -> None:
    model = ScriptedModel(
        tool_call("propose_run", {"products": ["Thomas"]}), say("Press Confirm to run Thomas.")
    )
    reply = Assistant(model, FakeTools()).reply([{"role": "user", "content": "re-run Thomas"}])
    assert reply.proposals == [{"action": "run", "skus": ["cattelan-italia-806"], "publish": True}]


def test_tool_rounds_are_capped() -> None:
    model = ScriptedModel(*[tool_call("get_price", {"product": "Richard"}, f"c{i}") for i in range(10)])
    reply = Assistant(model, FakeTools(), max_rounds=3).reply(ASK)
    assert not reply.verified and "couldn't" in reply.text


def test_small_counts_are_not_policed_but_prices_and_percentages_are() -> None:
    assert numbers_in("10 sizes, €7,192, +4.0% and 2,340 rows") == {"7192", "4.0", "2340"}


def test_nvidia_chat_sends_tools_with_thinking_off() -> None:
    sent = {}

    class Response:
        status_code = 200

        def json(self) -> dict:
            return {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}

    def post(url: str, **kwargs) -> Response:
        sent.update(kwargs["json"])
        return Response()

    assert (
        NvidiaChat("key", post=post).chat([{"role": "user", "content": "x"}], [{"t": 1}])["content"] == "hi"
    )
    assert sent["tools"] == [{"t": 1}] and sent["chat_template_kwargs"] == {"enable_thinking": False}


def test_instructions_ask_for_every_matching_price() -> None:
    from fci.assistant.agent import SYSTEM

    assert "every" in SYSTEM and "cover group" in SYSTEM
