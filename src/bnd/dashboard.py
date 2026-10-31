"""Datele pentru aplicația de pe telefon: cele trei conturi virtuale și consiliul AI.

Citește (doar citire) conturile SQLite și registrul consiliului din folderele
date și scrie un singur JSON, apoi îl pune în șablonul HTML al aplicației.
Nimic de aici nu tranzacționează și nu cheamă servicii externe.

    python -m src.bnd.dashboard --paper d1 --crypto d2 --ai d3 --council d4 \\
        --template src/bnd/dashboard_template.html --out aplicatie.html
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .paper_engine import PaperEngine, PaperEngineError

ACCOUNTS = (("paper", "Reguli matematice", "Strategie: regime_switch, piețe ETF/forex/crypto"),
            ("crypto", "Cripto (AI)", "Consiliul AI pe 5 monede"),
            ("ai", "AI unificat", "Consiliul AI pe 13 piețe"))


def read_account(folder, key: str, title: str, subtitle: str) -> dict:
    path = Path(folder) / "paper.sqlite" if folder else None
    base = {"key": key, "title": title, "subtitle": subtitle}
    if not path or not path.exists():
        return {**base, "exists": False}
    try:
        engine = PaperEngine.open(path)
    except PaperEngineError:
        return {**base, "exists": False}
    try:
        summary = engine.summary()
        history = [{"t": e["payload"]["time"], "equity": e["payload"]["equity"]}
                   for e in engine.journal("daily_run")]
        positions = []
        for p in engine.positions():
            mark = engine.mark(p["symbol"])
            last = mark["price"] if mark else p["avg_price"]
            positions.append({"symbol": p["symbol"], "quantity": p["quantity"],
                              "avg": p["avg_price"], "last": last,
                              "value": p["quantity"] * last,
                              "pnl": (last - p["avg_price"]) * p["quantity"],
                              "stop": p["stop_loss"]})
        orders = [{"symbol": o["symbol"], "side": o["side"], "quantity": o["quantity"],
                   "status": o["status"]} for o in summary["open_orders"]]
        return {**base, "exists": True, "currency": summary["currency"],
                "initial": summary["initial_capital"], "equity": summary["equity"],
                "cash": summary["cash"], "profit": summary["net_profit"],
                "leverage": summary["gross_leverage"], "kill_switch": summary["kill_switch"],
                "kill_reason": summary["kill_reason"], "fills": summary["fills"],
                "history": history[-60:], "positions": positions, "orders": orders}
    finally:
        engine.close()


def read_council(folder) -> dict:
    path = Path(folder) / "registry.sqlite" if folder else None
    if not path or not path.exists():
        return {"exists": False}
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        days = [r[0] for r in db.execute(
            "SELECT DISTINCT substr(id, 1, 10) d FROM decisions ORDER BY d DESC LIMIT 1")]
        if not days:
            return {"exists": True, "day": None, "markets": []}
        day = days[0]
        markets = []
        for decision_id, symbol, vote, price in db.execute(
                "SELECT id, symbol, vote, price FROM decisions WHERE id LIKE ? ORDER BY symbol",
                (day + ":%",)):
            votes = {agent: v for agent, v in db.execute(
                "SELECT agent, vote FROM votes WHERE decision_id = ? AND stage = 'final'",
                (decision_id,))}
            markets.append({"symbol": symbol, "decision": vote, "price": price, "votes": votes})
        settled = db.execute("SELECT COUNT(*) FROM decisions WHERE settled_at IS NOT NULL"
                             ).fetchone()[0]
        total = db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        return {"exists": True, "day": day, "markets": markets, "settled": settled,
                "decisions": total}
    finally:
        db.close()


def collect(paper=None, crypto=None, ai=None, council=None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    folders = {"paper": paper, "crypto": crypto, "ai": ai}
    return {"generated": now.isoformat(timespec="minutes"),
            "accounts": [read_account(folders[k], k, t, s) for k, t, s in ACCOUNTS],
            "council": read_council(council)}


def render(data: dict, template: str) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    if "/*DATA*/null" not in template:
        raise ValueError("Șablonul nu are locul pentru date (/*DATA*/null)")
    return template.replace("/*DATA*/null", payload, 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dashboard")
    for name in ("paper", "crypto", "ai", "council"):
        parser.add_argument(f"--{name}")
    parser.add_argument("--template", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        data = collect(args.paper, args.crypto, args.ai, args.council)
        html = render(data, Path(args.template).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    Path(args.out).write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
