"""Top 50 criptomonede (inclusiv memecoin-uri): arhivă de prețuri și o privire de ansamblu.

Selecție statică de monede mari și lichide cu pereche USDT pe Binance (stablecoin-urile sunt
excluse; XMR, KAS și HYPE nu au piață spot publică acolo, deci lipsesc). Prețurile zilnice vin din
API-ul public de date Binance, se completează zi de zi în `crypto50/<MONEDA>.csv`, iar `summary`
calculează pentru fiecare: ultimul preț, variația pe 1/7/30 de zile și semnalul simplu SMA 20/50.
Doar colectare și afișare: monedele NU intră în consiliul AI (cost) și nu în conturile virtuale.

    python -m src.bnd.crypto50 --out arhiva/crypto50
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .council_context import bot_signal
from .market_data import MarketDataError, fetch_binance_klines, load_csv, save_csv

from .coins import COINS  # noqa: E402  (lista e într-un modul fără dependențe)


# Monedele care au deja piață în consiliu, din surse Yahoo, sub alt nume.
COVERED = {"BTC": "BITCOIN", "ETH": "ETHEREUM", "SOL": "SOLANA", "BNB": "BNB", "XRP": "XRP"}
EXTRA = tuple(name for name, _, _ in COINS if name not in COVERED)       # cele 45 în plus
YAHOO_CRYPTO = ("SOLANA", "BNB", "XRP")


def split_markets(markets) -> dict:
    """Împarte lista consiliului după sursa de date: ETF/forex, crypto Yahoo, crypto Binance."""
    markets = list(markets)
    if not all(re.fullmatch(r"[A-Z0-9_]{1,20}", m) for m in markets):
        raise ValueError("Nume de piață invalid (doar litere mari, cifre și _)")
    binance = [m for m in markets if m in EXTRA]
    yahoo = [m for m in markets if m in YAHOO_CRYPTO]
    return {"etf": [m for m in markets if m not in binance and m not in yahoo],
            "yahoo_crypto": yahoo, "binance": binance}


def update(out, fetch=fetch_binance_klines, now: datetime | None = None, years: int = 3,
           only=None) -> dict:
    """Completează fișierele cu zilele noi; o monedă care nu răspunde nu oprește restul."""
    now = now or datetime.now(timezone.utc)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    status = {"time": now.isoformat(timespec="minutes"), "coins": {}}
    for name, symbol, meme in COINS:
        if only is not None and name not in only:
            continue
        path = out / f"{name}.csv"
        try:
            old = load_csv(path) if path.exists() else []
            start = old[-1].open_time + timedelta(days=1) if old else today - timedelta(days=365 * years)
            new = fetch(symbol, "1d", start, today) if start < today else []
            merged = {c.open_time: c for c in old}
            merged.update({c.open_time: c for c in new})
            candles = [merged[k] for k in sorted(merged)]
            if not candles:
                raise MarketDataError("nicio lumânare")
            save_csv(candles, path)
            status["coins"][name] = {"ok": True, "added": len(new), "last": candles[-1].open_time.date().isoformat(),
                                     "meme": meme}
        except (MarketDataError, OSError, ValueError) as exc:
            status["coins"][name] = {"ok": False, "error": str(exc)[:100], "meme": meme}
    (out / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))
    return status


def _change(candles, days):
    return 100 * (candles[-1].close / candles[-1 - days].close - 1) if len(candles) > days else None


def summary(folder) -> list:
    """Pe monedă: ultimul preț, variații și semnalul SMA 20/50 (1 cumpără, -1 vinde, 0 nimic)."""
    rows = []
    for name, symbol, meme in COINS:
        path = Path(folder) / f"{name}.csv"
        if not path.exists():
            continue
        try:
            candles = load_csv(path)
        except MarketDataError:
            continue
        if len(candles) < 2:
            continue
        rows.append({"name": name, "meme": meme, "price": candles[-1].close,
                     "date": candles[-1].open_time.date().isoformat(),
                     "d1": _change(candles, 1), "d7": _change(candles, 7), "d30": _change(candles, 30),
                     "signal": bot_signal(candles) if len(candles) >= 60 else 0})
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="crypto50")
    parser.add_argument("--out")
    parser.add_argument("--only", help="doar aceste monede, separate prin virgulă")
    parser.add_argument("--split", help="lista consiliului: afișează grupele după sursa de date")
    args = parser.parse_args(argv)
    if args.split is not None:
        try:
            groups = split_markets([m for m in args.split.split(",") if m])
        except ValueError as exc:
            print("Error:", exc, file=sys.stderr)
            return 2
        for key, names in groups.items():
            print(f"{key}={','.join(names)}")
        return 0
    if not args.out:
        parser.error("--out sau --split")
    only = {n for n in args.only.split(",") if n} if args.only else None
    status = update(args.out, only=only)
    ok = sum(1 for v in status["coins"].values() if v["ok"])
    print(json.dumps({"ok": ok, "failed": [k for k, v in status["coins"].items() if not v["ok"]]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
