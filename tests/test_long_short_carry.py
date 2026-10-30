"""Offline tests for long/short volatility targeting, funding and interest."""

import contextlib
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.backtest_cli import main as cli
from src.bnd.backtester import BacktestConfig, CostModel, run_backtest
from src.bnd.market_data import Candle, save_csv
from src.bnd.strategies import volatility_target

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)
YEAR_DAYS = 365.25


def flat_days(count, price=100.0):
    return [Candle(START + DAY * i, price, price, price, price, 1) for i in range(count)]


def test_funding_is_charged_on_open_position():
    candles = flat_days(366)
    costs = CostModel(fee_pct=0, slippage_pct=0, funding_pct_annual=10)

    result = run_backtest(candles, lambda h: 1, BacktestConfig(costs=costs))

    # Long from day 1: ~365 days of 10%/yr on a ~10,000 notional.
    expected = 10_000 * 0.10 * 365 / YEAR_DAYS
    assert result.metrics["total_funding"] == pytest.approx(expected, rel=0.01)
    assert result.metrics["final_equity"] == pytest.approx(10_000 - expected, rel=0.001)


def test_idle_cash_earns_interest():
    candles = flat_days(366)
    costs = CostModel(fee_pct=0, slippage_pct=0, cash_rate_pct_annual=4)

    flat = run_backtest(candles, lambda h: 0, BacktestConfig(costs=costs))
    half = run_backtest(candles, lambda h: 0.5, BacktestConfig(costs=costs))

    year = 366 / YEAR_DAYS
    assert flat.metrics["total_interest"] == pytest.approx(10_000 * 0.04 * year, rel=0.03)
    # Half invested: about half the interest.
    assert half.metrics["total_interest"] == pytest.approx(
        flat.metrics["total_interest"] / 2, rel=0.03
    )


def test_defaults_add_no_carry():
    result = run_backtest(flat_days(30), lambda h: 1, BacktestConfig())

    assert result.metrics["total_funding"] == 0
    assert result.metrics["total_interest"] == 0


@pytest.mark.parametrize("field", ["funding_pct_annual", "cash_rate_pct_annual"])
def test_rate_validation(field):
    with pytest.raises(ValueError):
        CostModel(**{field: -1})


def trend_then_crash():
    """Rises for 300 days, then falls for 300 days, with daily noise."""
    candles, price = [], 100.0
    for i in range(600):
        drift = 1.01 if i < 300 else 0.99
        close = price * drift * (1.02 if i % 2 else 0.98)
        candles.append(Candle(START + DAY * i, price, max(price, close),
                              min(price, close), close, 1))
        price = close
    return candles


def test_long_short_goes_short_below_trend():
    candles = trend_then_crash()
    strategy = volatility_target(target_vol=40, lookback=30, trend=60, long_short=True)

    late = strategy(candles)

    assert late < 0
    assert volatility_target(target_vol=40, lookback=30, trend=60)(candles) == 0


def test_long_short_profits_from_the_fall():
    candles = trend_then_crash()
    costs = CostModel(fee_pct=0.1, slippage_pct=0.05)
    config = BacktestConfig(costs=costs, allow_short=True)

    long_only = run_backtest(candles, volatility_target(lookback=30, trend=60), config)
    both = run_backtest(
        candles, volatility_target(lookback=30, trend=60, long_short=True), config
    )

    assert any(t.side == -1 for t in both.trades)
    assert both.metrics["final_equity"] > long_only.metrics["final_equity"]


def test_long_short_requires_trend():
    with pytest.raises(ValueError):
        volatility_target(long_short=True)


def run_cli(args):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli(args)
    return code, buffer.getvalue()


def test_cli_long_short_defaults(tmp_path):
    path = tmp_path / "crash.csv"
    save_csv(trend_then_crash(), path)

    code, out = run_cli(["run", "--data", str(path), "--strategy", "volatility_target",
                         "--vol-lookback", "30", "--trend", "60", "--long-short",
                         "--no-risk-gate", "--cash-rate", "4"])

    assert code == 0
    report = json.loads(out)
    assert report["costs"]["allow_short"] is True
    assert report["costs"]["funding_pct_annual"] == 10.0
    assert report["costs"]["cash_rate_pct_annual"] == 4.0
    full = report["periods"]["full"]
    assert full["strategy"]["total_funding"] > 0
    # Buy-and-hold is spot: no funding.
    assert full["buy_and_hold"]["total_funding"] == 0


def test_cli_long_only_spot_has_no_funding(tmp_path):
    path = tmp_path / "crash.csv"
    save_csv(trend_then_crash(), path)

    code, out = run_cli(["run", "--data", str(path), "--no-risk-gate",
                         "--fast", "5", "--slow", "20"])

    assert code == 0
    assert json.loads(out)["costs"]["funding_pct_annual"] == 0.0


def test_cost_stress_scales_funding(tmp_path):
    from src.bnd.robustness import cost_stress

    candles = flat_days(120)
    config = BacktestConfig(costs=CostModel(0.1, 0.05, funding_pct_annual=10))

    rows = cost_stress(candles, lambda: (lambda h: 1), config)

    assert rows[0]["total_return_pct"] > rows[1]["total_return_pct"] > rows[2]["total_return_pct"]


def test_incremental_trend_matches_full_recompute():
    candles = trend_then_crash()

    rolling = volatility_target(lookback=30, trend=60, long_short=True, step=0.01)
    outputs = [rolling(candles[: n + 1]) for n in range(len(candles))]
    fresh = [volatility_target(lookback=30, trend=60, long_short=True, step=0.01)(candles[: n + 1])
             for n in range(len(candles))]

    assert outputs == pytest.approx(fresh, abs=1e-9)
