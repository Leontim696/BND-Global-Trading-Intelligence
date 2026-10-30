"""Extreme situations for the daily paper runner: crashes, gaps, stale data, errors."""

from datetime import timedelta

import pytest

from src.bnd.market_data import Candle
from src.bnd.paper_engine import PaperEngine
from src.bnd.paper_runner import run_daily
from tests.test_paper_runner import (
    DAY,
    MARKETS,
    START,
    config,
    factory,
    make_data,
    now_after,
)


def account(tmp_path):
    return PaperEngine.create(tmp_path / "extreme.sqlite", 10_000, currency="USD", now=START)


def holding(tmp_path):
    """An account that holds positions (long UP, short DOWN) after two runs."""
    data = make_data(121)
    engine = account(tmp_path)
    today = {name: candles[:-1] for name, candles in data.items()}
    run_daily(engine, today, MARKETS, factory, config(), "sma", now_after(today))
    run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    held = {p["symbol"]: p["quantity"] for p in engine.positions()}
    assert held["UP"] > 0 > held["DOWN"]
    return engine, data


def add_bar(data, name, open_, close=None):
    last = data[name][-1]
    close = open_ if close is None else close
    bar = Candle(last.open_time + DAY, open_, max(open_, close), min(open_, close), close, 1000)
    return {**data, name: data[name] + [bar]}


def quiet_bar(data, name):
    last = data[name][-1]
    return add_bar(data, name, last.close)


def test_crash_against_every_position_trips_the_kill_switch_and_stops_trading(tmp_path):
    engine, data = holding(tmp_path)
    up, down = data["UP"][-1].close, data["DOWN"][-1].close
    crash = add_bar(add_bar(data, "UP", up * 0.6), "DOWN", down * 1.4)
    crash = quiet_bar(crash, "FX")

    report = run_daily(engine, crash, MARKETS, factory, config(), "sma", now_after(crash))

    assert report["kill_switch"] and report["orders"] == []
    assert engine.positions() == []
    # Stops were jumped: the fills happened at the gapped open, not at the stop.
    exits = {f["symbol"]: f for f in engine.fills() if f["reason"] in ("stop_loss", "kill_switch")}
    assert exits["UP"]["price"] <= up * 0.6
    assert exits["DOWN"]["price"] >= down * 1.4
    assert engine.journal("kill_switch")

    # Later days: still stopped, nothing new, until a manual reset.
    later = quiet_bar(quiet_bar(quiet_bar(crash, "UP"), "DOWN"), "FX")
    again = run_daily(engine, later, MARKETS, factory, config(), "sma", now_after(later))
    assert again["kill_switch"] and again["orders"] == [] and engine.positions() == []


def test_stale_market_gets_no_new_risk(tmp_path):
    data = make_data(120)
    data["DOWN"] = data["DOWN"][:-10]          # this market stopped updating
    engine = account(tmp_path)

    report = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))

    down = [o for o in report["orders"] if o["market"] == "DOWN"]
    assert down and all(o["status"] == "REJECTED" and "Stale" in o["reason"] for o in down)
    assert any(o["status"] == "PENDING" for o in report["orders"] if o["market"] == "UP")


def test_extreme_gap_blocks_new_risk_on_that_market(tmp_path):
    data = make_data(120)
    engine = account(tmp_path)
    before = {name: candles[:-1] for name, candles in data.items()}
    run_daily(engine, before, MARKETS, factory, config(), "sma", now_after(before))
    for order in engine.orders():
        engine.cancel_order(order["client_order_id"], now_after(before))
    last = data["UP"][-1]
    jump = data["UP"][-2].close * 1.25           # +25% close to close
    data["UP"][-1] = Candle(last.open_time, last.open, max(jump, last.open),
                            min(last.low, last.open), jump, last.volume)

    report = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))

    opening = [o for o in report["orders"] if o["market"] == "UP" and o["side"] == "BUY"]
    assert opening and all(o["status"] == "REJECTED" and "gap" in o["reason"] for o in opening)


def test_error_while_processing_a_bar_stops_safely_and_survives_restart(tmp_path, monkeypatch):
    engine, data = holding(tmp_path)
    nxt = quiet_bar(quiet_bar(quiet_bar(data, "UP"), "DOWN"), "FX")

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(engine, "_exit_checks", broken)
    with pytest.raises(RuntimeError):
        run_daily(engine, nxt, MARKETS, factory, config(), "sma", now_after(nxt))
    engine.close()
    monkeypatch.undo()

    reopened = PaperEngine.open(tmp_path / "extreme.sqlite")
    assert reopened.account()["kill_switch"]
    assert "disk full" in reopened.account()["kill_reason"]
    report = run_daily(reopened, nxt, MARKETS, factory, config(), "sma",
                       now_after(nxt) + timedelta(hours=1))
    assert report["kill_switch"] and report["orders"] == []
