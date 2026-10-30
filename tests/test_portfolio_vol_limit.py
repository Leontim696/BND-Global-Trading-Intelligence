"""Engine limit on the whole book's volatility, correlations included."""

from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.market_data import Candle
from src.bnd.paper_engine import EngineLimits, Instrument, OrderRequest, PaperEngine

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def feed(engine, symbol, days, sign=1):
    price = 100.0
    for i in range(days):
        price *= 1 + sign * 0.015 * (-1) ** i      # +-1.5% a day: about 29%/yr alone
        engine.on_bar(symbol, Candle(T0 + timedelta(days=i), price, price, price, price, 1e9))


@pytest.fixture
def engine(tmp_path):
    eng = PaperEngine.create(tmp_path / "vol.sqlite", 10_000, currency="USD",
                             limits=EngineLimits(max_portfolio_vol_pct=40), now=T0)
    for symbol, cls in (("A", "index"), ("B", "commodity"), ("H", "bond")):
        eng.register_instrument(Instrument(symbol, cls, fee_pct=0, slippage_pct=0))
    feed(eng, "A", 40)
    feed(eng, "B", 40)            # moves exactly like A
    feed(eng, "H", 40, sign=-1)   # moves exactly opposite
    return eng


def buy(engine, cid, symbol, side="BUY", quantity=95):
    price = engine.mark(symbol)["price"]
    stop = price * (0.99 if side == "BUY" else 1.01)
    now = T0 + timedelta(days=40)
    order = engine.submit_order(OrderRequest(cid, symbol, side, quantity, stop_loss=stop), now)
    engine.on_bar(symbol, Candle(now, price, price, price, price, 1e9))
    return order


def test_one_market_alone_fits(engine):
    assert buy(engine, "a", "A")["status"] == "PENDING"
    assert 0.25 < engine.portfolio_volatility() < 0.33


def test_second_market_moving_together_is_refused(engine):
    buy(engine, "a", "A")

    second = buy(engine, "b", "B")

    assert second["status"] == "REJECTED"
    assert "Portfolio volatility" in second["reason"] and "moving together" in second["reason"]


def test_a_hedge_that_lowers_volatility_is_allowed(engine):
    buy(engine, "a", "A")

    hedge = buy(engine, "h", "H")

    assert hedge["status"] == "PENDING"
    assert engine.portfolio_volatility() < 0.05


def test_not_enough_history_skips_the_check(tmp_path):
    eng = PaperEngine.create(tmp_path / "new.sqlite", 10_000, currency="USD", now=T0)
    eng.register_instrument(Instrument("A", "index", fee_pct=0, slippage_pct=0))
    feed(eng, "A", 5)

    assert eng.portfolio_volatility({"A": 9_000}) is None


def test_history_is_trimmed_to_the_lookback(tmp_path):
    eng = PaperEngine.create(tmp_path / "long.sqlite", 10_000, currency="USD", now=T0)
    eng.register_instrument(Instrument("A", "index", fee_pct=0, slippage_pct=0))
    feed(eng, "A", 100)

    rows = eng._db.execute("SELECT COUNT(*) FROM closes WHERE symbol = 'A'").fetchone()[0]

    assert rows == eng.limits().vol_lookback + 1
