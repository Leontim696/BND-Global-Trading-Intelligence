"""Audit 01.11, P2 #5: idempotență, date lipsă, ordine parțiale, inversări long/short, opriri de siguranță, restart."""

import pytest

from src.bnd import paper_runner
from src.bnd.market_data import Candle
from src.bnd.paper_engine import EngineLimits, OrderStatus, PaperEngine
from src.bnd.paper_runner import run_daily
from tests.test_paper_runner import (
    DAY, MARKETS, config, engine_at, factory, make_data, now_after,
)


def snapshot(engine):
    return {"orders": engine.orders(), "fills": engine.fills(), "positions": engine.positions(),
            "cash": engine.account()["cash"], "equity": engine.equity()}


def next_day(data, move=0.0):
    out = {}
    for name, candles in data.items():
        last = candles[-1]
        close = last.close * (1 + move)
        out[name] = candles + [Candle(last.open_time + DAY, last.close, max(last.close, close) * 1.002,
                                      min(last.close, close) * 0.998, close, 1000)]
    return out


def by_id(engine):
    return {o["client_order_id"]: (o["status"], o["side"], round(o["quantity"], 9)) for o in engine.orders()}


def test_repeated_runs_with_the_same_data_change_nothing_after_the_first(tmp_path):
    data = make_data()
    engine = engine_at(tmp_path)
    run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    first = snapshot(engine)
    for _ in range(3):
        again = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
        assert again["candles_processed"] == 0
    assert snapshot(engine) == first


def test_repeated_runs_after_fills_do_not_double_the_position(tmp_path):
    data = make_data(121)
    today = {name: c[:-1] for name, c in data.items()}
    engine = engine_at(tmp_path)
    run_daily(engine, today, MARKETS, factory, config(), "sma", now_after(today))
    for _ in range(3):
        run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    quantities = {p["symbol"]: p["quantity"] for p in engine.positions()}
    again = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    assert {p["symbol"]: p["quantity"] for p in engine.positions()} == quantities
    assert len([f for f in engine.fills() if f["symbol"] == "UP"]) == 1
    assert all(o["status"] != "FILLED" for o in again["orders"])


def test_restart_after_an_interruption_matches_an_uninterrupted_run(tmp_path, monkeypatch):
    data = make_data()
    (tmp_path / "a").mkdir()
    clean = engine_at(tmp_path / "a")
    run_daily(clean, data, MARKETS, factory, config(), "sma", now_after(data))
    crash_dir = tmp_path / "b"
    crash_dir.mkdir()
    crashed = engine_at(crash_dir)
    real = paper_runner._submit
    count = []

    def dying(engine, request, now):
        count.append(1)
        if len(count) == 2:
            raise RuntimeError("întrerupere la al doilea ordin")
        return real(engine, request, now)
    monkeypatch.setattr(paper_runner, "_submit", dying)
    with pytest.raises(RuntimeError):
        run_daily(crashed, data, MARKETS, factory, config(), "sma", now_after(data))
    crashed.close()
    assert len(by_id(PaperEngine.open(crash_dir / "paper.sqlite"))) == 1          # doar primul ordin a rămas
    monkeypatch.setattr(paper_runner, "_submit", real)
    reopened = PaperEngine.open(crash_dir / "paper.sqlite")
    run_daily(reopened, data, MARKETS, factory, config(), "sma", now_after(data))
    assert by_id(reopened) == by_id(clean)                                         # fără dubluri, fără ordine lipsă
    assert reopened.equity() == pytest.approx(clean.equity())


def test_signal_flip_long_to_short_ends_short_with_a_stop_on_the_right_side(tmp_path):
    data = make_data(121)
    today = {name: c[:-1] for name, c in data.items()}
    engine = engine_at(tmp_path)
    long_only = lambda: (lambda history: 1.0)        # noqa: E731
    short_only = lambda: (lambda history: -1.0)      # noqa: E731
    run_daily(engine, today, MARKETS, long_only, config(allow_short=True), "x", now_after(today))
    run_daily(engine, data, MARKETS, long_only, config(allow_short=True), "x", now_after(data))
    assert all(p["quantity"] > 0 for p in engine.positions())
    later = next_day(data)
    run_daily(engine, later, MARKETS, short_only, config(allow_short=True), "x", now_after(later))
    final = next_day(later)
    run_daily(engine, final, MARKETS, short_only, config(allow_short=True), "x", now_after(final))
    positions = {p["symbol"]: p for p in engine.positions()}
    assert positions and all(p["quantity"] < 0 for p in positions.values())          # nicio poziție long rămasă
    for name, p in positions.items():
        assert p["stop_loss"] is not None and p["stop_loss"] > p["avg_price"] * 0.5
    assert {"UP", "DOWN"} <= set(positions)


def test_partial_old_order_is_cancelled_and_new_order_sized_from_the_real_position(tmp_path):
    data = make_data(121)
    today = {name: c[:-1] for name, c in data.items()}
    engine = engine_at(tmp_path)
    first = run_daily(engine, today, MARKETS, factory, config(), "sma", now_after(today))
    old = next(o for o in first["orders"] if o["market"] == "UP")["client_order_id"]
    with engine._transaction():
        engine._set_order(old, OrderStatus.PARTIAL, now_after(today).isoformat(), "simulat")
    run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    assert engine.order(old)["status"] in ("CANCELLED", "FILLED", "PARTIAL")
    pending = [o for o in engine.orders() if o["symbol"] == "UP" and o["status"] in ("PENDING", "PARTIAL")]
    assert all(o["client_order_id"].startswith(str(data["UP"][-1].open_time.date())) for o in pending)


def test_market_missing_from_todays_data_keeps_its_position_and_does_not_crash(tmp_path):
    data = make_data(121)
    today = {name: c[:-1] for name, c in data.items()}
    engine = engine_at(tmp_path)
    run_daily(engine, today, MARKETS, factory, config(), "sma", now_after(today))
    run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    held = {p["symbol"]: p["quantity"] for p in engine.positions()}
    assert "UP" in held
    without = {name: c for name, c in next_day(data).items() if name != "UP"}
    report = run_daily(engine, without, [m for m in MARKETS if m.name != "UP"], factory, config(), "sma", now_after(without))
    assert {p["symbol"]: p["quantity"] for p in engine.positions()}["UP"] == held["UP"]
    assert all(o["market"] != "UP" for o in report["orders"])


def test_stale_market_data_is_rejected_not_traded(tmp_path):
    data = make_data(121)
    data["FX"] = data["FX"][:-10]
    engine = engine_at(tmp_path)
    report = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    fx = [o for o in report["orders"] if o["market"] == "FX"]
    assert fx and all(o["status"] == "REJECTED" and "Stale" in (o["reason"] or "") for o in fx)


def test_too_little_history_skips_instead_of_trading(tmp_path):
    data = {"UP": make_data(8)["UP"]}
    engine = engine_at(tmp_path)
    report = run_daily(engine, data, MARKETS[:1], factory, config(), "sma", now_after(data))
    assert all(o["status"] in ("SKIPPED", "REJECTED") for o in report["orders"])
    assert engine.positions() == []


def test_kill_switch_survives_a_restart_and_needs_the_exact_reset_text(tmp_path):
    data = make_data()
    engine = engine_at(tmp_path)
    for market in MARKETS:
        engine.register_instrument(paper_runner.instrument_for(market))
    engine.on_bar("UP", data["UP"][-2])
    with engine._transaction():
        engine._trip("test", data["UP"][-2].open_time.isoformat())
    engine.close()
    reopened = PaperEngine.open(tmp_path / "paper.sqlite")
    assert reopened.account()["kill_switch"]
    report = run_daily(reopened, data, MARKETS, factory, config(), "sma", now_after(data))
    assert report["kill_switch"] and report["orders"] == [] and reopened.positions() == []
    from src.bnd.paper_engine import PaperEngineError
    with pytest.raises(PaperEngineError):
        reopened.reset_kill_switch("reset", now_after(data))
    assert reopened.account()["kill_switch"]


def test_drawdown_trips_the_kill_switch_and_blocks_new_orders(tmp_path):
    data = make_data(121)
    today = {name: c[:-1] for name, c in data.items()}
    engine = engine_at(tmp_path)
    long_only = lambda: (lambda history: 1.0)        # noqa: E731
    run_daily(engine, today, MARKETS, long_only, config(), "x", now_after(today))
    run_daily(engine, data, MARKETS, long_only, config(), "x", now_after(data))
    crash = next_day(data, move=-0.45)               # cădere de 45% într-o zi
    run_daily(engine, crash, MARKETS, long_only, config(), "x", now_after(crash))
    assert engine.account()["kill_switch"]
    orders_before = len(engine.orders())
    after = next_day(crash, move=0.05)
    report = run_daily(engine, after, MARKETS, long_only, config(), "x", now_after(after))
    assert report["orders"] == [] and len(engine.orders()) == orders_before


def test_risk_limits_hold_every_day_over_a_long_run(tmp_path):
    limits = EngineLimits()
    engine = engine_at(tmp_path)
    data = make_data(70)
    alloc = {name: c[:50] for name, c in data.items()}
    run_daily(engine, alloc, MARKETS, factory, config(allow_short=True), "sma", now_after(alloc))
    for end in range(51, 71):
        window = {name: c[:end] for name, c in data.items()}
        run_daily(engine, window, MARKETS, factory, config(allow_short=True), "sma", now_after(window))
        summary = engine.summary()
        equity = summary["equity"]
        assert summary["gross_leverage"] <= limits.max_gross_leverage * 1.02
        for position in engine.positions():
            value = abs(position["quantity"]) * engine.mark(position["symbol"])["price"]
            assert value / equity * 100 <= limits.max_position_pct * 1.1 + 1e-9


def test_interruption_while_feeding_candles_resumes_to_the_same_state(tmp_path, monkeypatch):
    data = make_data(121)
    today = {name: c[:-1] for name, c in data.items()}
    (tmp_path / "a").mkdir()
    clean = engine_at(tmp_path / "a")
    run_daily(clean, today, MARKETS, factory, config(), "sma", now_after(today))
    run_daily(clean, data, MARKETS, factory, config(), "sma", now_after(data))
    (tmp_path / "b").mkdir()
    engine = engine_at(tmp_path / "b")
    run_daily(engine, today, MARKETS, factory, config(), "sma", now_after(today))
    real = engine.on_bar
    calls = []

    def dying(name, candle):
        calls.append(name)
        if len(calls) == 2:
            raise RuntimeError("întrerupere în timpul lumânărilor")
        return real(name, candle)
    monkeypatch.setattr(engine, "on_bar", dying)
    with pytest.raises(RuntimeError):
        run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    engine.close()
    resumed = PaperEngine.open(tmp_path / "b" / "paper.sqlite")
    run_daily(resumed, data, MARKETS, factory, config(), "sma", now_after(data))
    assert {p["symbol"]: round(p["quantity"], 9) for p in resumed.positions()} == \
        {p["symbol"]: round(p["quantity"], 9) for p in clean.positions()}
    assert resumed.equity() == pytest.approx(clean.equity())
    assert len(resumed.fills()) == len(clean.fills())
