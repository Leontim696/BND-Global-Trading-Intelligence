"""OHLCV market data: validation, CSV storage and Binance download.

Downloads use Binance's public market-data endpoint and need no
API key. Nothing here places orders.
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"
BINANCE_PAGE_LIMIT = 1000
CSV_FIELDS = ("open_time", "open", "high", "low", "close", "volume")


class MarketDataError(Exception):
    """Raised when market data is missing, malformed or inconsistent."""


@dataclass(frozen=True)
class Candle:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self):
        if (
            not isinstance(self.open_time, datetime)
            or self.open_time.tzinfo is None
            or self.open_time.utcoffset() is None
        ):
            raise MarketDataError("Timezone-aware open_time required")

        prices = (self.open, self.high, self.low, self.close)

        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value <= 0
            for value in prices
        ):
            raise MarketDataError("Prices must be positive and finite")

        if (
            isinstance(self.volume, bool)
            or not isinstance(self.volume, (int, float))
            or not isfinite(self.volume)
            or self.volume < 0
        ):
            raise MarketDataError("Volume must be nonnegative and finite")

        if self.high < max(self.open, self.close, self.low):
            raise MarketDataError("High is below another price")

        if self.low > min(self.open, self.close, self.high):
            raise MarketDataError("Low is above another price")


def validate_series(candles: Sequence[Candle]) -> None:
    """Require a nonempty, strictly increasing candle series."""

    if not candles:
        raise MarketDataError("No candles")

    for previous, current in zip(candles, candles[1:]):
        if current.open_time <= previous.open_time:
            raise MarketDataError(
                "Candles must be strictly increasing in time: "
                + current.open_time.isoformat()
            )


def find_gaps(
    candles: Sequence[Candle], step: timedelta | None = None
) -> list[tuple[datetime, datetime]]:
    """Return (previous, next) open times where candles are missing.

    The step defaults to the most common spacing. This suits 24/7
    markets; session-based markets need an exchange calendar.
    """

    if len(candles) < 2:
        return []

    if step is None:
        spacings = [b.open_time - a.open_time for a, b in zip(candles, candles[1:])]
        step = max(set(spacings), key=spacings.count)

    return [
        (a.open_time, b.open_time)
        for a, b in zip(candles, candles[1:])
        if b.open_time - a.open_time != step
    ]


def to_bars(candles: Sequence[Candle]):
    """Adapter from canonical candles to the quant_* walk-forward Bar."""

    from .quant_backtest import Bar

    return [Bar(candle.open, candle.close) for candle in candles]


def save_csv(candles: Sequence[Candle], path) -> None:
    validate_series(candles)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")

    with temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_FIELDS)
        for candle in candles:
            writer.writerow((
                candle.open_time.astimezone(timezone.utc).isoformat(),
                repr(candle.open),
                repr(candle.high),
                repr(candle.low),
                repr(candle.close),
                repr(candle.volume),
            ))

    temp.replace(path)


def load_csv(path) -> list[Candle]:
    path = Path(path)

    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != CSV_FIELDS:
                raise MarketDataError(
                    "CSV header must be: " + ",".join(CSV_FIELDS)
                )
            candles = []
            for line, row in enumerate(reader, start=2):
                try:
                    candles.append(Candle(
                        open_time=datetime.fromisoformat(row["open_time"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    ))
                except (TypeError, ValueError, MarketDataError) as exc:
                    raise MarketDataError(
                        f"Invalid candle on line {line}"
                    ) from exc
    except OSError as exc:
        raise MarketDataError("Cannot read " + str(path)) from exc

    validate_series(candles)
    return candles


def parse_binance_klines(rows) -> list[Candle]:
    """Convert Binance kline arrays into candles."""

    if not isinstance(rows, list):
        raise MarketDataError("Binance klines must be a list")

    candles = []

    for row in rows:
        try:
            candles.append(Candle(
                open_time=datetime.fromtimestamp(
                    int(row[0]) / 1000, tz=timezone.utc
                ),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            ))
        except (TypeError, ValueError, IndexError, OverflowError) as exc:
            raise MarketDataError("Invalid Binance kline") from exc

    return candles


def fetch_binance_klines(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    timeout: float = 30.0,
) -> list[Candle]:
    """Download closed candles with open_time in [start, end)."""

    for value in (start, end):
        if value.tzinfo is None or value.utcoffset() is None:
            raise MarketDataError("Timezone-aware start/end required")

    if end <= start:
        raise MarketDataError("End must be after start")

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000) - 1
    now = datetime.now(timezone.utc)
    candles: list[Candle] = []

    while start_ms <= end_ms:
        query = urlencode({
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": BINANCE_PAGE_LIMIT,
        })
        request = Request(BINANCE_KLINES_URL + "?" + query, method="GET")

        try:
            with urlopen(request, timeout=timeout) as response:
                rows = json.loads(response.read(5_000_001))
        except HTTPError as exc:
            raise MarketDataError(
                f"Binance HTTP error: {exc.code}"
            ) from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise MarketDataError("Binance request failed") from exc

        page = parse_binance_klines(rows)

        if not page:
            break

        candles.extend(page)
        next_ms = int(page[-1].open_time.timestamp() * 1000) + 1

        if next_ms <= start_ms:
            raise MarketDataError("Binance pagination did not advance")

        start_ms = next_ms

        if len(page) < BINANCE_PAGE_LIMIT:
            break

    # The newest candle may still be forming; keep only closed ones.
    if len(candles) >= 2:
        step = candles[-1].open_time - candles[-2].open_time
        if candles[-1].open_time + step > now:
            candles.pop()

    validate_series(candles)
    return candles


def parse_yahoo_chart(payload) -> tuple[list[Candle], dict]:
    """Daily candles from a Yahoo Finance chart response, plus a quality
    report. Rows with missing or non-positive prices are dropped (e.g.
    WTI crude settled at -37 USD on 2020-04-20); inconsistent highs and
    lows are widened to contain open and close; duplicate days keep the
    last row. Every change is counted so reports can show it.
    """

    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote_data = result["indicators"]["quote"][0]
        columns = [quote_data[key] for key in ("open", "high", "low", "close", "volume")]
    except (KeyError, IndexError, TypeError) as exc:
        raise MarketDataError("Invalid Yahoo chart response") from exc

    quality = {"rows": len(timestamps), "dropped_missing": 0,
               "dropped_non_positive": 0, "repaired_high_low": 0,
               "duplicate_days": 0}
    by_day: dict = {}
    for index, stamp in enumerate(timestamps):
        try:
            open_, high, low, close, volume = (column[index] for column in columns)
        except (IndexError, TypeError):
            quality["dropped_missing"] += 1
            continue
        if None in (stamp, open_, high, low, close):
            quality["dropped_missing"] += 1
            continue
        if min(open_, high, low, close) <= 0:
            quality["dropped_non_positive"] += 1
            continue
        fixed_high, fixed_low = max(open_, high, low, close), min(open_, high, low, close)
        if (fixed_high, fixed_low) != (high, low):
            quality["repaired_high_low"] += 1
        moment = datetime.fromtimestamp(int(stamp), tz=timezone.utc)
        day = moment.date()
        if day in by_day:
            quality["duplicate_days"] += 1
        by_day[day] = Candle(
            # One candle per UTC day, stamped at 00:00 UTC.
            datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            float(open_), float(fixed_high), float(fixed_low), float(close),
            float(volume or 0.0),
        )

    candles = [by_day[day] for day in sorted(by_day)]
    validate_series(candles)
    quality["candles"] = len(candles)
    return candles, quality


def fetch_yahoo_daily(
    symbol: str, start: datetime, end: datetime, timeout: float = 30.0
) -> tuple[list[Candle], dict]:
    """Download daily candles for forex (EURUSD=X), futures (GC=F),
    indices (^GSPC) or stocks (AAPL) from Yahoo Finance."""

    for value in (start, end):
        if value.tzinfo is None or value.utcoffset() is None:
            raise MarketDataError("Timezone-aware start/end required")
    if end <= start:
        raise MarketDataError("End must be after start")

    query = urlencode({
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
        "interval": "1d",
        "events": "history",
    })
    request = Request(
        YAHOO_CHART_URL + quote(symbol, safe="") + "?" + query,
        # Yahoo rejects requests without a browser-like user agent.
        headers={"User-Agent": "Mozilla/5.0 (BND research backtester)"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(20_000_001))
    except HTTPError as exc:
        raise MarketDataError(f"Yahoo HTTP error for {symbol}: {exc.code}") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise MarketDataError(f"Yahoo request failed for {symbol}") from exc

    candles, quality = parse_yahoo_chart(payload)
    # Today's candle is still forming until the market closes.
    if candles and candles[-1].open_time.date() >= datetime.now(timezone.utc).date():
        candles.pop()
        quality["candles"] = len(candles)
    validate_series(candles)
    return candles, quality
