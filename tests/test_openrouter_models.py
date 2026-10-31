"""OpenRouter catalogue parsing, offline."""

from decimal import Decimal

from src.bnd import openrouter_models as om

PAYLOAD = {"data": [
    {"id": "anthropic/claude-opus-5.5", "context_length": 200000,
     "pricing": {"prompt": "0.000015", "completion": "0.000075"}},
    {"id": "openai/gpt-4o-mini", "context_length": 128000,
     "pricing": {"prompt": "0.00000015", "completion": "0.0000006"}},
    {"id": "meta-llama/llama-4", "pricing": {"prompt": "0.000001", "completion": "0.000001"}},
    {"id": "x-ai/grok-broken", "pricing": {"prompt": "-1", "completion": "0.000001"}},
    {"id": "google/gemini-free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "deepseek/no-price", "pricing": {}},
]}


def test_prices_become_dollars_per_million_and_cost_per_call():
    rows = {r["id"]: r for r in om.parse(PAYLOAD)}

    opus = rows["anthropic/claude-opus-5.5"]
    assert opus["input_per_million"] == Decimal("15") and opus["output_per_million"] == Decimal("75")
    # 3,000 in x 15 + 600 out x 75 per million = 0.09 dollars a call.
    assert opus["call_usd"] == Decimal("0.09")
    assert rows["google/gemini-free"]["call_usd"] == 0


def test_other_vendors_and_bad_prices_are_left_out():
    ids = [r["id"] for r in om.parse(PAYLOAD)]

    assert "meta-llama/llama-4" not in ids and "x-ai/grok-broken" not in ids
    assert "deepseek/no-price" not in ids


def test_match_filter_and_markdown(capsys, monkeypatch):
    assert [r["id"] for r in om.parse(PAYLOAD, match="OPUS")] == ["anthropic/claude-opus-5.5"]
    monkeypatch.setattr(om, "fetch", lambda: PAYLOAD)

    assert om.main(["--vendors", "openai"]) == 0
    out = capsys.readouterr().out
    assert "`openai/gpt-4o-mini`" in out and "claude" not in out


def test_network_failure_is_a_clear_error(monkeypatch, capsys):
    def down():
        raise om.URLError("down")

    monkeypatch.setattr(om, "fetch", down)

    assert om.main([]) == 2 and "Error" in capsys.readouterr().err
