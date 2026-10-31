"""Calitatea consiliului AI: trasabilitate, erori de agent, contract de răspuns, analiză."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.bnd import council_analytics as ca
from src.bnd import council_daily as cd
from src.bnd.ai_gateway import AIGateway, GatewayMode, MockAIProvider, ProviderUnavailable
from src.bnd.council_runner import CouncilRunner
from src.bnd.decision_registry import DecisionRegistry
from src.bnd.decision_rules import CouncilDecision, DecisionRule
from src.bnd.fusion_council import AGENTS, FusionCouncil, Opinion, Vote
from src.bnd.response_contract import INCOMPLETE, INVALID, VALID, validate
from tests.test_council_daily import MARKETS, series, upto  # noqa: F401


# --- trasabilitate ---------------------------------------------------------------------

def test_every_decision_keeps_a_trace_with_data_version_and_per_agent_facts(tmp_path, series):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    data = upto(series, 700)
    now = data["SP500"][-1].open_time + timedelta(days=1)

    cd.run_markets(data, MARKETS, cd.simulated_gateway(), registry, now, Decimal("0.6"))

    trace = registry.meta(f"{now.date().isoformat()}:SP500")["trace"]
    assert trace["data_through"] == data["SP500"][-1].open_time.isoformat()
    assert len(trace["context_sha256"]) == 64 and trace["at"] == now.isoformat()
    assert set(trace["agents"]) == set(AGENTS)
    assert all(a["status"] == "ok" and a["request_sha256"] for a in trace["agents"].values())


def test_original_and_revised_votes_are_both_kept_with_minority_opinions(tmp_path):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    council = FusionCouncil()
    council.submit(Opinion("gpt", Vote.BUY, "a", 0.8))
    council.submit(Opinion("claude", Vote.SELL, "b", 0.6))
    for other in AGENTS:
        if other not in ("gpt", "claude"):
            council.submit(Opinion(other, Vote.HOLD, "d", 0.5))
    council.revise(Opinion("claude", Vote.BUY, "c", 0.7))
    decision = CouncilDecision(Vote.BUY, DecisionRule.MAJORITY, {}, (), (), False, ())
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    registry.record("2026-11-01:X", now, "X", 10.0, council, decision)

    import sqlite3
    rows = sqlite3.connect(tmp_path / "r.sqlite").execute(
        "SELECT agent, stage, vote FROM votes ORDER BY agent, stage").fetchall()
    assert ("claude", "initial", "SELL") in rows and ("claude", "final", "BUY") in rows


# --- erori de agent ----------------------------------------------------------------------

class Raises:
    def __init__(self, exc):
        self.exc = exc

    def analyze(self, request):
        raise self.exc


def gateway_with(**broken):
    gateway = AIGateway(GatewayMode.MOCK)
    for agent in AGENTS:
        gateway.register(agent, MockAIProvider(agent, Vote.BUY, 0.7))
    for agent, exc in broken.items():
        gateway.providers[agent] = Raises(exc)
    return gateway


@pytest.mark.parametrize("exc", [TimeoutError("lent"), ConnectionResetError("rupt"),
                                 KeyError("câmp"), ValueError("json"),
                                 ProviderUnavailable("rate limit")])
def test_a_broken_agent_never_stops_the_round_and_no_vote_is_invented(exc):
    runner = CouncilRunner(gateway_with(grok=exc), max_attempts=2, sleep=lambda s: None)

    outcome = runner.run_round("index", "SP500", "context", Decimal("0.5"))

    assert outcome["complete"] is False
    assert outcome["agents"]["grok"]["status"] == "failed"
    assert "grok" not in outcome["council"].initial_opinions
    assert len(outcome["council"].initial_opinions) == len(AGENTS) - 1
    assert len(outcome["agents"]["grok"]["attempts"]) == 2          # reîncercări limitate


def test_all_agents_failing_gives_an_empty_round_not_a_crash():
    runner = CouncilRunner(gateway_with(**{a: TimeoutError() for a in AGENTS}), max_attempts=1,
                           sleep=lambda s: None)

    outcome = runner.run_round("index", "SP500", "context", Decimal("0.5"))

    assert outcome["complete"] is False and not outcome["council"].initial_opinions


# --- contract de răspuns ---------------------------------------------------------------

GOOD = {"vote": "BUY", "confidence": 0.7, "arguments": ["trend"], "evidence": ["RSI 55"],
        "risks": ["gap"], "abstention_reason": ""}


def test_complete_answer_is_valid():
    assert validate(GOOD).status == VALID


@pytest.mark.parametrize("change,status", [
    ({"vote": "MAYBE"}, INVALID), ({"confidence": 1.5}, INVALID), ({"confidence": True}, INVALID),
    ({"confidence": float("nan")}, INVALID), ({"arguments": "text"}, INVALID),
    ({"risks": []}, INCOMPLETE), ({"evidence": []}, INCOMPLETE),
    ({"vote": "HOLD", "abstention_reason": ""}, INCOMPLETE)])
def test_bad_or_partial_answers_are_marked_explicitly(change, status):
    assert validate({**GOOD, **change}).status == status


def test_non_objects_are_invalid():
    assert validate("BUY").status == INVALID and validate(None).status == INVALID


def test_hold_with_a_reason_is_valid():
    assert validate({**GOOD, "vote": "HOLD", "abstention_reason": "semnale contradictorii"}).status == VALID


# --- analiză -----------------------------------------------------------------------------

def make_registry(tmp_path, cases):
    """cases: (symbol, votes{agent:(vote,conf)}, council_vote, outcome, bot_signal)."""
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    for i, (symbol, votes, council_vote, outcome, bot) in enumerate(cases):
        council = FusionCouncil()
        for agent, (vote, conf) in votes.items():
            council.submit(Opinion(agent, Vote(vote), "x", conf))
        decision = CouncilDecision(Vote(council_vote), DecisionRule.MAJORITY, {}, (), (), False, ())
        when = start + timedelta(days=i)
        registry.record(f"{when.date()}:{symbol}", when, symbol, 100.0, council, decision,
                        meta={"bot_signal": bot})
        import sqlite3
        db = sqlite3.connect(tmp_path / "r.sqlite")
        db.execute("UPDATE decisions SET settled_at = ?, outcome_price = ?, outcome_return = ?"
                   " WHERE id = ?", (when.isoformat(), 100 * (1 + outcome), outcome,
                                     f"{when.date()}:{symbol}"))
        db.commit(); db.close()
    return tmp_path / "r.sqlite"


def test_scoreboard_calibration_minority_and_hold(tmp_path):
    path = make_registry(tmp_path, [
        ("SP500", {"gpt": ("BUY", 0.9), "claude": ("BUY", 0.9), "gemini": ("SELL", 0.6)}, "BUY", 0.02, 1),
        ("SP500", {"gpt": ("BUY", 0.9), "claude": ("HOLD", 0.5), "gemini": ("SELL", 0.6)}, "HOLD", -0.03, -1),
        ("GOLD", {"gpt": ("HOLD", 0.5), "claude": ("BUY", 0.9), "gemini": ("BUY", 0.6)}, "BUY", 0.004, 1),
    ])

    report = ca.analyse(path)

    gpt = report["agents"]["gpt"]
    assert gpt["calls"] == 2 and gpt["hit_rate"] == 0.5          # a avut dreptate o dată din două
    assert gpt["calibration"][0]["declared"] == pytest.approx(0.9) and gpt["calibration_gap"] == pytest.approx(0.4)
    gemini = report["agents"]["gemini"]
    assert gemini["minority_calls"] == 2 and gemini["minority_right"] == 1   # minoritate corectă a doua zi
    assert report["agents"]["gpt"]["hold_correct_rate"] == 1.0   # HOLD când mișcarea a fost sub 1%
    assert not report["enough_data"] and "orientative" in report["note"]


def test_disagreement_and_hybrid(tmp_path):
    path = make_registry(tmp_path, [
        ("SP500", {"gpt": ("BUY", .8), "claude": ("BUY", .8), "gemini": ("BUY", .8)}, "BUY", 0.01, 1),
        ("SP500", {"gpt": ("BUY", .8), "claude": ("SELL", .8), "gemini": ("HOLD", .8)}, "HOLD", 0.06, 1),
    ])

    report = ca.analyse(path)

    assert report["disagreement"]["scazut"]["decisions"] == 1
    assert report["disagreement"]["ridicat"]["mean_abs_move_pct"] == pytest.approx(6.0)
    assert report["strategies"]["hybrid"]["calls"] == 1          # doar unde consiliul e de acord cu botul


def test_model_registry_combines_config_costs_and_traces(tmp_path, series):
    import sqlite3
    from src.bnd import model_registry
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    data = upto(series, 700)
    now = data["SP500"][-1].open_time + timedelta(days=1)
    cd.run_markets(data, MARKETS, cd.simulated_gateway(), registry, now, Decimal("0.6"))
    db = sqlite3.connect(tmp_path / "costs.sqlite")
    db.execute("CREATE TABLE usage_records (id INTEGER PRIMARY KEY, agent TEXT, model TEXT,"
               " input_tokens INT, output_tokens INT, cost_usd TEXT, timestamp TEXT)")
    db.execute("INSERT INTO usage_records (agent, model, input_tokens, output_tokens, cost_usd, timestamp)"
               " VALUES ('gpt', 'openai/gpt-6-astra', 1000, 200, '0.02', '2026-11-01T00:00:00+00:00')")
    db.commit(); db.close()

    result = model_registry.build(tmp_path / "r.sqlite", tmp_path / "costs.sqlite")

    gpt = result["agents"]["gpt"]
    assert gpt["model"] == "openai/gpt-6-astra" and gpt["provider"] == "OpenAI"
    assert gpt["total_cost_usd"] == 0.02 and gpt["paid_calls"] == 1
    assert gpt["availability"] == 1.0 and gpt["traced_calls"] == len(MARKETS)
    assert "| gpt | OpenAI |" in model_registry.render(result)
