"""Offline tests for manual connectivity scripts; never contact OpenRouter."""

import json

import pytest

from src.bnd import manual_live_review, three_agents_live


class FakeResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit):
        return self.raw[:limit]


@pytest.fixture
def review_env(monkeypatch):
    values = {
        "CONFIRM": "YES",
        "LIMIT_CONFIRM": "YES",
        "OPENROUTER_API_KEY": "test-key",
        "GPT_MODEL": "openai/gpt-test",
        "CLAUDE_MODEL": "anthropic/claude-test",
        "GPT_IN": "1",
        "GPT_OUT": "2",
        "CLAUDE_IN": "1",
        "CLAUDE_OUT": "2",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def three_env(monkeypatch):
    values = {
        "CONFIRM": "YES",
        "LIMIT_CONFIRM": "YES",
        "OPENROUTER_API_KEY": "test-key",
        "GEMINI_MODEL": "google/gemini-test",
        "DEEPSEEK_MODEL": "deepseek/deepseek-test",
        "GROK_MODEL": "x-ai/grok-test",
    }
    for agent in ("GEMINI", "DEEPSEEK", "GROK"):
        values[agent + "_IN"] = "1"
        values[agent + "_OUT"] = "2"
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_review_preflight_passes(review_env):
    assert manual_live_review.preflight() > 0


@pytest.mark.parametrize("price", ["", "abc"])
def test_review_invalid_price_is_clear_error(review_env, monkeypatch, price):
    monkeypatch.setenv("CLAUDE_OUT", price)

    with pytest.raises(RuntimeError, match="price"):
        manual_live_review.preflight()


def test_review_prompt_uses_real_newlines(review_env, monkeypatch):
    prompts = []

    def fake_call(agent, prompt):
        prompts.append(prompt)
        return "proposal text"

    monkeypatch.setattr(manual_live_review, "call", fake_call)
    monkeypatch.setattr("sys.argv", ["manual_live_review", "--execute"])

    manual_live_review.main()

    # GPT proposal, Claude critique, GPT revision.
    assert len(prompts) == 3
    assert all("\\n" not in prompt for prompt in prompts)
    assert "\nOriginal task: " in prompts[1]
    assert "\nClaude critique: " in prompts[2]


def test_review_call_rejects_missing_content(review_env, monkeypatch):
    monkeypatch.setattr(
        manual_live_review,
        "urlopen",
        lambda request, timeout: FakeResponse(
            {"model": "openai/gpt-test", "choices": []}
        ),
    )

    with pytest.raises(RuntimeError, match="no message content"):
        manual_live_review.call("GPT", "task")


@pytest.mark.parametrize("price", ["", "abc"])
def test_three_invalid_price_is_clear_error(three_env, monkeypatch, price):
    monkeypatch.setenv("GROK_IN", price)

    with pytest.raises(RuntimeError, match="price"):
        three_agents_live.preflight()


def test_three_execute_verifies_each_agent(three_env, monkeypatch, capsys):
    def fake_urlopen(request, timeout):
        model = json.loads(request.data)["model"]
        return FakeResponse(
            {
                "model": model,
                "choices": [{"message": {"content": "Test whitespace."}}],
                "usage": {"prompt_tokens": 10},
            }
        )

    monkeypatch.setattr(three_agents_live, "urlopen", fake_urlopen)

    three_agents_live.execute()

    output = capsys.readouterr().out
    for agent in ("GEMINI", "DEEPSEEK", "GROK"):
        assert agent + " verified:" in output


def test_three_execute_rejects_invalid_response(three_env, monkeypatch):
    monkeypatch.setattr(
        three_agents_live,
        "urlopen",
        lambda request, timeout: FakeResponse({"error": "bad"}),
    )

    with pytest.raises(RuntimeError, match="invalid response"):
        three_agents_live.execute()
