"""Baseline strategies for the backtester.

These are reference points, not recommendations. Every strategy
receives only past candles and returns 1 (long), 0 (flat) or -1 (short).
"""

from typing import Sequence

from .backtester import Strategy
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


STRATEGIES = {
    "buy_and_hold": buy_and_hold,
    "sma_crossover": sma_crossover,
    "donchian_breakout": donchian_breakout,
}
