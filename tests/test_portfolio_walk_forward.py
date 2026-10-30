"""Portfolio walk-forward: calendar folds, no leakage, honest comparison."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.portfolio import PortfolioConfig
from src.bnd.portfolio_walk_forward import calendar_folds, portfolio_walk_forward
from src.bnd.strategies import sma_crossover
from src.bnd.universe import Market
from tests.test_multi_market_cli import run_cli, write_markets

START = datetime(2020, 1, 1, tzinfo=timezone.utc)
MARKETS = (Market("EURUSD", "EURUSD=X", "forex", 0.002, 0.005),
           Market("GOLD", "GC=F", "commodity", 0.02, 0.05),
           Market("SP500", "^GSPC", "index", 0.01, 0.02))


def test_calendar_folds_do_not_overlap_and_respect_embargo():
    times = [START + timedelta(days=i) for i in range(1000)]

    folds = calendar_folds(times, train_days=400, test_days=200, embargo_days=5)

    assert len(folds) == 2
    for train_start, train_end, test_start, test_end in folds:
        assert train_end - train_start == timedelta(days=400)
        assert test_start - train_end == timedelta(days=5)
    assert folds[1][2] >= folds[0][3]
    with pytest.raises(ValueError):
        calendar_folds(times[:100], 400, 200)


def load(tmp_path, days=1000):
    from src.bnd.market_data import load_csv

    write_markets(tmp_path, [m.name for m in MARKETS], days=days)
    return {m.name: load_csv(tmp_path / f"{m.name}.csv") for m in MARKETS}


def test_parameters_are_chosen_without_seeing_the_test_window(tmp_path):
    data = load(tmp_path)
    seen_ends = []

    def make_factory(params, frame):
        seen_ends.append(max(c[-1].open_time for c in frame.values()))
        return lambda: sma_crossover(**params)

    report = portfolio_walk_forward(
        data, MARKETS, make_factory, [{"fast": 5, "slow": 20}, {"fast": 10, "slow": 40}],
        PortfolioConfig(vol_lookback=20), train_days=400, test_days=200, embargo_days=5)

    folds = calendar_folds(sorted({c.open_time for c in data["GOLD"]}), 400, 200, 5)
    # Training factories (two per fold) only ever see candles before train_end.
    for index, (_, train_end, _, test_end) in enumerate(folds):
        assert all(end < train_end for end in seen_ends[3 * index:3 * index + 2])
        assert seen_ends[3 * index + 2] < test_end
    summary = report["summary"]
    assert summary["fold_count"] == len(report["folds"]) == 2
    assert 0 <= summary["folds_beating_basket"] <= 2
    for row in report["folds"]:
        assert row["params"] in ({"fast": 5, "slow": 20}, {"fast": 10, "slow": 40})
        assert "basket_return_pct" in row


def test_cli_portfolio_wfo_and_summary(tmp_path):
    from src.bnd.backtest_summary import build_summary

    write_markets(tmp_path, [m.name for m in MARKETS], days=1000)
    args = ["portfolio-wfo", "--data-dir", str(tmp_path), "--markets", "EURUSD,GOLD,SP500",
            "--strategy", "sma_crossover", "--range", "fast=5:10:5", "--range", "slow=20:40:20",
            "--sizing-lookback", "20", "--train-days", "400", "--test-days", "200"]

    code, out, err = run_cli(args)

    assert code == 0, err
    report = json.loads(out)
    assert report["mode"] == "portfolio-wfo" and report["summary"]["fold_count"] == 2
    path = tmp_path / "pwfo.json"
    path.write_text(out)
    text = build_summary(portfolio_wfo=path)
    assert "## Portfolio walk-forward" in text and "basket" in text

    code, _, err = run_cli(args[:-4] + ["--param", "colour=1", "--train-days", "400",
                                         "--test-days", "200"])
    assert code == 2 and "Invalid parameters" in err


def test_cli_portfolio_wfo_cross_momentum(tmp_path):
    write_markets(tmp_path, [m.name for m in MARKETS], days=1000)

    code, out, err = run_cli(["portfolio-wfo", "--data-dir", str(tmp_path),
                              "--markets", "EURUSD,GOLD,SP500", "--strategy", "cross_momentum",
                              "--range", "lookback=60:120:60", "--range", "skip=0",
                              "--sizing-lookback", "20", "--train-days", "400",
                              "--test-days", "200"])

    assert code == 0, err
    assert json.loads(out)["folds"][0]["params"]["lookback"] in (60, 120)


def test_verdict_needs_more_return_and_most_windows():
    from src.bnd.backtest_summary import portfolio_wfo_verdict

    def report(ours, basket, beat, folds=4):
        return {"summary": {"chained_test_return_pct": ours, "chained_basket_return_pct": basket,
                            "folds_beating_basket": beat, "fold_count": folds}}

    assert "No evidence" in portfolio_wfo_verdict(report(10, 20, 3))
    assert "No evidence" in portfolio_wfo_verdict(report(30, 20, 2))
    assert "Beat the basket" in portfolio_wfo_verdict(report(30, 20, 3))
