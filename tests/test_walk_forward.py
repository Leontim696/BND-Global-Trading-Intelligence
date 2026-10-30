"""Tests for walk-forward optimisation."""

import contextlib
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.backtest_cli import main as cli
from src.bnd.backtester import BacktestConfig, CostModel
from src.bnd.market_data import Candle, save_csv
from src.bnd.robustness import parameter_sets
from src.bnd.strategies import momentum, sma_crossover
from src.bnd.walk_forward import folds, walk_forward

START = datetime(2020, 1, 1, tzinfo=timezone.utc)


def candles_from(closes):
    out, previous = [], closes[0]
    for i, close in enumerate(closes):
        out.append(Candle(START + timedelta(days=i), previous, max(previous, close),
                          min(previous, close), close, 1))
        previous = close
    return out


def test_folds_rolling_expanding_and_embargo():
    rolling = folds(100, train=40, test=20, embargo=5)
    expanding = folds(100, train=40, test=20, embargo=5, mode="expanding")

    assert rolling == [(0, 40, 45, 65), (20, 60, 65, 85)]
    assert expanding == [(0, 40, 45, 65), (0, 60, 65, 85)]
    # Test windows never overlap and never touch their own training data.
    for start, end, test_start, test_end in rolling:
        assert test_start - end == 5
    with pytest.raises(ValueError):
        folds(30, train=40, test=20)


def test_parameters_are_chosen_on_training_data_only(monkeypatch):
    import src.bnd.walk_forward as wf

    seen = []
    original = wf.parameter_grid

    def spy(candles, *args, **kwargs):
        seen.append((candles[0].open_time, candles[-1].open_time))
        return original(candles, *args, **kwargs)

    monkeypatch.setattr(wf, "parameter_grid", spy)
    data = candles_from([100 + (i % 17) for i in range(300)])
    report = walk_forward(data, momentum, parameter_sets(lookback=[5, 10]),
                          BacktestConfig(costs=CostModel(0, 0)), train=100, test=50, embargo=3)

    for (first, last), row in zip(seen, report["folds"]):
        assert last < datetime.fromisoformat(row["test"][0])
        assert datetime.fromisoformat(row["test"][0]) - last == timedelta(days=4)


def test_trend_rewards_trend_parameters_and_reports_stability():
    closes = [100 * 1.003 ** i * (1 + 0.01 * (-1) ** i) for i in range(900)]
    report = walk_forward(candles_from(closes), sma_crossover,
                          parameter_sets(fast=[5, 10], slow=[20, 40]),
                          BacktestConfig(costs=CostModel(0, 0)), train=300, test=150)

    summary = report["summary"]
    assert summary["fold_count"] == 4
    assert summary["positive_folds"] >= 3
    assert 0 <= summary["parameter_change_rate"] <= 1
    assert summary["chained_test_return_pct"] > 0
    # Buy-and-hold on the same windows is reported for comparison.
    assert summary["chained_buy_and_hold_return_pct"] > 0
    assert 0 <= summary["folds_beating_buy_and_hold"] <= summary["fold_count"]
    assert all("buy_and_hold_return_pct" in row for row in report["folds"])


def test_switch_off_after_poor_folds():
    from math import pi, sin

    # An up-trend, then a sideways market whose swings whipsaw a trend rule.
    closes = [100 * 1.004 ** i for i in range(400)]
    base = closes[-1]
    closes += [base * (1 + 0.04 * sin(2 * pi * i / 26)) * (1 + 0.01 * (-1) ** i)
               for i in range(1, 1001)]
    report = walk_forward(candles_from(closes), sma_crossover,
                          parameter_sets(fast=[5], slow=[20]),
                          BacktestConfig(costs=CostModel(0.1, 0.05)), train=200, test=100,
                          disable_below=0.0, disable_after=2)

    summary = report["summary"]
    assert summary["folds_switched_off"] >= 1
    # Losing folds after two poor ones are skipped, so the record improves.
    assert summary["chained_return_with_switch_off_pct"] > summary["chained_test_return_pct"]
    # The rule only looks at folds already finished.
    assert report["folds"][0]["switched_off"] is False
    assert report["folds"][1]["switched_off"] is False


def test_cli_walk_forward_opt(tmp_path):
    path = tmp_path / "trend.csv"
    save_csv(candles_from([100 * 1.002 ** i * (1 + 0.01 * (-1) ** i) for i in range(700)]), path)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli(["walk-forward-opt", "--data", str(path), "--strategy", "sma_crossover",
                    "--no-risk-gate", "--train", "300", "--test", "100",
                    "--range", "fast=5:10:5", "--range", "slow=20:40:20"])

    assert code == 0
    report = json.loads(out.getvalue())
    assert report["summary"]["fold_count"] == 3
    assert report["dataset"]["sha256"]
    assert {"fast", "slow"} == set(report["folds"][0]["params"])

    from src.bnd.backtest_summary import build_summary
    report_path = tmp_path / "wfo.json"
    report_path.write_text(out.getvalue())
    text = build_summary(optimisation=report_path)
    assert "## Walk-forward optimisation (rolling" in text and "switch-off" in text
