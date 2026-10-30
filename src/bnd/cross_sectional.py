"""Cross-sectional momentum: rank markets against each other.

Each day every market is scored by its return over ``lookback`` candles,
skipping the most recent ``skip`` (the last month tends to reverse). The
top ``fraction`` of markets is held long, the bottom ``fraction`` short,
the rest flat; the portfolio's volatility sizing then sets the sizes.

No look-ahead across markets: markets close at different hours (crypto at
midnight UTC, US ETFs at 21:00), so the ranking used on date D is built
only from candles of earlier dates. Using one day older data costs little
for a twelve-month signal and removes any intraday leak.
"""

from bisect import bisect_left
from datetime import date
from typing import Mapping, Sequence

from .market_data import Candle


def ranking_table(data: Mapping[str, Sequence[Candle]], lookback: int = 252,
                  skip: int = 21, fraction: float = 1 / 3,
                  minimum_markets: int = 3) -> dict:
    """market -> {date: signal in {-1, 0, 1}} for every candle date."""
    if lookback < 5 or skip < 0 or not 0 < fraction <= 0.5 or minimum_markets < 2:
        raise ValueError("Require lookback >= 5, skip >= 0, fraction in (0, 0.5], "
                         "minimum_markets >= 2")
    days = {name: [c.open_time.date() for c in candles] for name, candles in data.items()}
    every_day = sorted({d for values in days.values() for d in values})
    table: dict = {name: {} for name in data}
    for day in every_day:
        scores = {}
        for name, candles in data.items():
            # Last candle strictly before this date.
            last = bisect_left(days[name], day) - 1
            end, start = last - skip, last - skip - lookback
            if start >= 0:
                scores[name] = candles[end].close / candles[start].close - 1
        if len(scores) < minimum_markets:
            continue
        ranked = sorted(scores, key=lambda name: (scores[name], name))
        count = max(1, int(len(ranked) * fraction))
        for name in ranked[:count]:
            table[name][day] = -1
        for name in ranked[-count:]:
            table[name][day] = 1
    return table


def cross_momentum_factory(data, lookback: int = 252, skip: int = 21,
                           fraction: float = 1 / 3, minimum_markets: int = 3):
    """Portfolio factory (``per_market``) reading each market's row of the ranking."""
    table = ranking_table(data, lookback, skip, fraction, minimum_markets)

    def factory(market):
        row = table[market.name]

        def strategy(history) -> int:
            today: date = history[-1].open_time.date()
            return row.get(today, 0)

        return strategy

    factory.per_market = True
    return factory
