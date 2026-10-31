"""Regimuri de piață: urcare sau scădere, calm sau agitat.

Un regim se stabilește la închiderea fiecărei zile, doar din date până atunci:
- tendință: prețul peste (urcare) sau sub (scădere) media pe 200 de zile;
- volatilitate: mișcarea din ultimele 20 de zile peste sau sub mediana tuturor
  celor de până atunci (agitat sau calm).
Rezultatul unei zile se atribuie regimului cunoscut la închiderea zilei de
dinainte, deci nu există informație din viitor.

    labels = label_regimes(candles_sp500)
    table = regime_breakdown(equity_curve, labels)
"""

from bisect import bisect_right
from datetime import datetime
from math import log, sqrt
from statistics import mean, median, stdev
from typing import Sequence

from .market_data import Candle

REGIMES = ("urcare calmă", "urcare agitată", "scădere calmă", "scădere agitată")


def label_regimes(candles: Sequence[Candle], trend_days: int = 200,
                  vol_days: int = 20) -> dict:
    """data -> numele regimului (doar pentru zilele cu suficient istoric)."""
    if trend_days < 20 or vol_days < 5:
        raise ValueError("trend_days >= 20 și vol_days >= 5")
    closes = [c.close for c in candles]
    labels, volatilities = {}, []
    for i, candle in enumerate(candles):
        if i < vol_days:
            continue
        window = closes[i - vol_days:i + 1]
        returns = [log(b / a) for a, b in zip(window, window[1:])]
        vol = stdev(returns) * sqrt(365)
        history = list(volatilities)            # doar zilele de dinainte
        volatilities.append(vol)
        if i < trend_days or len(history) < 30:
            continue
        sma = mean(closes[i - trend_days + 1:i + 1])
        trend = "urcare" if candle.close > sma else "scădere"
        mood = "agitată" if vol > median(history) else "calmă"
        labels[candle.open_time] = f"{trend} {mood}"
    return labels


def regime_breakdown(curve: Sequence[tuple[datetime, float]], labels: dict,
                     periods_per_year: float = 365.0) -> dict:
    """Pe regim: zile, randament total, randament anualizat, volatilitate, Sharpe."""
    times = sorted(labels)
    daily = {name: [] for name in REGIMES}
    for (t0, v0), (t1, v1) in zip(curve, curve[1:]):
        index = bisect_right(times, t0) - 1
        if index < 0 or v0 <= 0:
            continue
        daily[labels[times[index]]].append(v1 / v0 - 1)
    table = {}
    for name, returns in daily.items():
        if not returns:
            table[name] = {"days": 0, "return_pct": None, "annual_return_pct": None,
                           "annual_vol_pct": None, "sharpe": None}
            continue
        growth = 1.0
        for r in returns:
            growth *= 1 + r
        deviation = stdev(returns) if len(returns) > 1 else 0.0
        table[name] = {
            "days": len(returns),
            "return_pct": 100 * (growth - 1),
            "annual_return_pct": 100 * (growth ** (periods_per_year / len(returns)) - 1),
            "annual_vol_pct": 100 * deviation * sqrt(periods_per_year),
            "sharpe": mean(returns) / deviation * sqrt(periods_per_year) if deviation > 0 else None,
        }
    return table
