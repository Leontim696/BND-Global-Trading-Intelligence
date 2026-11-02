"""Decontare cu intrare la prima închidere de după decizie și alpha față de benchmark."""

import sqlite3
from datetime import datetime, timedelta, timezone

from src.bnd import council_analytics as ca
from src.bnd import settlement
from src.bnd.decision_registry import DecisionRegistry
from src.bnd.decision_rules import decide
from src.bnd.market_data import Candle
from tests.test_decision_registry import council

T0 = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)          # luni; ținta e la 00:00 ca să se potrivească cu bara zilnică


def series(start, closes):
    day = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    return [Candle(day + timedelta(days=i), c, c, c, c, 1) for i, c in enumerate(closes)]


def test_benchmarks():
    assert settlement.benchmark_for("GOLD") == "SP500" and settlement.benchmark_for("AAPL") == "SP500"
    assert settlement.benchmark_for("PEPE") == "BITCOIN" and settlement.benchmark_for("ETHEREUM") == "BITCOIN"
    assert settlement.benchmark_for("SP500") is None and settlement.benchmark_for("BITCOIN") is None


def test_entry_is_the_first_close_after_the_decision_date_not_the_decision_close():
    # luni (ziua deciziei) închide 100; marți 110; joi (țintă la 3 zile) 121
    data = {"GOLD": series(T0, [100, 110, 115, 121]), "SP500": series(T0, [1000, 1000, 1000, 1100])}
    info = settlement.details("GOLD", T0, 3, data)
    assert abs(info["entry_next_return"] - (121 / 110 - 1)) < 1e-12 and info["entry_next_date"] == "2026-11-03"
    assert abs(info["alpha_raw"] - ((121 / 100 - 1) - (1100 / 1000 - 1))) < 1e-12      # 0,21 - 0,10
    assert abs(info["alpha_next"] - ((121 / 110 - 1) - (1100 / 1000 - 1))) < 1e-12     # 0,10 - 0,10
    assert info["benchmark"] == "SP500"


def test_missing_benchmark_or_too_short_horizon_just_leave_fields_out():
    data = {"GOLD": series(T0, [100, 110, 115, 121])}
    info = settlement.details("GOLD", T0, 3, data)
    assert "alpha_next" not in info and "entry_next_return" in info
    assert settlement.details("GOLD", T0, 30, data) == {}                       # nicio închidere la orizont
    one_day = settlement.details("GOLD", T0, 1, {"GOLD": series(T0, [100, 110, 115])})
    assert "entry_next_return" not in one_day                                    # intrarea ar coincide cu ieșirea


def test_settle_stores_the_details_without_changing_the_original_outcome(tmp_path):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    c = council(up=True)
    registry.record("d1", T0, "GOLD", 100.0, c, decide(c), horizon_days=3, meta={"bot_signal": 1})
    data = {"GOLD": series(T0, [100, 110, 115, 121]), "SP500": series(T0, [1000, 1000, 1000, 1100])}
    assert registry.settle_from_candles(data, T0 + timedelta(days=4)) == 1
    meta = registry.meta("d1")
    assert meta["bot_signal"] == 1 and meta["settle"]["benchmark"] == "SP500"          # meta păstrat + cheie nouă
    db = sqlite3.connect(tmp_path / "r.sqlite")
    assert abs(db.execute("SELECT outcome_return FROM decisions").fetchone()[0] - 0.21) < 1e-12


def bullish():
    from src.bnd.fusion_council import AGENTS, FusionCouncil, Opinion, Vote
    c = FusionCouncil()
    for i, agent in enumerate(AGENTS):
        c.submit(Opinion(agent, Vote.BUY if i < 2 else Vote.HOLD, f"{agent} motiv", 0.7))
    return c


def test_alpha_report_separates_market_direction_from_skill(tmp_path):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    c = bullish()                                          # înclinație BUY
    registry.record("d1", T0, "GOLD", 100.0, c, decide(c), horizon_days=3)
    data = {"GOLD": series(T0, [100, 110, 115, 121]), "SP500": series(T0, [1000, 1000, 1000, 1300])}
    registry.settle_from_candles(data, T0 + timedelta(days=4))
    report = ca.analyse(tmp_path / "r.sqlite")["alpha"]
    assert report["raw"]["hit_rate"] == 1.0 and report["entry_next"]["hit_rate"] == 1.0
    assert report["alpha_next"]["hit_rate"] == 0.0         # SP500 a urcat mai mult: BUY pe GOLD n-a adăugat alpha


def test_incomplete_rounds_are_excluded_from_the_statistics(tmp_path):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    c = council(up=True)
    registry.record("ok", T0, "GOLD", 100.0, c, decide(c), horizon_days=3, meta={"complete": True})
    registry.record("incomplet", T0, "SILVER", 100.0, c, decide(c), horizon_days=3, meta={"complete": False})
    data = {"GOLD": series(T0, [100, 110, 115, 121]), "SILVER": series(T0, [100, 110, 115, 121])}
    registry.settle_from_candles(data, T0 + timedelta(days=4))
    report = ca.analyse(tmp_path / "r.sqlite")
    assert report["settled"] == 1 and report["incomplete_excluded"] == 1
    assert set(ca._rows(tmp_path / "r.sqlite")) == {"ok"}
    assert set(ca._rows(tmp_path / "r.sqlite", include_incomplete=True)) == {"ok", "incomplet"}
