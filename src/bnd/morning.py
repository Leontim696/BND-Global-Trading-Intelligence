"""Rezumatul de dimineață pentru telefon: ce s-a întâmplat peste noapte și ce urmează azi.

Se construiește din aceleași date ca aplicația (conturile virtuale, registrul consiliului,
costuri, rulări), fără apeluri AI și fără să tranzacționeze. Text scurt în română, ore în ora
Germaniei. Se trimite prin ntfy (workflow-ul `dimineata.yml`) sau se afișează.

    python -m src.bnd.morning --paper D1 --crypto D2 --ai D3 --council D4 [--send]
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import dashboard, notify
from .paper_engine import PaperEngine, PaperEngineError

BERLIN = ZoneInfo("Europe/Berlin")
TEST_START = datetime(2026, 10, 31, tzinfo=timezone.utc).date()
TEST_DAYS = 16
OVERNIGHT = timedelta(hours=14)
SCHEDULE_UTC = [("21:40", "consiliul AI votează pe 13 piețe (plătit, ~0,35 $)"),
                ("22:10", "contul Cripto AI citește voturile"),
                ("22:15", "contul AI unificat citește voturile"),
                ("22:23", "contul Reguli face pasul zilnic")]
MILESTONES = {
    "2026-11-05": "se închid primele decizii ale consiliului (la 5 zile)",
    "2026-11-06": "primești comparația consiliului cu botul pe reguli (dimineață)",
    "2026-11-16": "ultima zi a testului de 16 zile",
    "2026-11-17": "raportul final al testului",
}


def _local(utc_text: str) -> str:
    return datetime.fromisoformat(utc_text).astimezone(BERLIN).strftime("%H:%M")


def overnight_fills(folder, now: datetime) -> list:
    path = Path(folder) / "paper.sqlite" if folder else None
    if not path or not path.exists():
        return []
    try:
        engine = PaperEngine.open(path)
    except PaperEngineError:
        return []
    try:
        since = now - OVERNIGHT
        return [f for f in engine.fills() if datetime.fromisoformat(f["time"]) >= since]
    finally:
        engine.close()


def day_change(account: dict) -> float | None:
    history = account.get("history") or []
    if len(history) < 2:
        return None
    previous = history[-2]["equity"]
    current = account["live_equity"] if account.get("live") else account["equity"]
    return 100 * (current / previous - 1) if previous else None


def council_lines(council: dict) -> list:
    if not council.get("exists") or not council.get("day"):
        return ["Consiliul: nicio rundă încă."]
    moves = []
    for m in council["markets"]:
        votes = m["votes"].values()
        net = sum({"BUY": 1, "SELL": -1}.get(v, 0) for v in votes)
        if net:
            moves.append(f"{m['symbol']} {'cumpără' if net > 0 else 'vinde'} ({abs(net)} net)")
    text = f"Consiliul ({council['day']}): {len(council['markets'])} piețe"
    if moves:
        shown = moves[:8]
        text += f", {len(moves)} cu direcție: " + ", ".join(shown) + (f" (+{len(moves) - 8} altele)" if len(moves) > 8 else "")
    else:
        text += ", toți pe HOLD"
    failed = [a for a, c in (council.get("last_round") or {}).get("agents", {}).items() if c["failed"]]
    if failed:
        text += f". Agenți cu eșecuri: {', '.join(failed)}"
    return [text + "."]


def plans(now: datetime, council: dict) -> list:
    today = now.astimezone(BERLIN).date()
    day_no = (now.date() - TEST_START).days + 1
    lines = [f"Ziua {min(max(day_no, 0), TEST_DAYS)} din {TEST_DAYS} a testului."]
    for hhmm, what in SCHEDULE_UTC:
        local = datetime.fromisoformat(f"{now.date().isoformat()}T{hhmm}:00+00:00").astimezone(BERLIN)
        lines.append(f"- {local.strftime('%H:%M')}: {what}")
    lines.append("- din oră în oră: rapoarte, prețuri, aplicația și verificarea de sănătate")
    if str(now.date()) in MILESTONES:
        lines.append("Azi: " + MILESTONES[str(now.date())] + ".")
    costs = council.get("costs") if council.get("exists") else None
    if costs and costs["spent"] > 0 and costs["today"] > 0:
        days = costs["remaining"] / max(costs["today"], 0.05)
        lines.append(f"Soldul cheii AI ({costs['remaining']:.2f} $) ajunge pentru ~{int(days)} zile la ritmul de ieri.")
    del today
    return lines


def build(paper=None, crypto=None, ai=None, council=None, now: datetime | None = None,
          quotes=None, runs=None) -> dict:
    now = now or datetime.now(timezone.utc)
    data = dashboard.collect(paper, crypto, ai, council, now, quotes, runs)
    folders = {"paper": paper, "crypto": crypto, "ai": ai}
    fx = data.get("fx")
    rate = fx["eurusd"] if fx else None
    lines = ["Peste noapte:"]
    if rate is not None:
        header = f"Curs EUR/USD: {rate:.4f} (1 € = {rate:.2f} $)"
        if fx.get("eurron"):
            header += f"; EUR/RON: {fx['eurron']:.4f}; USD/RON: {fx['usdron']:.4f}"
        lines = [header, "Peste noapte:"]
    for account in data["accounts"]:
        if not account["exists"]:
            lines.append(f"- {account['title']}: nu există încă.")
            continue
        value = account["live_equity"] if account["live"] else account["equity"]
        change = day_change(account)
        move = "" if change is None else f", {change:+.2f}% față de ultima rulare"
        fills = overnight_fills(folders[account["key"]], now)
        executed = ""
        if fills:
            shown = [f"{'cumpărat' if f['quantity'] > 0 else 'vândut'} {f['symbol']}" for f in fills[:4]]
            executed = "; executat: " + ", ".join(shown) + (f" (+{len(fills) - 4})" if len(fills) > 4 else "")
        euro = f" ≈ {value / rate:,.0f} €," if rate and account["currency"] == "USD" else ""
        if rate and fx.get("usdron") and account["currency"] == "USD":
            euro += f" ≈ {value * fx['usdron']:,.0f} lei,"
        lines.append(f"- {account['title']}: {value:,.0f} {account['currency']}{euro} "
                     f"({100 * (value / account['initial'] - 1):+.2f}% de la start{move}), "
                     f"{len(account['positions'])} poziții, {len(account['orders'])} comenzi în așteptare{executed}")
    lines += council_lines(data["council"])
    costs = data["council"].get("costs") if data["council"].get("exists") else None
    if costs:
        lines.append(f"Cost AI ieri-azi: {costs['today']:.2f} $; sold cheie: {costs['remaining']:.2f} $.")
    lines.append("Alerte: " + ("niciuna." if not data["alerts"] else "; ".join(data["alerts"]) + "."))
    lines += ["", "Planuri azi (ora Germaniei):"] + plans(now, data["council"])
    day_no = min(max((now.date() - TEST_START).days + 1, 1), TEST_DAYS)
    return {"title": f"BND: dimineața, ziua {day_no}/{TEST_DAYS}", "message": "\n".join(lines)[:2900],
            "alerts": data["alerts"]}


def main(argv=None, sender=notify.send) -> int:
    parser = argparse.ArgumentParser(prog="morning")
    for name in ("paper", "crypto", "ai", "council"):
        parser.add_argument(f"--{name}")
    parser.add_argument("--quotes")
    parser.add_argument("--runs")
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    try:
        quotes = json.loads(Path(args.quotes).read_text()) if args.quotes and Path(args.quotes).exists() else None
        runs = json.loads(Path(args.runs).read_text()) if args.runs and Path(args.runs).exists() else None
        result = build(args.paper, args.crypto, args.ai, args.council, quotes=quotes, runs=runs)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    print(result["title"] + "\n" + result["message"])
    if args.send:
        topic = os.environ.get("NTFY_TOPIC", "").strip()
        if not topic:
            print("NTFY_TOPIC nu e setat: nu se trimite nimic.")
            return 0
        try:
            sender(topic, result["title"], result["message"], "default")
        except notify.NotifyError as exc:
            print("Notificarea nu a plecat:", exc, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
