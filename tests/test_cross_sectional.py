"""Cross-sectional momentum ranking: correctness and no look-ahead."""

from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.cross_sectional import cross_momentum_factory, ranking_table
from src.bnd.market_data import Candle
from src.bnd.universe import Market

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def series(count, step, hour=0):
    out, price = [], 100.0
    for i in range(count):
        close = price * (1 + step)
        out.append(Candle(START + timedelta(days=i, hours=hour), price, max(price, close),
                          min(price, close), close, 1))
        price = close
    return out


def data(count=60):
    return {"UP": series(count, 0.01), "FLAT": series(count, 0.0001),
            "DOWN": series(count, -0.01, hour=14)}


def test_strongest_long_weakest_short_middle_flat():
    table = ranking_table(data(), lookback=20, skip=5)

    day = START.date() + timedelta(days=50)
    assert (table["UP"][day], table["FLAT"].get(day, 0), table["DOWN"][day]) == (1, 0, -1)
    # Not enough history yet: no ranking (26 earlier candles are needed).
    assert START.date() + timedelta(days=25) not in table["UP"]
    assert START.date() + timedelta(days=26) in table["UP"]


def test_ranking_for_a_date_ignores_that_date_and_later():
    original = data()
    changed = {name: list(candles) for name, candles in original.items()}
    # Make DOWN the best market from day 40 on.
    changed["DOWN"] = changed["DOWN"][:40] + [
        Candle(c.open_time, c.open * 100, c.high * 100, c.low * 100, c.close * 100, 1)
        for c in changed["DOWN"][40:]]

    before, after = ranking_table(original, 20, 0), ranking_table(changed, 20, 0)

    for day in sorted(before["UP"]):
        if day <= START.date() + timedelta(days=40):
            assert all(before[n].get(day) == after[n].get(day) for n in original)
    assert after["DOWN"][START.date() + timedelta(days=45)] == 1


def test_too_few_markets_gives_no_ranking():
    two = {k: v for k, v in data().items() if k != "FLAT"}

    assert ranking_table(two, 20, 5) == {"UP": {}, "DOWN": {}}


@pytest.mark.parametrize("kwargs", [dict(lookback=2), dict(skip=-1), dict(fraction=0.6),
                                    dict(minimum_markets=1)])
def test_validation(kwargs):
    with pytest.raises(ValueError):
        ranking_table(data(), **kwargs)


def test_factory_reads_each_markets_row():
    frame = data()
    factory = cross_momentum_factory(frame, lookback=20, skip=5)
    assert factory.per_market

    up = factory(Market("UP", "UP", "index", 0, 0))
    down = factory(Market("DOWN", "DOWN", "index", 0, 0))

    assert up(frame["UP"][:51]) == 1 and down(frame["DOWN"][:51]) == -1
    assert up(frame["UP"][:5]) == 0
