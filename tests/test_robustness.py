"""Offline robustness tests on synthetic candles; never contact Binance."""

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from itertools import groupby

import pytest

from src.bnd.backtest_cli import main
from src.bnd.backtester import BacktestConfig, CostModel
from src.bnd.market_data import Candle, save_csv
from src.bnd.robustness import (
    cost_stress,
    parameter_grid,
    parameter_sets,
    parse_range,
    permutation_test,
    permute_runs,
    record_targets,
    select_in_sample,
)
from src.bnd.strategies import sma_crossover

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
NO_COSTS = CostModel(fee_pct=0.0, slippage_pct=0.0)


def cycle_candles(cycles=12, leg=5, move=0.02):
    """Repeating pattern: `leg` candles up, then `leg` candles down."""
    candles, price = [], 100.0
    for i in range(cycles * 2 * leg):
        up = (i // leg) % 2 == 0
        close = price * (1 + move if up else 1 - move)
        candles.append(Candle(START + timedelta(hours=4 * i), price,
                              max(price, close), min(price, close), close, 1))
        price = close
    return candles


def cycle_timer(leg=5):
    """Long during up legs, using only the candle count (no prices)."""
    def strategy(history):
        next_index = len(history)
        return 1 if (next_index // leg) % 2 == 0 else 0
    return strategy


def test_parse_range():
    assert parse_range("10:30:10") == [10, 20, 30]
    assert parse_range("7") == [7]
    for bad in ("10:5:1", "1:5:0", "a:b:c", "1:2"):
        with pytest.raises(ValueError):
            parse_range(bad)


def test_permute_runs_preserves_holding_periods_and_head():
    targets = [0, 0, 1, 1, 1, 0, 1, 0, 0, 1, 1]
    rng = random.Random(1)

    shuffled = permute_runs(targets, rng, start=2)

    assert shuffled[:2] == targets[:2]
    assert len(shuffled) == len(targets)
    assert sum(shuffled) == sum(targets)

    def runs(seq):
        return sorted((k, len(list(g))) for k, g in groupby(seq))

    assert runs(shuffled[2:]) == runs(targets[2:])
    # Runs never merge, so the number of position changes is unchanged.
    assert len(list(groupby(shuffled[2:]))) == len(list(groupby(targets[2:])))


def test_permutation_test_detects_real_timing_edge():
    candles = cycle_candles()
    config = BacktestConfig(costs=NO_COSTS)
    result, targets = record_targets(candles, cycle_timer(), config)

    report = permutation_test(candles, targets, config, permutations=99, seed=3)

    assert report["actual_return_pct"] == pytest.approx(
        result.metrics["total_return_pct"]
    )
    assert report["actual_return_pct"] > report["shuffled_p95_return_pct"]
    assert report["p_value"] <= 0.05


def test_permutation_test_finds_no_edge_in_random_positions():
    candles = cycle_candles()
    config = BacktestConfig(costs=NO_COSTS)
    rng = random.Random(11)
    positions = [rng.choice((0, 1)) for _ in candles]

    _, targets = record_targets(
        candles, lambda h: positions[len(h) - 1], config
    )
    report = permutation_test(candles, targets, config, permutations=99, seed=5)

    assert report["p_value"] > 0.05


def test_permutation_test_is_reproducible_with_seed():
    candles = cycle_candles()
    config = BacktestConfig(costs=NO_COSTS)
    _, targets = record_targets(candles, cycle_timer(), config)

    first = permutation_test(candles, targets, config, permutations=20, seed=9)
    second = permutation_test(candles, targets, config, permutations=20, seed=9)

    assert first == second


def test_grid_skips_invalid_combinations():
    candles = cycle_candles()
    params = parameter_sets(fast=[5, 10], slow=[5, 20])

    rows = parameter_grid(candles, sma_crossover, params,
                          BacktestConfig(costs=NO_COSTS))

    # fast >= slow is invalid: (5, 5), (10, 5) are skipped.
    assert [row["params"] for row in rows] == [
        {"fast": 5, "slow": 20}, {"fast": 10, "slow": 20}
    ]


def test_select_in_sample_reports_out_of_sample_rank():
    def row(fast, sharpe):
        return {"params": {"fast": fast}, "total_return_pct": sharpe,
                "sharpe": sharpe, "max_drawdown_pct": 0, "trades": 1}

    in_sample = [row(1, 2.0), row(2, 1.0), row(3, None)]
    out_of_sample = [row(1, 0.1), row(2, 0.9), row(3, 0.5)]

    selection = select_in_sample(in_sample, out_of_sample)

    assert selection["params"] == {"fast": 1}
    assert selection["out_of_sample_rank"] == 3
    assert selection["out_of_sample"]["sharpe"] == 0.1


def test_cost_stress_lowers_returns():
    candles = cycle_candles()
    config = BacktestConfig(costs=CostModel(fee_pct=0.1, slippage_pct=0.05))

    rows = cost_stress(candles, cycle_timer, config)

    returns = [row["total_return_pct"] for row in rows]
    assert returns == sorted(returns, reverse=True)
    assert rows[1]["fee_pct"] == pytest.approx(0.2)


def test_wiped_out_targets_can_be_replayed():
    # Short into a 3x rally wipes the account out and stops the run early.
    candles = [Candle(START + timedelta(hours=4 * i), p, p, p, p, 1)
               for i, p in enumerate([100, 100, 300, 300, 300, 300])]
    config = BacktestConfig(costs=NO_COSTS, allow_short=True)

    _, targets = record_targets(candles, lambda h: -1, config)
    report = permutation_test(candles, targets, config, permutations=5)

    assert len(targets) < len(candles)
    assert report["permutations"] == 5


def test_cli_robustness_end_to_end(tmp_path, capsys):
    path = tmp_path / "cycles.csv"
    save_csv(cycle_candles(cycles=20), path)

    code = main([
        "robustness", "--data", str(path), "--no-risk-gate",
        "--fast-range", "2:6:2", "--slow-range", "8:12:4",
        "--permutations", "19",
    ])

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report["risk_gate"] == "disabled_research_only"
    assert report["grid_summary"]["in_sample"]["combinations"] == 6
    assert report["in_sample_selection"]["out_of_sample_combinations"] == 6
    assert report["permutation_test_out_of_sample"]["permutations"] == 19
    assert [r["cost_multiplier"] for r in report["cost_stress_out_of_sample"]] == [1, 2, 3]
    assert report["grid"] is None


def test_cli_robustness_requires_risk_choice(tmp_path, capsys):
    path = tmp_path / "cycles.csv"
    save_csv(cycle_candles(), path)

    code = main(["robustness", "--data", str(path)])

    assert code == 2
    assert "--no-risk-gate" in capsys.readouterr().err


def test_cli_robustness_rejects_strategy_without_parameters(tmp_path, capsys):
    path = tmp_path / "cycles.csv"
    save_csv(cycle_candles(), path)

    code = main(["robustness", "--data", str(path), "--no-risk-gate",
                 "--strategy", "buy_and_hold"])

    assert code == 2


def test_run_report_includes_dataset_hash(tmp_path, capsys):
    path = tmp_path / "cycles.csv"
    save_csv(cycle_candles(), path)

    main(["run", "--data", str(path), "--no-risk-gate",
          "--fast", "2", "--slow", "8"])

    report = json.loads(capsys.readouterr().out)
    assert report["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report["candles"] == len(cycle_candles())
