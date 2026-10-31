"""Daily paper runner: offline, synthetic candles, virtual money only."""

import json
from datetime import datetime, timedelta, timezone
from math import sin

import pytest

from src.bnd import paper_runner
from src.bnd.market_data import Candle, save_csv
from src.bnd.paper_engine import EngineLimits, PaperEngine
from src.bnd.paper_runner import (
    RunnerConfig,
    fit_limits,
    instrument_for,
    latest_weights,
    run_daily,
)
from src.bnd.portfolio import PortfolioConfig
from src.bnd.strategies import buy_and_hold, sma_crossover
from src.bnd.universe import Market

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)
MARKETS = (
    Market("UP", "UP", "index", 0.01, 0.02),
    Market("DOWN", "DOWN", "commodity", 0.02, 0.05),
    Market("FX", "FX", "forex", 0.002, 0.005),
)


def series(count, drift, base=100.0, wiggle=0.01, phase=0.0):
    candles, price = [], base
    for i in range(count):
        close = price * (1 + drift + wiggle * sin(i * 0.7 + phase))
        high, low = max(price, close) * 1.004, min(price, close) * 0.996
        candles.append(Candle(START + DAY * i, price, high, low, close, 1000))
        price = close
    return candles


def make_data(count=120):
    return {"UP": series(count, 0.004), "DOWN": series(count, -0.004, phase=1.0),
            "FX": series(count, 0.0005, base=1.1, wiggle=0.002, phase=2.0)}


def now_after(data):
    return max(c[-1].open_time for c in data.values()) + DAY


def config(**portfolio):
    return RunnerConfig(portfolio=PortfolioConfig(vol_lookback=20, **portfolio))


def factory():
    return sma_crossover(5, 20)


def engine_at(tmp_path, capital=10_000.0, **limits):
    return PaperEngine.create(tmp_path / "paper.sqlite", capital, currency="USD",
                              limits=EngineLimits(**limits), now=START)


def test_first_run_takes_only_the_latest_candle_and_orders_for_next_open(tmp_path):
    data = make_data()
    engine = engine_at(tmp_path)

    report = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))

    assert report["candles_processed"] == 3          # history is never traded
    assert engine.positions() == []                  # orders wait for the next open
    sides = {o["market"]: o["side"] for o in report["orders"]}
    assert sides["UP"] == "BUY" and sides["DOWN"] == "SELL"
    assert all(o["status"] == "PENDING" for o in report["orders"])
    up = next(o for o in report["orders"] if o["market"] == "UP")
    assert up["stop_loss"] < up["price"]


def test_same_data_twice_submits_nothing_new(tmp_path):
    data = make_data()
    engine = engine_at(tmp_path)
    run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    orders = len(engine.orders())

    again = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))

    assert again["candles_processed"] == 0
    assert len(engine.orders()) == orders
    assert engine.journal("duplicate_order_ignored")


def test_next_candle_fills_at_its_open_with_a_stop(tmp_path):
    data = make_data(121)
    today = {name: candles[:-1] for name, candles in data.items()}
    engine = engine_at(tmp_path)
    run_daily(engine, today, MARKETS, factory, config(), "sma", now_after(today))

    report = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))

    assert report["candles_processed"] == 3
    positions = {p["symbol"]: p for p in engine.positions()}
    assert positions["UP"]["quantity"] > 0 and positions["DOWN"]["quantity"] < 0
    fill = next(f for f in engine.fills() if f["symbol"] == "UP")
    assert fill["price"] == pytest.approx(data["UP"][-1].open * 1.0002)
    assert positions["UP"]["stop_loss"] < positions["UP"]["avg_price"]
    assert positions["DOWN"]["stop_loss"] > positions["DOWN"]["avg_price"]


def test_added_risk_at_the_stop_stays_under_the_engine_limit(tmp_path):
    data = make_data()
    engine = engine_at(tmp_path, max_risk_per_trade_pct=0.5)
    equity = engine.equity()

    report = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))

    for order in report["orders"]:
        assert order["status"] == "PENDING"
        risk = order["quantity"] * abs(order["price"] - order["stop_loss"])
        assert risk <= 0.005 * equity + 1e-9
    assert any(o["risk_capped"] for o in report["orders"])


def test_weights_follow_the_strategy_and_respect_leverage():
    data = make_data()

    weights, signals = latest_weights(data, MARKETS, factory,
                                      PortfolioConfig(vol_lookback=20, max_leverage=1.5))

    for name, candles in data.items():
        strategy = factory()
        for end in range(1, len(candles) + 1):
            expected = strategy(candles[:end])
        assert signals[name] == expected
    assert weights["UP"] > 0 > weights["DOWN"]
    assert sum(abs(w) for w in weights.values()) <= 1.5 + 1e-9


def test_no_shorts_turns_short_signals_flat():
    data = make_data()

    weights, _ = latest_weights(data, MARKETS, factory,
                                PortfolioConfig(vol_lookback=20, allow_short=False))

    assert weights["DOWN"] == 0


def test_fit_limits_caps_position_sector_and_gross(tmp_path):
    engine = engine_at(tmp_path, max_position_pct=80, max_sector_pct=100,
                       max_gross_leverage=1.5)
    for market in MARKETS + (Market("FX2", "FX2", "forex", 0.002, 0.005),):
        engine.register_instrument(instrument_for(market))

    fitted = fit_limits(engine, {"UP": 2.0, "DOWN": -0.1, "FX": 0.7, "FX2": 0.7}, margin=1.0)

    assert abs(fitted["UP"]) <= 0.8 + 1e-9
    assert abs(fitted["FX"]) + abs(fitted["FX2"]) <= 1.0 + 1e-9
    assert sum(abs(w) for w in fitted.values()) == pytest.approx(1.5)


def test_flat_signal_closes_with_a_reduce_only_order(tmp_path):
    data = make_data(121)
    today = {name: candles[:-1] for name, candles in data.items()}
    engine = engine_at(tmp_path)
    run_daily(engine, today, MARKETS, buy_and_hold, config(), "hold", now_after(today))
    run_daily(engine, data, MARKETS, buy_and_hold, config(), "hold", now_after(data))
    assert engine.positions()
    later = {name: candles + [Candle(candles[-1].open_time + DAY, candles[-1].close,
                                     candles[-1].close * 1.001, candles[-1].close * 0.999,
                                     candles[-1].close, 1000)]
             for name, candles in data.items()}

    flat = lambda: (lambda history: 0)  # noqa: E731
    report = run_daily(engine, later, MARKETS, flat, config(), "flat", now_after(later))

    assert report["orders"]
    for order in report["orders"]:
        stored = engine.order(order["client_order_id"])
        assert stored["reduce_only"] == 1 and stored["stop_loss"] is None


def test_kill_switch_blocks_new_orders(tmp_path):
    data = make_data()
    engine = engine_at(tmp_path)
    for market in MARKETS:
        engine.register_instrument(instrument_for(market))
    engine.on_bar("UP", data["UP"][-2])
    with engine._transaction():
        engine._trip("test", data["UP"][-2].open_time.isoformat())

    report = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))

    assert report["kill_switch"] and report["orders"] == []


def write_data(folder, data):
    folder.mkdir()
    for name, candles in data.items():
        save_csv(candles, folder / f"{name}.csv")


def test_cli_needs_confirmed_capital_then_resumes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paper_runner, "select_markets", lambda *a: MARKETS)
    write_data(tmp_path / "data", make_data())
    state = tmp_path / "state" / "paper.sqlite"
    base = ["--state", str(state), "--data-dir", str(tmp_path / "data"),
            "--strategy", "sma_crossover", "--param", "fast=5", "--param", "slow=20",
            "--sizing-lookback", "20"]

    assert paper_runner.main(base) == 2
    assert "--capital" in capsys.readouterr().err
    assert not state.exists()

    report_path = tmp_path / "REPORT.md"
    assert paper_runner.main(base + ["--capital", "5000", "--report", str(report_path),
                                     "--json", str(tmp_path / "run.json")]) == 0
    capsys.readouterr()
    assert json.loads((tmp_path / "run.json").read_text())["initial_capital"] == 5000
    page = report_path.read_text()
    assert "virtual money" in page.lower() and "Orders for the next open" in page

    assert paper_runner.main(base + ["--capital", "5000"]) == 2
    assert "already exists" in capsys.readouterr().err
    assert paper_runner.main(base) == 0
    capsys.readouterr()

    # Scheduled runs pass no settings: the stored ones are used.
    assert paper_runner.main(base[:4]) == 0
    assert json.loads(capsys.readouterr().out)["settings"]["param"] == ["fast=5", "slow=20"]
    assert paper_runner.main(base[:4] + ["--strategy", "momentum"]) == 2
    assert "other settings (strategy)" in capsys.readouterr().err


def test_cli_rejects_bad_strategy_parameters_before_creating(tmp_path, capsys):
    write_data(tmp_path / "data", make_data())
    state = tmp_path / "paper.sqlite"

    code = paper_runner.main(["--state", str(state), "--data-dir", str(tmp_path / "data"),
                              "--capital", "1000", "--param", "nonsense=1"])

    assert code == 2 and not state.exists()


def test_cli_kill_switch_reset_needs_exact_confirmation(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paper_runner, "select_markets", lambda *a: MARKETS)
    write_data(tmp_path / "data", make_data())
    state = tmp_path / "paper.sqlite"
    base = ["--state", str(state), "--data-dir", str(tmp_path / "data")]
    assert paper_runner.main(base + ["--capital", "1000"]) == 0

    assert paper_runner.main(base + ["--reset-kill-switch", "RESET-KILL-SWITCH"]) == 2
    assert "not active" in capsys.readouterr().err

    engine = PaperEngine.open(state)
    with engine._transaction():
        engine._trip("test", START.isoformat())
    engine.close()
    assert paper_runner.main(base + ["--reset-kill-switch", "yes"]) == 2
    assert "RESET-KILL-SWITCH" in capsys.readouterr().err
    assert paper_runner.main(base + ["--reset-kill-switch", "RESET-KILL-SWITCH"]) == 0
    assert json.loads(capsys.readouterr().out)["kill_switch"] is False


def test_cli_combo_members_are_stored(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paper_runner, "select_markets", lambda *a: MARKETS)
    write_data(tmp_path / "data", make_data())
    base = ["--state", str(tmp_path / "paper.sqlite"), "--data-dir", str(tmp_path / "data")]

    assert paper_runner.main(base + ["--capital", "1000", "--members", "macd,momentum"]) == 2
    assert "only for --strategy combo" in capsys.readouterr().err
    assert paper_runner.main(base + ["--capital", "1000", "--strategy", "combo",
                                     "--members", "macd,momentum"]) == 0
    capsys.readouterr()
    assert paper_runner.main(base) == 0
    settings = json.loads(capsys.readouterr().out)["settings"]
    assert settings["strategy"] == "combo" and settings["members"] == "macd,momentum"


def test_report_shows_stress_scenarios_once_positions_exist(tmp_path):
    from src.bnd.paper_runner import render_report

    data = make_data(121)
    today = {name: candles[:-1] for name, candles in data.items()}
    engine = engine_at(tmp_path)
    first = run_daily(engine, today, MARKETS, factory, config(), "sma", now_after(today))
    assert "Stress scenarios" not in render_report(engine, first)

    report = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))

    assert {row["scenario"] for row in report["scenarios"]} >= {"crisis_2008", "covid_2020"}
    assert "Stress scenarios" in render_report(engine, report)


def test_fit_limits_caps_net_currency_exposure(tmp_path):
    engine = engine_at(tmp_path, max_currency_pct=50, max_sector_pct=500)
    pairs = (Market("EURUSD", "EURUSD=X", "forex", 0.002, 0.005),
             Market("EURGBP", "EURGBP=X", "forex", 0.002, 0.005))
    for market in pairs:
        engine.register_instrument(instrument_for(market))
    assert engine.instrument("EURUSD").currency_pair == "EURUSD"

    fitted = fit_limits(engine, {"EURUSD": 0.4, "EURGBP": 0.4}, margin=1.0)

    # EUR would be +80%; both pairs hold EUR, so both shrink to fit 50%.
    assert fitted["EURUSD"] + fitted["EURGBP"] == pytest.approx(0.5)


def test_cli_cross_momentum_account(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paper_runner, "select_markets", lambda *a: MARKETS)
    write_data(tmp_path / "data", make_data())
    base = ["--state", str(tmp_path / "paper.sqlite"), "--data-dir", str(tmp_path / "data")]

    assert paper_runner.main(base + ["--capital", "1000", "--strategy", "cross_momentum",
                                     "--param", "fraction=0.9"]) == 2
    assert not (tmp_path / "paper.sqlite").exists()
    capsys.readouterr()
    assert paper_runner.main(base + ["--capital", "1000", "--strategy", "cross_momentum",
                                     "--param", "lookback=40", "--param", "skip=5",
                                     "--sizing-lookback", "20"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["signals"] == {"UP": 1, "DOWN": -1, "FX": 0}



def test_zero_atr_skips_the_market_instead_of_crashing(tmp_path, monkeypatch):
    data = make_data()
    engine = engine_at(tmp_path)
    monkeypatch.setattr(paper_runner, "average_true_range", lambda candles, period: 0.0)

    report = run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))

    skipped = [o for o in report["orders"] if o["status"] == "SKIPPED"]
    assert skipped and all("ATR is zero" in o["reason"] for o in skipped)
    assert engine.orders() == []                      # nothing was submitted
    assert not report["kill_switch"]



def test_obsolete_pending_order_is_cancelled_even_when_no_new_order_is_needed(tmp_path):
    from src.bnd.paper_engine import OrderRequest
    from src.bnd.paper_runner import rebalance

    data = make_data()
    engine = engine_at(tmp_path)
    for market in MARKETS:
        engine.register_instrument(instrument_for(market))
    paper_runner.feed_new_candles(engine, data)
    price = engine.mark("UP")["price"]
    engine.submit_order(OrderRequest("2000-01-01:UP", "UP", "BUY", 5, stop_loss=price * 0.9),
                        now_after(data))
    cfg = paper_runner.RunnerConfig(portfolio=config().portfolio)

    # No position and a zero target: nothing to trade, but yesterday's order is obsolete.
    plans = rebalance(engine, data, {}, cfg, now_after(data))

    assert plans == []
    assert engine.order("2000-01-01:UP")["status"] == "CANCELLED"


def test_invalid_settings_do_not_create_an_account(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paper_runner, "select_markets", lambda *a: MARKETS)
    write_data(tmp_path / "data", make_data())
    state = tmp_path / "paper.sqlite"

    for bad in (["--stop-atr", "-1"], ["--rebalance", "-5"], ["--max-leverage", "0"]):
        code = paper_runner.main(["--state", str(state), "--data-dir", str(tmp_path / "data"),
                                  "--capital", "1000", *bad])
        assert code == 2, bad
        assert not state.exists(), bad
    capsys.readouterr()
