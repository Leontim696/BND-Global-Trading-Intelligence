"""Offline tests for EMA, MACD, momentum, RSI and Bollinger strategies.

Each indicator is checked against a plain reference implementation, and
the streaming (one candle per call) path against full recomputation.
"""

import contextlib
import io
import json
import random
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev

import pytest

from src.bnd.backtest_cli import main as cli
from src.bnd.backtester import BacktestConfig, CostModel, run_backtest
from src.bnd.market_data import Candle, save_csv
from src.bnd.robustness import parse_range, parse_value
from src.bnd.strategies import (
    STRATEGIES,
    SWEEP_RANGES,
    bollinger_reversion,
    ema_crossover,
    macd,
    momentum,
    rsi_reversion,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
STEP = timedelta(hours=4)


def random_walk(count=600, seed=3, sigma=0.02):
    rng = random.Random(seed)
    candles, price = [], 100.0
    for i in range(count):
        close = price * (1 + rng.gauss(0, sigma))
        candles.append(Candle(START + STEP * i, price, max(price, close),
                              min(price, close), close, 1))
        price = close
    return candles


def closes_to_candles(closes):
    candles, previous = [], closes[0]
    for i, close in enumerate(closes):
        candles.append(Candle(START + STEP * i, previous, max(previous, close),
                              min(previous, close), close, 1))
        previous = close
    return candles


# Reference implementations -------------------------------------------------

def ref_ema(values, length):
    alpha, out, value = 2 / (length + 1), [], None
    for v in values:
        value = v if value is None else value + alpha * (v - value)
        out.append(value)
    return out


def ref_rsi(closes, period):
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    avg_gain, avg_loss = mean(gains[:period]), mean(losses[:period])
    values = [None] * period
    values.append(100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        values.append(100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    return values  # aligned with closes


def sequential(strategy, candles):
    return [strategy(candles[: n + 1]) for n in range(len(candles))]


def fresh(make, candles):
    return [make()(candles[: n + 1]) for n in range(len(candles))]


# Indicator correctness -----------------------------------------------------

def test_ema_crossover_matches_reference():
    candles = random_walk()
    closes = [c.close for c in candles]
    fast, slow = ref_ema(closes, 5), ref_ema(closes, 20)

    targets = sequential(ema_crossover(5, 20), candles)

    for i, target in enumerate(targets):
        if i + 1 < 20:
            assert target == 0
        else:
            diff = fast[i] - slow[i]
            assert target == (diff > 0) - (diff < 0)


def test_macd_matches_reference():
    candles = random_walk()
    closes = [c.close for c in candles]
    line = [f - s for f, s in zip(ref_ema(closes, 12), ref_ema(closes, 26))]
    # Signal EMA starts once the slow EMA has warmed up.
    signal = [None] * 25 + ref_ema(line[25:], 9)

    targets = sequential(macd(12, 26, 9), candles)

    for i, target in enumerate(targets):
        if i < 25 + 8:
            assert target == 0
        else:
            diff = line[i] - signal[i]
            assert target == (diff > 0) - (diff < 0)


def test_momentum_sign_of_lookback_return():
    candles = random_walk()
    targets = sequential(momentum(lookback=10, threshold=2.0), candles)

    for i, target in enumerate(targets):
        if i < 10:
            assert target == 0
            continue
        change = 100 * (candles[i].close / candles[i - 10].close - 1)
        assert target == (1 if change > 2 else -1 if change < -2 else 0)


def test_rsi_reversion_follows_reference_rsi():
    candles = random_walk(sigma=0.03)
    rsi = ref_rsi([c.close for c in candles], 14)

    targets = sequential(rsi_reversion(14, 30, 70, 50), candles)

    position = 0
    for i, target in enumerate(targets):
        value = rsi[i]
        if value is not None:
            if position > 0 and value >= 50 or position < 0 and value <= 50:
                position = 0
            if position == 0:
                position = 1 if value < 30 else -1 if value > 70 else 0
        assert target == position
    assert 1 in targets and -1 in targets


def test_bollinger_reversion_follows_reference_bands():
    candles = random_walk(sigma=0.03)
    targets = sequential(bollinger_reversion(20, 2.0), candles)

    position = 0
    for i, target in enumerate(targets):
        if i + 1 >= 20:
            window = [c.close for c in candles[i - 19: i + 1]]
            mid, band = mean(window), 2 * stdev(window)
            close = candles[i].close
            if position > 0 and close >= mid or position < 0 and close <= mid:
                position = 0
            if position == 0:
                position = 1 if close < mid - band else -1 if close > mid + band else 0
        assert target == position
    assert 1 in targets and -1 in targets


@pytest.mark.parametrize("make", [
    lambda: ema_crossover(5, 20),
    lambda: macd(12, 26, 9),
    lambda: momentum(30, 1.0),
    lambda: rsi_reversion(14),
    lambda: bollinger_reversion(20, 2.0),
])
def test_streaming_matches_full_recompute(make):
    candles = random_walk(count=700)

    assert sequential(make(), candles) == fresh(make, candles)


# Behaviour ----------------------------------------------------------------

def test_trend_strategies_go_long_in_uptrend_and_short_in_downtrend():
    up = closes_to_candles([100 * 1.01 ** i for i in range(120)])
    down = closes_to_candles([100 * 0.99 ** i for i in range(120)])

    for make in (lambda: ema_crossover(5, 20), lambda: momentum(20)):
        assert make()(up) == 1
        assert make()(down) == -1


def test_macd_turns_short_when_a_rally_rolls_over():
    # MACD measures trend acceleration: rally, then a turn down.
    closes = [100 * 1.01 ** i for i in range(80)]
    closes += [closes[-1] * 0.98 ** i for i in range(1, 15)]

    assert macd(5, 20, 5)(closes_to_candles(closes[:80])) == 1
    assert macd(5, 20, 5)(closes_to_candles(closes)) == -1


def test_mean_reversion_buys_a_sharp_drop():
    closes = [100.0 + (i % 2) * 0.5 for i in range(60)] + [80.0]
    candles = closes_to_candles(closes)

    assert bollinger_reversion(20, 2.0)(candles) == 1
    assert rsi_reversion(14)(candles) == 1


def test_shorts_are_dropped_unless_allowed():
    down = closes_to_candles([100 * 0.99 ** i for i in range(200)])
    config = BacktestConfig(costs=CostModel(0, 0))

    long_only = run_backtest(down, ema_crossover(5, 20), config)
    both = run_backtest(down, ema_crossover(5, 20),
                        BacktestConfig(costs=CostModel(0, 0), allow_short=True))

    assert long_only.trades == []
    assert both.trades and both.trades[0].side == -1
    assert both.metrics["final_equity"] > 10_000


@pytest.mark.parametrize("make", [
    lambda: ema_crossover(20, 5),
    lambda: macd(26, 12),
    lambda: momentum(0),
    lambda: momentum(10, -1),
    lambda: rsi_reversion(14, 60, 70, 50),
    lambda: bollinger_reversion(1),
    lambda: bollinger_reversion(20, 0),
])
def test_parameter_validation(make):
    with pytest.raises(ValueError):
        make()


def test_every_parameterised_strategy_has_valid_default_ranges():
    for name, ranges in SWEEP_RANGES.items():
        assert name in STRATEGIES
        for text in ranges.values():
            assert parse_range(text)


# Parsing and CLI ------------------------------------------------------------

def test_parse_range_and_value():
    assert parse_range("1.5:3:0.5") == [1.5, 2.0, 2.5, 3.0]
    assert parse_range("10:30:10") == [10, 20, 30]
    assert parse_range("2.5") == [2.5]
    assert parse_value("21") == 21 and parse_value("2.5") == 2.5
    assert parse_value("true") is True
    for bad in ("x", "nan", "inf"):
        with pytest.raises(ValueError):
            parse_value(bad)


def run_cli(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli(args)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def data(tmp_path):
    path = tmp_path / "walk.csv"
    save_csv(random_walk(count=500), path)
    return str(path)


def test_cli_param_sets_strategy_parameters(data):
    code, out, _ = run_cli(["run", "--data", data, "--strategy", "rsi_reversion",
                            "--param", "period=10", "--param", "oversold=25",
                            "--no-risk-gate", "--allow-short"])

    assert code == 0
    assert json.loads(out)["periods"]["full"]["strategy"]["trades"] > 0


def test_cli_unknown_parameter_is_clear_error(data):
    code, _, err = run_cli(["run", "--data", data, "--strategy", "macd",
                            "--param", "colour=3", "--no-risk-gate"])

    assert code == 2
    assert "Invalid parameters for macd" in err


def test_cli_robustness_with_float_range(data):
    code, out, _ = run_cli(["robustness", "--data", data,
                            "--strategy", "bollinger_reversion", "--no-risk-gate",
                            "--range", "window=10:20:10", "--range", "width=1.5:2:0.5",
                            "--permutations", "9"])

    assert code == 0
    report = json.loads(out)
    assert report["grid_summary"]["in_sample"]["combinations"] == 4
    assert set(report["in_sample_selection"]["params"]) == {"window", "width"}


def test_cli_compare_ranks_every_strategy(data):
    code, out, _ = run_cli(["compare", "--data", data, "--no-risk-gate",
                            "--allow-short", "--permutations", "9"])

    assert code == 0
    report = json.loads(out)
    names = [row["strategy"] for row in report["ranking"]]
    assert sorted(names) == sorted(SWEEP_RANGES)
    sharpes = [row["out_of_sample"]["sharpe"] for row in report["ranking"]
               if row["out_of_sample"]["sharpe"] is not None]
    assert sharpes == sorted(sharpes, reverse=True)
    assert "out_of_sample" in report["buy_and_hold"]


def test_holm_adjustment():
    from src.bnd.robustness import holm_adjust

    # Classic example: sorted p-values times (m - rank), made monotone.
    assert holm_adjust([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert holm_adjust([0.5, 0.9]) == pytest.approx([1.0, 1.0])


def test_cli_compare_reports_adjusted_p_values(data):
    code, out, _ = run_cli(["compare", "--data", data, "--no-risk-gate",
                            "--permutations", "9"])

    rows = json.loads(out)["ranking"]
    assert all(row["p_value_adjusted"] >= row["p_value"] for row in rows)


# ADX, Keltner (ATR) and Stochastic ----------------------------------------

from src.bnd.strategies import adx_trend, keltner_breakout, stochastic_reversion  # noqa: E402


def ref_wilder(values, length):
    out, value = [], None
    for i, v in enumerate(values):
        if i + 1 < length:
            out.append(None)
            continue
        value = mean(values[:length]) if i + 1 == length else (value * (length - 1) + v) / length
        out.append(value)
    return out


def ref_true_ranges(candles):
    ranges = [candles[0].high - candles[0].low]
    for prev, c in zip(candles, candles[1:]):
        ranges.append(max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close)))
    return ranges


def ref_adx_targets(candles, period, threshold):
    plus_dm, minus_dm, trs = [], [], []
    for prev, c in zip(candles, candles[1:]):
        up, down = c.high - prev.high, prev.low - c.low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close)))
    tr_s, plus_s, minus_s = (ref_wilder(x, period) for x in (trs, plus_dm, minus_dm))
    dxs, di = [], []
    for tr, p, m in zip(tr_s, plus_s, minus_s):
        if tr is None:
            continue
        pdi, mdi = 100 * p / tr, 100 * m / tr
        di.append((pdi, mdi))
        dxs.append(0.0 if pdi + mdi == 0 else 100 * abs(pdi - mdi) / (pdi + mdi))
    adx = ref_wilder(dxs, period)
    targets = [0] * (len(candles) - len(dxs))
    target = 0
    for value, (pdi, mdi) in zip(adx, di):
        if value is not None:
            target = 0 if value < threshold else (pdi > mdi) - (pdi < mdi)
        targets.append(target)
    return targets


def test_adx_matches_reference():
    candles = random_walk(count=500, sigma=0.02)

    assert sequential(adx_trend(14, 20), candles) == ref_adx_targets(candles, 14, 20)


def test_adx_follows_strong_trend_and_ignores_chop():
    up = closes_to_candles([100 * 1.01 ** i for i in range(120)])
    # Symmetric oscillation: equal up and down moves, no trend.
    chop = closes_to_candles([(100, 102, 100, 98)[i % 4] for i in range(120)])

    assert adx_trend(14, 25)(up) == 1
    assert adx_trend(14, 25)(chop) == 0


def test_keltner_breaks_out_on_a_surge():
    closes = [100 + 0.5 * (-1) ** i for i in range(60)] + [104.0, 108.0]
    candles = closes_to_candles(closes)

    assert keltner_breakout(20, 2.0)(candles[:60]) == 0
    assert keltner_breakout(20, 2.0)(candles) == 1


def test_keltner_atr_matches_reference_wilder():
    candles = random_walk(count=300)
    ranges = ref_true_ranges(candles)
    expected = ref_wilder(ranges, 20)

    # Rebuild the strategy state step by step and compare its ATR.
    from src.bnd.strategies import _Wilder, _true_range
    atr, previous = _Wilder(20), None
    for candle, want in zip(candles, expected):
        got = atr.update(_true_range(candle, previous))
        previous = candle.close
        assert (got is None and want is None) or got == pytest.approx(want)


def ref_stochastic_targets(candles, period, smooth, low_level, high_level):
    ks, targets, target = [], [], 0
    for i, candle in enumerate(candles):
        if i + 1 >= period:
            window = candles[i + 1 - period: i + 1]
            high, low = max(c.high for c in window), min(c.low for c in window)
            ks.append(50.0 if high == low else 100 * (candle.close - low) / (high - low))
            if len(ks) >= smooth:
                d = mean(ks[-smooth:])
                if target > 0 and d >= 50 or target < 0 and d <= 50:
                    target = 0
                if target == 0:
                    target = 1 if d < low_level else -1 if d > high_level else 0
        targets.append(target)
    return targets


def test_stochastic_matches_reference():
    candles = random_walk(count=500, sigma=0.03)

    got = sequential(stochastic_reversion(14, 3, 20, 80), candles)

    assert got == ref_stochastic_targets(candles, 14, 3, 20, 80)
    assert 1 in got and -1 in got


@pytest.mark.parametrize("make", [
    lambda: adx_trend(14, 25),
    lambda: keltner_breakout(20, 2.0),
    lambda: stochastic_reversion(14, 3),
])
def test_new_indicators_stream_like_full_recompute(make):
    candles = random_walk(count=600)

    assert sequential(make(), candles) == fresh(make, candles)


@pytest.mark.parametrize("make", [
    lambda: adx_trend(0), lambda: adx_trend(14, 0),
    lambda: keltner_breakout(20, 0), lambda: stochastic_reversion(14, 3, 60, 80),
])
def test_new_indicator_validation(make):
    with pytest.raises(ValueError):
        make()


# Regime switching -------------------------------------------------------

from src.bnd.strategies import regime_switch  # noqa: E402


def regime_state(strategy, candles):
    strategy(candles)
    # The streaming closure keeps the state; reach it for inspection.
    stream = strategy.__closure__[0].cell_contents
    return stream.state


def test_regime_switch_uses_momentum_in_a_trend():
    up = closes_to_candles([100 * 1.01 ** i for i in range(150)])
    strategy = regime_switch(window=30, trend_lookback=20)

    target = strategy(up)

    assert regime_state(regime_switch(window=30, trend_lookback=20), up).regime == "trend"
    assert target == momentum(20)(up) == 1


def test_regime_switch_uses_mean_reversion_in_a_range():
    closes = [(100, 102, 100, 98)[i % 4] for i in range(120)] + [92.0]
    candles = closes_to_candles(closes)

    state = regime_state(regime_switch(window=30), candles)

    assert state.regime == "range"
    assert state.target == bollinger_reversion(20, 2.0)(candles) == 1


def test_regime_switch_hysteresis_limits_flip_flopping():
    # Alternating short trends and ranges every 12 candles.
    closes, price = [], 100.0
    for i in range(600):
        price *= 1.02 if (i // 12) % 2 == 0 else (1.01 if i % 2 else 0.99)
        closes.append(price)
    candles = closes_to_candles(closes)

    loose = regime_state(regime_switch(window=10, min_bars=1), candles)
    strict = regime_state(regime_switch(window=10, min_bars=40), candles)

    assert strict.switches < loose.switches
    assert strict.switches <= len(candles) // 40


def test_regime_switch_streams_like_full_recompute():
    candles = random_walk(count=400)

    def make():
        return regime_switch(window=20, trend_lookback=30)

    assert sequential(make(), candles) == fresh(make, candles)


def test_regime_switch_validation():
    with pytest.raises(ValueError):
        regime_switch(trend_level=0.1, range_level=0.2)


def test_combo_averages_member_signals():
    from src.bnd.strategies import combo

    candles = random_walk(count=300)
    mixed = combo("sma_crossover, rsi_reversion")
    trend, reversion = STRATEGIES["sma_crossover"](), STRATEGIES["rsi_reversion"]()

    for end in range(1, len(candles) + 1):
        history = candles[:end]
        assert mixed(history) == (trend(history) + reversion(history)) / 2


@pytest.mark.parametrize("members", ["sma_crossover", "macd,macd", "macd,nope",
                                     "macd,combo", "macd,buy_and_hold"])
def test_combo_rejects_bad_members(members):
    from src.bnd.strategies import combo

    with pytest.raises(ValueError):
        combo(members)
