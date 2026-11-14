"""The agents' model client: claude-haiku-5-5 through the Anthropic SDK (faked here)."""
import json
from types import SimpleNamespace

import pytest

from app import llm
from app.config import settings


class FakeMessages:
    def __init__(self, reply, stop_reason="end_turn"):
        self.reply, self.stop_reason, self.calls = reply, stop_reason, []

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason=self.stop_reason, stop_details=None,
                               content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.reply)])


@pytest.fixture()
def fake(monkeypatch):
    def make(reply, stop_reason="end_turn"):
        msgs = FakeMessages(reply, stop_reason)
        monkeypatch.setattr(settings, "llm_enabled", True)
        monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(llm, "_client", SimpleNamespace(messages=msgs))
        return msgs
    return make


def test_default_model_is_haiku_5_5():
    assert settings.llm_model == "claude-haiku-5-5"


def test_structured_request_shape(fake):
    msgs = fake(json.dumps({"destination": "Rovaniemi", "nights": 3}))
    schema = llm.obj({"destination": llm.nullable("string"), "nights": llm.nullable("integer")})
    out = llm.complete("Extract the destination.", [("user", "3 nights in Rovaniemi")], schema=schema)
    assert out == {"destination": "Rovaniemi", "nights": 3}
    kw = msgs.calls[0]
    assert kw["model"] == "claude-haiku-5-5"
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": schema}
    assert kw["output_config"]["effort"] == "low"
    assert schema["additionalProperties"] is False and schema["required"] == ["destination", "nights"]
    # current models reject sampling params and prefill
    assert "temperature" not in kw and "thinking" not in kw
    assert kw["messages"][-1]["role"] == "user"


def test_chat_turns_are_normalised(fake):
    msgs = fake("Hey! 👋")
    out = llm.complete("persona", [("model", "earlier bot line"), ("user", "hi"), ("user", "there"), ("bot", "ok")])
    assert out == "Hey! 👋"
    roles = [m["role"] for m in msgs.calls[0]["messages"]]
    assert roles[0] == "user" and roles[-1] == "user"
    assert all(a != b for a, b in zip(roles, roles[1:]))  # consecutive same-role turns merged


def test_refusal_and_truncation_fall_back(fake):
    fake("partial", stop_reason="refusal")
    assert llm.complete("s", [("user", "x")]) is None
    fake('{"destination": "Ro', stop_reason="max_tokens")
    assert llm.complete("s", [("user", "x")], schema=llm.obj({"destination": {"type": "string"}})) is None


def test_disabled_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", False)
    assert llm.available() is False and llm.complete("s", [("user", "x")]) is None


def test_laundry_headline_uses_model(client, fake, monkeypatch):
    msgs = fake("Pop a load of underwear on tonight so you don't run out.")
    from tests.test_laundry_camera import BASE, frame
    st = client.post("/api/v1/laundry/observations", json={"reset": True, "observations": [frame("bf-llm-0", BASE)]}).json()
    assert st["headline"] == {"text": "Pop a load of underwear on tonight so you don't run out.", "by": "claude-haiku-5-5", "basis": st["headline"]["basis"]}
    sent = json.loads(msgs.calls[-1]["messages"][0]["content"][0]["text"])
    assert all(set(s) == {"title", "detail"} for s in sent)  # only computed advice goes to the model
