"""Stress scenario library against a paper account."""

from datetime import datetime, timezone

import pytest

from src.bnd.market_data import Candle
from src.bnd.paper_engine import Instrument, OrderRequest, PaperEngine
from src.bnd.scenarios import SCENARIOS, run_scenarios, shocks_for
from src.bnd.universe import UNIVERSES

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
T1 = datetime(2024, 1, 2, tzinfo=timezone.utc)


def bar(time, price):
    return Candle(time, price, price, price, price, 1e9)


def test_every_scenario_covers_every_asset_class_and_known_markets():
    names = {m.name for markets in UNIVERSES.values() for m in markets}
    classes = {m.asset_class for markets in UNIVERSES.values() for m in markets}
    for spec in SCENARIOS.values():
        assert set(spec["classes"]) == classes
        assert set(spec["markets"]) <= names
        assert all(-100 < v for v in (*spec["classes"].values(), *spec["markets"].values()))


def test_market_value_overrides_class_default():
    shocks = shocks_for("crisis_2008", {"SP500": "index", "EMERGING": "index", "X": "forex"})

    assert shocks == {"SP500": -40, "EMERGING": -55, "X": 0}


def test_scenarios_on_positions_worst_first(tmp_path):
    engine = PaperEngine.create(tmp_path / "p.sqlite", 10_000, now=T0)
    engine.register_instrument(Instrument("SP500", "index", fee_pct=0, slippage_pct=0))
    engine.register_instrument(Instrument("US20Y_BOND", "bond", fee_pct=0, slippage_pct=0))
    for symbol in ("SP500", "US20Y_BOND"):
        engine.on_bar(symbol, bar(T0, 100.0))
    engine.submit_order(OrderRequest("a", "SP500", "BUY", 40, stop_loss=99), T0)
    engine.submit_order(OrderRequest("b", "US20Y_BOND", "BUY", 20, stop_loss=99), T0)
    for symbol in ("SP500", "US20Y_BOND"):
        engine.on_bar(symbol, bar(T1, 100.0))

    rows = run_scenarios(engine)

    assert [r["change_pct"] for r in rows] == sorted(r["change_pct"] for r in rows)
    crisis = next(r for r in rows if r["scenario"] == "crisis_2008")
    # 4,000 of stocks at -40% and 2,000 of long bonds at +20% on 10,000.
    assert crisis["change_pct"] == pytest.approx(-12.0)
    assert crisis["worst_market"] == "SP500" and crisis["beyond_kill_switch"] is False
    rates = next(r for r in rows if r["scenario"] == "rates_2022")
    assert rates["change_pct"] == pytest.approx(-17.0)


def test_no_positions_means_no_change(tmp_path):
    engine = PaperEngine.create(tmp_path / "p.sqlite", 10_000, now=T0)

    assert all(r["change_pct"] == 0 and r["worst_market"] is None for r in run_scenarios(engine))
