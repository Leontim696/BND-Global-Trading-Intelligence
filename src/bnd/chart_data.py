"""Date pentru modulele vizuale ale aplicației: lumânări zilnice compacte și motivele agenților.

Doar citire din arhive existente (CSV-uri zilnice, raportul zilei al consiliului). Nimic nu se
descarcă și nimic nu tranzacționează. Formatul e compact ca pagina să rămână ușoară pe telefon:
pe piață, data de început și decalajele în zile, plus coloanele OHLCV rotunjite.
"""

from pathlib import Path

from .drive_pack import parse_council
from .market_data import MarketDataError, load_csv

BARS = 120                        # ~4 luni de lumânări zilnice pe piață
REASON_CHARS = 420
# Monedele din top 50 care au deja serie proprie sub numele lung (din arhiva zilnică).
ALIASES = {"BTC": "BITCOIN", "ETH": "ETHEREUM", "SOL": "SOLANA"}


def _r(x: float, digits: int = 6) -> float:
    return float(f"{x:.{digits}g}")


def candles(folders, bars: int = BARS) -> dict:
    """{piață: {"s": prima zi ISO, "d": [zile de la s], "o", "h", "l", "c", "v"}} din toate CSV-urile găsite."""
    out = {}
    for folder in folders or []:
        root = Path(folder)
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.csv")):
            name = ALIASES.get(path.stem, path.stem)
            if name in out:                       # prima sursă câștigă (arhiva zilnică înaintea top 50)
                continue
            try:
                series = load_csv(path)[-bars:]
            except (MarketDataError, OSError, ValueError):
                continue
            if len(series) < 2:
                continue
            start = series[0].open_time.date()
            out[name] = {"s": start.isoformat(), "d": [(c.open_time.date() - start).days for c in series],
                         "o": [_r(c.open) for c in series], "h": [_r(c.high) for c in series],
                         "l": [_r(c.low) for c in series], "c": [_r(c.close) for c in series],
                         "v": [_r(c.volume, 3) for c in series]}
    return out


def council_reasons(folder, day: str | None) -> dict:
    """{piață: {agent: motiv}} din raportul consiliului pentru `day` (altfel ultimul raport)."""
    if not folder:
        return {}
    root = Path(folder)
    picks = [root / f"{day}.md"] if day else []
    picks.append(root / "LATEST.md")
    for path in picks:
        if path.is_file():
            try:
                markets = parse_council(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            return {m["market"]: {v["agent"]: v["reason"][:REASON_CHARS] for v in m["votes"]} for m in markets}
    return {}

