"""Broker margin per market (ESMA retail CFD rules) and margin close-out."""

from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.market_data import Candle
from src.bnd.paper_engine import EngineLimits, Instrument, OrderRequest, PaperEngine
from src.bnd.paper_runner import fit_limits, instrument_for
from src.bnd.universe import UNIVERSES, Market, esma_margin_pct

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
LOOSE = dict(max_position_pct=300, max_sector_pct=500, max_risk_per_trade_pct=100,
             max_portfolio_vol_pct=0, max_drawdown_pct=99, max_daily_loss_pct=99)


def test_esma_margins_for_every_market():
    by_name = {m.name: esma_margin_pct(m) for markets in UNIVERSES.values() for m in markets}

    assert by_name["EURUSD"] == by_name["USDJPY"] == 3.33
    assert by_name["AUDUSD"] == 5.0                      # AUD is not a major currency
    assert by_name["GOLD"] == by_name["SP500"] == by_name["DAX"] == 5.0
    assert by_name["SILVER"] == by_name["CRUDE_OIL"] == by_name["EMERGING"] == 10.0
    assert by_name["US10Y_NOTE"] == 20.0
    assert by_name["BITCOIN"] == by_name["ETHEREUM"] == 50.0
    assert all(0 < value <= 50 for value in by_name.values())


def crypto_account(tmp_path):
    eng = PaperEngine.create(tmp_path / "m.sqlite", 10_000, currency="USD",
                             limits=EngineLimits(**LOOSE), now=T0)
    eng.register_instrument(Instrument("BTC", "crypto", fee_pct=0, slippage_pct=0,
                                       margin_pct=50))
    eng.on_bar("BTC", Candle(T0, 100, 100, 100, 100, 1e9))
    return eng


def test_order_needing_more_margin_than_equity_is_refused(tmp_path):
    eng = crypto_account(tmp_path)
    now = T0 + timedelta(hours=1)

    too_big = eng.submit_order(OrderRequest("big", "BTC", "BUY", 250, stop_loss=50), now)
    fits = eng.submit_order(OrderRequest("ok", "BTC", "BUY", 180, stop_loss=50), now)

    assert too_big["status"] == "REJECTED" and too_big["reason"].startswith("Margin")
    assert fits["status"] == "PENDING"


def test_margin_close_out_liquidates(tmp_path):
    eng = crypto_account(tmp_path)
    eng.submit_order(OrderRequest("ok", "BTC", "BUY", 180, stop_loss=50),
                     T0 + timedelta(hours=1))
    eng.on_bar("BTC", Candle(T0 + timedelta(days=1), 100, 100, 100, 100, 1e9))
    assert eng.positions()

    # -45%: equity 10,000 - 8,100 = 1,900, below half of the 4,950 margin needed.
    eng.on_bar("BTC", Candle(T0 + timedelta(days=2), 100, 100, 55, 55, 1e9))

    account = eng.account()
    assert account["kill_switch"] and "margin close-out" in account["kill_reason"]
    assert eng.positions() == []


def test_runner_scales_weights_to_the_margin_available(tmp_path):
    eng = PaperEngine.create(tmp_path / "r.sqlite", 10_000, currency="USD",
                             limits=EngineLimits(**LOOSE, max_gross_leverage=5), now=T0)
    coins = (Market("BITCOIN", "BTC-USD", "crypto", 0.1, 0.05),
             Market("ETHEREUM", "ETH-USD", "crypto", 0.1, 0.05))
    for market in coins:
        eng.register_instrument(instrument_for(market))
    assert eng.instrument("BITCOIN").margin_pct == 50

    fitted = fit_limits(eng, {"BITCOIN": 1.5, "ETHEREUM": 1.5}, margin=1.0)

    # 3x crypto would need 150% of equity as margin; it is cut to 2x.
    assert sum(abs(w) for w in fitted.values()) == pytest.approx(2.0)


def test_margin_must_be_a_percentage():
    from src.bnd.paper_engine import PaperEngineError

    with pytest.raises(PaperEngineError):
        Instrument("X", "crypto", margin_pct=150)
