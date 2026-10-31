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
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .decision_registry import DecisionRegistry
from .paper_engine import PaperEngine, PaperEngineError

ACCOUNTS = (("paper", "Reguli matematice", "Strategie: regime_switch, piețe ETF/forex/crypto"),
            ("crypto", "Cripto (AI)", "Consiliul AI pe 5 monede"),
            ("ai", "AI unificat", "Consiliul AI pe 13 piețe"))


STALE_AFTER = timedelta(hours=36)
LOW_BALANCE_USD = 2.0
KEY_LIMIT_USD = 10.0
# Ancora confirmată de proprietar pe 2026-10-31: din cheie mai rămâneau 8,05 $,
# când registrul consiliului arăta 0,2838356 $ cheltuiți. De aici, rămasul scade
# cu ce se adaugă în registru după acel moment.
ANCHOR_REMAINING_USD = Decimal("8.05")
ANCHOR_LEDGER_USD = Decimal("0.2838356")
WATCHED = {"Consiliul AI în umbră": "consiliul AI", "Bot virtual zilnic": "botul pe reguli",
           "Bot cripto virtual (AI)": "botul de cripto", "Bot AI unificat (virtual)": "botul AI unificat"}


def read_account(folder, key: str, title: str, subtitle: str, quotes: dict | None = None) -> dict:
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
        positions, live_equity, live_used = [], summary["equity"], 0
        for p in engine.positions():
            mark = engine.mark(p["symbol"])
            close = mark["price"] if mark else p["avg_price"]
            last = close
            quote = (quotes or {}).get(p["symbol"])
            if quote and quote[0] > 0:
                last = float(quote[0])
                live_equity += p["quantity"] * (last - close)
                live_used += 1
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
                "history": history[-60:], "positions": positions, "orders": orders,
                "live_equity": live_equity, "live": bool(live_used),
                "last_run": history[-1]["t"] if history else None}
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
            return {"exists": True, "day": None, "markets": [], "costs": read_costs(folder)}
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
    finally:
        db.close()
    registry = DecisionRegistry(path)
    return {"exists": True, "day": day, "markets": markets, "settled": settled,
            "decisions": total, "comparison": registry.comparison(),
            "agents": registry.performance()["agents"], "costs": read_costs(folder)}


def read_costs(folder) -> dict | None:
    """Cât a cheltuit consiliul (registrul de costuri) și cât a rămas din cheia de 10 $."""
    path = Path(folder) / "costs.sqlite"
    if not path.exists():
        return None
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT cost_usd, timestamp FROM usage_records").fetchall()
    finally:
        db.close()
    spent = sum(Decimal(cost) for cost, _ in rows)
    today = datetime.now(timezone.utc).date().isoformat()
    spent_today = sum(Decimal(cost) for cost, stamp in rows if stamp[:10] == today)
    remaining = ANCHOR_REMAINING_USD - (spent - ANCHOR_LEDGER_USD)
    return {"spent": float(spent), "today": float(spent_today), "limit": KEY_LIMIT_USD,
            "remaining": float(remaining)}


def alerts_from(accounts: list, runs: list | None, now: datetime) -> list:
    """Texte scurte despre ce cere atenție: opriri de siguranță, date vechi, rulări eșuate."""
    found = []
    for a in accounts:
        if not a.get("exists"):
            continue
        if a["kill_switch"]:
            found.append(f"{a['title']}: oprire de siguranță activă ({a['kill_reason']})")
        last = a.get("last_run")
        if last and now - datetime.fromisoformat(last) > STALE_AFTER:
            found.append(f"{a['title']}: ultima rulare e mai veche de 36 de ore")
    latest = {}
    for run in sorted(runs or [], key=lambda r: r.get("createdAt", "")):
        if run.get("event") == "schedule":
            latest[run.get("workflowName")] = run
    for name, run in latest.items():
        if name in WATCHED and run.get("conclusion") not in ("success", "", None, "skipped"):
            found.append(f"Ultima rulare programată a {WATCHED[name]} a eșuat ({run['conclusion']})")
    return found


def collect(paper=None, crypto=None, ai=None, council=None, now: datetime | None = None,
            quotes: dict | None = None, runs: list | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    folders = {"paper": paper, "crypto": crypto, "ai": ai}
    prices = (quotes or {}).get("quotes", {})
    accounts = [read_account(folders[k], k, t, s, prices) for k, t, s in ACCOUNTS]
    council = read_council(council)
    alerts = alerts_from(accounts, runs, now)
    costs = council.get("costs") if council.get("exists") else None
    if costs and costs["remaining"] < LOW_BALANCE_USD:
        alerts.append(f"Soldul cheii AI e mic: au mai rămas {costs['remaining']:.2f} $. Reîncarc-o.")
    return {"generated": now.isoformat(timespec="minutes"),
            "quotes_time": (quotes or {}).get("time"),
            "accounts": accounts, "council": council, "alerts": alerts}


def render(data: dict, template: str) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    if "/*DATA*/null" not in template:
        raise ValueError("Șablonul nu are locul pentru date (/*DATA*/null)")
    return template.replace("/*DATA*/null", payload, 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dashboard")
    for name in ("paper", "crypto", "ai", "council"):
        parser.add_argument(f"--{name}")
    parser.add_argument("--quotes", help="JSON de la quotes_snapshot (prețuri de acum)")
    parser.add_argument("--runs", help="JSON de la `gh run list --json workflowName,event,conclusion,createdAt`")
    parser.add_argument("--template", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        quotes = json.loads(Path(args.quotes).read_text()) if args.quotes and Path(args.quotes).exists() else None
        runs = json.loads(Path(args.runs).read_text()) if args.runs and Path(args.runs).exists() else None
        data = collect(args.paper, args.crypto, args.ai, args.council, quotes=quotes, runs=runs)
        html = render(data, Path(args.template).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    Path(args.out).write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
