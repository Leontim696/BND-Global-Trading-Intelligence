"""Offline backtester tests on hand-built candles."""

import math
from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.backtester import (
    BacktestConfig,
    CostModel,
    compute_metrics,
    run_backtest,
    split_candles,
)
from src.bnd.market_data import Candle, MarketDataError
from src.bnd.risk_engine import RiskLimits
from src.bnd.strategies import buy_and_hold, donchian_breakout, sma_crossover

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
NO_COSTS = CostModel(fee_pct=0.0, slippage_pct=0.0)


def bars(prices, step_hours=4, spread=0.0):
    """Candles whose open is the previous close; prices are closes."""
    candles = []
    previous = prices[0]
    for i, close in enumerate(prices):
        open_ = previous
        candles.append(Candle(
            open_time=START + timedelta(hours=step_hours * i),
            open=open_,
            high=max(open_, close) + spread,
            low=min(open_, close) - spread,
            close=close,
            volume=1.0,
        ))
        previous = close
    return candles


def fixed(*targets):
    """Strategy returning a scripted target per bar index."""
    def strategy(history):
        return targets[len(history) - 1]
    return strategy


def test_strategy_never_sees_future_candles():
    candles = bars([100, 101, 102, 103, 104])
    seen = []

    def strategy(history):
        seen.append(history[-1].open_time)
        assert len(history) == len(seen)
        return 0

    run_backtest(candles, strategy)

    assert seen == [c.open_time for c in candles]


def test_entry_executes_at_next_open_with_costs():
    candles = bars([100, 110, 120, 130])
    config = BacktestConfig(costs=CostModel(fee_pct=0.1, slippage_pct=0.05))

    result = run_backtest(candles, fixed(1, 1, 0, 0), config)

    trade = result.trades[0]
    # Signal on bar 0 close -> fill at bar 1 open (=100) plus slippage.
    assert trade.entry_time == candles[1].open_time
    assert trade.entry_price == pytest.approx(100 * 1.0005)
    # Flat signal on bar 2 close -> exit at bar 3 open (=120) minus slippage.
    assert trade.exit_time == candles[3].open_time
    assert trade.exit_price == pytest.approx(120 * 0.9995)
    assert trade.exit_reason == "signal"


def test_buy_and_hold_return_matches_hand_calculation():
    candles = bars([100, 100, 150, 200])
    fee = 0.001
    config = BacktestConfig(costs=CostModel(fee_pct=0.1, slippage_pct=0.0))

    result = run_backtest(candles, buy_and_hold(), config)

    quantity = 10_000 / (100 * (1 + fee))
    final = quantity * 200 * (1 - fee)
    assert result.metrics["final_equity"] == pytest.approx(final)
    assert result.trades[-1].exit_reason == "end_of_data"
    assert result.metrics["total_fees"] == pytest.approx(
        quantity * 100 * fee + quantity * 200 * fee
    )


def test_flat_strategy_keeps_equity_and_has_no_trades():
    result = run_backtest(bars([100, 90, 120, 80]), fixed(0, 0, 0, 0))

    assert result.trades == []
    assert result.metrics["final_equity"] == 10_000
    assert result.metrics["max_drawdown_pct"] == 0


def test_short_profits_when_price_falls():
    candles = bars([100, 100, 80, 60])
    config = BacktestConfig(costs=NO_COSTS, allow_short=True)

    result = run_backtest(candles, fixed(-1, -1, -1, -1), config)

    assert result.trades[0].side == -1
    assert result.metrics["final_equity"] == pytest.approx(10_000 * 1.4)


def test_short_signal_ignored_unless_allowed():
    result = run_backtest(bars([100, 100, 80]), fixed(-1, -1, -1))

    assert result.trades == []


def test_stop_loss_fills_at_stop_price():
    # Bar 2 trades down to 85 intrabar, through the 90 stop.
    candles = bars([100, 100, 95])
    candles[2] = Candle(candles[2].open_time, 100, 101, 85, 95, 1)
    config = BacktestConfig(costs=NO_COSTS, stop_loss_pct=10.0)

    result = run_backtest(candles, fixed(1, 1, 1), config)

    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(90)
    assert result.metrics["final_equity"] == pytest.approx(9_000)


def test_stop_loss_gap_fills_at_worse_open():
    candles = bars([100, 100])
    candles.append(Candle(START + timedelta(hours=8), 70, 75, 65, 72, 1))
    config = BacktestConfig(costs=NO_COSTS, stop_loss_pct=10.0)

    result = run_backtest(candles, fixed(1, 1, 1), config)

    assert result.trades[0].exit_price == pytest.approx(70)


def test_no_reentry_after_stop_until_signal_changes():
    candles = bars([100, 100, 95, 96, 97, 98])
    candles[2] = Candle(candles[2].open_time, 100, 101, 85, 95, 1)
    config = BacktestConfig(costs=NO_COSTS, stop_loss_pct=10.0)

    # Stays long-biased after the stop, then goes flat, then long again.
    result = run_backtest(candles, fixed(1, 1, 1, 0, 1, 1), config)

    assert [t.exit_reason for t in result.trades] == ["stop_loss", "end_of_data"]
    assert result.trades[1].entry_time == candles[5].open_time


def test_risk_engine_sizes_position_from_stop():
    candles = bars([100, 100, 100])
    config = BacktestConfig(
        costs=NO_COSTS,
        stop_loss_pct=5.0,
        risk_limits=RiskLimits(1.0, 3.0, 25.0, 100.0, 1.0),
    )

    result = run_backtest(candles, fixed(1, 1, 1), config)

    # 1% risk of 10,000 with a 5% stop -> 2,000 notional -> 20 units.
    assert result.trades[0].quantity == pytest.approx(20)


def test_risk_engine_rejects_entry_after_daily_loss():
    # Sizing caps the planned loss at the 3% daily limit, but a gap
    # through the 10% stop loses more; later entries that day are vetoed.
    candles = bars([100, 100], step_hours=1)
    gap_time = START + timedelta(hours=2)
    candles.append(Candle(gap_time, 50, 52, 48, 50, 1))
    candles += [
        Candle(gap_time + timedelta(hours=h), 50, 50, 50, 50, 1)
        for h in (1, 2, 3)
    ]
    config = BacktestConfig(
        costs=NO_COSTS,
        stop_loss_pct=10.0,
        risk_limits=RiskLimits(50.0, 3.0, 25.0, 100.0, 1.0),
    )

    result = run_backtest(candles, fixed(1, 1, 0, 1, 1, 1), config)

    # 3% of 10,000 / 10% stop -> 3,000 notional; the gap costs 1,500.
    assert result.trades[0].quantity == pytest.approx(30)
    assert result.trades[0].pnl == pytest.approx(-1_500)
    assert len(result.trades) == 1
    # Re-entry is attempted (and vetoed) on each of the last two bars.
    assert result.rejected_entries == 2


def test_risk_limits_require_stop_loss():
    with pytest.raises(ValueError):
        BacktestConfig(risk_limits=RiskLimits(1.0, 3.0, 25.0, 100.0, 1.0))


def test_invalid_strategy_output_rejected():
    with pytest.raises(ValueError):
        run_backtest(bars([100, 101]), fixed(2, 2))


def test_unsorted_candles_rejected():
    candles = bars([100, 101, 102])
    with pytest.raises(MarketDataError):
        run_backtest([candles[1], candles[0], candles[2]], buy_and_hold())


def test_max_drawdown_and_metrics():
    curve = [(START, v) for v in (100.0, 120.0, 60.0, 90.0)]

    metrics = compute_metrics(curve, [], bars_per_year=4, initial_equity=100.0)

    assert metrics["max_drawdown_pct"] == pytest.approx(50.0)
    assert metrics["total_return_pct"] == pytest.approx(-10.0)
    assert metrics["cagr_pct"] == pytest.approx(-10.0)
    assert metrics["sharpe"] is not None and math.isfinite(metrics["sharpe"])


def test_split_is_chronological():
    candles = bars(list(range(100, 110)))

    first, second = split_candles(candles, 70)

    assert first[-1].open_time < second[0].open_time
    assert len(first) == 7 and len(second) == 3


def test_sma_crossover_follows_trend():
    up = list(range(100, 130))
    result = run_backtest(bars(up), sma_crossover(fast=3, slow=10),
                          BacktestConfig(costs=NO_COSTS))

    assert result.trades and result.trades[0].side == 1
    assert result.metrics["final_equity"] > 10_000


def test_donchian_breakout_enters_on_new_high():
    prices = [100] * 10 + [101, 102, 103, 104]
    strategy = donchian_breakout(entry=5, exit=2)
    targets = [strategy(bars(prices)[: i + 1]) for i in range(len(prices))]

    assert targets[9] == 0
    assert targets[10] == 1


def test_parameter_validation():
    with pytest.raises(ValueError):
        sma_crossover(fast=50, slow=20)
    with pytest.raises(ValueError):
        CostModel(fee_pct=-1)
    with pytest.raises(ValueError):
        BacktestConfig(allocation_pct=0)


def test_history_view_cannot_reach_future():
    candles = bars([100, 101, 102, 103])
    checked = []

    def strategy(history):
        with pytest.raises(IndexError):
            history[len(history)]
        assert history[-1] is candles[len(history) - 1]
        assert history[-10:] == candles[: len(history)]
        checked.append(len(history))
        return 0

    run_backtest(candles, strategy)

    assert checked == [1, 2, 3, 4]
