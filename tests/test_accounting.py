"""Contabilitate cu rezultate cunoscute, calculate de mână, plus reconcilierea independentă."""

from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.market_data import Candle
from src.bnd.paper_engine import EngineLimits, Instrument, OrderRequest, PaperEngine
from src.bnd.reconcile import reconcile

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def bar(day, o, h=None, l=None, c=None):
    return Candle(T0 + DAY * day, o, h or max(o, c or o), l or min(o, c or o), c or o, 1000)


def account(tmp_path, instrument, **limits):
    engine = PaperEngine.create(tmp_path / "a.sqlite", 10_000.0, currency="USD",
                                limits=EngineLimits(**limits), now=T0)
    engine.register_instrument(instrument)
    return engine


def test_long_round_trip_matches_hand_calculation(tmp_path):
    # Comision 0,1% și slippage 0,1% pe fiecare parte.
    engine = account(tmp_path, Instrument("AAA", "index", fee_pct=0.1, slippage_pct=0.1))
    engine.on_bar("AAA", bar(0, 100))
    engine.submit_order(OrderRequest("buy", "AAA", "BUY", 10, stop_loss=99), T0 + DAY / 2)
    engine.on_bar("AAA", bar(1, 100, c=105))           # umplut la deschiderea 100 -> 100,1

    buy_price = 100 * 1.001                             # 100,1
    buy_fee = 10 * buy_price * 0.001                    # 1,001
    cash = 10_000 - 10 * buy_price - buy_fee            # 8 998,999 (-1001 - 1,001)
    assert engine.account()["cash"] == pytest.approx(cash)
    assert engine.equity() == pytest.approx(cash + 10 * 105)          # 10 048,999 la marcaj 105

    engine.submit_order(OrderRequest("sell", "AAA", "SELL", 10, reduce_only=True), T0 + DAY * 1.5)
    engine.on_bar("AAA", bar(2, 110, c=110))            # vândut la 110 -> 109,89
    sell_price = 110 * 0.999
    sell_fee = 10 * sell_price * 0.001
    final = cash + 10 * sell_price - sell_fee
    assert engine.equity() == pytest.approx(final)
    assert engine.positions() == []
    # Câștig net = diferența de preț minus slippage și comisioane pe ambele părți.
    assert final - 10_000 == pytest.approx(10 * (sell_price - buy_price) - buy_fee - sell_fee)
    assert reconcile(engine)["ok"]


def test_short_profits_when_price_falls_and_pays_costs(tmp_path):
    engine = account(tmp_path, Instrument("AAA", "index", fee_pct=0.1, slippage_pct=0.1))
    engine.on_bar("AAA", bar(0, 100))
    engine.submit_order(OrderRequest("short", "AAA", "SELL", 10, stop_loss=101), T0 + DAY / 2)
    engine.on_bar("AAA", bar(1, 100, c=95))

    sell_price = 100 * 0.999                            # 99,9
    fee = 10 * sell_price * 0.001
    cash = 10_000 + 10 * sell_price - fee
    assert engine.account()["cash"] == pytest.approx(cash)
    assert engine.equity() == pytest.approx(cash - 10 * 95)           # pierde valoarea poziției
    assert engine.positions()[0]["quantity"] == -10
    assert reconcile(engine)["ok"]


def test_carry_is_charged_on_the_held_position_per_year_fraction(tmp_path):
    engine = account(tmp_path, Instrument("AAA", "index", fee_pct=0, slippage_pct=0,
                                          carry_pct_annual=10.0))
    engine.on_bar("AAA", bar(0, 100))
    engine.submit_order(OrderRequest("buy", "AAA", "BUY", 10, stop_loss=99), T0 + DAY / 2)
    engine.on_bar("AAA", bar(1, 100, c=100))
    cash_after_buy = engine.account()["cash"]
    engine.on_bar("AAA", bar(2, 100, c=100))             # încă o zi de deținere

    expected = 10 * 100 * 0.10 * (1 / 365.25)            # 0,2738 pe o zi
    assert cash_after_buy - engine.account()["cash"] == pytest.approx(expected, rel=1e-9)
    assert reconcile(engine)["ok"]


def test_financing_charges_only_borrowed_exposure_per_calendar_day(tmp_path):
    engine = account(tmp_path, Instrument("AAA", "index", fee_pct=0, slippage_pct=0),
                     financing_pct_annual=5.0, max_gross_leverage=3.0,
                     max_position_pct=250, max_sector_pct=250)
    engine.on_bar("AAA", bar(0, 100))
    engine.submit_order(OrderRequest("buy", "AAA", "BUY", 200, stop_loss=99.5), T0 + DAY / 2)  # 2x
    engine.on_bar("AAA", bar(1, 100, c=100))
    before = engine.account()["cash"]
    engine.on_bar("AAA", bar(2, 100, c=100))

    borrowed = 200 * 100 - 10_000                        # 10.000 împrumutat
    interest = borrowed * 0.05 * 1 / 365.25
    assert before - engine.account()["cash"] == pytest.approx(interest, rel=1e-9)
    assert reconcile(engine)["ok"]


def test_reconcile_detects_a_tampered_cash_balance(tmp_path):
    engine = account(tmp_path, Instrument("AAA", "index", fee_pct=0, slippage_pct=0))
    engine.on_bar("AAA", bar(0, 100))
    engine._db.execute("UPDATE account SET cash = cash + 5")
    result = reconcile(engine)

    assert not result["ok"]
    assert any(not c["ok"] and "numerar" in c["check"] for c in result["checks"])


def test_reconcile_detects_a_position_without_trades(tmp_path):
    engine = account(tmp_path, Instrument("AAA", "index", fee_pct=0, slippage_pct=0))
    engine.on_bar("AAA", bar(0, 100))
    engine._db.execute("INSERT INTO positions (symbol, quantity, avg_price, opened_at)"
                       " VALUES ('AAA', 3, 100, '2026-01-05T00:00:00+00:00')")

    assert not reconcile(engine)["ok"]


def test_a_fresh_account_reconciles_and_reports_costs_split(tmp_path):
    engine = account(tmp_path, Instrument("AAA", "index", fee_pct=0.1, slippage_pct=0))
    result = reconcile(engine)

    assert result["ok"] and result["net_profit"] == 0
    assert result["costs"]["total"] == 0 and result["initial"] == 10_000
