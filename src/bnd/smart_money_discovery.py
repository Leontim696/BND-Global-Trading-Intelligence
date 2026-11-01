"""Explorare și descoperire de walleturi Solana Tracker (read-only, doar în CI, cu cheia).

Documentația API-ului nu poate fi citită din sandbox, așa că întâi se SONDEAZĂ ce răspunde API-ul (stare HTTP, forma
răspunsului, doar NUMELE câmpurilor, niciodată valorile sau cheia), apoi se construiește descoperirea pe ce există:
monede care au explodat -> primii cumpărători -> walleturi care apar câștigătoare în mai multe monede.

    python -m src.bnd.smart_money_discovery --probe --out arhiva
"""

import argparse
import json
import os
import sys
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request

from .smart_money import ALLOWED_HOSTS, BASE_URL, _NoRedirect, build_opener

PROBES = (
    "/tokens/trending", "/tokens/volume", "/tokens/multi/graduated", "/tokens/latest",
    "/top-traders/all", "/top-traders/all?sortBy=roi", "/top-traders/all?sortBy=winPercentage",
    "/top-traders/all?expandPnl=true", "/top-traders/all/1",
)


def get(path: str, key: str, timeout: float = 30.0) -> tuple[int, object]:
    """(cod HTTP, JSON sau text scurt). Nu ridică la erori HTTP: ne interesează exact răspunsul."""
    url = BASE_URL + path
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("URL refuzat")
    request = Request(url, headers={"x-api-key": key, "User-Agent": "BND-research"}, method="GET")
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:  # nosec B310 - https, gazdă fixă
            body = response.read(8_000_000)
            status = response.status
    except HTTPError as exc:
        return exc.code, exc.read(400).decode("utf-8", "replace")
    except (URLError, TimeoutError, OSError) as exc:
        return 0, type(exc).__name__
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body[:200].decode("utf-8", "replace")


def shape(payload) -> dict:
    """Forma unui răspuns fără valori: tip, lungime și numele câmpurilor primului element."""
    def keys(obj):
        if not isinstance(obj, dict):
            return []
        out = sorted(obj)
        for k, v in obj.items():
            if isinstance(v, dict):
                out += [f"{k}.{x}" for x in sorted(v)[:15]]
        return out[:60]
    if isinstance(payload, list):
        return {"type": "list", "length": len(payload), "keys": keys(payload[0]) if payload else []}
    if isinstance(payload, dict):
        info = {"type": "dict", "keys": keys(payload)}
        for name in ("data", "tokens", "wallets", "traders", "results"):
            if isinstance(payload.get(name), list) and payload[name]:
                info["list_field"] = name
                info["length"] = len(payload[name])
                info["item_keys"] = keys(payload[name][0])
        return info
    return {"type": type(payload).__name__, "text": str(payload)[:200]}


def probe(key: str, fetch=get, pause: float = 1.2) -> dict:
    report = {}
    first_mint = None
    for path in PROBES:
        code, payload = fetch(path, key)
        report[path] = {"status": code, **(shape(payload) if code == 200 else {"error": str(payload)[:200]})}
        if code == 200 and first_mint is None:
            items = payload if isinstance(payload, list) else next(
                (payload[n] for n in ("data", "tokens", "results") if isinstance(payload.get(n), list)), []) if isinstance(payload, dict) else []
            for item in items:
                mint = (item.get("token") or item).get("mint") if isinstance(item, dict) and isinstance(item.get("token") or item, dict) else None
                if isinstance(mint, str) and 32 <= len(mint) <= 44:
                    first_mint = mint
                    break
        sleep(pause)
    if first_mint:
        for path in (f"/first-buyers/{first_mint}", f"/top-traders/{first_mint}", f"/tokens/{first_mint}"):
            code, payload = fetch(path, key)
            report[path.replace(first_mint, "{mint}")] = {"status": code, **(shape(payload) if code == 200 else {"error": str(payload)[:200]})}
            sleep(pause)
    return report


# --- descoperire ----------------------------------------------------------------------------

LISTS = ("/tokens/trending", "/tokens/volume", "/tokens/multi/graduated", "/tokens/latest")
MAX_TOKENS = 100                     # câte monede se cercetează (un apel pe monedă)
MIN_INVESTED, MAX_INVESTED = 15.0, 3000.0     # „sume mici” pe o monedă, în dolari
MIN_TOKEN_ROI, MIN_TOKEN_PROFIT = 5.0, 2000.0  # câștig de cel puțin 500% și 2.000 $ pe moneda respectivă
MIN_HITS = 1                         # un singur câștig nu dovedește nimic singur: trece prin filtrele pe tot istoricul (/pnl)
INSIDER_HITS = 3                     # primii cumpărători câștigători pe cel puțin 3 monede = tipar de intrare timpurie
ENRICH_MAX = 30
HEADER = ["time", "wallet", "hits", "tokens_seen", "best_token_roi", "profit_in_batch", "avg_invested", "tokens",
          "trades", "win_rate", "avg_buy_usd", "realized_pnl_usd", "roi", "passes", "tags", "reasons"]


def _items(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for name in ("data", "tokens", "results", "wallets"):
            if isinstance(payload.get(name), list):
                return payload[name]
    return []


def _price_change_24h(item) -> float:
    events = item.get("events") if isinstance(item, dict) else None
    day = events.get("24h") if isinstance(events, dict) else None
    if isinstance(day, dict):
        for key, value in day.items():
            if "price" in key.lower() and isinstance(value, (int, float)):
                return float(value)
    return 0.0


def pick_tokens(lists: dict, limit: int = MAX_TOKENS) -> list[str]:
    """Monedele de cercetat: reuniunea listelor, cele mai urcate în 24h primele (acolo apar câștigurile mari)."""
    best = {}
    for items in lists.values():
        for item in items:
            token = item.get("token") if isinstance(item, dict) and isinstance(item.get("token"), dict) else item
            mint = token.get("mint") if isinstance(token, dict) else None
            if isinstance(mint, str) and 32 <= len(mint) <= 44:
                best[mint] = max(best.get(mint, float("-inf")), _price_change_24h(item))
    return [m for m, _ in sorted(best.items(), key=lambda kv: -kv[1])][:limit]


def winners_of(buyers: list) -> dict:
    """wallet -> (roi, profit, investit) pentru cumpărătorii cu sumă mică și câștig mare pe această monedă."""
    from .smart_money import _num, valid_address
    out = {}
    for b in buyers:
        if not isinstance(b, dict) or not valid_address(b.get("wallet")):
            continue
        invested, realized = _num(b.get("total_invested")), _num(b.get("realized"))
        if invested is None or realized is None or not MIN_INVESTED <= invested <= MAX_INVESTED:
            continue
        roi = realized / invested
        if roi >= MIN_TOKEN_ROI and realized >= MIN_TOKEN_PROFIT:
            out[b["wallet"]] = (roi, realized, invested)
    return out


def discover(key: str, fetch=get, pause: float = 1.2, now=None) -> dict:
    from datetime import datetime, timezone
    from .smart_money import assess, normalise
    now = now or datetime.now(timezone.utc)
    lists, errors = {}, []
    for path in LISTS:
        code, payload = fetch(path, key)
        if code == 200:
            lists[path] = _items(payload)
        else:
            errors.append(f"{path}: HTTP {code}")
        sleep(pause)
    mints = pick_tokens(lists)
    hits, seen = {}, 0
    for mint in mints:
        code, payload = fetch(f"/first-buyers/{mint}", key)
        sleep(pause)
        if code != 200:
            errors.append(f"first-buyers: HTTP {code}")
            continue
        seen += 1
        for wallet, (roi, profit, invested) in winners_of(_items(payload)).items():
            hits.setdefault(wallet, []).append((roi, profit, invested))
    candidates = {w: v for w, v in hits.items() if len(v) >= MIN_HITS}   # cele repetate (hits mai mare) primele
    rows = []
    for wallet, v in sorted(candidates.items(), key=lambda kv: (-len(kv[1]), -sum(p for _, p, _ in kv[1])))[:ENRICH_MAX]:
        code, detail = fetch(f"/pnl/{wallet}", key)
        sleep(pause)
        stats = normalise({**detail, "wallet": wallet}) if code == 200 and isinstance(detail, dict) else {"wallet": wallet}
        verdict = assess({**(stats or {}), "early_share": None})
        tags = ["tipar_insider"] if len(v) >= INSIDER_HITS else []
        rows.append([now.isoformat(timespec="minutes"), wallet, len(v), seen, f"{max(r for r, _, _ in v):.1f}",
                     f"{sum(p for _, p, _ in v):.0f}", f"{sum(i for _, _, i in v) / len(v):.0f}"]
                    + [("" if (stats or {}).get(k) is None else stats[k]) for k in
                       ("tokens", "trades", "win_rate", "avg_buy_usd", "realized_pnl_usd", "roi")]
                    + [int(verdict["passes"]), ";".join(tags), "; ".join(verdict["reasons"])])
    return {"tokens_checked": seen, "wallets_with_hits": len(hits), "candidates": len(candidates),
            "rows": rows, "errors": errors[:10]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="smart_money_discovery")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    key = os.getenv("SOLANATRACKER_API_KEY")
    if not key:
        print("::warning::fără SOLANATRACKER_API_KEY")
        return 0
    out = Path(args.out) / "smart_money"
    out.mkdir(parents=True, exist_ok=True)
    if args.probe:
        report = probe(key)
        (out / "sondaj.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({p: r["status"] for p, r in report.items()}, ensure_ascii=False))
    if args.discover:
        from .context_data import merge_csv
        result = discover(key)
        path = out / "descoperite.csv"
        added = merge_csv(path, ["id"] + HEADER, [[f"{r[1]}|{r[0][:10]}"] + r for r in result["rows"]])
        (out / "descoperire.json").write_text(json.dumps({k: v for k, v in result.items() if k != "rows"} | {"added": added},
                                                         indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
