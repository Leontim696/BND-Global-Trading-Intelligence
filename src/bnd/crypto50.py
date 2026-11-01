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
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .council_context import bot_signal
from .market_data import MarketDataError, fetch_binance_klines, load_csv, save_csv

# (nume, pereche Binance, memecoin?)
COINS = (
    ("BTC", "BTCUSDT", False), ("ETH", "ETHUSDT", False), ("XRP", "XRPUSDT", False),
    ("BNB", "BNBUSDT", False), ("SOL", "SOLUSDT", False), ("TRX", "TRXUSDT", False),
    ("DOGE", "DOGEUSDT", True), ("ADA", "ADAUSDT", False), ("LINK", "LINKUSDT", False),
    ("AVAX", "AVAXUSDT", False), ("XLM", "XLMUSDT", False), ("SUI", "SUIUSDT", False),
    ("TON", "TONUSDT", False), ("SHIB", "SHIBUSDT", True), ("BCH", "BCHUSDT", False),
    ("LTC", "LTCUSDT", False), ("DOT", "DOTUSDT", False), ("HBAR", "HBARUSDT", False),
    ("UNI", "UNIUSDT", False), ("PEPE", "PEPEUSDT", True), ("AAVE", "AAVEUSDT", False),
    ("NEAR", "NEARUSDT", False), ("ICP", "ICPUSDT", False), ("ETC", "ETCUSDT", False),
    ("APT", "APTUSDT", False), ("ONDO", "ONDOUSDT", False), ("ATOM", "ATOMUSDT", False),
    ("POL", "POLUSDT", False), ("ARB", "ARBUSDT", False), ("FIL", "FILUSDT", False),
    ("ALGO", "ALGOUSDT", False), ("VET", "VETUSDT", False), ("OP", "OPUSDT", False),
    ("INJ", "INJUSDT", False), ("RENDER", "RENDERUSDT", False), ("TAO", "TAOUSDT", False),
    ("FET", "FETUSDT", False), ("SEI", "SEIUSDT", False), ("STX", "STXUSDT", False),
    ("BONK", "BONKUSDT", True), ("WIF", "WIFUSDT", True), ("FLOKI", "FLOKIUSDT", True),
    ("TRUMP", "TRUMPUSDT", True), ("PENGU", "PENGUUSDT", True), ("ENA", "ENAUSDT", False),
    ("WLD", "WLDUSDT", False), ("JUP", "JUPUSDT", False), ("LDO", "LDOUSDT", False),
    ("CRV", "CRVUSDT", False), ("TIA", "TIAUSDT", False),
)


def update(out, fetch=fetch_binance_klines, now: datetime | None = None, years: int = 3) -> dict:
    """Completează fișierele cu zilele noi; o monedă care nu răspunde nu oprește restul."""
    now = now or datetime.now(timezone.utc)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    status = {"time": now.isoformat(timespec="minutes"), "coins": {}}
    for name, symbol, meme in COINS:
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
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    status = update(args.out)
    ok = sum(1 for v in status["coins"].values() if v["ok"])
    print(json.dumps({"ok": ok, "failed": [k for k, v in status["coins"].items() if not v["ok"]]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
