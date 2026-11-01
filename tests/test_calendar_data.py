import csv
from datetime import datetime, timezone

import pytest

from src.bnd import calendar_data as cal

SAMPLE = [
    {"title": "CPI m/m", "country": "USD", "date": "2026-11-12T08:30:00-05:00", "impact": "High",
     "forecast": "0.3%", "previous": "0.4%"},
    {"title": "Bank Holiday", "country": "JPY", "date": "2026-11-03T00:00:00-05:00", "impact": "Holiday",
     "forecast": "", "previous": ""},
    {"title": "Retail Sales", "country": "EUR", "date": "2026-11-13T05:00:00-05:00", "impact": "low"},
    {"country": "USD"},                                        # rând stricat
    {"title": "X", "country": "USD", "date": "nu e dată", "impact": "High"},
    {"title": "Y", "country": "USD", "date": "2026-11-12T10:00:00-05:00", "impact": "Dramatic"},
]


def test_parse_converts_to_utc_and_skips_broken_rows():
    rows = cal.parse(SAMPLE)
    assert [r[3] for r in rows] == ["Bank Holiday", "CPI m/m", "Retail Sales"]
    cpi = rows[1]
    assert cpi[1] == "2026-11-12T13:30+00:00" and cpi[4] == "High" and cpi[5] == "0.3%"
    assert rows[2][4] == "Low"


def test_parse_rejects_wrong_shapes():
    with pytest.raises(ValueError):
        cal.parse({"a": 1})
    with pytest.raises(ValueError):
        cal.parse([{"x": 1}])


def test_collect_merges_without_duplicates_and_updates_forecast(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return SAMPLE

    cal.collect(tmp_path, fetch)
    changed = [dict(SAMPLE[0], forecast="0.2%")] + SAMPLE[1:]
    status = cal.collect(tmp_path, lambda url: changed)
    rows = list(csv.DictReader((tmp_path / "calendar" / "economic.csv").open(encoding="utf-8")))
    assert len(rows) == 3                                       # fără dubluri
    assert next(r for r in rows if r["title"] == "CPI m/m")["forecast"] == "0.2%"
    assert status["sources"]["ff_calendar_thisweek"]["ok"] and len(calls) == 2


def test_one_failing_source_does_not_stop_the_other(tmp_path):
    def fetch(url):
        if "next" in url:
            raise ValueError("nu răspunde")
        return SAMPLE

    status = cal.collect(tmp_path, fetch)
    assert status["sources"]["ff_calendar_thisweek"]["ok"]
    assert not status["sources"]["ff_calendar_nextweek"]["ok"]
    assert (tmp_path / "calendar-status.json").exists()


def test_upcoming_filters_by_window_and_impact(tmp_path):
    cal.collect(tmp_path, lambda url: SAMPLE)
    path = tmp_path / "calendar" / "economic.csv"
    now = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)
    events = cal.upcoming(path, now, hours=24)
    assert [e["title"] for e in events] == ["CPI m/m"]
    assert cal.upcoming(path, now, hours=1) == []
    assert cal.upcoming(tmp_path / "lipsa.csv", now) == []
