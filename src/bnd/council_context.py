"""Întrebarea pentru consiliul AI: date de piață reale, ca text scurt.

Folosește doar lumânări închise (nicio informație din viitor) și doar prețuri:
nu există știri în acest context, iar textul le spune agenților asta, ca să
voteze HOLD când datele nu ajung. Include și semnalul regulii simple a botului
(SMA 20/50), doar ca informație; consiliul nu e obligat să-l urmeze.
"""

from math import log, sqrt
from statistics import stdev
from typing import Sequence

from .market_data import Candle
from .strategies import sma_crossover

HORIZON_DAYS = 5
LABELS = {"SP500": "S&P 500 (ETF)", "GOLD": "aur (ETF)", "BITCOIN": "Bitcoin",
          "EURUSD": "curs EUR/USD", "NASDAQ100": "Nasdaq 100 (ETF)", "ETHEREUM": "Ethereum",
          "SILVER": "argint (ETF)", "CRUDE_OIL": "petrol (ETF)", "USDJPY": "curs USD/JPY",
          "US10Y_NOTE": "obligațiuni americane pe 10 ani (ETF)",
          "SOLANA": "Solana", "BNB": "BNB", "XRP": "XRP"}


def label(name: str) -> str:
    """Eticheta unei piețe; monedele din top 50 primesc una generică (cu mențiune pentru memecoin)."""
    if name in LABELS:
        return LABELS[name]
    from .universe import DEFENSE_CURRENCY, STOCK_UNIVERSE
    for stock in STOCK_UNIVERSE:
        if stock.name == name:
            return f"{name} (acțiune americană, sector {stock.sector})"
    if name in DEFENSE_CURRENCY:
        return f"{name} (acțiune din industria de apărare, în {DEFENSE_CURRENCY[name]})"
    from .crypto50 import COINS
    for coin, _, meme in COINS:
        if coin == name:
            return f"{name} (memecoin, volatilitate foarte mare)" if meme else f"{name} (criptomonedă)"
    return name


def _change(candles: Sequence[Candle], days: int) -> float | None:
    if len(candles) <= days:
        return None
    return 100 * (candles[-1].close / candles[-1 - days].close - 1)


def _volatility(candles: Sequence[Candle], days: int) -> float | None:
    if len(candles) <= days:
        return None
    window = candles[-days - 1:]
    returns = [log(b.close / a.close) for a, b in zip(window, window[1:])]
    return 100 * stdev(returns) * sqrt(365)


def _sma(candles: Sequence[Candle], days: int) -> float | None:
    if len(candles) < days:
        return None
    return sum(c.close for c in candles[-days:]) / days


def _rsi(candles: Sequence[Candle], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    moves = [b.close - a.close for a, b in zip(candles[-period - 1:], candles[-period:])]
    gains = sum(m for m in moves if m > 0) / period
    losses = -sum(m for m in moves if m < 0) / period
    if losses == 0:
        return 100.0 if gains else 50.0
    return 100 - 100 / (1 + gains / losses)


def bot_signal(candles: Sequence[Candle]) -> int:
    """Semnalul regulii simple SMA 20/50: 1, -1 sau 0."""
    return sma_crossover(20, 50)(candles)


def _fmt(value, suffix="", digits=1) -> str:
    return "n/a" if value is None else f"{value:+.{digits}f}{suffix}"


def _plain(value, suffix="", digits=0) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}{suffix}"


def build_context(name: str, candles: Sequence[Candle], others: dict | None = None) -> str:
    """Textul trimis agenților pentru piața ``name``. ``others``: nume -> lumânări."""
    if len(candles) < 60:
        raise ValueError(f"Prea puține zile pentru {name}: {len(candles)} (minimum 60)")
    last = candles[-1]
    window = candles[-252:]
    high, low = max(c.high for c in window), min(c.low for c in window)
    sma20, sma50, sma200 = _sma(candles, 20), _sma(candles, 50), _sma(candles, 200)
    signal = bot_signal(candles)
    lines = [
        f"Piața: {label(name)} ({name}). Ultima închidere: "
        f"{last.open_time.date().isoformat()}, preț {last.close:.4f}.",
        "Modificare pe 1/5/20/60/120 de zile: " + ", ".join(
            _fmt(_change(candles, d), "%") for d in (1, 5, 20, 60, 120)),
        f"Față de maximul și minimul ultimului an: {100 * (last.close / high - 1):+.1f}% "
        f"sub maxim, {100 * (last.close / low - 1):+.1f}% peste minim.",
        f"Volatilitate anualizată: {_plain(_volatility(candles, 20), '%')} pe 20 de zile, "
        f"{_plain(_volatility(candles, 60), '%')} pe 60.",
        "Medii mobile (prețul față de ele): " + ", ".join(
            f"SMA{d} {_fmt(100 * (last.close / m - 1) if m else None, '%')}"
            for d, m in ((20, sma20), (50, sma50), (200, sma200))),
        f"RSI(14): {_plain(_rsi(candles))}",
        "Regula simplă a botului (SMA 20/50) spune acum: "
        + {1: "cumpără", -1: "vinde", 0: "nimic"}[signal] + ".",
    ]
    if others:
        peers = []
        for other, series in sorted(others.items()):
            if other != name and (move := _change(series, 20)) is not None:
                peers.append(f"{label(other)} {move:+.1f}%")
        if peers:
            lines.append("Alte piețe, modificare pe 20 de zile: " + ", ".join(peers) + ".")
    lines += [
        f"Întrebare: cum se va mișca prețul în următoarele {HORIZON_DAYS} zile de tranzacționare?",
        "Răspunde BUY dacă urcă, SELL dacă scade, HOLD dacă nu poți decide din aceste date.",
        "Ai doar aceste prețuri: nu ai știri, rezultate sau date economice. Nu inventa. "
        "Scrie câmpul reasoning în română, în cel mult două propoziții.",
    ]
    return "\n".join(lines)
