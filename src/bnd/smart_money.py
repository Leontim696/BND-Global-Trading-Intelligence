"""Smart-Money Graph, pasul 1: colector read-only pentru walleturi Solana de meme-coinuri.

Doar colectare și clasificare în arhivă. NU ia nicio decizie, NU intră în niciun cont și NU e dat consiliului.
Datele sunt publice (blockchain); sursa implicită e API-ul Solana Tracker (cheie gratuită, `SOLANATRACKER_API_KEY`).
Pe lângă walleturile găsite automat, citește lista ta manuală `smart_money/wallete.json`.

Filtrele (toate scrise aici, fără ghicit):
- câștig real, nu noroc dintr-o singură monedă: cel puțin 8 monede diferite, 50 de tranzacții, rată de succes >= 40%;
- sume mici: cumpărătură medie <= 2.000 $; profit realizat >= 20.000 $ și ROI >= 200%;
- nu e bot: timp mediu de ținere >= 5 minute (dacă sursa îl dă); nu e cont nou: vechime >= 90 de zile (dacă o dă).
Etichetă `tipar_insider`: cel puțin jumătate dintre cumpărături sunt în primele minute de la lansarea monedei, pe cel
puțin 5 monede. E un TIPAR DE COMPORTAMENT (intrare foarte timpurie, repetată), nu o dovadă că cineva are informații
interne; poate fi și un sniper rapid sau un bot. Se urmărește tocmai pentru că astfel de intrări anunță mișcări.

Sursa nu a putut fi verificată din sandbox: căile API și numele câmpurilor sunt configurabile, parserul acceptă
variante de nume, iar `status.json` arată exact ce a răspuns sursa.

    python -m src.bnd.smart_money --out arhiva
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ALLOWED_HOSTS = ("data.solanatracker.io",)


def checked_base_url(value: str) -> str:
    """Doar https și gazde cunoscute: cheia API nu trebuie să poată pleca pe http sau pe alt server."""
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.port not in (None, 443):
        raise ValueError(f"SMART_MONEY_BASE_URL refuzat: doar https către {', '.join(ALLOWED_HOSTS)}")
    return f"https://{parsed.hostname}"


BASE_URL = checked_base_url(os.getenv("SMART_MONEY_BASE_URL", "https://data.solanatracker.io"))


class _NoRedirect(HTTPRedirectHandler):
    """Un redirect ar putea duce cheia pe alt host: se refuză."""

    def redirect_request(self, *args, **kwargs):
        return None

SAFE_PATH = re.compile(r"/[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-{}]+)*")


def checked_path(value: str, placeholders=()) -> str:
    """Doar o cale simplă, care începe cu / (fără @, //, .., ?, #): altfel gazda din URL ar putea fi schimbată."""
    stripped = value
    for name in placeholders:
        stripped = stripped.replace("{" + name + "}", "x")
    if not SAFE_PATH.fullmatch(stripped) or "{" in stripped or "}" in stripped:
        raise ValueError(f"cale refuzată: {value[:40]!r}")
    return value


LEADERBOARD_PATH = checked_path(os.getenv("SMART_MONEY_LEADERBOARD_PATH", "/top-traders/all"))
WALLET_PATH = checked_path(os.getenv("SMART_MONEY_WALLET_PATH", "/pnl/{wallet}"), ("wallet",))
ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

MIN_TOKENS, MIN_TRADES, MIN_WIN_RATE = 8, 50, 0.40
MAX_AVG_BUY_USD, MIN_PNL_USD, MIN_ROI = 2000.0, 20_000.0, 2.0
MIN_HOLD_MINUTES, MIN_AGE_DAYS = 5.0, 90
EARLY_SHARE, EARLY_TOKENS = 0.5, 5
HEADER = ["time", "wallet", "source", "tokens", "trades", "win_rate", "realized_pnl_usd", "avg_buy_usd",
          "roi", "median_hold_min", "age_days", "early_share", "passes", "tags", "reasons"]


def valid_address(text) -> bool:
    return isinstance(text, str) and bool(ADDRESS.match(text))


def _pick(row: dict, *names):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def normalise(row: dict) -> dict | None:
    """Rând din sursă -> statistici comune; None dacă nu are adresă validă."""
    wallet = _pick(row, "wallet", "address", "owner", "walletAddress")
    if not valid_address(wallet):
        return None
    summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
    row = {**summary, **row}
    win = _num(_pick(row, "win_rate", "winRate", "winrate", "win_percentage", "winPercentage"))
    if win is not None and win > 1:
        win /= 100                                     # unele surse dau procente
    trades = _num(_pick(row, "trades", "total_trades", "totalTrades"))
    if trades is None:
        buys, sells = _num(_pick(row, "buys", "totalBuys")), _num(_pick(row, "sells", "totalSells"))
        trades = (buys or 0) + (sells or 0) if (buys is not None or sells is not None) else None
    invested = _num(_pick(row, "total_invested", "totalInvested", "invested"))
    pnl = _num(_pick(row, "realized", "realized_pnl_usd", "realizedPnl", "total", "pnl", "totalPnl"))
    avg_buy = _num(_pick(row, "avg_buy_usd", "avgBuy", "average_buy"))
    if avg_buy is None and invested is not None and trades:
        avg_buy = invested / max(1.0, trades / 2)
    roi = _num(_pick(row, "roi", "ROI"))
    if roi is None and pnl is not None and invested:
        roi = pnl / invested
    return {"wallet": wallet, "tokens": _num(_pick(row, "tokens", "token_count", "tokensTraded", "totalTokens")),
            "trades": trades, "win_rate": win, "realized_pnl_usd": pnl, "avg_buy_usd": avg_buy, "roi": roi,
            "median_hold_min": _num(_pick(row, "median_hold_min", "medianHoldMinutes", "avgHoldMinutes")),
            "age_days": _num(_pick(row, "age_days", "walletAgeDays")),
            "early_share": _num(_pick(row, "early_share", "earlyBuyShare"))}


def assess(stats: dict) -> dict:
    """Trece/nu trece filtrele, cu motivele; câmpurile lipsă nu penalizează, dar se notează."""
    reasons, unknown = [], []

    def need(name, ok, text):
        value = stats.get(name)
        if value is None:
            unknown.append(name)
        elif not ok(value):
            reasons.append(text.format(value=value))

    need("tokens", lambda v: v >= MIN_TOKENS, "doar {value:.0f} monede (minim 8)")
    need("trades", lambda v: v >= MIN_TRADES, "doar {value:.0f} tranzacții (minim 50)")
    need("win_rate", lambda v: v >= MIN_WIN_RATE, "rată de succes {value:.0%} (minim 40%)")
    need("avg_buy_usd", lambda v: v <= MAX_AVG_BUY_USD, "cumpărătură medie {value:.0f} $ (maxim 2.000 $)")
    need("realized_pnl_usd", lambda v: v >= MIN_PNL_USD, "profit realizat {value:.0f} $ (minim 20.000 $)")
    need("roi", lambda v: v >= MIN_ROI, "ROI {value:.0%} (minim 200%)")
    need("median_hold_min", lambda v: v >= MIN_HOLD_MINUTES, "ținere {value:.1f} min: probabil bot")
    need("age_days", lambda v: v >= MIN_AGE_DAYS, "wallet de {value:.0f} zile (minim 90)")
    tags = []
    early, tokens = stats.get("early_share"), stats.get("tokens")
    if early is not None and tokens is not None and early >= EARLY_SHARE and tokens >= EARLY_TOKENS:
        tags.append("tipar_insider")
    core_known = all(stats.get(k) is not None for k in ("tokens", "trades", "win_rate", "realized_pnl_usd"))
    return {"passes": core_known and not reasons, "reasons": reasons, "unknown": unknown, "tags": tags}


def _get(url: str, key: str, timeout: float = 30.0):
    if urlparse(url).hostname not in ALLOWED_HOSTS or urlparse(url).scheme != "https":
        raise ValueError("URL refuzat: gazdă sau schemă nepermisă")
    request = Request(url, headers={"x-api-key": key, "User-Agent": "BND-research"}, method="GET")
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:  # nosec B310 - https, gazdă fixă, fără redirect
            return json.loads(response.read(5_000_001))
    except HTTPError as exc:
        raise ValueError(f"{url.split('?')[0]} a răspuns HTTP {exc.code}") from exc
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        raise ValueError(f"{url.split('?')[0]} nu răspunde: {type(exc).__name__}") from exc


def rows_of(payload) -> list:
    """Lista de rânduri dintr-un răspuns (listă directă sau învelită în data/wallets/traders)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for name in ("data", "wallets", "traders", "results", "items"):
            if isinstance(payload.get(name), list):
                return payload[name]
    raise ValueError("Răspuns neașteptat (nu conține o listă de walleturi)")


def manual_wallets(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    items = json.loads(path.read_text(encoding="utf-8"))
    return [{"wallet": i["wallet"], "label": i.get("label", ""), "source": "manual"}
            for i in items if valid_address(i.get("wallet"))]


ENRICH_LIMIT = 25          # câte walleturi din clasament primesc și detalii (un apel fiecare)


def _keys(obj) -> list:
    """Doar NUMELE câmpurilor (nu valorile) unui răspuns, ca să putem potrivi parserul pe răspunsul real."""
    if not isinstance(obj, dict):
        return []
    keys = sorted(obj)
    if isinstance(obj.get("summary"), dict):
        keys += ["summary." + k for k in sorted(obj["summary"])]
    return keys


def collect(out, key: str | None, manual_path="smart_money/wallete.json", fetch=_get, now=None) -> dict:
    out = Path(out) / "smart_money"
    out.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(timezone.utc)
    status = {"time": now.isoformat(timespec="minutes"), "leaderboard": None, "manual": 0, "errors": []}
    candidates = {}
    if key:
        try:
            board = rows_of(fetch(BASE_URL + LEADERBOARD_PATH, key))
            status["sample_keys"] = {"clasament": _keys(board[0]) if board else []}
            for row in board:
                stats = normalise(row) if isinstance(row, dict) else None
                if stats:
                    candidates[stats["wallet"]] = {**stats, "source": "clasament"}
            status["leaderboard"] = {"ok": True, "wallets": len(candidates)}
            enriched = 0
            for wallet in list(candidates)[:ENRICH_LIMIT]:
                try:
                    detail = fetch(BASE_URL + WALLET_PATH.format(wallet=wallet), key)
                except ValueError as exc:
                    status["errors"].append(f"detalii {wallet[:6]}…: {exc}")
                    continue
                if enriched == 0:
                    status["sample_keys"]["detalii"] = _keys(detail)
                found = normalise({**detail, "wallet": wallet}) if isinstance(detail, dict) else None
                if found:
                    base = candidates[wallet]
                    candidates[wallet] = {**base, **{k: v for k, v in found.items() if v is not None}}
                    enriched += 1
            status["leaderboard"]["enriched"] = enriched
        except ValueError as exc:
            status["leaderboard"] = {"ok": False, "error": str(exc)}
            status["errors"].append(str(exc))
    else:
        status["leaderboard"] = {"ok": False, "error": "fără cheie SOLANATRACKER_API_KEY"}
    for item in manual_wallets(manual_path):
        status["manual"] += 1
        stats = candidates.get(item["wallet"], {"wallet": item["wallet"], "source": "manual"})
        if key and stats["source"] == "manual":
            try:
                found = normalise({**fetch(BASE_URL + WALLET_PATH.format(wallet=item["wallet"]), key),
                                   "wallet": item["wallet"]})
                stats = {**(found or stats), "source": "manual"}
            except ValueError as exc:
                status["errors"].append(f"{item['wallet'][:6]}…: {exc}")
        candidates[item["wallet"]] = {**stats, "source": "manual"}
    rows = []
    for wallet, stats in sorted(candidates.items()):
        verdict = assess(stats)
        stats = {**stats, **verdict}
        rows.append([now.isoformat(timespec="minutes"), wallet, stats["source"]]
                    + [("" if stats.get(k) is None else stats[k]) for k in HEADER[3:12]]
                    + [int(verdict["passes"]), ";".join(verdict["tags"]), "; ".join(verdict["reasons"])])
    path = out / "wallete.csv"
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(HEADER)
        writer.writerows(rows)
    status["written"] = len(rows)
    status["passing"] = sum(r[HEADER.index("passes")] for r in rows)
    status["insider_pattern"] = sum(bool(r[HEADER.index("tags")]) for r in rows)
    (out / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    return status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="smart_money")
    parser.add_argument("--out", required=True)
    parser.add_argument("--manual", default="smart_money/wallete.json")
    args = parser.parse_args(argv)
    status = collect(args.out, os.getenv("SOLANATRACKER_API_KEY") or None, args.manual)
    print(json.dumps({k: status[k] for k in ("leaderboard", "manual", "written", "passing", "insider_pattern")}))
    if not status["leaderboard"]["ok"]:
        print(f"::warning::clasamentul smart-money nu s-a citit: {status['leaderboard'].get('error', '')}")
    for error in status["errors"][:5]:
        print(f"::warning::{error}")
    return 0           # o sursă căzută nu strică restul


if __name__ == "__main__":
    sys.exit(main())
