"""Baseline strategies for the backtester.

These are reference points, not recommendations. Every strategy
receives only past candles and returns a target exposure in [-1, 1]:
1 (long), 0 (flat), -1 (short) or a fraction such as 0.6 (60% long).
"""

from collections import deque
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


class _Stream:
    """Feed each new candle to an indicator state exactly once, in order.

    The backtester calls a strategy once per candle with a history one
    candle longer than before, so normally only the newest candle is
    processed. Any other call replays the whole history from a fresh
    state, which gives identical results.
    """

    def __init__(self, make_state):
        self.make_state = make_state
        self.state = None
        self.length = None
        self.last = None

    def feed(self, history: Sequence[Candle]):
        length = len(history)
        if (
            self.state is not None
            and length == self.length + 1
            and history[-2] is self.last
        ):
            self.state.update(history[-1])
        else:
            self.state = self.make_state()
            for candle in history:
                self.state.update(candle)
        self.length, self.last = length, history[-1]
        return self.state


def _streaming(make_state) -> Strategy:
    stream = _Stream(make_state)

    def strategy(history: Sequence[Candle]) -> float:
        return stream.feed(history).target

    return strategy


class _Ema:
    def __init__(self, length: int):
        self.alpha = 2 / (length + 1)
        self.value = None
        self.count = 0

    def update(self, value: float) -> float:
        self.value = value if self.value is None else (
            self.value + self.alpha * (value - self.value)
        )
        self.count += 1
        return self.value


def _check_lengths(**lengths):
    for name, value in lengths.items():
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")


def ema_crossover(fast: int = 12, slow: int = 26) -> Strategy:
    """Trend: long while the fast EMA is above the slow EMA, else short."""

    _check_lengths(fast=fast, slow=slow)
    if fast >= slow:
        raise ValueError("Require fast < slow")

    class State:
        def __init__(self):
            self.fast, self.slow, self.target = _Ema(fast), _Ema(slow), 0

        def update(self, candle):
            difference = self.fast.update(candle.close) - self.slow.update(candle.close)
            self.target = 0 if self.slow.count < slow else (
                (difference > 0) - (difference < 0)
            )

    return _streaming(State)


def macd(fast: int = 12, slow: int = 26, signal: int = 9) -> Strategy:
    """Trend: long while MACD is above its signal line, short below."""

    _check_lengths(fast=fast, slow=slow, signal=signal)
    if fast >= slow:
        raise ValueError("Require fast < slow")

    class State:
        def __init__(self):
            self.fast, self.slow, self.signal = _Ema(fast), _Ema(slow), _Ema(signal)
            self.target = 0

        def update(self, candle):
            line = self.fast.update(candle.close) - self.slow.update(candle.close)
            if self.slow.count < slow:
                return
            difference = line - self.signal.update(line)
            self.target = 0 if self.signal.count < signal else (
                (difference > 0) - (difference < 0)
            )

    return _streaming(State)


def momentum(lookback: int = 180, threshold: float = 0.0) -> Strategy:
    """Time-series momentum: long after a rise over ``lookback`` candles
    of more than ``threshold`` percent, short after a fall, else flat."""

    _check_lengths(lookback=lookback)
    if not 0 <= threshold < 100:
        raise ValueError("Threshold must be in [0, 100) percent")

    class State:
        def __init__(self):
            self.closes, self.target = deque(maxlen=lookback + 1), 0

        def update(self, candle):
            self.closes.append(candle.close)
            if len(self.closes) <= lookback:
                return
            change = 100 * (self.closes[-1] / self.closes[0] - 1)
            self.target = 1 if change > threshold else -1 if change < -threshold else 0

    return _streaming(State)


def rsi_reversion(period: int = 14, oversold: float = 30.0,
                  overbought: float = 70.0, exit: float = 50.0) -> Strategy:
    """Mean reversion: long when RSI is oversold until it recovers to
    ``exit``; short when overbought until it falls back to ``exit``."""

    _check_lengths(period=period)
    if not 0 < oversold < exit < overbought < 100:
        raise ValueError("Require 0 < oversold < exit < overbought < 100")

    class State:
        def __init__(self):
            self.previous = None
            self.gains = self.losses = 0.0
            self.count = 0
            self.target = 0

        def update(self, candle):
            if self.previous is None:
                self.previous = candle.close
                return
            change = candle.close - self.previous
            self.previous = candle.close
            gain, loss = max(change, 0.0), max(-change, 0.0)
            self.count += 1
            if self.count <= period:
                # Seed with a simple average, then use Wilder smoothing.
                self.gains += gain / period
                self.losses += loss / period
                if self.count < period:
                    return
            else:
                self.gains = (self.gains * (period - 1) + gain) / period
                self.losses = (self.losses * (period - 1) + loss) / period

            rsi = 100.0 if self.losses == 0 else 100 - 100 / (1 + self.gains / self.losses)
            if self.target > 0 and rsi >= exit:
                self.target = 0
            elif self.target < 0 and rsi <= exit:
                self.target = 0
            if self.target == 0:
                self.target = 1 if rsi < oversold else -1 if rsi > overbought else 0

    return _streaming(State)


def bollinger_reversion(window: int = 20, width: float = 2.0) -> Strategy:
    """Mean reversion: long below the lower band until the close returns
    to the average; short above the upper band until it returns."""

    _check_lengths(window=window)
    if window < 2 or not 0 < width <= 10:
        raise ValueError("Require window >= 2 and 0 < width <= 10")

    class State:
        def __init__(self):
            self.closes = deque(maxlen=window)
            self.total = self.squares = 0.0
            self.updates = 0
            self.target = 0

        def update(self, candle):
            if len(self.closes) == window:
                old = self.closes[0]
                self.total -= old
                self.squares -= old * old
            self.closes.append(candle.close)
            self.total += candle.close
            self.squares += candle.close * candle.close
            self.updates += 1
            if self.updates % 500 == 0:
                # Refresh the running sums to stop rounding drift.
                self.total = sum(self.closes)
                self.squares = sum(c * c for c in self.closes)
            if len(self.closes) < window:
                return

            mean = self.total / window
            variance = (self.squares - window * mean * mean) / (window - 1)
            band = width * sqrt(max(variance, 0.0))
            close = candle.close
            if self.target > 0 and close >= mean:
                self.target = 0
            elif self.target < 0 and close <= mean:
                self.target = 0
            if self.target == 0:
                self.target = 1 if close < mean - band else -1 if close > mean + band else 0

    return _streaming(State)


class _Wilder:
    """Wilder smoothing: simple average of the first ``length`` values,
    then value = (previous * (length - 1) + new) / length."""

    def __init__(self, length: int):
        self.length, self.value, self.count, self.seed = length, None, 0, 0.0

    def update(self, value: float):
        self.count += 1
        if self.count < self.length:
            self.seed += value
            return None
        if self.count == self.length:
            self.value = (self.seed + value) / self.length
        else:
            self.value = (self.value * (self.length - 1) + value) / self.length
        return self.value


def _true_range(candle, previous_close):
    if previous_close is None:
        return candle.high - candle.low
    return max(candle.high - candle.low, abs(candle.high - previous_close),
               abs(candle.low - previous_close))


def adx_trend(period: int = 14, threshold: float = 25.0) -> Strategy:
    """Trend strength: follow +DI/-DI direction only while ADX is above
    ``threshold``; flat in weak, choppy markets."""

    _check_lengths(period=period)
    if not 0 < threshold < 100:
        raise ValueError("Threshold must be in (0, 100)")

    class State:
        def __init__(self):
            self.previous = None
            self.tr, self.plus, self.minus = _Wilder(period), _Wilder(period), _Wilder(period)
            self.adx = _Wilder(period)
            self.target = 0

        def update(self, candle):
            previous = self.previous
            self.previous = candle
            if previous is None:
                return
            up = candle.high - previous.high
            down = previous.low - candle.low
            plus_dm = up if up > down and up > 0 else 0.0
            minus_dm = down if down > up and down > 0 else 0.0
            tr = self.tr.update(_true_range(candle, previous.close))
            plus = self.plus.update(plus_dm)
            minus = self.minus.update(minus_dm)
            if tr is None or tr <= 0:
                return
            plus_di, minus_di = 100 * plus / tr, 100 * minus / tr
            total = plus_di + minus_di
            dx = 0.0 if total == 0 else 100 * abs(plus_di - minus_di) / total
            adx = self.adx.update(dx)
            if adx is None:
                return
            if adx < threshold:
                self.target = 0
            else:
                self.target = (plus_di > minus_di) - (plus_di < minus_di)

    return _streaming(State)


def keltner_breakout(window: int = 20, multiplier: float = 2.0) -> Strategy:
    """Volatility breakout: long above EMA + multiplier x ATR, short below
    EMA - multiplier x ATR, exit when the close crosses back over the EMA."""

    _check_lengths(window=window)
    if not 0 < multiplier <= 10:
        raise ValueError("Multiplier must be in (0, 10]")

    class State:
        def __init__(self):
            self.ema, self.atr = _Ema(window), _Wilder(window)
            self.previous_close = None
            self.target = 0

        def update(self, candle):
            middle = self.ema.update(candle.close)
            atr = self.atr.update(_true_range(candle, self.previous_close))
            self.previous_close = candle.close
            if atr is None or self.ema.count < window:
                return
            close = candle.close
            if self.target > 0 and close < middle or self.target < 0 and close > middle:
                self.target = 0
            if self.target == 0:
                if close > middle + multiplier * atr:
                    self.target = 1
                elif close < middle - multiplier * atr:
                    self.target = -1

    return _streaming(State)


def stochastic_reversion(period: int = 14, smooth: int = 3,
                         oversold: float = 20.0, overbought: float = 80.0) -> Strategy:
    """Mean reversion on %D (smoothed stochastic): long when oversold until
    it reaches 50, short when overbought until it falls to 50."""

    _check_lengths(period=period, smooth=smooth)
    if not 0 < oversold < 50 < overbought < 100:
        raise ValueError("Require 0 < oversold < 50 < overbought < 100")

    class State:
        def __init__(self):
            self.candles = deque(maxlen=period)
            self.k_values = deque(maxlen=smooth)
            self.target = 0

        def update(self, candle):
            self.candles.append(candle)
            if len(self.candles) < period:
                return
            high = max(c.high for c in self.candles)
            low = min(c.low for c in self.candles)
            k = 50.0 if high == low else 100 * (candle.close - low) / (high - low)
            self.k_values.append(k)
            if len(self.k_values) < smooth:
                return
            d = sum(self.k_values) / smooth
            if self.target > 0 and d >= 50 or self.target < 0 and d <= 50:
                self.target = 0
            if self.target == 0:
                self.target = 1 if d < oversold else -1 if d > overbought else 0

    return _streaming(State)


STRATEGIES = {
    "buy_and_hold": buy_and_hold,
    "sma_crossover": sma_crossover,
    "donchian_breakout": donchian_breakout,
    "volatility_target": volatility_target,
    "ema_crossover": ema_crossover,
    "macd": macd,
    "momentum": momentum,
    "rsi_reversion": rsi_reversion,
    "bollinger_reversion": bollinger_reversion,
    "adx_trend": adx_trend,
    "keltner_breakout": keltner_breakout,
    "stochastic_reversion": stochastic_reversion,
}

# Default robustness ranges ("start:stop:step") for each strategy's
# swept parameters. Other parameters stay at their given values.
SWEEP_RANGES = {
    "sma_crossover": {"fast": "10:50:10", "slow": "50:200:25"},
    "donchian_breakout": {"entry": "20:100:20", "exit": "10:50:10"},
    "volatility_target": {"target_vol": "20:80:10", "lookback": "60:360:60"},
    "ema_crossover": {"fast": "6:30:6", "slow": "26:156:26"},
    "macd": {"fast": "6:18:6", "slow": "20:40:10"},
    "momentum": {"lookback": "30:360:30", "threshold": "0:10:5"},
    "rsi_reversion": {"period": "7:28:7", "oversold": "20:35:5"},
    "bollinger_reversion": {"window": "10:50:10", "width": "1.5:3:0.5"},
    "adx_trend": {"period": "7:28:7", "threshold": "15:35:5"},
    "keltner_breakout": {"window": "10:50:10", "multiplier": "1:3:0.5"},
    "stochastic_reversion": {"period": "7:28:7", "oversold": "10:30:5"},
}
