"""Raport în română despre contul virtual, pentru citit pe telefon.

Citește contul (doar citire) și, pentru pozițiile deschise, ultimul preț de la
Yahoo, ca raportul din timpul zilei să arate valoarea de acum, nu doar cea de
la ultima închidere. Fără prețuri noi, folosește ultima închidere și spune asta.
Nimic de aici nu tranzacționează.

    python -m src.bnd.report_card --state paper.sqlite --out raport.md [--json raport.json]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote as url_quote
from urllib.request import Request, urlopen

from .health_check import check
from .market_data import YAHOO_CHART_URL
from .paper_engine import PaperEngine, PaperEngineError
from .calendars import open_sessions
from .scenarios import run_scenarios
from .universe import select as select_markets

PERIOD_DAYS = 30                  # testul a fost prelungit de la 16 la 30 de zile (2.11)


BINANCE_TICKER_URL = "https://data-api.binance.vision/api/v3/ticker/24hr?symbol="


def is_binance_pair(symbol: str) -> bool:
    """Perechile Binance (de ex. LINKUSDT) nu există pe Yahoo: prețul lor vine de la Binance."""
    return symbol.endswith("USDT") and symbol.isalnum() and symbol.isupper()


def fetch_binance_quote(symbol: str, timeout: float = 20.0):
    """(preț, ora) de acum pentru o pereche Binance, din datele publice; None dacă nu se poate."""
    request = Request(BINANCE_TICKER_URL + url_quote(symbol, safe=""),
                      headers={"User-Agent": "Mozilla/5.0 (BND research report)"}, method="GET")
    try:
        # Reviewed: fixed https URL constant, simbol validat (litere mari și cifre).
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            data = json.loads(response.read(200_000))
        price, stamp = float(data["lastPrice"]), int(data["closeTime"]) / 1000
    except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
        return None
    if price <= 0:
        return None
    return price, datetime.fromtimestamp(stamp, timezone.utc)


def fetch_quote(symbol: str, timeout: float = 20.0):
    """(preț, ora) cel mai recent: Binance pentru perechile USDT, Yahoo pentru rest; None dacă nu se poate."""
    if is_binance_pair(symbol):
        return fetch_binance_quote(symbol, timeout)
    request = Request(YAHOO_CHART_URL + url_quote(symbol, safe="") + "?range=1d&interval=1d",
                      headers={"User-Agent": "Mozilla/5.0 (BND research report)"}, method="GET")
    try:
        # Reviewed: fixed https URL constant.
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            meta = json.loads(response.read(2_000_000))["chart"]["result"][0]["meta"]
        price, stamp = float(meta["regularMarketPrice"]), int(meta["regularMarketTime"])
    except (URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    if price <= 0:
        return None
    return price, datetime.fromtimestamp(stamp, timezone.utc)


def quotes_for(names, fetch=fetch_quote, universe="etf") -> dict:
    """Prețuri de acum pentru piețele cu nume dat (nume BND -> simbol Yahoo)."""
    symbols = {m.name: m.symbol for m in select_markets(universe=universe)}
    found = {}
    for name in names:
        if name in symbols and (value := fetch(symbols[name])) is not None:
            found[name] = value
    return found


def build(state_path, now: datetime, quotes: dict | None = None) -> dict:
    """Datele raportului, sau o eroare clară dacă nu există cont."""
    quotes = quotes or {}
    health = check(state_path, now)
    if not Path(state_path).exists():
        return {"has_account": False, "health": health, "time": now.isoformat()}
    engine = PaperEngine.open(state_path)
    try:
        account, summary = engine.account(), engine.summary()
        started = datetime.fromisoformat(account["created_at"])
        runs = engine.journal("daily_run")
        positions = []
        live_value = 0.0
        for position in engine.positions():
            name, quantity = position["symbol"], position["quantity"]
            mark = engine.mark(name)["price"]
            live = quotes.get(name)
            price = live[0] if live else mark
            positions.append({
                "market": name, "quantity": quantity, "avg_price": position["avg_price"],
                "last_close": mark, "price_now": price, "is_live": bool(live),
                "value_now": quantity * price, "pnl_now": (price - position["avg_price"]) * quantity,
                "change_today_pct": 100 * (price / mark - 1) if mark else 0.0,
                "stop_loss": position["stop_loss"],
            })
            live_value += quantity * price
        equity_close = summary["equity"]
        equity_now = account["cash"] + live_value if positions else equity_close
        since = now - timedelta(hours=24)
        fills = [f for f in engine.fills() if datetime.fromisoformat(f["time"]) >= since]
        financing = sum(e["payload"]["amount"] for e in engine.journal("financing"))
        scenarios = run_scenarios(engine)
        return {
            "has_account": True, "time": now.isoformat(), "currency": account["currency"],
            "start": account["initial_capital"], "day": (now - started).days + 1,
            "equity_close": equity_close, "equity_now": equity_now,
            "cash": account["cash"], "gross_leverage": summary["gross_leverage"],
            "positions": positions, "live_prices": sum(p["is_live"] for p in positions),
            "pending_orders": [{"market": o["symbol"], "side": o["side"],
                                "quantity": o["quantity"]} for o in summary["open_orders"]],
            "fills_24h": [{"market": f["symbol"], "quantity": f["quantity"], "price": f["price"],
                           "reason": f["reason"]} for f in fills],
            "open_sessions": open_sessions(now),
            "kill_switch": summary["kill_switch"], "kill_reason": summary["kill_reason"],
            "last_run": runs[-1]["payload"]["time"] if runs else None,
            "runs": len(runs), "financing_paid": financing,
            "worst_scenario": scenarios[0] if scenarios and summary["positions"] else None,
            "health": health,
        }
    except PaperEngineError as exc:
        return {"has_account": False, "health": {"ok": False, "problems": [str(exc)]},
                "time": now.isoformat()}
    finally:
        engine.close()


def _money(value: float, currency: str) -> str:
    return f"{value:,.2f} {currency}".replace(",", " ")


def _pct(value: float) -> str:
    return f"{value:+.2f}%".replace(".", ",")


def render(report: dict) -> str:
    when = report["time"][:16].replace("T", " ")
    lines = [f"# Raport bot virtual, {when} UTC", ""]
    if not report["has_account"]:
        lines += ["Contul virtual nu există încă sau nu poate fi citit.", ""]
        lines += [f"- {p}" for p in report["health"]["problems"]]
        return "\n".join(lines) + "\n"
    c = report["currency"]
    start, now_value, close = report["start"], report["equity_now"], report["equity_close"]
    ratio = 100 * (now_value / start - 1)
    lines += [
        (f"**Ziua {report['day']} din {PERIOD_DAYS}** de test în timp real, cu bani virtuali."
         if report["day"] <= PERIOD_DAYS else
         f"**Perioada de test de {PERIOD_DAYS} zile s-a încheiat** (ziua {report['day']}); "
         "contul continuă să ruleze, cu bani virtuali."),
        "",
        "## Pe scurt",
        f"- Valoarea contului acum: **{_money(now_value, c)}** ({_pct(ratio)} față de start, "
        f"{_money(start, c)})"
        + ("" if report["live_prices"] or not report["positions"] else " (prețuri de la ultima închidere)"),
        f"- La ultima închidere: {_money(close, c)}; bani liberi: {_money(report['cash'], c)}",
        f"- Poziții deschise: {len(report['positions'])}; ordine pregătite pentru mâine: "
        f"{len(report['pending_orders'])}",
        "- Piețe deschise acum: " + (", ".join(report["open_sessions"]) or "niciuna"),
        "- Oprirea de siguranță: " + (f"**ACTIVĂ** ({report['kill_reason']})" if report["kill_switch"]
                                     else "oprită (totul în regulă)"),
        "- Ultima rulare a botului: " + (report["last_run"][:16].replace("T", " ") + " UTC"
                                         if report["last_run"] else "încă niciuna"),
    ]
    if report["gross_leverage"]:
        lines.append(f"- Levier folosit: {report['gross_leverage']:.2f}×")
    if report["financing_paid"]:
        lines.append(f"- Dobândă plătită până acum: {_money(report['financing_paid'], c)}")
    lines += ["", "## Pozițiile"]
    if report["positions"]:
        lines += ["", "| Piață | Valoare | Câștig/pierdere | Azi | Stop |", "|---|---:|---:|---:|---:|"]
        for p in sorted(report["positions"], key=lambda p: -abs(p["value_now"])):
            side = "scurt " if p["quantity"] < 0 else ""
            stop = f"{p['stop_loss']:.2f}" if p["stop_loss"] else "–"
            lines.append(f"| {side}{p['market']} | {_money(p['value_now'], c)} | "
                         f"{_money(p['pnl_now'], c)} | {_pct(p['change_today_pct']) if p['is_live'] else 'fără preț live'} | {stop} |")
    else:
        lines += ["", "Nicio poziție deschisă: banii stau în numerar."]
    if report["pending_orders"]:
        lines += ["", "## Ordine pregătite (se execută la deschiderea următoare)", ""]
        lines += [f"- {o['side'].lower()} {o['market']}, {abs(o['quantity']):.2f} bucăți"
                  for o in report["pending_orders"]]
    if report["fills_24h"]:
        lines += ["", "## Executate în ultimele 24 de ore", ""]
        lines += [f"- {f['market']}: {f['quantity']:+.2f} la {f['price']:.2f} ({f['reason']})"
                  for f in report["fills_24h"]]
    worst = report["worst_scenario"]
    if worst:
        lines += ["", "## Riscul", "",
                  f"Cel mai rău scenariu testat ({worst['description']}): "
                  f"{_pct(worst['change_pct'])} din cont"
                  + ("; ar declanșa oprirea de siguranță." if worst["beyond_kill_switch"]
                     else "; nu ar declanșa oprirea de siguranță.")]
    if not report["health"]["ok"]:
        lines += ["", "## Atenție", ""] + [f"- {p}" for p in report["health"]["problems"]]
    if report["currency"] == "EUR":
        note = ("Bani virtuali. Prețurile sunt în dolari, iar contul ține socoteala în unități "
                "etichetate în euro: procentele sunt corecte, dar nu includ cursul EUR/USD. ")
    else:
        note = f"Bani virtuali, în {report['currency']} (prețurile piețelor sunt în dolari). "
    lines += ["", "_" + note + "Un rezultat bun într-un test nu garantează profit în viitor._", ""]
    return "\n".join(lines)


def load_quotes(path) -> dict:
    """Prețurile din quotes.json (quotes_snapshot): nume -> (preț, ora); {} dacă fișierul lipsește sau e stricat."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))["quotes"]
        return {name: (float(price), datetime.fromisoformat(when)) for name, (price, when) in raw.items() if float(price) > 0}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="report_card")
    parser.add_argument("--state", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--json")
    parser.add_argument("--no-live", action="store_true", help="nu cere prețuri noi")
    parser.add_argument("--quotes", help="prețuri deja citite (JSON de la quotes_snapshot); nu se mai cer din nou")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    names = []
    if Path(args.state).exists() and not args.no_live:
        try:
            engine = PaperEngine.open(args.state)
            names = [p["symbol"] for p in engine.positions()]
            engine.close()
        except PaperEngineError:
            names = []
    if args.quotes and names:
        live = load_quotes(args.quotes)
        quotes = {n: live[n] for n in names if n in live}
    else:
        quotes = quotes_for(names, universe="unic") if names else {}
    report = build(args.state, now, quotes)
    Path(args.out).write_text(render(report), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    print(render(report), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
