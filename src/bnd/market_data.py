"""OHLCV market data: validation, CSV storage and Binance download.

Downloads use Binance's public market-data endpoint and need no
API key. Nothing here places orders.
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
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
