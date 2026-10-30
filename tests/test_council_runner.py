"""Offline tests for the resilient five-agent council runner."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Lock

import pytest

from src.bnd.ai_gateway import (
    AIGateway,
    AIResponse,
    GatewayMode,
    InvalidAIResponse,
    LiveAuthorization,
    MockAIProvider,
    ProviderUnavailable,
)
from src.bnd.cost_storage import SQLiteCostStorage
from src.bnd.cost_tracker import BudgetLimits, ModelPricing
from src.bnd.council_runner import CouncilRunner
from src.bnd.decision_rules import decide
from src.bnd.fusion_council import AGENTS, Vote

PRICING = ModelPricing(Decimal("1"), Decimal("4"))   # USD per million tokens


class ScriptedProvider:
    """Fails a given number of times, then answers; records what it saw."""

    def __init__(self, agent, failures=0, error=ProviderUnavailable, model=None, seen=None):
        self.agent, self.failures, self.error = agent, failures, error
        self.model = model or f"vendor/{agent}-model"
        self.seen = seen if seen is not None else []
        self.lock = Lock()

    def expected_model(self):
        return self.model

    def analyze(self, request):
        with self.lock:
            self.seen.append((request.agent, request.context))
            if self.failures:
                self.failures -= 1
                raise self.error("temporary")
        return AIResponse(self.agent, Vote.BUY, f"{self.agent} view", 0.8, self.model,
                          input_tokens=1000, output_tokens=500, provider="TestCloud")


def gateway(providers, storage=None):
    g = AIGateway(cost_storage=storage, pricing={p.model: PRICING for p in providers.values()})
    for agent, provider in providers.items():
        g.register(agent, provider)
    return g


def no_sleep(_):
    pass


def test_round_collects_five_independent_answers_in_parallel():
    seen = []
    providers = {a: ScriptedProvider(a, seen=seen) for a in AGENTS}
    runner = CouncilRunner(gateway(providers), sleep=no_sleep)

    result = runner.run_round("forex", "EURUSD", "Same context for all", "1.00")

    assert result["complete"]
    assert decide(result["council"]).vote == Vote.BUY
    # Identical context, nothing from other agents.
    assert {context for _, context in seen} == {"Same context for all"}
    hashes = {r["request_sha256"] for r in result["agents"].values()}
    assert len(hashes) == 1
    record = result["agents"]["claude"]
    assert record["model"] == "vendor/claude-model" and record["provider"] == "TestCloud"
    # 1,000 in x 1 + 500 out x 4 per million = 0.003 USD per agent.
    assert Decimal(record["cost_usd"]) == Decimal("0.003")
    assert Decimal(result["spent_usd"]) == Decimal("0.015")


def test_bounded_retry_recovers_from_a_transient_failure():
    providers = {a: ScriptedProvider(a, failures=1 if a == "grok" else 0) for a in AGENTS}
    runner = CouncilRunner(gateway(providers), max_attempts=2, sleep=no_sleep)

    result = runner.run_round("crypto", "BTC", "ctx", "1")

    grok = result["agents"]["grok"]
    assert result["complete"] and len(grok["attempts"]) == 2
    assert runner.availability()["grok"]["availability"] == pytest.approx(0.5)


def test_failover_to_a_second_gateway():
    primary = {a: ScriptedProvider(a, failures=9 if a == "gemini" else 0) for a in AGENTS}
    backup = {"gemini": ScriptedProvider("gemini", model="vendor/gemini-backup")}
    runner = CouncilRunner(gateway(primary), gateway(backup), max_attempts=2, sleep=no_sleep)

    result = runner.run_round("index", "SP500", "ctx", "1")

    gemini = result["agents"]["gemini"]
    assert gemini["route"] == "fallback" and gemini["model"] == "vendor/gemini-backup"
    assert result["complete"]


def test_invalid_answers_leave_the_round_incomplete():
    providers = {a: ScriptedProvider(a, failures=9 if a == "deepseek" else 0,
                                     error=InvalidAIResponse) for a in AGENTS}
    runner = CouncilRunner(gateway(providers), max_attempts=2, sleep=no_sleep)

    result = runner.run_round("forex", "EURUSD", "ctx", "1")

    assert not result["complete"] and "NO TRADE" in result["note"]
    assert result["agents"]["deepseek"]["status"] == "failed"
    assert decide(result["council"]).vote == Vote.HOLD
    assert runner.health["deepseek"].consecutive_failures == 2


def test_round_budget_is_checked_before_each_call():
    providers = {a: ScriptedProvider(a) for a in AGENTS}
    g = gateway(providers)   # estimate: 1,000 in + 1,000 out = 0.005 USD per call
    runner = CouncilRunner(g, sleep=no_sleep)

    result = runner.run_round("forex", "EURUSD", "ctx", "0.012", parallel=False)

    # Each call reserves the 0.005 estimate, then only the actual 0.003 is
    # kept: 0.003 + 0.003 + 0.005 fits 0.012, a fourth call (0.009 + 0.005) does not.
    statuses = [result["agents"][a]["status"] for a in AGENTS]
    assert statuses == ["ok", "ok", "ok", "skipped_budget", "skipped_budget"]
    assert sum(len(p.seen) for p in providers.values()) == 3
    assert Decimal(result["spent_usd"]) == Decimal("0.009")


def test_per_model_cap():
    shared = {a: ScriptedProvider(a, model="vendor/shared") for a in AGENTS}
    runner = CouncilRunner(gateway(shared), sleep=no_sleep)

    result = runner.run_round("forex", "EURUSD", "ctx", "1",
                              per_model_budget_usd={"vendor/shared": "0.011"}, parallel=False)

    # Same arithmetic as the round budget, on one model's cap.
    assert [result["agents"][a]["status"] for a in AGENTS].count("ok") == 3


def test_persistent_budget_stops_the_agent(tmp_path):
    storage = SQLiteCostStorage(tmp_path / "costs.db", BudgetLimits(Decimal("0.004"), Decimal("1")))
    providers = {a: ScriptedProvider(a) for a in AGENTS}
    runner = CouncilRunner(gateway(providers, storage), sleep=no_sleep)

    result = runner.run_round("forex", "EURUSD", "ctx", "1", parallel=False)

    # Each call reserves 0.005 against a 0.004 daily limit: refused, never sent.
    assert all(r["status"] == "skipped_budget" for r in result["agents"].values())
    assert sum(len(p.seen) for p in providers.values()) == 0


def test_live_gateway_needs_flag_authorisation_and_budget(tmp_path, monkeypatch):
    storage = SQLiteCostStorage(tmp_path / "c.db", BudgetLimits(Decimal("1"), Decimal("5")))
    providers = {a: ScriptedProvider(a) for a in AGENTS}
    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    live = AIGateway(GatewayMode.LIVE, cost_storage=storage,
                     pricing={p.model: PRICING for p in providers.values()},
                     live_authorization=LiveAuthorization("owner", "0.10", soon, "test"))
    for agent, provider in providers.items():
        live.register(agent, provider)
    runner = CouncilRunner(live, sleep=no_sleep)

    monkeypatch.setenv("BND_ALLOW_LIVE_AI", "false")
    blocked = runner.run_round("forex", "EURUSD", "ctx", "0.10")
    assert not blocked["complete"] and sum(len(p.seen) for p in providers.values()) == 0

    monkeypatch.setenv("BND_ALLOW_LIVE_AI", "true")
    with pytest.raises(ValueError, match="authorised maximum"):
        runner.run_round("forex", "EURUSD", "ctx", "0.50")
    allowed = runner.run_round("forex", "EURUSD", "ctx", "0.10")
    assert allowed["complete"]
    assert storage.summary()["record_count"] == 5


def test_expired_authorisation_blocks(monkeypatch, tmp_path):
    storage = SQLiteCostStorage(tmp_path / "e.db", BudgetLimits(Decimal("1"), Decimal("5")))
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    live = AIGateway(GatewayMode.LIVE, cost_storage=storage,
                     live_authorization=LiveAuthorization("owner", "0.10", past))
    live.register("gpt", MockAIProvider("gpt"))
    monkeypatch.setenv("BND_ALLOW_LIVE_AI", "true")

    with pytest.raises(ProviderUnavailable, match="expired"):
        live.analyze(__import__("src.bnd.ai_gateway", fromlist=["AIRequest"]).AIRequest(
            "gpt", "forex", "EURUSD", "ctx"))
