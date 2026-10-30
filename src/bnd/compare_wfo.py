"""Paired comparison of two portfolio walk-forward reports, window by window.

Both reports must cover the same test windows (same data, train/test/
embargo days). For each window the difference in test return is taken;
the summary gives how many windows A won, the mean and spread of the
differences, a t-statistic, and a two-sided sign-test p-value (exact
binomial): the chance of a win/loss split at least this lopsided if A
and B were equally good. With about a dozen windows only large,
consistent differences can count as evidence.

    python -m src.bnd.compare_wfo a.json b.json
"""

import argparse
import json
import sys
from math import comb, sqrt
from pathlib import Path
from statistics import mean, stdev


def sign_test_p(wins: int, losses: int) -> float:
    """Two-sided exact binomial p-value for wins vs losses at 50/50 (ties dropped)."""
    n = wins + losses
    if n == 0:
        return 1.0
    extreme = max(wins, losses)
    tail = sum(comb(n, k) for k in range(extreme, n + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def compare(a: dict, b: dict) -> dict:
    windows_a = {tuple(r["test"]): r for r in a["folds"]}
    windows_b = {tuple(r["test"]): r for r in b["folds"]}
    shared = sorted(set(windows_a) & set(windows_b))
    if len(shared) < 2:
        raise ValueError("The reports share fewer than two test windows")
    diffs = [windows_a[w]["test_return_pct"] - windows_b[w]["test_return_pct"] for w in shared]
    wins, losses = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    spread = stdev(diffs)
    return {
        "a": a.get("strategy"), "b": b.get("strategy"),
        "windows": len(shared),
        "unmatched_windows": len(set(windows_a) ^ set(windows_b)),
        "a_wins": wins, "b_wins": losses,
        "mean_difference_pct": mean(diffs),
        "stdev_difference_pct": spread,
        "t_statistic": mean(diffs) / (spread / sqrt(len(diffs))) if spread > 0 else None,
        "sign_test_p": sign_test_p(wins, losses),
        "per_window": [{"test": list(w), "a_pct": windows_a[w]["test_return_pct"],
                        "b_pct": windows_b[w]["test_return_pct"], "difference_pct": d}
                       for w, d in zip(shared, diffs)],
    }


def render(result: dict, label_a: str = "A", label_b: str = "B") -> str:
    t = result["t_statistic"]
    lines = [
        f"# {label_a} vs {label_b}, window by window",
        "",
        f"- Windows: {result['windows']}; {label_a} better in {result['a_wins']}, "
        f"{label_b} better in {result['b_wins']}",
        f"- Mean difference {result['mean_difference_pct']:+.2f} points per window "
        f"(spread {result['stdev_difference_pct']:.2f}); t = "
        + (f"{t:.2f}" if t is not None else "n/a"),
        f"- Sign test p = {result['sign_test_p']:.3f} "
        + ("(unlikely to be luck)" if result["sign_test_p"] < 0.05 else "(could be luck)"),
        "", "| Test window | " + label_a + " | " + label_b + " | Difference |",
        "| --- | ---: | ---: | ---: |",
    ]
    lines += [f"| {w['test'][0]} → {w['test'][1]} | {w['a_pct']:+.1f}% | {w['b_pct']:+.1f}% | "
              f"{w['difference_pct']:+.1f} |" for w in result["per_window"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="compare_wfo")
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    args = parser.parse_args(argv)
    try:
        a = json.loads(Path(args.a).read_text())
        b = json.loads(Path(args.b).read_text())
        result = compare(a, b)
    except (OSError, ValueError, KeyError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json
          else render(result, a.get("strategy", "A"), b.get("strategy", "B")), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
