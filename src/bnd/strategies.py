"""Baseline strategies for the backtester.

These are reference points, not recommendations. Every strategy
receives only past candles and returns a target exposure in [-1, 1]:
1 (long), 0 (flat), -1 (short) or a fraction such as 0.6 (60% long).
"""

from math import log, sqrt
from typing import Sequence

from .backtester import SECONDS_PER_YEAR, Strategy
from .market_data import Candle


def buy_and_hold() -> Strategy:
    def strategy(history: Sequence[Candle]) -> int:
        return 1

    return strategy


def _sma(history: Sequence[Candle], length: int) -> float:
    window = history[-length:]
    return sum(candle.close for candle in window) / length


def sma_crossover(fast: int = 20, slow: int = 50) -> Strategy:
    """Long (or short) while the fast average is above (below) the slow."""

    if not 1 <= fast < slow:
        raise ValueError("Require 1 <= fast < slow")

    def strategy(history: Sequence[Candle]) -> int:
        if len(history) < slow:
            return 0
        difference = _sma(history, fast) - _sma(history, slow)
        if difference > 0:
            return 1
        if difference < 0:
            return -1
        return 0

    return strategy


def donchian_breakout(entry: int = 55, exit: int = 20) -> Strategy:
    """Trend following: enter on an N-bar breakout, exit on an M-bar reversal."""

    if not 1 <= exit < entry:
        raise ValueError("Require 1 <= exit < entry")

    state = {"position": 0}

    def strategy(history: Sequence[Candle]) -> int:
        if len(history) <= entry:
            return 0

        close = history[-1].close
        # Channels use the bars before the current one.
        entry_bars = history[-entry - 1:-1]
        exit_bars = history[-exit - 1:-1]
        entry_high = max(c.high for c in entry_bars)
        entry_low = min(c.low for c in entry_bars)
        exit_high = max(c.high for c in exit_bars)
        exit_low = min(c.low for c in exit_bars)
        position = state["position"]

        if position > 0 and close < exit_low:
            position = 0
        elif position < 0 and close > exit_high:
            position = 0

        if position == 0:
            if close > entry_high:
                position = 1
            elif close < entry_low:
                position = -1

        state["position"] = position
        return position

    return strategy


def volatility_target(
    target_vol: float = 40.0,
    lookback: int = 180,
    trend: int = 0,
    max_exposure: float = 1.0,
    step: float = 0.1,
    long_short: bool = False,
) -> Strategy:
    """Exposure = target / realised volatility, capped, no leverage.

    target_vol: annualised volatility target in percent.
    lookback: candles used to measure realised volatility.
    trend: optional SMA length (0 = off). Long-only: flat while the close
        is below it. long_short: long above it, short below it.
    step: exposure is rounded to this grid to limit rebalancing.
    """

    if not 0 < target_vol <= 500:
        raise ValueError("Target volatility must be in (0, 500] percent")
    if type(lookback) is not int or lookback < 2:
        raise ValueError("Lookback must be an integer >= 2")
    if type(trend) is not int or trend < 0:
        raise ValueError("Trend length must be a nonnegative integer")
    if not 0 < max_exposure <= 1:
        raise ValueError("Maximum exposure must be in (0, 1]")
    if not 0 < step <= max_exposure:
        raise ValueError("Step must be in (0, max_exposure]")
    if long_short and not trend:
        raise ValueError("Long/short needs a trend length to pick a direction")

    # Rolling sums of log returns over the window. The backtester calls
    # the strategy once per candle in order, so each call normally adds
    # one return and drops one; anything else triggers a full recompute.
    state = {"length": None, "last": None, "sum": 0.0, "sumsq": 0.0,
             "closes": 0.0, "steps": 0}

    def rolling_stdev(history: Sequence[Candle]) -> float:
        length = len(history)
        incremental = (
            state["length"] == length - 1
            and history[-2] is state["last"]
            and state["steps"] < 500
        )
        if incremental:
            new = log(history[-1].close / history[-2].close)
            old = log(history[-lookback - 1].close / history[-lookback - 2].close)
            state["sum"] += new - old
            state["sumsq"] += new * new - old * old
            if trend:
                state["closes"] += history[-1].close - history[-trend - 1].close
            state["steps"] += 1
        else:
            window = history[-lookback - 1:]
            returns = [log(b.close / a.close) for a, b in zip(window, window[1:])]
            state["sum"], state["sumsq"] = sum(returns), sum(r * r for r in returns)
            if trend:
                state["closes"] = sum(c.close for c in history[-trend:])
            state["steps"] = 0
        state["length"], state["last"] = length, history[-1]
        variance = (state["sumsq"] - state["sum"] ** 2 / lookback) / (lookback - 1)
        return sqrt(max(variance, 0.0))

    def strategy(history: Sequence[Candle]) -> float:
        if len(history) <= max(lookback, trend) + 1:
            return 0

        # Always update the rolling windows, even when the trend filter
        # keeps the strategy flat, so they stay incremental.
        deviation = rolling_stdev(history)

        direction = 1
        if trend and history[-1].close < state["closes"] / trend:
            if not long_short:
                return 0
            direction = -1

        # Average spacing, so occasional missing candles do not distort it.
        seconds = (
            history[-1].open_time - history[-lookback - 1].open_time
        ).total_seconds()
        volatility = deviation * sqrt(SECONDS_PER_YEAR * lookback / seconds)

        exposure = (
            max_exposure if volatility <= 0
            else min(max_exposure, target_vol / 100 / volatility)
        )
        return direction * min(max_exposure, round(exposure / step) * step)

    return strategy


STRATEGIES = {
    "buy_and_hold": buy_and_hold,
    "sma_crossover": sma_crossover,
    "donchian_breakout": donchian_breakout,
    "volatility_target": volatility_target,
}
