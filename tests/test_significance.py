"""Bootstrap pe blocuri pentru diferența dintre două curbe de capital."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.significance import bootstrap_difference

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def curve(daily):
    value, out = 100.0, [(T0, 100.0)]
    for i, r in enumerate(daily, 1):
        value *= 1 + r
        out.append((T0 + timedelta(days=i), value))
    return out


def noise(n, seed, mu=0.0, sigma=0.01):
    rng = random.Random(seed)
    return [rng.gauss(mu, sigma) for _ in range(n)]


def test_a_clearly_better_strategy_is_significant():
    base = noise(400, 1)
    better = [r + 0.002 for r in base]            # +0,2% pe zi, zgomot identic

    result = bootstrap_difference(curve(better), curve(base))

    assert result["p_not_better"] < 0.01 and result["ci95_low_pct_annual"] > 0
    assert result["mean_difference_pct_annual"] == pytest.approx(73, rel=0.05)


def test_two_unrelated_noisy_curves_are_not_significant():
    result = bootstrap_difference(curve(noise(400, 2)), curve(noise(400, 3)))

    assert result["p_not_better"] > 0.05 or result["ci95_low_pct_annual"] <= 0
    assert result["ci95_low_pct_annual"] < 0 < result["ci95_high_pct_annual"]


def test_same_seed_same_answer_and_validation():
    a, b = curve(noise(200, 4)), curve(noise(200, 5))

    assert bootstrap_difference(a, b) == bootstrap_difference(a, b)
    for kwargs in (dict(block=0), dict(samples=10)):
        with pytest.raises(ValueError):
            bootstrap_difference(a, b, **kwargs)
    with pytest.raises(ValueError, match="Prea puține"):
        bootstrap_difference(curve([0.01] * 5), curve([0.0] * 5))


def test_portfolio_report_carries_the_check(tmp_path):
    import json

    from src.bnd.backtest_summary import build_summary
    from tests.test_multi_market_cli import run_cli, write_markets

    write_markets(tmp_path, ["EURUSD", "GOLD", "SP500"], days=900)
    code, out, err = run_cli(["portfolio", "--permutations", "0", "--data-dir", str(tmp_path),
                              "--markets", "EURUSD,GOLD,SP500", "--strategy", "macd"])

    assert code == 0, err
    check = json.loads(out)["ranking"][0]["vs_basket_bootstrap"]
    assert check["days"] > 100 and 0 <= check["p_not_better"] <= 1
    path = tmp_path / "p.json"
    path.write_text(out)
    assert "Verificare statistică" in build_summary(portfolio=path)
