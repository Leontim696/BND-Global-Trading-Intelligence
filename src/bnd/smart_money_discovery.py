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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="smart_money_discovery")
    parser.add_argument("--probe", action="store_true")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
