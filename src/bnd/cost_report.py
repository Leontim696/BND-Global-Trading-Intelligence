"""AI cost report: what each model and agent cost, per day and in total.

Reads the usage records written by ``cost_storage.SQLiteCostStorage`` and,
optionally, the ``ai_cache.ResponseCache`` statistics (money saved by not
asking the same question twice). Read-only.

    python -m src.bnd.cost_report --db ai_costs.sqlite [--cache ai_cache.sqlite]
"""

import argparse
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

from .ai_cache import ResponseCache


def usage(db_path) -> dict:
    """Totals by model, by agent and by UTC day from the usage records."""
    if not Path(db_path).exists():
        raise ValueError(f"No cost database at {db_path}")
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT agent, model, input_tokens, output_tokens, cost_usd,"
                          " timestamp FROM usage_records ORDER BY timestamp").fetchall()
    finally:
        db.close()
    report = {"calls": len(rows), "total_usd": Decimal("0"), "input_tokens": 0,
              "output_tokens": 0, "by_model": {}, "by_agent": {}, "by_day": {}}
    for agent, model, tokens_in, tokens_out, cost, timestamp in rows:
        cost = Decimal(cost)
        report["total_usd"] += cost
        report["input_tokens"] += tokens_in
        report["output_tokens"] += tokens_out
        for group, name in (("by_model", model), ("by_agent", agent),
                            ("by_day", timestamp[:10])):
            entry = report[group].setdefault(name, {"calls": 0, "usd": Decimal("0")})
            entry["calls"] += 1
            entry["usd"] += cost
    return report


def render(report: dict, cache: dict | None = None) -> str:
    lines = ["# AI cost report", "",
             f"- Calls: {report['calls']}, total ${report['total_usd']:.4f}",
             f"- Tokens: {report['input_tokens']:,} in, {report['output_tokens']:,} out"]
    if cache is not None:
        lines.append(f"- Cache: {cache['hits']} hits, {cache['misses']} misses, "
                     f"saved ${Decimal(cache['saved_usd']):.4f}")
    for title, group in (("By model", "by_model"), ("By agent", "by_agent"),
                         ("By day (UTC)", "by_day")):
        lines += ["", f"## {title}", "", "| Name | Calls | USD |", "|---|---:|---:|"]
        items = sorted(report[group].items(),
                       key=lambda kv: kv[0] if group == "by_day" else -kv[1]["usd"])
        lines += [f"| {name} | {e['calls']} | {e['usd']:.4f} |" for name, e in items]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cost_report")
    parser.add_argument("--db", required=True, help="cost_storage SQLite file")
    parser.add_argument("--cache", help="ai_cache SQLite file")
    args = parser.parse_args(argv)
    try:
        report = usage(args.db)
        cache = ResponseCache(args.cache).stats() if args.cache else None
    except (ValueError, sqlite3.Error) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    print(render(report, cache), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
