"""Paired window-by-window comparison of walk-forward reports."""

import json

import pytest

from src.bnd.compare_wfo import compare, main, sign_test_p


def report(name, returns, start=2014):
    return {"strategy": name, "folds": [
        {"test": [f"{start + i}-01-05", f"{start + i + 1}-01-05"], "test_return_pct": r}
        for i, r in enumerate(returns)]}


def test_sign_test_values():
    assert sign_test_p(6, 6) == 1.0
    assert sign_test_p(12, 0) == pytest.approx(2 / 4096)
    assert sign_test_p(10, 2) == pytest.approx(0.0386, abs=1e-4)
    assert sign_test_p(0, 0) == 1.0


def test_compare_counts_wins_and_differences():
    a = report("sma", [10, 5, -2, 8])
    b = report("hold", [4, 7, -5, 8])

    result = compare(a, b)

    assert (result["windows"], result["a_wins"], result["b_wins"]) == (4, 2, 1)
    assert result["mean_difference_pct"] == pytest.approx((6 - 2 + 3 + 0) / 4)
    assert result["per_window"][0]["difference_pct"] == 6


def test_only_shared_windows_are_compared():
    result = compare(report("a", [1, 2, 3]), report("b", [1, 1, 1, 1], start=2015))

    assert result["windows"] == 2 and result["unmatched_windows"] == 3
    with pytest.raises(ValueError):
        compare(report("a", [1]), report("b", [1]))


def test_cli(tmp_path, capsys):
    (tmp_path / "a.json").write_text(json.dumps(report("sma", [10, 12, 9, 11])))
    (tmp_path / "b.json").write_text(json.dumps(report("hold", [1, 2, 3, 4])))

    assert main([str(tmp_path / "a.json"), str(tmp_path / "b.json")]) == 0
    text = capsys.readouterr().out
    assert "sma better in 4" in text and "Sign test p" in text
    assert main([str(tmp_path / "a.json"), str(tmp_path / "missing.json")]) == 2
