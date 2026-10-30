"""Response cache and cost report: offline, no paid calls."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.bnd.ai_cache import ResponseCache, cache_key
from src.bnd.ai_gateway import AIResponse
from src.bnd.cost_report import main as report_main
from src.bnd.cost_report import usage
from src.bnd.cost_storage import SQLiteCostStorage
from src.bnd.cost_tracker import BudgetLimits
from src.bnd.council_runner import CouncilRunner
from src.bnd.fusion_council import AGENTS, Vote
from tests.test_council_runner import ScriptedProvider, gateway, no_sleep

T0 = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


def answer():
    return AIResponse("claude", Vote.SELL, "view", 0.7, "m", 10, 5, "P")


def test_cache_returns_fresh_answers_and_counts_savings(tmp_path):
    clock = Clock()
    cache = ResponseCache(tmp_path / "c.sqlite", ttl=timedelta(hours=1), clock=clock)
    key = cache_key("claude", "m", "forex", "EURUSD", "ctx")

    assert cache.get(key) is None
    cache.put(key, answer(), Decimal("0.25"))
    assert cache.get(key) == answer()
    clock.now += timedelta(hours=2)
    assert cache.get(key) is None                      # expired

    assert cache.stats() == {"hits": 1, "misses": 2, "saved_usd": "0.25", "entries": 1}


def test_key_changes_with_any_part_of_the_question():
    base = ("claude", "m", "forex", "EURUSD", "ctx")
    keys = {cache_key(*base)}
    for i in range(len(base)):
        changed = list(base)
        changed[i] += "x"
        keys.add(cache_key(*changed))
    assert len(keys) == len(base) + 1


def test_second_identical_round_is_free(tmp_path):
    providers = {a: ScriptedProvider(a) for a in AGENTS}
    cache = ResponseCache(tmp_path / "c.sqlite")
    runner = CouncilRunner(gateway(providers), sleep=no_sleep, cache=cache)

    first = runner.run_round("forex", "EURUSD", "ctx", "1")
    second = runner.run_round("forex", "EURUSD", "ctx", "1")
    third = runner.run_round("forex", "EURUSD", "new data", "1")

    assert first["complete"] and second["complete"]
    assert Decimal(second["spent_usd"]) == 0
    assert all(r["route"] == "cache" for r in second["agents"].values())
    assert sum(len(p.seen) for p in providers.values()) == 2 * len(AGENTS)
    assert Decimal(third["spent_usd"]) == Decimal(first["spent_usd"])
    assert Decimal(cache.stats()["saved_usd"]) == Decimal(first["spent_usd"])


def test_cost_report_groups_by_model_agent_and_day(tmp_path, capsys):
    db = tmp_path / "costs.sqlite"
    providers = {a: ScriptedProvider(a) for a in AGENTS}
    storage = SQLiteCostStorage(db, BudgetLimits(Decimal("10"), Decimal("100")))
    CouncilRunner(gateway(providers, storage), sleep=no_sleep).run_round(
        "forex", "EURUSD", "ctx", "1", parallel=False)

    report = usage(db)

    assert report["calls"] == len(AGENTS)
    assert report["total_usd"] == Decimal("0.015")
    assert report["by_agent"]["claude"] == {"calls": 1, "usd": Decimal("0.003")}
    assert sum(e["calls"] for e in report["by_day"].values()) == len(AGENTS)
    assert report_main(["--db", str(db)]) == 0
    text = capsys.readouterr().out
    assert "## By model" in text and "vendor/claude-model" in text


def test_cost_report_missing_database(tmp_path, capsys):
    assert report_main(["--db", str(tmp_path / "none.sqlite")]) == 2
    assert "No cost database" in capsys.readouterr().err


def test_cache_rejects_non_positive_ttl(tmp_path):
    with pytest.raises(ValueError):
        ResponseCache(tmp_path / "c.sqlite", ttl=timedelta(0))
