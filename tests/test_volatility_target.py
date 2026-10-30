"""Offline tests for the volatility-targeting strategy."""

import contextlib
import io
import json
from datetime import datetime, timedelta, timezone
from math import log, sqrt
from statistics import stdev

import pytest

from src.bnd.backtest_cli import main as cli
from src.bnd.backtester import SECONDS_PER_YEAR, BacktestConfig, CostModel, run_backtest
from src.bnd.market_data import Candle, save_csv
from src.bnd.strategies import volatility_target

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
STEP = timedelta(hours=4)


def zigzag(count, move, drift=0.0):
    """Closes alternate up/down by `move`, with an optional drift."""
    candles, price = [], 100.0
    for i in range(count):
        close = price * (1 + drift) * (1 + move if i % 2 == 0 else 1 - move)
        candles.append(Candle(START + STEP * i, price, max(price, close),
                              min(price, close), close, 1))
        price = close
    return candles


def expected_exposure(candles, target, lookback, step=0.1):
    window = candles[-lookback - 1:]
    returns = [log(b.close / a.close) for a, b in zip(window, window[1:])]
    seconds = (window[-1].open_time - window[0].open_time).total_seconds()
    vol = stdev(returns) * sqrt(SECONDS_PER_YEAR * lookback / seconds)
    return min(1.0, round(min(1.0, target / 100 / vol) / step) * step)


def test_exposure_is_target_over_realised_volatility():
    candles = zigzag(200, 0.01)
    strategy = volatility_target(target_vol=40, lookback=50)

    exposure = strategy(candles)

    assert exposure == pytest.approx(expected_exposure(candles, 40, 50))
    assert 0 < exposure < 1


def test_higher_volatility_means_lower_exposure():
    strategy = volatility_target(target_vol=40, lookback=50)

    calm = strategy(zigzag(200, 0.005))
    wild = strategy(zigzag(200, 0.02))

    assert wild < calm


def test_exposure_is_capped_and_rounded():
    strategy = volatility_target(target_vol=200, lookback=50, step=0.25)

    exposure = strategy(zigzag(200, 0.001))

    assert exposure == 1.0
    stepped = volatility_target(target_vol=40, lookback=50, step=0.25)(zigzag(200, 0.01))
    assert (stepped / 0.25) == pytest.approx(round(stepped / 0.25))


def test_flat_during_warm_up_and_below_trend():
    strategy = volatility_target(lookback=50, trend=100)
    falling = zigzag(200, 0.01, drift=-0.01)

    assert strategy(falling[:100]) == 0
    assert strategy(falling) == 0
    assert volatility_target(lookback=50, trend=100)(zigzag(200, 0.01, drift=0.01)) > 0


@pytest.mark.parametrize(
    "kwargs",
    [dict(target_vol=0), dict(lookback=1), dict(trend=-1),
     dict(max_exposure=1.5), dict(step=0)],
)
def test_parameter_validation(kwargs):
    with pytest.raises(ValueError):
        volatility_target(**kwargs)


def test_backtest_holds_partial_position():
    candles = zigzag(300, 0.01, drift=0.002)

    result = run_backtest(candles, volatility_target(target_vol=40, lookback=50),
                          BacktestConfig(costs=CostModel(0.1, 0.05)))

    exposure = result.metrics["avg_capital_exposure_pct"]
    assert 0 < exposure < 100
    assert result.trades


def run_cli(args):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli(args)
    return code, buffer.getvalue()


def test_cli_run_and_robustness_with_volatility_target(tmp_path):
    path = tmp_path / "zigzag.csv"
    save_csv(zigzag(400, 0.01, drift=0.001), path)

    code, out = run_cli(["run", "--data", str(path), "--strategy", "volatility_target",
                         "--vol-lookback", "50", "--no-risk-gate"])
    assert code == 0
    full = json.loads(out)["periods"]["full"]["strategy"]
    assert 0 < full["avg_capital_exposure_pct"] < 100

    code, out = run_cli(["robustness", "--data", str(path), "--strategy",
                         "volatility_target", "--no-risk-gate",
                         "--target-vol-range", "20:40:20",
                         "--vol-lookback-range", "30:60:30", "--permutations", "9"])
    assert code == 0
    report = json.loads(out)
    assert report["grid_summary"]["in_sample"]["combinations"] == 4
    assert set(report["in_sample_selection"]["params"]) == {"target_vol", "lookback"}


def test_incremental_volatility_matches_full_recompute():
    import random

    rng = random.Random(4)
    candles, price = [], 100.0
    for i in range(1500):
        close = price * (1 + rng.gauss(0, 0.02))
        candles.append(Candle(START + STEP * i, price, max(price, close),
                              min(price, close), close, 1))
        price = close

    rolling = volatility_target(target_vol=40, lookback=60, step=0.01)
    outputs = [rolling(candles[: n + 1]) for n in range(len(candles))]
    fresh = [volatility_target(target_vol=40, lookback=60, step=0.01)(candles[: n + 1])
             for n in range(len(candles))]

    assert outputs == pytest.approx(fresh, abs=1e-9)
