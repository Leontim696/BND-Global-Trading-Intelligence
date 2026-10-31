"""Tests for the persistent paper-trading engine (virtual money only)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.market_data import Candle
from src.bnd.paper_engine import (
    EngineLimits,
    Instrument,
    OrderRequest,
    PaperEngine,
    PaperEngineError,
    TradingMode,
)

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
DAY = timedelta(days=1)
FREE = dict(fee_pct=0.0, slippage_pct=0.0)


def bar(day, o, h, l, c, volume=1_000_000):
    return Candle(T0 + DAY * day, o, h, l, c, volume)


@pytest.fixture
def engine(tmp_path):
    e = PaperEngine.create(tmp_path / "paper.db", 10_000,
                           limits=EngineLimits(max_risk_per_trade_pct=5.0), now=T0)
    e.register_instrument(Instrument("EURUSD", "forex", **FREE))
    e.register_instrument(Instrument("GOLD", "commodity", sector="metals", **FREE))
    e.on_bar("EURUSD", bar(0, 100, 100, 100, 100))
    e.on_bar("GOLD", bar(0, 100, 100, 100, 100))
    yield e
    e.close()


def buy(cid, qty, stop=95.0, **kw):
    return OrderRequest(cid, kw.pop("symbol", "EURUSD"), "BUY", qty, stop_loss=stop, **kw)


def test_new_account_needs_confirmed_capital(tmp_path):
    with pytest.raises(PaperEngineError):
        PaperEngine.create(tmp_path / "x.db", 0)
    PaperEngine.create(tmp_path / "y.db", 5_000).close()
    with pytest.raises(PaperEngineError, match="already exists"):
        PaperEngine.create(tmp_path / "y.db", 5_000)


def test_live_mode_is_refused():
    with pytest.raises(PaperEngineError, match="LIVE"):
        PaperEngine.require_mode(TradingMode.LIVE)
    PaperEngine.require_mode(TradingMode.PAPER)
    assert PaperEngine.mode == TradingMode.PAPER


def test_market_order_fills_at_next_open_with_costs(tmp_path):
    e = PaperEngine.create(tmp_path / "c.db", 10_000, now=T0)
    e.register_instrument(Instrument("EURUSD", "forex", fee_pct=0.1, slippage_pct=0.05))
    e.on_bar("EURUSD", bar(0, 100, 100, 100, 100))

    order = e.submit_order(buy("o1", 10), T0)
    assert order["status"] == "PENDING"
    e.on_bar("EURUSD", bar(1, 101, 102, 100, 101.5))

    fill = e.fills()[0]
    assert fill["price"] == pytest.approx(101 * 1.0005)
    assert fill["fee"] == pytest.approx(10 * 101 * 1.0005 * 0.001)
    assert e.order("o1")["status"] == "FILLED"
    assert e.equity() == pytest.approx(10_000 - 10 * fill["price"] - fill["fee"] + 10 * 101.5)


def test_duplicate_order_is_not_traded_twice(engine):
    first = engine.submit_order(buy("dup", 10), T0)
    second = engine.submit_order(buy("dup", 99), T0)

    assert second == first
    engine.on_bar("EURUSD", bar(1, 100, 101, 99, 100))
    assert [f["quantity"] for f in engine.fills()] == [10]
    assert engine.journal("duplicate_order_ignored")


def test_state_survives_restart(tmp_path, engine):
    engine.submit_order(buy("a", 10), T0)
    engine.on_bar("EURUSD", bar(1, 100, 101, 99, 100))
    engine.submit_order(OrderRequest("lim", "GOLD", "BUY", 5, "LIMIT", limit_price=90, stop_loss=85), T0 + DAY)
    path = engine.path
    before = engine.summary()
    engine.close()

    resumed = PaperEngine.open(path)
    assert resumed.summary() == before
    resumed.on_bar("GOLD", bar(2, 95, 96, 89, 92))
    assert resumed.order("lim")["status"] == "FILLED"
    assert resumed.order("lim")["average_price"] == pytest.approx(90)
    resumed.close()


def test_limit_order_waits_then_expires(engine):
    engine.submit_order(OrderRequest("l", "EURUSD", "BUY", 10, "LIMIT", limit_price=90, stop_loss=85), T0)
    for day in range(1, 6):
        engine.on_bar("EURUSD", bar(day, 100, 101, 99, 100))

    assert engine.order("l")["status"] == "EXPIRED"
    assert engine.fills() == []


def test_partial_fills_limited_by_liquidity(tmp_path):
    e = PaperEngine.create(tmp_path / "p.db", 100_000, limits=EngineLimits(max_risk_per_trade_pct=5), now=T0)
    e.register_instrument(Instrument("SMALL", "crypto", max_participation=0.1, **FREE))
    e.on_bar("SMALL", bar(0, 10, 10, 10, 10, volume=100))
    e.submit_order(OrderRequest("big", "SMALL", "BUY", 25, stop_loss=9), T0)

    e.on_bar("SMALL", bar(1, 10, 10, 10, 10, volume=100))
    assert e.order("big")["status"] == "PARTIAL" and e.order("big")["filled_quantity"] == 10
    e.on_bar("SMALL", bar(2, 10, 10, 10, 10, volume=100))
    e.on_bar("SMALL", bar(3, 10, 10, 10, 10, volume=100))
    assert e.order("big")["status"] == "FILLED"
    assert e.positions()[0]["quantity"] == pytest.approx(25)


def test_stop_loss_and_gap_fill_at_worse_open(engine):
    engine.submit_order(buy("s", 10, stop=95), T0)
    engine.on_bar("EURUSD", bar(1, 100, 101, 99, 100))
    engine.on_bar("EURUSD", bar(2, 90, 92, 88, 91))   # gaps through 95

    exit_fill = engine.fills()[-1]
    assert exit_fill["reason"] == "stop_loss" and exit_fill["price"] == pytest.approx(90)
    assert engine.positions() == []


def test_take_profit(engine):
    engine.submit_order(buy("t", 10, stop=95, take_profit=105), T0)
    engine.on_bar("EURUSD", bar(1, 100, 101, 99, 100))
    engine.on_bar("EURUSD", bar(2, 101, 106, 100, 104))

    assert engine.fills()[-1]["reason"] == "take_profit"
    assert engine.fills()[-1]["price"] == pytest.approx(105)


def test_trailing_stop_follows_the_high(engine):
    engine.submit_order(buy("tr", 10, stop=90, trailing_stop_pct=5), T0)
    engine.on_bar("EURUSD", bar(1, 100, 100, 100, 100))
    engine.on_bar("EURUSD", bar(2, 100, 110, 100, 109))   # best price 110
    engine.on_bar("EURUSD", bar(3, 108, 108, 103, 104))   # trail 104.5 hit

    fill = engine.fills()[-1]
    assert fill["reason"] == "trailing_stop" and fill["price"] == pytest.approx(104.5)


def test_short_position_and_simultaneous_long(engine):
    engine.submit_order(OrderRequest("sh", "GOLD", "SELL", 10, stop_loss=110), T0)
    engine.submit_order(buy("lg", 10), T0)
    engine.on_bar("GOLD", bar(1, 100, 100, 100, 100))
    engine.on_bar("EURUSD", bar(1, 100, 100, 100, 100))
    engine.on_bar("GOLD", bar(2, 100, 100, 90, 90))

    positions = {p["symbol"]: p["quantity"] for p in engine.positions()}
    assert positions == {"GOLD": -10, "EURUSD": 10}
    assert engine.equity() == pytest.approx(10_100)


@pytest.mark.parametrize("request_, reason", [
    (OrderRequest("ns", "EURUSD", "BUY", 10), "stop_loss is required"),
    (OrderRequest("ws", "EURUSD", "BUY", 10, stop_loss=101), "below entry"),
    (OrderRequest("big", "EURUSD", "BUY", 150, stop_loss=95), "Position limit"),
    (OrderRequest("unk", "MOON", "BUY", 1, stop_loss=1), "Unknown instrument"),
])
def test_mandatory_pre_trade_checks(engine, request_, reason):
    result = engine.submit_order(request_, T0)

    assert result["status"] == "REJECTED" and reason in result["reason"]


def test_risk_per_trade_and_leverage_limits(tmp_path):
    e = PaperEngine.create(tmp_path / "r.db", 10_000,
                           limits=EngineLimits(max_risk_per_trade_pct=1.0, max_position_pct=500,
                                               max_sector_pct=500, max_gross_leverage=2),
                           now=T0)
    e.register_instrument(Instrument("ES", "index", **FREE))
    e.on_bar("ES", bar(0, 100, 100, 100, 100))

    # 1% risk with a 5% stop allows 2,000 notional = 20 units.
    too_risky = e.submit_order(OrderRequest("r1", "ES", "BUY", 50, stop_loss=95), T0)
    assert too_risky["status"] == "REJECTED" and "at most 2000.00" in too_risky["reason"]
    # A wide 1% stop allows more risk-wise, but 300 units = 3x > 2x leverage.
    levered = e.submit_order(OrderRequest("r2", "ES", "BUY", 300, stop_loss=99.9), T0)
    assert levered["status"] == "REJECTED" and "Risk engine" in levered["reason"]
    ok = e.submit_order(OrderRequest("r3", "ES", "BUY", 20, stop_loss=95), T0)
    assert ok["status"] == "PENDING"


def test_sector_limit(tmp_path):
    e = PaperEngine.create(tmp_path / "s.db", 10_000,
                           limits=EngineLimits(max_risk_per_trade_pct=50, max_sector_pct=80),
                           now=T0)
    for name in ("GOLD", "SILVER"):
        e.register_instrument(Instrument(name, "commodity", sector="metals", **FREE))
        e.on_bar(name, bar(0, 100, 100, 100, 100))
    e.submit_order(OrderRequest("g", "GOLD", "BUY", 45, stop_loss=90), T0)
    e.on_bar("GOLD", bar(1, 100, 100, 100, 100))

    # 4,500 + 4,500 in metals = 90% of equity > 80%.
    second = e.submit_order(OrderRequest("s", "SILVER", "BUY", 45, stop_loss=90), T0 + DAY)

    assert second["status"] == "REJECTED" and "Sector limit" in second["reason"]


def test_stale_data_blocks_new_risk(engine):
    late = engine.submit_order(buy("late", 10), T0 + timedelta(days=10))

    assert late["status"] == "REJECTED" and "Stale" in late["reason"]


def test_extreme_gap_blocks_new_risk_at_fill(engine):
    engine.submit_order(buy("g", 10, stop=80), T0)
    engine.on_bar("EURUSD", bar(1, 130, 131, 129, 130))   # +30% gap

    order = engine.order("g")
    assert order["status"] == "REJECTED" and "At fill" in order["reason"]
    assert engine.fills() == []


def test_drawdown_kill_switch_is_persistent(tmp_path):
    e = PaperEngine.create(tmp_path / "k.db", 10_000,
                           limits=EngineLimits(max_risk_per_trade_pct=50, max_drawdown_pct=10,
                                               max_daily_loss_pct=50),
                           now=T0)
    e.register_instrument(Instrument("ES", "index", **FREE))
    e.on_bar("ES", bar(0, 100, 100, 100, 100))
    # The risk engine sizes the stop-out loss within the 10% drawdown limit...
    e.submit_order(OrderRequest("k", "ES", "BUY", 90, stop_loss=95), T0)
    e.on_bar("ES", bar(1, 100, 100, 100, 100))
    # ...but a gap through the stop loses 90 x 14 = 12.6%.
    e.on_bar("ES", bar(2, 86, 87, 85, 86))

    assert e.positions() == []
    assert e.fills()[-1]["price"] == pytest.approx(86)
    assert "Drawdown" in e.summary()["kill_reason"]
    path = e.path
    e.close()

    resumed = PaperEngine.open(path)
    assert resumed.summary()["kill_switch"]
    blocked = resumed.submit_order(OrderRequest("after", "ES", "BUY", 1, stop_loss=80), T0 + 2 * DAY)
    assert blocked["status"] == "REJECTED" and "Kill switch" in blocked["reason"]
    with pytest.raises(PaperEngineError):
        resumed.reset_kill_switch("yes", T0 + 3 * DAY)
    resumed.reset_kill_switch("RESET-KILL-SWITCH", T0 + 3 * DAY)
    assert not resumed.summary()["kill_switch"]
    resumed.close()


def test_daily_loss_counts_overnight_gap(tmp_path):
    e = PaperEngine.create(tmp_path / "d.db", 10_000,
                           limits=EngineLimits(max_risk_per_trade_pct=50, max_daily_loss_pct=3,
                                               max_drawdown_pct=50),
                           now=T0)
    e.register_instrument(Instrument("ES", "index", **FREE))
    e.on_bar("ES", bar(0, 100, 100, 100, 100))
    e.submit_order(OrderRequest("d", "ES", "BUY", 50, stop_loss=95), T0)
    e.on_bar("ES", bar(1, 100, 100, 100, 100))
    # Overnight gap through the stop: 50 x 7 = 3.5% of the day-start equity.
    e.on_bar("ES", bar(2, 93, 94, 93, 94))

    assert e.summary()["kill_switch"] and "Daily loss" in e.summary()["kill_reason"]


def test_reduce_only_never_opens_a_position(engine):
    engine.submit_order(buy("pos", 10, stop=95), T0)
    engine.on_bar("EURUSD", bar(1, 100, 100, 100, 100))
    engine.submit_order(OrderRequest("cut", "EURUSD", "SELL", 10, reduce_only=True), T0 + DAY)
    engine.on_bar("EURUSD", bar(2, 90, 90, 90, 90))     # stop closes the long first

    assert engine.positions() == []
    assert engine.order("cut")["status"] == "CANCELLED"


def test_error_rolls_back_and_trips_kill_switch(engine, monkeypatch):
    engine.submit_order(buy("e", 10), T0)
    fills_before = engine.fills()

    def boom(*args, **kwargs):
        raise RuntimeError("feed corrupted")

    monkeypatch.setattr(engine, "_fill_orders", boom)
    with pytest.raises(RuntimeError):
        engine.on_bar("EURUSD", bar(1, 100, 100, 100, 100))

    assert engine.fills() == fills_before
    assert engine.mark("EURUSD")["time"] == (T0).isoformat()   # bar rolled back
    assert engine.summary()["kill_switch"] and "feed corrupted" in engine.summary()["kill_reason"]


def test_old_bars_are_ignored(engine):
    engine.on_bar("EURUSD", bar(0, 50, 50, 50, 50))

    assert engine.mark("EURUSD")["price"] == 100
    assert engine.journal("bar_ignored")


def test_carry_is_charged(tmp_path):
    e = PaperEngine.create(tmp_path / "f.db", 10_000, limits=EngineLimits(max_risk_per_trade_pct=50), now=T0)
    e.register_instrument(Instrument("BTC", "crypto", carry_pct_annual=10, **FREE))
    e.on_bar("BTC", bar(0, 100, 100, 100, 100))
    e.submit_order(OrderRequest("c", "BTC", "BUY", 50, stop_loss=95), T0)
    for day in range(1, 11):
        e.on_bar("BTC", bar(day, 100, 100, 100, 100))

    carry = sum(j["payload"]["amount"] for j in e.journal("carry"))
    assert carry == pytest.approx(5_000 * 0.10 * 9 / 365.25)


def test_stress_test_does_not_change_state(engine):
    engine.submit_order(buy("x", 50), T0)
    engine.on_bar("EURUSD", bar(1, 100, 100, 100, 100))
    before = engine.summary()

    shocked = engine.stress_test({"EURUSD": -20})

    assert shocked["shocked_equity"] == pytest.approx(engine.equity() - 1_000)
    assert engine.summary() == before


def test_currency_limit_counts_both_sides_of_each_pair(tmp_path):
    from src.bnd.paper_engine import EngineLimits, Instrument, OrderRequest, PaperEngine

    eng = PaperEngine.create(tmp_path / "fx.sqlite", 10_000, currency="USD",
                             limits=EngineLimits(max_currency_pct=60, max_risk_per_trade_pct=50,
                                                 max_sector_pct=500),
                             now=T0)
    for pair in ("EURUSD", "EURGBP"):
        eng.register_instrument(Instrument(pair, "forex", fee_pct=0, slippage_pct=0,
                                           currency_pair=pair))
        eng.on_bar(pair, bar(0, 1.0, 1.0, 1.0, 1.0))
    now = T0 + timedelta(hours=1)

    first = eng.submit_order(OrderRequest("a", "EURUSD", "BUY", 5_000, stop_loss=0.9), now)
    eng.on_bar("EURUSD", bar(1, 1.0, 1.0, 1.0, 1.0))
    assert first["status"] == "PENDING" and eng.currency_exposure() == {"EUR": 5_000, "USD": -5_000}

    # Another 2,000 long EUR (via EURGBP) would make EUR 70% > 60%.
    too_much = eng.submit_order(OrderRequest("b", "EURGBP", "BUY", 2_000, stop_loss=0.9), now)
    assert too_much["status"] == "REJECTED" and "Currency limit 60" in too_much["reason"]
    assert "EUR" in too_much["reason"]
    # Short EURGBP lowers EUR exposure; GBP +4,000 = 40% stays inside.
    hedge = eng.submit_order(OrderRequest("c", "EURGBP", "SELL", 4_000, stop_loss=1.1), now)
    assert hedge["status"] == "PENDING"


def test_currency_pair_must_be_six_capital_letters():
    from src.bnd.paper_engine import Instrument, PaperEngineError

    with pytest.raises(PaperEngineError):
        Instrument("X", "forex", currency_pair="eurusd")


def test_old_accounts_get_the_default_currency_limit(tmp_path):
    import json

    from src.bnd.paper_engine import PaperEngine

    eng = PaperEngine.create(tmp_path / "old.sqlite", 1_000, now=T0)
    data = json.loads(eng._db.execute("SELECT limits FROM account").fetchone()[0])
    del data["max_currency_pct"]
    eng._db.execute("UPDATE account SET limits = ?", (json.dumps(data),))

    assert eng.limits().max_currency_pct == 100.0



def test_limit_orders_never_fill_worse_than_their_limit(tmp_path):
    from src.bnd.paper_engine import EngineLimits, Instrument, OrderRequest, PaperEngine

    eng = PaperEngine.create(tmp_path / "lim.sqlite", 10_000, currency="USD",
                             limits=EngineLimits(max_portfolio_vol_pct=0), now=T0)
    eng.register_instrument(Instrument("X", "index"))          # default slippage 0.05%
    eng.on_bar("X", bar(0, 100, 100, 100, 100))
    later = T0 + timedelta(hours=1)
    eng.submit_order(OrderRequest("buy", "X", "BUY", 10, order_type="LIMIT", limit_price=100,
                                  stop_loss=90), later)
    eng.submit_order(OrderRequest("market", "X", "BUY", 5, stop_loss=90), later)

    eng.on_bar("X", bar(1, 100, 101, 99, 100))

    fills = {f["client_order_id"]: f["price"] for f in eng.fills()}
    assert fills["buy"] == 100.0                         # not 100.05
    assert fills["market"] == pytest.approx(100.05)      # market orders still slip


def test_zero_day_start_equity_does_not_crash_the_bar(tmp_path):
    from src.bnd.paper_engine import Instrument, PaperEngine

    eng = PaperEngine.create(tmp_path / "zero.sqlite", 10_000, currency="USD", now=T0)
    eng.register_instrument(Instrument("X", "index"))
    eng.on_bar("X", bar(0, 100, 100, 100, 100))
    eng._db.execute("UPDATE account SET day_start_equity = 0")

    eng.on_bar("X", bar(0, 100, 100, 100, 100).__class__(T0 + timedelta(hours=2),
                                                         100, 100, 100, 100, 1e9))

    assert not eng.account()["kill_switch"]
