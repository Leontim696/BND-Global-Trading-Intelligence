"""Date de context pentru cripto, strânse în arhivă: Fear & Greed și rata de finanțare (funding).

Doar colectare pentru analiză după test; nu intră în decizia niciunui cont și nu sunt date
consiliului în timpul evaluării. Fiecare sursă e „best effort”: dacă una nu răspunde (de exemplu
Binance blocat din SUA), se notează în `context-status.json` și se încearcă rezerva (OKX); un eșec nu
oprește restul. Fișierele se completează zi de zi, fără dubluri.

    python -m src.bnd.context_data --out arhiva
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import funding

FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
OKX_URL = "https://www.okx.com/api/v5/public/funding-rate-history?instId={inst}&limit=100"
COINS = {"BITCOIN": ("BTCUSDT", "BTC-USDT-SWAP"), "ETHEREUM": ("ETHUSDT", "ETH-USDT-SWAP"),
         "SOLANA": ("SOLUSDT", "SOL-USDT-SWAP"), "BNB": ("BNBUSDT", "BNB-USDT-SWAP"),
         "XRP": ("XRPUSDT", "XRP-USDT-SWAP")}


def _get_json(url: str, timeout: float = 30.0):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (BND research)"}, method="GET")
    try:
        # Reviewed: fixed https URLs above, public read-only data.
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            return json.loads(response.read(5_000_001))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        raise ValueError(f"{url.split('?')[0]} nu răspunde: {type(exc).__name__}") from exc


def parse_fear_greed(payload) -> list[tuple[str, int, str]]:
    rows = []
    try:
        for item in payload["data"]:
            day = datetime.fromtimestamp(int(item["timestamp"]), timezone.utc).date().isoformat()
            value = int(item["value"])
            if not 0 <= value <= 100:
                raise ValueError("valoare în afara 0..100")
            rows.append((day, value, str(item.get("value_classification", ""))))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Răspuns Fear & Greed invalid") from exc
    return sorted(set(rows))


def parse_okx(payload) -> list[tuple[datetime, float]]:
    try:
        return sorted((datetime.fromtimestamp(int(r["fundingTime"]) / 1000, timezone.utc),
                       float(r["fundingRate"])) for r in payload["data"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Răspuns OKX invalid") from exc


def merge_csv(path: Path, header: list, rows: list) -> int:
    """Adaugă rândurile noi (cheia = prima coloană); întoarce câte au fost adăugate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.reader(handle):
                if row and row[0] != header[0]:
                    existing[row[0]] = row
    before = len(existing)
    for row in rows:
        existing[str(row[0])] = [str(x) for x in row]
    # Scriere atomică: fișierul nou se completează lângă cel vechi și îl înlocuiește dintr-o mișcare,
    # deci o oprire la mijloc nu lasă un fișier trunchiat.
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(existing[k] for k in sorted(existing))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return len(existing) - before


def collect(out, fetch_json=_get_json, fetch_binance=funding.fetch_funding) -> dict:
    out = Path(out)
    status = {"time": datetime.now(timezone.utc).isoformat(timespec="minutes"), "sources": {}}
    try:
        rows = parse_fear_greed(fetch_json(FNG_URL))
        added = merge_csv(out / "sentiment" / "fear_greed.csv", ["date", "value", "class"], rows)
        status["sources"]["fear_greed"] = {"ok": True, "added": added, "last": rows[-1][0]}
    except ValueError as exc:
        status["sources"]["fear_greed"] = {"ok": False, "error": str(exc)}
    for name, (binance, okx) in COINS.items():
        entry = {"ok": False}
        for source in ("binance", "okx"):
            try:
                if source == "binance":
                    rates = fetch_binance(binance, days=10)
                else:
                    rates = parse_okx(fetch_json(OKX_URL.format(inst=okx)))
                if not rates:
                    raise ValueError("fără rânduri")
                added = merge_csv(out / "funding" / f"{name}.csv", ["time", "rate", "source"],
                                  [(t.isoformat(), r, source) for t, r in rates])
                entry.update(ok=True, source=source, added=added, last=rates[-1][0].isoformat())
                break
            except ValueError as exc:
                entry[source + "_error"] = str(exc)
        status["sources"]["funding_" + name] = entry
    (out).mkdir(parents=True, exist_ok=True)
    (out / "context-status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))
    return status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="context_data")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    status = collect(args.out)
    ok = [k for k, v in status["sources"].items() if v["ok"]]
    failed = [k for k in status["sources"] if k not in ok]
    print(json.dumps({"ok": ok, "failed": failed}))
    for name in failed:               # anotare vizibilă în GitHub Actions (jobul rămâne verde: arhivarea continuă)
        print(f"::warning::sursa {name} nu a răspuns: {status['sources'][name].get('error', '')}")
    return 0           # un eșec de sursă nu oprește arhivarea restului


if __name__ == "__main__":
    sys.exit(main())
