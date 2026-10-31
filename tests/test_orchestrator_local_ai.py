"""Orchestratorul AI și adaptorul pentru AI local, fără rețea."""

import io
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.bnd import local_ai
from src.bnd.ai_budgets import BudgetSet, ModelOption, limits, ranked_models
from src.bnd.ai_gateway import AIRequest, InvalidAIResponse, ProviderUnavailable
from src.bnd.cost_tracker import ModelPricing
from src.bnd.orchestrator import plan, total_cost

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
OPTIONS = [
    ModelOption("local/llama", 1, ModelPricing(Decimal("0"), Decimal("0"))),
    ModelOption("cheap", 1, ModelPricing(Decimal("0.1"), Decimal("0.4"))),
    ModelOption("standard", 2, ModelPricing(Decimal("1"), Decimal("4"))),
    ModelOption("strong", 3, ModelPricing(Decimal("5"), Decimal("20"))),
]


def test_ranking_puts_the_free_local_model_first_for_simple_tasks_only():
    assert ranked_models("commit_message", OPTIONS)[0] == ("local/llama", Decimal("0"))
    assert [m for m, _ in ranked_models("code_review", OPTIONS)] == ["standard", "strong"]
    assert [m for m, _ in ranked_models("council_vote", OPTIONS)] == ["strong"]
    with pytest.raises(ValueError):
        ranked_models("necunoscut", OPTIONS)


def test_plan_assigns_models_with_fallbacks_and_respects_the_daily_budget(tmp_path):
    budgets = BudgetSet(tmp_path, {"research": limits("0.05", 10), "development": limits(1, 10)})

    rows = plan(["commit_message", "code_review", "council_vote", "council_vote"], OPTIONS,
                budgets, NOW)

    assert [r.model for r in rows] == ["local/llama", "standard", "strong", "strong"]
    assert rows[0].fallbacks == ("cheap", "standard") and rows[0].allowed
    assert rows[1].purpose == "development" and rows[1].allowed
    # Un vot cu modelul puternic costă ~0,027 $; bugetul de cercetare e 0,05 $: încape unul.
    assert [r.allowed for r in rows[2:]] == [True, False]
    assert "nu acoperă" in rows[3].reason
    assert total_cost(rows) == sum(r.estimated_usd for r in rows[:3])


def test_a_purpose_without_a_budget_cannot_spend_but_free_tasks_still_run(tmp_path):
    budgets = BudgetSet(tmp_path, {"development": limits(1, 10)})

    rows = plan(["council_vote", "commit_message"], OPTIONS, budgets, NOW)

    assert not rows[0].allowed and "nu există buget" in rows[0].reason
    assert rows[1].allowed and rows[1].estimated_usd == 0
    with pytest.raises(ValueError):
        plan(["necunoscut"], OPTIONS, budgets, NOW)


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def serve(monkeypatch, content, status=None):
    body = {"model": "llama3", "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20}}
    seen = {}

    def fake(request, timeout):
        seen["url"], seen["timeout"] = request.full_url, timeout
        return Reply(json.dumps(body).encode())

    monkeypatch.setattr(local_ai, "urlopen", fake)
    return seen


def test_local_ai_answers_in_the_common_format_at_zero_cost(monkeypatch):
    seen = serve(monkeypatch, '```json\n{"vote": "SELL", "reasoning": "motiv", "confidence": 0.6}\n```')
    adapter = local_ai.LocalAIAdapter("gemini", "llama3")

    answer = adapter.analyze(AIRequest("gemini", "forex", "EURUSD", "ctx"))

    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert answer.vote.value == "SELL" and answer.provider == "local"
    assert answer.reported_cost() == Decimal("0") and answer.input_tokens == 50
    assert adapter.expected_model() == "llama3"


def test_local_ai_rejects_remote_http_and_bad_answers(monkeypatch):
    for url in ("http://exemplu.ro/v1", "ftp://localhost/v1", "localhost"):
        with pytest.raises(ValueError):
            local_ai.LocalAIAdapter("gpt", "m", base_url=url)
    assert local_ai.LocalAIAdapter("gpt", "m", base_url="http://192.168.1.20:8000/v1")
    assert local_ai.LocalAIAdapter("gpt", "m", base_url="https://ai.exemplu.ro/v1")

    serve(monkeypatch, '{"vote": "BUY", "reasoning": "x", "confidence": 0.5, "extra": 1}')
    with pytest.raises(InvalidAIResponse):
        local_ai.LocalAIAdapter("gpt", "m").analyze(AIRequest("gpt", "x", "X", "c"))
    with pytest.raises(ProviderUnavailable, match="does not match"):
        local_ai.LocalAIAdapter("gpt", "m").analyze(AIRequest("claude", "x", "X", "c"))

    def down(request, timeout):
        raise local_ai.URLError("jos")

    monkeypatch.setattr(local_ai, "urlopen", down)
    with pytest.raises(ProviderUnavailable, match="not reachable"):
        local_ai.LocalAIAdapter("gpt", "m").analyze(AIRequest("gpt", "x", "X", "c"))


def test_council_costs_go_through_the_research_budget(tmp_path):
    from src.bnd.council_daily import live_gateway

    gateway = live_gateway({a: f"m/{a}" for a in ("gpt", "claude", "gemini", "grok", "deepseek")},
                           {f"m/{a}": ModelPricing(Decimal("1"), Decimal("2"))
                            for a in ("gpt", "claude", "gemini", "grok", "deepseek")},
                           tmp_path / "costs.sqlite", NOW, Decimal("0.6"), Decimal("0.8"),
                           Decimal("7"))

    summary = gateway.cost_storage.summary(NOW)
    assert (tmp_path / "costs.sqlite").exists()
    assert summary["daily_limit_usd"] == Decimal("0.8") and summary["monthly_limit_usd"] == Decimal("7")
