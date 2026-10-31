"""Lumânări pe ore sau minute pentru piețe în afară de crypto (Yahoo Finance).

Yahoo dă istoric limitat: 5, 15 și 30 de minute până la 60 de zile, o oră până
la 730 de zile. Lumânarea care încă se formează se elimină. Datele sunt pentru
cercetare și pentru rapoarte în timpul zilei; testele zilnice nu depind de ele.
"""

import json
from datetime import datetime, timezone
from math import isfinite
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .market_data import YAHOO_CHART_URL, Candle, MarketDataError, validate_series

RANGES = {"5m": "60d", "15m": "60d", "30m": "60d", "1h": "730d"}
STEP_SECONDS = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600}


def parse_intraday(payload, interval: str, now: datetime | None = None) -> list[Candle]:
    """Lumânări din răspunsul Yahoo; rândurile fără preț valid se omit, high/low se corectează."""
    if interval not in RANGES:
        raise MarketDataError("Interval necunoscut: " + interval)
    now = now or datetime.now(timezone.utc)
    try:
        result = payload["chart"]["result"][0]
        stamps, quote_data = result["timestamp"], result["indicators"]["quote"][0]
        columns = [quote_data[k] for k in ("open", "high", "low", "close", "volume")]
    except (KeyError, IndexError, TypeError) as exc:
        raise MarketDataError("Răspuns Yahoo neașteptat") from exc
    candles, seen = [], set()
    for stamp, *row in zip(stamps, *columns):
        open_, high, low, close, volume = row
        values = (open_, high, low, close)
        if stamp in seen or None in values or not all(isinstance(v, (int, float)) and isfinite(v)
                                                      and v > 0 for v in values):
            continue
        seen.add(stamp)
        candles.append(Candle(datetime.fromtimestamp(stamp, timezone.utc), open_,
                              max(high, open_, close), min(low, open_, close), close,
                              volume if isinstance(volume, (int, float)) and volume >= 0 else 0.0))
    candles.sort(key=lambda c: c.open_time)
    if candles and (now - candles[-1].open_time).total_seconds() < STEP_SECONDS[interval]:
        candles.pop()                      # încă se formează
    if len(candles) < 2:
        raise MarketDataError("Prea puține lumânări intraday")
    validate_series(candles)
    return candles


def fetch_intraday(symbol: str, interval: str = "1h", timeout: float = 30.0) -> list[Candle]:
    if interval not in RANGES:
        raise MarketDataError("Interval necunoscut: " + interval)
    request = Request(f"{YAHOO_CHART_URL}{quote(symbol, safe='')}?interval={interval}"
                      f"&range={RANGES[interval]}",
                      headers={"User-Agent": "Mozilla/5.0 (BND research)"}, method="GET")
    try:
        # Reviewed: fixed https URL constant.
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            payload = json.loads(response.read(20_000_001))
    except HTTPError as exc:
        raise MarketDataError(f"Yahoo HTTP error for {symbol}: {exc.code}") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise MarketDataError(f"Yahoo request failed for {symbol}") from exc
    return parse_intraday(payload, interval)
