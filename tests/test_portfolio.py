"""Offline tests for the multi-market portfolio backtester."""

from datetime import datetime, timedelta, timezone
from math import sqrt

import pytest

from src.bnd.portfolio import PortfolioConfig, run_portfolio
from src.bnd.market_data import Candle
from src.bnd.strategies import buy_and_hold
from src.bnd.universe import DEFAULT_UNIVERSE, Market, select

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def market(name, asset_class="index", fee=0.0, slip=0.0):
    return Market(name, name, asset_class, fee, slip)


def series(closes, step=DAY, start=START, weekdays_only=False):
    """Candles whose open equals the previous close."""
    candles, previous, time = [], closes[0], start
    for close in closes:
        while weekdays_only and time.weekday() >= 5:
            time += DAY
        candles.append(Candle(time, previous, max(previous, close),
                              min(previous, close), close, 1))
        previous = close
        time += step
    return candles


def equal(**kwargs):
    base = dict(sizing="equal", max_leverage=1.0, financing_pct_annual=0.0,
                max_drawdown_pct=None, vol_lookback=5)
    base.update(kwargs)
    return PortfolioConfig(**base)


def noisy(base, count, wiggle=0.01, drift=0.0):
    return [base * (1 + drift) ** i * (1 + wiggle * (-1) ** i) for i in range(count)]


def test_single_market_tracks_price():
    closes = noisy(100, 20) + [200.0]
    result = run_portfolio({"A": series(closes)}, [market("A")], buy_and_hold, equal())

    # Volatility needs 5 returns, known at candle 5's close; the target
    # executes at candle 6's open. Price then moves to 200.
    final = result["metrics"]["final_equity"]
    entry = series(closes)[6].open
    assert final == pytest.approx(10_000 * 200 / entry, rel=1e-9)


def test_two_markets_split_equally():
    a, b = noisy(100, 20), noisy(50, 20)
    result = run_portfolio({"A": series(a), "B": series(b)},
                           [market("A"), market("B")], buy_and_hold, equal())

    rows = {row["market"]: row for row in result["per_market"]}
    assert rows["A"]["avg_abs_weight"] == pytest.approx(rows["B"]["avg_abs_weight"], rel=0.05)
    assert result["metrics"]["max_gross_leverage"] <= 1.0 + 1e-9


def test_volatility_sizing_is_capped_by_max_leverage():
    calm = noisy(1.10, 120, wiggle=0.001)
    config = PortfolioConfig(target_vol_pct=20, max_leverage=3, max_weight=10,
                             financing_pct_annual=0, max_drawdown_pct=None,
                             vol_lookback=20)

    result = run_portfolio({"FX": series(calm)}, [market("FX", "forex")],
                           buy_and_hold, config)

    # Raw weight is about 20% / ~2% vol = 10x; capped at 3x.
    assert result["metrics"]["max_gross_leverage"] == pytest.approx(3.0, rel=0.02)


def test_calmer_market_gets_larger_weight():
    calm, wild = noisy(100, 120, wiggle=0.002), noisy(100, 120, wiggle=0.02)
    config = PortfolioConfig(max_leverage=10, max_weight=10, financing_pct_annual=0,
                             max_drawdown_pct=None, vol_lookback=20)

    result = run_portfolio({"C": series(calm), "W": series(wild)},
                           [market("C"), market("W")], buy_and_hold, config)

    rows = {row["market"]: row for row in result["per_market"]}
    assert rows["C"]["avg_abs_weight"] == pytest.approx(10 * rows["W"]["avg_abs_weight"], rel=0.1)


def test_financing_is_charged_on_borrowed_amount():
    flat = noisy(100, 400, wiggle=0.0005)
    # Two markets, each capped at weight 1: 2x gross on one account.
    config = PortfolioConfig(target_vol_pct=200, max_leverage=2, max_weight=1,
                             financing_pct_annual=5, max_drawdown_pct=None,
                             vol_lookback=5)

    result = run_portfolio({"A": series(flat), "B": series(flat)},
                           [market("A"), market("B")], buy_and_hold, config)

    years = (len(flat) - 7) / 365.25
    # About 10,000 borrowed at 5% a year.
    assert result["metrics"]["total_financing"] == pytest.approx(10_000 * 0.05 * years, rel=0.05)


def test_kill_switch_closes_everything():
    closes = noisy(100, 10) + [100 * 0.9 ** i for i in range(1, 6)] + [80.0] * 20
    config = equal(max_drawdown_pct=20)

    result = run_portfolio({"A": series(closes)}, [market("A")], buy_and_hold, config)

    metrics = result["metrics"]
    assert metrics["kill_switch_at"] is not None
    curve = [value for _, value in result["equity_curve"]]
    # After the switch the account is flat: equity no longer moves.
    assert curve[-1] == pytest.approx(curve[-5])
    assert metrics["max_drawdown_pct"] < 40


def test_shorts_only_when_allowed():
    falling = [100 * 0.99 ** i * (1 + 0.01 * (-1) ** i) for i in range(60)]
    data = {"A": series(falling)}

    short = run_portfolio(data, [market("A")], lambda: (lambda h: -1), equal())
    blocked = run_portfolio(data, [market("A")], lambda: (lambda h: -1),
                            equal(allow_short=False))

    assert short["metrics"]["total_return_pct"] > 20
    assert blocked["metrics"]["fills"] == 0


def test_mixed_calendars_and_no_lookahead():
    fx = series(noisy(1.1, 60), weekdays_only=True)
    crypto = series(noisy(100, 84))
    seen = {}

    def factory():
        def strategy(history):
            last = history[-1].open_time
            seen.setdefault(id(strategy), []).append(last)
            return 1
        return strategy

    result = run_portfolio({"FX": fx, "BTC": crypto},
                           [market("FX", "forex"), market("BTC", "crypto")], factory, equal())

    dates = [t for t, _ in result["equity_curve"]]
    assert dates == sorted(set(dates))
    for times in seen.values():
        assert times == sorted(times) and len(times) == len(set(times))


def test_warm_up_is_not_traded():
    closes = noisy(100, 60)
    candles = series(closes)
    result = run_portfolio({"A": candles}, [market("A")], buy_and_hold, equal(),
                           trade_from=candles[30].open_time)

    assert result["equity_curve"][0][0] == candles[30].open_time
    # Bought at candle 30's open, marked at its close.
    first = candles[30]
    assert result["equity_curve"][0][1] == pytest.approx(10_000 * first.close / first.open)


def test_costs_use_market_rates_and_multiplier():
    closes = noisy(100, 30)
    data = {"A": series(closes)}
    cheap = run_portfolio(data, [market("A", fee=0.01, slip=0.0)], buy_and_hold, equal())
    stressed = run_portfolio(data, [market("A", fee=0.01, slip=0.0)], buy_and_hold,
                             equal(cost_multiplier=3))

    assert stressed["metrics"]["total_fees"] == pytest.approx(
        3 * cheap["metrics"]["total_fees"], rel=0.01)


def test_universe_selection():
    assert len(DEFAULT_UNIVERSE) >= 20
    assert {m.asset_class for m in select(classes=["forex"])} == {"forex"}
    assert [m.name for m in select(names=["gold", "SP500"])] == ["GOLD", "SP500"]
    with pytest.raises(ValueError):
        select(names=["MOON"])


@pytest.mark.parametrize("kwargs", [dict(sizing="magic"), dict(max_leverage=0),
                                    dict(vol_lookback=2), dict(max_drawdown_pct=0)])
def test_config_validation(kwargs):
    with pytest.raises(ValueError):
        PortfolioConfig(**kwargs)


def test_sqrt_n_scaling():
    a, b = noisy(100, 120, wiggle=0.01), noisy(100, 120, wiggle=0.01)
    config = PortfolioConfig(max_leverage=10, max_weight=10, financing_pct_annual=0,
                             max_drawdown_pct=None, vol_lookback=20)

    one = run_portfolio({"A": series(a)}, [market("A")], buy_and_hold, config)
    two = run_portfolio({"A": series(a), "B": series(b)},
                        [market("A"), market("B")], buy_and_hold, config)

    w_one = one["per_market"][0]["avg_abs_weight"]
    w_two = {r["market"]: r for r in two["per_market"]}["A"]["avg_abs_weight"]
    assert w_two == pytest.approx(w_one / sqrt(2), rel=0.05)


def test_precomputed_volatility_matches_direct():
    import random

    from src.bnd.portfolio import _volatility, _volatility_by_end

    rng = random.Random(5)
    closes = [100.0]
    for _ in range(1300):
        closes.append(closes[-1] * (1 + rng.gauss(0, 0.02)))
    candles = series(closes, weekdays_only=True)

    fast = _volatility_by_end(candles, 20)

    for end in range(len(candles) + 1):
        direct = _volatility(candles, end, 20)
        assert (fast[end] is None) == (direct is None)
        if direct is not None:
            assert fast[end] == pytest.approx(direct, rel=1e-9)
