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

import math
import argparse
import csv
import json
import os
import re
import sys
from time import sleep
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
    return number if math.isfinite(number) else None


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
    if trades is None and (row.get("totalWins") is not None or row.get("totalLosses") is not None):
        trades = (_num(row.get("totalWins")) or 0) + (_num(row.get("totalLosses")) or 0)    # poziții închise
    if trades is None:
        buys, sells = _num(_pick(row, "buys", "totalBuys")), _num(_pick(row, "sells", "totalSells"))
        trades = (buys or 0) + (sells or 0) if (buys is not None or sells is not None) else None
    invested = _num(_pick(row, "total_invested", "totalInvested", "invested"))
    pnl = _num(_pick(row, "realized", "realized_pnl_usd", "realizedPnl", "total", "pnl", "totalPnl"))
    avg_buy = _num(_pick(row, "avg_buy_usd", "avgBuy", "average_buy", "averageBuyAmount"))
    if avg_buy is None and invested is not None and trades:
        avg_buy = invested / max(1.0, trades / 2)
    roi = _num(_pick(row, "roi", "ROI"))
    if roi is None and pnl is not None and invested:
        roi = pnl / invested
    tokens = _num(_pick(row, "token_count", "tokensTraded", "totalTokens"))
    listed = row.get("tokens")
    if tokens is None:
        tokens = float(len(listed)) if isinstance(listed, (dict, list)) else _num(listed)
    return {"wallet": wallet, "tokens": tokens,
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


class RateLimited(ValueError):
    """HTTP 429: sursa cere o pauză (Retry-After, în secunde, dacă a dat-o)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


MAX_WAIT = 30.0          # nu așteptăm mai mult de atât între încercări
RATE_LIMIT_ATTEMPTS = 3


def _retry_after(value) -> float | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _get(url: str, key: str, timeout: float = 30.0):
    if urlparse(url).hostname not in ALLOWED_HOSTS or urlparse(url).scheme != "https":
        raise ValueError("URL refuzat: gazdă sau schemă nepermisă")
    request = Request(url, headers={"x-api-key": key, "User-Agent": "BND-research"}, method="GET")
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:  # nosec B310 - https, gazdă fixă, fără redirect
            return json.loads(response.read(30_000_001))      # detaliile unui wallet activ pot fi mari
    except HTTPError as exc:
        if exc.code == 429:
            raise RateLimited(f"{url.split('?')[0]} a răspuns HTTP 429 (prea multe cereri)",
                              _retry_after(exc.headers.get("Retry-After") if exc.headers else None)) from exc
        raise ValueError(f"{url.split('?')[0]} a răspuns HTTP {exc.code}") from exc
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        raise ValueError(f"{url.split('?')[0]} nu răspunde: {type(exc).__name__}") from exc


def fetch_with_retry(fetch, url: str, key: str, status: dict, what: str = ""):
    """O cerere cu reîncercări: 429 așteaptă (Retry-After, plafonat) de până la 3 ori, restul o dată.

    Întoarce răspunsul sau ridică ValueError după ultima încercare (eroarea ajunge în status)."""
    attempts = 0
    while True:
        attempts += 1
        try:
            return fetch(url, key)
        except RateLimited as exc:
            status["rate_limited"] = status.get("rate_limited", 0) + 1
            if attempts >= RATE_LIMIT_ATTEMPTS:
                raise
            sleep(min(exc.retry_after if exc.retry_after is not None else 2.0 * attempts, MAX_WAIT))
        except ValueError:
            if attempts >= 2:
                raise
            sleep(1.5)


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


EXIT_CODES = {"ok": 0, "partial": 0, "failed": 2, "no_key": 3}


def classify(status: dict, key) -> str:
    """ok = totul citit; partial = clasamentul s-a citit dar unele cereri au eșuat; failed = fără date;
    no_key = lipsește cheia (nu s-a colectat nimic din sursă)."""
    if not key:
        return "no_key"
    if not status["leaderboard"] or not status["leaderboard"].get("ok"):
        return "failed"
    return "partial" if status["errors"] else "ok"


def collect(out, key: str | None, manual_path="smart_money/wallete.json", fetch=_get, now=None) -> dict:
    out = Path(out) / "smart_money"
    out.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(timezone.utc)
    status = {"time": now.isoformat(timespec="minutes"), "leaderboard": None, "manual": 0, "errors": []}
    candidates = {}
    if key:
        try:
            board = rows_of(fetch_with_retry(fetch, BASE_URL + LEADERBOARD_PATH, key, status))
            status["sample_keys"] = {"clasament": _keys(board[0]) if board else []}
            for row in board:
                stats = normalise(row) if isinstance(row, dict) else None
                if stats:
                    candidates[stats["wallet"]] = {**stats, "source": "clasament"}
            if not candidates:
                raise ValueError(f"Clasament fără niciun wallet valid ({len(board)} rânduri primite)")
            status["leaderboard"] = {"ok": True, "wallets": len(candidates)}
            enriched = 0
            for wallet in list(candidates)[:ENRICH_LIMIT]:
                try:
                    detail = fetch_with_retry(fetch, BASE_URL + WALLET_PATH.format(wallet=wallet), key, status)
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
                found = normalise({**fetch_with_retry(fetch, BASE_URL + WALLET_PATH.format(wallet=item["wallet"]), key, status),
                                   "wallet": item["wallet"]})
                stats = {**(found or stats), "source": "manual"}
            except ValueError as exc:
                status["errors"].append(f"{item['wallet'][:6]}…: {exc}")
        candidates[item["wallet"]] = {**stats, "source": "manual"}
    status["outcome"] = classify(status, key)
    rows = []
    for wallet, stats in sorted(candidates.items()):
        verdict = assess(stats)
        stats = {**stats, **verdict}
        rows.append([now.isoformat(timespec="minutes"), wallet, stats["source"]]
                    + [("" if stats.get(k) is None else stats[k]) for k in HEADER[3:12]]
                    + [int(verdict["passes"]), ";".join(verdict["tags"]), "; ".join(verdict["reasons"])])
    path = out / "wallete.csv"
    if status["outcome"] in ("ok", "partial"):     # fără date reale nu adăugăm rânduri goale în istoric
        new_file = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if new_file:
                writer.writerow(HEADER)
            writer.writerows(rows)
    else:
        rows = []
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
    print(json.dumps({k: status[k] for k in ("outcome", "leaderboard", "manual", "written", "passing", "insider_pattern")}))
    outcome = status["outcome"]
    if outcome == "no_key":
        print("::error::Lipsește SOLANATRACKER_API_KEY: nu s-a colectat nimic din sursă.")
    elif outcome == "failed":
        print(f"::error::Clasamentul smart-money nu s-a citit: {status['leaderboard'].get('error', '')}")
    elif outcome == "partial":
        print(f"::warning::Colectare parțială: {len(status['errors'])} cereri au eșuat "
              f"({status.get('rate_limited', 0)} limitări 429).")
    for error in status["errors"][:5]:
        print(f"::warning::{error}")
    return EXIT_CODES[outcome]


if __name__ == "__main__":
    sys.exit(main())
