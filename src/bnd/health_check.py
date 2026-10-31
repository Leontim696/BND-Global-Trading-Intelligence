"""Daily health check of the virtual paper account. Read-only.

Problems reported: the account has not run for ``max_age_hours``, the
kill switch is active, the last daily run's workflow failed, or the
account file cannot be read. No account yet is not a problem: it waits
for the owner's starting capital.

    python -m src.bnd.health_check --state paper.sqlite --last-run-conclusion success
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .paper_engine import PaperEngine, PaperEngineError


def check(state_path, now: datetime, max_age_hours: float = 50,
          last_run_conclusion: str | None = None) -> dict:
    problems, summary = [], {}
    if last_run_conclusion not in (None, "", "success", "skipped"):
        problems.append(f"Ultima rulare zilnică a botului s-a terminat cu: {last_run_conclusion}")
    if not Path(state_path).exists():
        return {"ok": not problems, "account": False, "problems": problems,
                "summary": {"note": "Nu există încă un cont virtual (așteaptă suma de pornire)."}}
    try:
        engine = PaperEngine.open(state_path)
    except (PaperEngineError, OSError, ValueError, sqlite3.Error) as exc:
        return {"ok": False, "account": True, "summary": {},
                "problems": problems + [f"Contul nu poate fi citit: {exc}"]}
    try:
        account, runs = engine.account(), engine.journal("daily_run")
        equity = engine.equity()
        summary = {"equity": round(equity, 2), "start": account["initial_capital"],
                   "currency": account["currency"], "positions": len(engine.positions()),
                   "last_run": runs[-1]["payload"]["time"] if runs else None}
        if account["kill_switch"]:
            problems.append(f"Oprirea de siguranță este activă: {account['kill_reason']}")
        if not runs:
            problems.append("Contul există, dar nu a rulat nicio zi.")
        else:
            last = datetime.fromisoformat(runs[-1]["payload"]["time"])
            if now - last > timedelta(hours=max_age_hours):
                problems.append(f"Botul nu a mai rulat din {last:%Y-%m-%d %H:%M} UTC "
                                f"(peste {max_age_hours:.0f} de ore).")
    finally:
        engine.close()
    return {"ok": not problems, "account": True, "problems": problems, "summary": summary}


def render(result: dict) -> str:
    lines = ["# Verificarea botului virtual", ""]
    lines.append("Totul este în regulă." if result["ok"] else "**Probleme găsite:**")
    lines += [f"- {p}" for p in result["problems"]]
    s = result["summary"]
    if "equity" in s:
        lines += ["", f"Capital: {s['equity']:,.2f} {s['currency']} (start {s['start']:,.2f}), "
                      f"poziții deschise: {s['positions']}, ultima rulare: {s['last_run']}"]
    elif s.get("note"):
        lines += ["", s["note"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="health_check")
    parser.add_argument("--state", required=True)
    parser.add_argument("--max-age-hours", type=float, default=50)
    parser.add_argument("--last-run-conclusion")
    parser.add_argument("--json", help="also write the result here")
    args = parser.parse_args(argv)
    result = check(args.state, datetime.now(timezone.utc), args.max_age_hours,
                   args.last_run_conclusion)
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    sys.stdout.write(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
