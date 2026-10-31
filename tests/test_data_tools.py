"""Intraday, calendarul burselor, funding și rolări."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from src.bnd import calendars, funding, intraday, rolls
from src.bnd.market_data import Candle, MarketDataError

UTC = timezone.utc


def payload(stamps, opens, highs, lows, closes, volumes=None):
    volumes = volumes or [10] * len(stamps)
    return {"chart": {"result": [{"timestamp": stamps, "indicators": {"quote": [{
        "open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes}]}}]}}


def test_intraday_keeps_every_candle_of_a_day_and_drops_the_forming_one():
    base = int(datetime(2026, 10, 30, 14, 30, tzinfo=UTC).timestamp())
    stamps = [base + 3600 * i for i in range(4)]
    data = payload(stamps, [100, 101, None, 103], [101, 102, 103, 104], [99, 100, 101, 102],
                   [101, 102, 103, 104])
    now = datetime.fromtimestamp(stamps[3] + 600, UTC)            # ultima lumânare încă se formează

    candles = intraday.parse_intraday(data, "1h", now)

    assert [c.open_time.hour for c in candles] == [14, 15]        # None omis, ultima eliminată
    assert candles[0].high == 101 and len(candles) == 2


def test_intraday_rejects_bad_input():
    with pytest.raises(MarketDataError):
        intraday.parse_intraday({}, "1h")
    with pytest.raises(MarketDataError):
        intraday.parse_intraday(payload([1], [1], [1], [1], [1]), "2m")
    with pytest.raises(MarketDataError):
        intraday.fetch_intraday("SPY", "2m")
    with pytest.raises(MarketDataError, match="Prea puține"):
        intraday.parse_intraday(payload([1000], [1], [1], [1], [1]), "1h",
                                datetime(2026, 1, 1, tzinfo=UTC))


def test_calendar_us_hours_follow_daylight_saving_time():
    summer = datetime(2026, 7, 15, 13, 45, tzinfo=UTC)            # 09:45 New York
    winter_same_utc = datetime(2026, 12, 15, 13, 45, tzinfo=UTC)  # 08:45 New York

    assert calendars.is_open("us", summer) and not calendars.is_open("us", winter_same_utc)
    assert calendars.is_open("us", datetime(2026, 12, 15, 14, 45, tzinfo=UTC))


def test_calendar_weekends_holidays_forex_and_crypto():
    saturday = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
    thanksgiving = datetime(2026, 11, 26, 16, 0, tzinfo=UTC)
    assert not calendars.is_open("us", saturday) and not calendars.is_open("forex", saturday)
    assert not calendars.is_open("us", thanksgiving)
    assert calendars.is_open("crypto", saturday)
    assert calendars.is_open("forex", datetime(2026, 11, 1, 22, 30, tzinfo=UTC))      # duminică seara
    assert not calendars.is_open("forex", datetime(2026, 11, 6, 22, 30, tzinfo=UTC))  # vineri seara
    assert calendars.open_sessions(saturday) == ["crypto"]
    assert calendars.session_of("GOLD", "commodity") == "us"
    assert calendars.session_of("DAX", "index") == "xetra"
    assert calendars.session_of("BITCOIN", "crypto") == "crypto"
    with pytest.raises(ValueError):
        calendars.is_open("us", datetime(2026, 1, 1))


def test_funding_parse_and_annualise():
    rows = [{"fundingTime": 1_700_000_000_000 + i * 28_800_000, "fundingRate": "0.0001"}
            for i in range(10)]

    stats = funding.annual_funding_pct(funding.parse_funding(rows))

    assert stats["annualised_pct"] == pytest.approx(0.01 * 3 * 365)       # 10,95% pe an
    assert stats["share_positive"] == 1.0 and stats["intervals"] == 10
    with pytest.raises(ValueError):
        funding.parse_funding([{"fundingTime": "x"}])
    with pytest.raises(ValueError):
        funding.annual_funding_pct([])
    with pytest.raises(ValueError):
        funding.fetch_funding("BTC/USDT")


def candles_with_a_roll():
    start, out, price = datetime(2026, 1, 1, tzinfo=UTC), [], 100.0
    for i in range(10):
        if i == 6:
            price *= 1.10                      # saltul de rolare, +10% fără nicio mișcare reală
        out.append(Candle(start + timedelta(days=i), price, price * 1.001, price * 0.999, price, 1))
    return out


def test_roll_jumps_are_found_and_back_adjusted_away():
    series = candles_with_a_roll()

    assert rolls.detect_jumps(series) == [(date(2026, 1, 7), pytest.approx(1.10))]
    adjusted = rolls.back_adjust(series, [date(2026, 1, 7)])

    assert rolls.detect_jumps(adjusted) == []
    assert adjusted[-1].close == series[-1].close and adjusted[0].close == pytest.approx(110)
    assert rolls.back_adjust(series, []) == series
    with pytest.raises(ValueError):
        rolls.detect_jumps(series, 0)
