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
from . import council_analytics, crypto50, market_groups, model_registry
from .paper_engine import PaperEngine, PaperEngineError
from .reconcile import reconcile

ACCOUNTS = (("paper", "Reguli matematice", "Reguli simple, piețe ETF/forex/crypto"),
            ("crypto", "Cripto (AI)", "Consiliul AI pe 5 monede"),
            ("ai", "AI unificat", "Consiliul AI pe 13 piețe"),
            ("rls", "Reguli long/short", "Reguli cu short și leverage"),
            ("unic", "Cont unic", "Regulile și consiliul AI amestecate, long și short"))


STALE_AFTER = timedelta(hours=36)
ARCHIVED = {"paper", "crypto", "ai", "rls"}      # conturile vechi, oprite la 1.11.2026 (înlocuite de „unic”)
LOW_BALANCE_USD = 2.0
KEY_LIMIT_USD = 10.0
# Ancora confirmată de proprietar pe 2026-11-01, după ce a încărcat 30 $ la OpenRouter: din cheie
# rămân 37,97 $, când registrul consiliului arăta 0.36590888092 $ cheltuiți. De aici, rămasul scade cu ce se
# adaugă în registru după acel moment. (Ancora anterioară: 8,05 $ pe 2026-10-31.)
ANCHOR_REMAINING_USD = Decimal("37.97")
ANCHOR_LEDGER_USD = Decimal("0.36590888092")
WATCHED = {"Consiliul AI în umbră": "consiliul AI", "Cont unic (virtual)": "contul unic",
           "Arhivă date de piață": "arhivei de date", "Date macro și context (arhivă)": "colectării de date macro",
           "Smart-Money (colector walleturi)": "colectorului smart-money"}
DRAWDOWN_ALERT_PCT = 5.0           # scădere față de vârful contului, de la care se trimite o alertă


def read_account(folder, key: str, title: str, subtitle: str, quotes: dict | None = None) -> dict:
    path = Path(folder) / "paper.sqlite" if folder else None
    base = {"key": key, "title": title, "subtitle": subtitle, "archived": key in ARCHIVED}
    if not path or not path.exists():
        return {**base, "exists": False}
    try:
        engine = PaperEngine.open(path)
    except PaperEngineError:
        return {**base, "exists": False}
    try:
        summary = engine.summary()
        account_row = engine.account()
        settings_rows = engine.journal("runner_settings")
        settings = settings_rows[-1]["payload"] if settings_rows else {}
        daily = engine.journal("daily_run")
        weights = daily[-1]["payload"].get("weights", {}) if daily else {}
        longs = sum(v for v in weights.values() if v > 0)
        shorts = -sum(v for v in weights.values() if v < 0)
        checked = reconcile(engine)
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
            positions.append({"symbol": p["symbol"], "group": market_groups.group_of(p["symbol"]),
                              "quantity": p["quantity"],
                              "avg": p["avg_price"], "last": last,
                              "value": p["quantity"] * last,
                              "pnl": (last - p["avg_price"]) * p["quantity"],
                              "stop": p["stop_loss"]})
        held = {p["symbol"]: p["quantity"] for p in engine.positions()}
        orders = []
        for o in summary["open_orders"]:
            closing = bool(o["reduce_only"]) or (held.get(o["symbol"], 0) > 0 and o["side"] == "SELL"
                                                 and o["quantity"] <= held[o["symbol"]] + 1e-9) \
                or (held.get(o["symbol"], 0) < 0 and o["side"] == "BUY"
                    and o["quantity"] <= -held[o["symbol"]] + 1e-9)
            kind = "închide" if closing else ("long" if o["side"] == "BUY" else "short")
            orders.append({"symbol": o["symbol"], "group": market_groups.group_of(o["symbol"]),
                           "side": o["side"], "quantity": o["quantity"],
                           "status": o["status"], "kind": kind})
        return {**base, "exists": True, "currency": summary["currency"],
                "initial": summary["initial_capital"], "equity": summary["equity"],
                "cash": summary["cash"], "profit": summary["net_profit"],
                "leverage": summary["gross_leverage"], "kill_switch": summary["kill_switch"],
                "kill_reason": summary["kill_reason"], "fills": summary["fills"],
                "history": history[-60:], "positions": positions, "orders": orders,
                "live_equity": live_equity, "live": bool(live_used),
                "peak": account_row["peak_equity"],
                "rules": {"strategy": settings.get("strategy"), "shorts": not settings.get("no_shorts", False),
                          "max_leverage": settings.get("max_leverage"),
                          "target_vol": settings.get("portfolio_vol"),
                          "financing": settings.get("financing")},
                "plan": {"long": longs, "short": shorts, "gross": longs + shorts, "net": longs - shorts},
                "drawdown_pct": 100 * (1 - live_equity / account_row["peak_equity"])
                if account_row["peak_equity"] > 0 and live_equity < account_row["peak_equity"] else 0.0,
                "reconciled": checked["ok"],
                "costs_total": checked["costs"]["total"],
                "last_run": history[-1]["t"] if history else None}
    finally:
        engine.close()


def read_council(folder, balance: dict | None = None, now: datetime | None = None) -> dict:
    path = Path(folder) / "registry.sqlite" if folder else None
    if not path or not path.exists():
        return {"exists": False}
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        days = [r[0] for r in db.execute(
            "SELECT DISTINCT substr(id, 1, 10) d FROM decisions ORDER BY d DESC LIMIT 1")]
        if not days:
            return {"exists": True, "day": None, "markets": [], "costs": read_costs(folder, balance, now)}
        day = days[0]
        markets = []
        for decision_id, symbol, vote, price in db.execute(
                "SELECT id, symbol, vote, price FROM decisions WHERE id LIKE ? ORDER BY symbol",
                (day + ":%",)):
            votes = {agent: v for agent, v in db.execute(
                "SELECT agent, vote FROM votes WHERE decision_id = ? AND stage = 'final'",
                (decision_id,))}
            info = json.loads(db.execute("SELECT meta FROM decisions WHERE id = ?",
                                         (decision_id,)).fetchone()[0] or "{}")
            net = sum({"BUY": 1, "SELL": -1}.get(v, 0) for v in votes.values())
            markets.append({"symbol": symbol, "decision": vote, "price": price, "votes": votes,
                            "net": net, "bot": info.get("bot_signal") or 0,
                            "group": market_groups.group_of(symbol)})
        settled = db.execute("SELECT COUNT(*) FROM decisions WHERE settled_at IS NOT NULL"
                             ).fetchone()[0]
        total = db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    finally:
        db.close()
    registry = DecisionRegistry(path)
    return {"exists": True, "day": day, "markets": markets, "settled": settled,
            "decisions": total, "comparison": registry.comparison(),
            "agents": registry.performance()["agents"], "costs": read_costs(folder, balance, now),
            "models": model_registry.build(path, Path(folder) / "costs.sqlite")["agents"],
            "last_round": last_round(path), "analysis": analysis_summary(path)}


def analysis_summary(path) -> dict:
    """Rezumat scurt al analizei agenților (doar citire) pentru aplicație."""
    try:
        full = council_analytics.analyse(path)
    except Exception:          # analiza nu are voie să strice aplicația
        return {}
    oos = full["out_of_sample"]
    return {"enough_data": full["enough_data"], "note": full["note"],
            "overconfidence": {a: v["overconfidence"] for a, v in full["agents"].items()
                               if v["overconfidence"] is not None},
            "alpha": {k: full["alpha"][k] for k in ("raw", "alpha_next")},
            "oos": {"evaluated": oos["evaluated"], "note": oos.get("note"),
                    "verdict": oos.get("verdict")}}


def last_round(path) -> dict:
    """Starea fiecărui agent în ultima zi analizată: ok/failed și latența, din urma analizelor."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT id, meta FROM decisions ORDER BY id DESC LIMIT 60").fetchall()
    finally:
        db.close()
    if not rows:
        return {}
    day = rows[0][0][:10]
    state: dict = {}
    for decision_id, meta in rows:
        if decision_id[:10] != day:
            continue
        for agent, a in (json.loads(meta or "{}").get("trace") or {}).get("agents", {}).items():
            cell = state.setdefault(agent, {"ok": 0, "failed": 0, "latency": []})
            cell["ok" if a.get("status") == "ok" else "failed"] += 1
            if a.get("latency_s") is not None:
                cell["latency"].append(a["latency_s"])
    return {"day": day, "agents": {k: {"ok": v["ok"], "failed": v["failed"],
                                         "mean_latency_s": sum(v["latency"]) / len(v["latency"]) if v["latency"] else None}
                                   for k, v in state.items()}}


BALANCE_MAX_AGE = timedelta(hours=8)


def live_balance(balance: dict | None, now: datetime) -> float | None:
    """Soldul real de la OpenRouter, dacă citirea e recentă și reușită; altfel None."""
    if not balance or not balance.get("ok") or balance.get("effective_remaining") is None:
        return None
    try:
        age = now - datetime.fromisoformat(balance["time"])
    except (KeyError, ValueError):
        return None
    return float(balance["effective_remaining"]) if timedelta(0) <= age <= BALANCE_MAX_AGE else None


def read_costs(folder, balance: dict | None = None, now: datetime | None = None) -> dict | None:
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
    remaining = float(ANCHOR_REMAINING_USD - (spent - ANCHOR_LEDGER_USD))
    real = live_balance(balance, now or datetime.now(timezone.utc))
    return {"spent": float(spent), "today": float(spent_today), "limit": KEY_LIMIT_USD,
            "remaining": real if real is not None else remaining,
            "source": "openrouter" if real is not None else "estimare",
            "balance_time": balance.get("time") if real is not None else None}


def alerts_from(accounts: list, runs: list | None, now: datetime) -> list:
    """Texte scurte despre ce cere atenție: opriri de siguranță, date vechi, rulări eșuate."""
    found = []
    for a in accounts:
        if not a.get("exists"):
            continue
        if a.get("reconciled") is False:
            found.append(f"{a['title']}: discrepanță contabilă (reconcilierea independentă nu se potrivește)")
        if a["kill_switch"]:
            found.append(f"{a['title']}: oprire de siguranță activă ({a['kill_reason']})")
        if a["key"] not in ARCHIVED and (a.get("drawdown_pct") or 0) >= DRAWDOWN_ALERT_PCT:
            found.append(f"{a['title']}: scădere de {a['drawdown_pct']:.1f}% față de vârf")
        last = a.get("last_run")
        if a["key"] not in ARCHIVED and last and now - datetime.fromisoformat(last) > STALE_AFTER:
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
            quotes: dict | None = None, runs: list | None = None, top50=None,
            balance: dict | None = None, rls=None, unic=None, exposure: dict | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    folders = {"paper": paper, "crypto": crypto, "ai": ai, "rls": rls, "unic": unic}
    prices = (quotes or {}).get("quotes", {})
    accounts = [read_account(folders[k], k, t, s, prices) for k, t, s in ACCOUNTS]
    for account in accounts:
        if account["key"] == "unic" and account.get("exists") and exposure and "error" not in exposure:
            account["exposure"] = exposure
    council = read_council(council, balance, now)
    alerts = alerts_from(accounts, runs, now)
    quotes_time = (quotes or {}).get("time")
    if quotes_time and now - datetime.fromisoformat(quotes_time) > timedelta(hours=6):
        alerts.append("Prețurile de acum sunt mai vechi de 6 ore (feed întârziat)")
    for agent, cell in (council.get("last_round") or {}).get("agents", {}).items() if council.get("exists") else []:
        if cell["failed"]:
            alerts.append(f"Agentul {agent} a eșuat la {cell['failed']} piețe în ultima rundă")
    costs = council.get("costs") if council.get("exists") else None
    if costs and costs["remaining"] < LOW_BALANCE_USD:
        alerts.append(f"Soldul cheii AI e mic: au mai rămas {costs['remaining']:.2f} $. Reîncarc-o.")
    eurusd = prices.get("EURUSD")
    eurron = prices.get("EURRON")
    fx = {"eurusd": float(eurusd[0]), "time": eurusd[1]} if eurusd and eurusd[0] > 0 else None
    if fx and eurron and eurron[0] > 0:
        fx["eurron"] = float(eurron[0])
        fx["usdron"] = fx["eurron"] / fx["eurusd"]
    events = events_from(accounts, council if council.get("exists") else None, now)
    return {"generated": now.isoformat(timespec="minutes"), "events": events, "fx": fx, "groups": market_groups.labels(),
            "top50": crypto50.summary(top50) if top50 and Path(top50).exists() else [],
            "quotes_time": quotes_time, "system": system_status(runs),
            "test": {"start": TEST_START, "end": TEST_END, "report": TEST_REPORT},
            "accounts": accounts, "council": council, "alerts": alerts}


TEST_START = "2026-10-31"
TEST_REPORT = "2026-11-17"


def system_status(runs: list | None) -> list:
    """Ultima rulare programată a fiecărui flux urmărit: nume, rezultat, ora (pentru panoul „Stare sistem”)."""
    latest = {}
    for run in sorted(runs or [], key=lambda r: r.get("createdAt", "")):
        if run.get("event") == "schedule" and run.get("workflowName") in WATCHED:
            latest[run["workflowName"]] = run
    return [{"name": WATCHED[name], "conclusion": run.get("conclusion") or "în curs", "time": run.get("createdAt")}
            for name, run in latest.items()]


DAILY_MOVE_ALERT_PCT = 2.0        # variație zilnică a contului de la care se trimite o notificare
TEST_END = "2026-11-16"


def events_from(accounts: list, council: dict | None, now: datetime) -> list:
    """Evenimente importante, trimise o SINGURĂ dată fiecare (textul le face unice): nu sunt probleme, sunt vești."""
    events = []
    for a in accounts:
        if not a.get("exists") or a["key"] in ARCHIVED:
            continue
        if a.get("fills"):
            events.append(f"{a['title']}: s-au executat primele ordine ({len(a['positions'])} poziții deschise)")
        history = a.get("history") or []
        if len(history) >= 2 and history[-2]["equity"] > 0:
            change = 100 * (history[-1]["equity"] / history[-2]["equity"] - 1)
            if abs(change) >= DAILY_MOVE_ALERT_PCT:
                events.append(f"{a['title']}: variație zilnică {change:+.1f}% (valoare {history[-1]['equity']:,.0f} "
                              f"{a['currency']}) la {history[-1]['t'][:10]}")
    if council and council.get("exists") and council.get("day"):
        costs = council.get("costs") or {}
        line = f"Consiliul AI {council['day']}: {len(council.get('markets', []))} piețe votate"
        if costs:
            line += f", cost azi {costs.get('today', 0):.2f} $, rămas {costs.get('remaining', 0):.2f} $"
        events.append(line)
    if now.date().isoformat() >= TEST_END:
        events.append("Testul de 16 zile s-a încheiat: raportul final urmează (17.11)")
    return events


def status_summary(data: dict) -> dict:
    """JSON mic, plat, pentru senzori (de exemplu Home Assistant): o valoare simplă pe cont."""
    accounts = {}
    for a in data["accounts"]:
        if not a.get("exists"):
            continue
        value = a["live_equity"] if a["live"] else a["equity"]
        accounts[a["key"]] = {"equity": round(value, 2), "currency": a["currency"],
                              "return_pct": round(100 * (value / a["initial"] - 1), 3),
                              "drawdown_pct": round(a["drawdown_pct"], 3),
                              "positions": len(a["positions"]), "orders": len(a["orders"]),
                              "kill_switch": a["kill_switch"], "reconciled": a["reconciled"]}
    costs = (data["council"] or {}).get("costs") or {}
    return {"generated": data["generated"], "ok": not data["alerts"], "alerts": data["alerts"],
            "events": data.get("events", []),
            "accounts": accounts, "ai_balance_usd": costs.get("remaining"),
            "ai_spent_today_usd": costs.get("today")}


def render(data: dict, template: str) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    if "/*DATA*/null" not in template:
        raise ValueError("Șablonul nu are locul pentru date (/*DATA*/null)")
    return template.replace("/*DATA*/null", payload, 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dashboard")
    for name in ("paper", "crypto", "ai", "council", "rls", "unic"):
        parser.add_argument(f"--{name}")
    parser.add_argument("--quotes", help="JSON de la quotes_snapshot (prețuri de acum)")
    parser.add_argument("--runs", help="JSON de la `gh run list --json workflowName,event,conclusion,createdAt`")
    parser.add_argument("--balance", help="JSON de la openrouter_balance (soldul real al cheii)")
    parser.add_argument("--exposure", help="JSON de la exposure (expuneri corelate, contul unic)")
    parser.add_argument("--top50", help="folderul cu CSV-urile top 50 cripto (arhiva)")
    parser.add_argument("--template", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--status-json", help="scrie și un JSON mic pentru senzori (Home Assistant)")
    args = parser.parse_args(argv)
    try:
        quotes = json.loads(Path(args.quotes).read_text()) if args.quotes and Path(args.quotes).exists() else None
        runs = json.loads(Path(args.runs).read_text()) if args.runs and Path(args.runs).exists() else None
        balance = json.loads(Path(args.balance).read_text()) if args.balance and Path(args.balance).exists() else None
        exposure = json.loads(Path(args.exposure).read_text()) if args.exposure and Path(args.exposure).exists() else None
        data = collect(args.paper, args.crypto, args.ai, args.council, quotes=quotes, runs=runs,
                       top50=args.top50, balance=balance, rls=args.rls, unic=args.unic, exposure=exposure)
        html = render(data, Path(args.template).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    Path(args.out).write_text(html, encoding="utf-8")
    if args.status_json:
        Path(args.status_json).write_text(json.dumps(status_summary(data), indent=2,
                                                     ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
