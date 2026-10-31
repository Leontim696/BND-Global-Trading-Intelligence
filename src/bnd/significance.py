"""Validare statistică: strategia bate cu adevărat „cumperi și ții”, sau e noroc?

Bootstrap pe blocuri (blocuri de zile consecutive, ca să păstreze dependența din
serii) pe diferența zilnică de randament dintre două curbe de capital, aliniate
pe dată. Rezultat: diferența medie anualizată, un interval de încredere de 95%
și p-ul: partea din reeșantionări în care strategia nu bate varianta de
comparație. Cu zeci de zile sau cu un singur episod, intervalul va fi larg.
"""

import random
from datetime import datetime
from math import sqrt
from statistics import mean, stdev
from typing import Sequence


def daily_returns(curve: Sequence[tuple[datetime, float]]) -> dict:
    return {t1: v1 / v0 - 1 for (t0, v0), (t1, v1) in zip(curve, curve[1:]) if v0 > 0}


def bootstrap_difference(curve_a, curve_b, block: int = 10, samples: int = 2000,
                         seed: int = 7, periods_per_year: float = 365.0) -> dict:
    """A minus B: diferență medie anualizată, interval 95% și p (A nu bate B)."""
    if block < 1 or samples < 100:
        raise ValueError("block >= 1 și samples >= 100")
    a, b = daily_returns(curve_a), daily_returns(curve_b)
    days = sorted(set(a) & set(b))
    if len(days) < 2 * block:
        raise ValueError("Prea puține zile comune pentru bootstrap")
    diffs = [a[d] - b[d] for d in days]
    n, rng = len(diffs), random.Random(seed)
    means = []
    for _ in range(samples):
        picked = []
        while len(picked) < n:
            start = rng.randrange(n)
            picked.extend(diffs[(start + k) % n] for k in range(block))
        means.append(mean(picked[:n]))
    means.sort()
    annual = periods_per_year
    spread = stdev(diffs)
    return {
        "days": n, "block": block, "samples": samples,
        "mean_difference_pct_annual": 100 * mean(diffs) * annual,
        "ci95_low_pct_annual": 100 * means[int(0.025 * samples)] * annual,
        "ci95_high_pct_annual": 100 * means[int(0.975 * samples) - 1] * annual,
        "p_not_better": sum(m <= 0 for m in means) / samples,
        "sharpe_of_difference": mean(diffs) / spread * sqrt(annual) if spread > 0 else None,
    }
