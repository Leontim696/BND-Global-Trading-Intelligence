"""Offline tests for the Markdown backtest summary."""

import contextlib
import io
import json
from datetime import datetime, timedelta, timezone

from src.bnd.backtest_cli import main as cli
from src.bnd.backtest_summary import build_summary, verdict
from src.bnd.market_data import Candle, save_csv

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def write_reports(tmp_path):
    candles, price = [], 100.0
    for i in range(400):
        close = price * (1.02 if (i // 5) % 2 == 0 else 0.98)
        candles.append(Candle(START + timedelta(hours=4 * i), price,
                              max(price, close), min(price, close), close, 1))
        price = close
    data = tmp_path / "cycles.csv"
    save_csv(candles, data)

    commands = {
        "run": ["run", "--fast", "2", "--slow", "8"],
        "walk": ["walk-forward", "--window", "10", "--train", "100", "--test", "100"],
        "robust": ["robustness", "--fast-range", "2:4:2", "--slow-range", "8:10:2",
                   "--permutations", "9"],
    }
    paths = {}
    for name, args in commands.items():
        extra = ["--no-risk-gate"] if name != "walk" else []
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert cli(args + ["--data", str(data)] + extra) == 0
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(buffer.getvalue())
    return paths


def test_summary_contains_every_section(tmp_path):
    paths = write_reports(tmp_path)

    text = build_summary(paths["run"], paths["walk"], paths["robust"])

    for heading in ("## Dataset", "## Verdict", "## Backtest", "## Walk-forward",
                    "## Robustness", "**Permutation test**"):
        assert heading in text
    sha = json.loads(paths["run"].read_text())["sha256"]
    assert sha in text
    assert "## Missing reports" not in text


def test_summary_lists_missing_reports(tmp_path):
    paths = write_reports(tmp_path)

    text = build_summary(paths["run"], tmp_path / "absent.json", None)

    assert "## Missing reports" in text
    assert "absent.json" in text
    assert "No robustness report" in text


def robustness_report(p_value, oos_return, stressed_return):
    return {
        "permutation_test_out_of_sample": {"p_value": p_value},
        "in_sample_selection": {"out_of_sample": {"total_return_pct": oos_return}},
        "cost_stress_out_of_sample": [
            {"cost_multiplier": 1.0, "total_return_pct": oos_return},
            {"cost_multiplier": 2.0, "total_return_pct": stressed_return},
        ],
    }


def test_verdict_requires_all_conditions():
    assert "Preliminary evidence" in verdict(robustness_report(0.01, 12.0, 4.0))

    weak = verdict(robustness_report(0.20, 12.0, 4.0))
    assert "No evidence" in weak and "p-value" in weak

    assert "2× costs" in verdict(robustness_report(0.01, 12.0, -1.0))
    assert "out-of-sample return" in verdict(robustness_report(0.01, -3.0, -5.0))


def test_verdict_without_report():
    assert "No robustness report" in verdict(None)


def test_compare_summary_and_verdict(tmp_path):
    from src.bnd.backtest_summary import compare_verdict

    candles, price = [], 100.0
    for i in range(400):
        close = price * (1.02 if (i // 5) % 2 == 0 else 0.98)
        candles.append(Candle(START + timedelta(hours=4 * i), price,
                              max(price, close), min(price, close), close, 1))
        price = close
    data = tmp_path / "cycles.csv"
    save_csv(candles, data)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert cli(["compare", "--data", str(data), "--no-risk-gate",
                    "--permutations", "9"]) == 0
    path = tmp_path / "compare.json"
    path.write_text(buffer.getvalue())

    text = build_summary(compare=path)

    assert "## Strategy comparison" in text
    assert "buy & hold" in text
    assert "## Missing reports" not in text

    row = {"strategy": "x", "p_value_adjusted": 0.01,
           "out_of_sample": {"total_return_pct": 5.0}}
    assert "Candidates" in compare_verdict({"ranking": [row]})
    row["p_value_adjusted"] = 0.2
    assert "No strategy shows evidence" in compare_verdict({"ranking": [row]})
