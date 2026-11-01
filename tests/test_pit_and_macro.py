"""Reguli point-in-time și colectarea de context macro (Polymarket, FRED, EDGAR)."""

import csv
import json
from datetime import datetime, timezone

import pytest

from src.bnd import macro_data as md
from src.bnd import pit

NOW = datetime(2026, 11, 1, 6, 20, tzinfo=timezone.utc)


# --- pit -----------------------------------------------------------------------------------

def test_dates_are_clamped_to_the_analysis_date_and_unpadded_dates_are_read_correctly():
    assert pit.as_of_date("2026-12-31", "2026-11-01") == "2026-11-01"
    assert pit.as_of_date("2024-7-5", "2026-11-01") == "2024-07-05"          # nu mai citește depuneri ulterioare
    assert pit.as_of_date(datetime(2026, 1, 2), "2026-11-01") == "2026-01-02"
    for bad in ("2024-13-01", "azi", "2024-07", ""):
        with pytest.raises(ValueError):
            pit.as_of_date(bad, "2026-11-01")


def test_window_ending_before_it_starts_is_an_error_not_an_empty_list():
    assert pit.window("2026-10-01", "2026-12-01", "2026-11-01") == ("2026-10-01", "2026-11-01")
    with pytest.raises(ValueError, match="înainte să înceapă"):
        pit.window("2026-10-10", "2026-10-01", "2026-11-01")


def test_in_window_excludes_the_future_and_undated_items_unless_the_window_reaches_today():
    start, end = datetime(2026, 10, 1), datetime(2026, 10, 31)
    assert pit.in_window(datetime(2026, 10, 31, 23, 0), start, end)                   # ultima zi, inclusiv
    assert not pit.in_window(datetime(2026, 11, 1, 0, 0), start, end)                 # miezul nopții de după: exclus
    assert not pit.in_window(None, start, end, now=NOW)                               # fără dată, fereastră închisă
    assert pit.in_window(None, datetime(2026, 10, 1), datetime(2026, 11, 1), now=NOW)  # fereastra ajunge în prezent


def test_filed_as_of_serves_the_vintage_that_was_current():
    rows = [{"ticker": "AAPL", "tag": "Assets", "end": "2008-09-27", "value": "39.6", "filed": "2008-11-05"},
            {"ticker": "AAPL", "tag": "Assets", "end": "2008-09-27", "value": "36.2", "filed": "2010-01-25"},
            {"ticker": "AAPL", "tag": "Assets", "end": "2009-09-26", "value": "47.5", "filed": "2009-10-27"}]
    at_2009 = {r["end"]: r["value"] for r in pit.filed_as_of(rows, "2009-12-31")}
    assert at_2009 == {"2008-09-27": "39.6", "2009-09-26": "47.5"}                   # restatarea din 2010 încă nu exista
    assert {r["end"]: r["value"] for r in pit.filed_as_of(rows, "2011-01-01")}["2008-09-27"] == "36.2"
    assert pit.filed_as_of(rows, "2008-01-01") == []


# --- parsere -------------------------------------------------------------------------------

POLY = [{"slug": "fed-cut-dec", "question": "Fed cut in December?", "outcomes": '["Yes","No"]',
         "outcomePrices": '["0.76","0.24"]', "volume": "123456.7", "endDate": "2026-12-10T00:00:00Z"},
        {"slug": "x", "question": "Bad", "outcomePrices": '["abc"]'},
        {"slug": "multi", "question": "Who wins?", "outcomes": '["A","B"]', "outcomePrices": '["0.5","0.5"]'}]


def test_polymarket_keeps_only_valid_yes_no_markets():
    rows = md.parse_polymarket(POLY, "2026-11-01")
    assert rows == [["2026-11-01|fed-cut-dec", "2026-11-01", "fed-cut-dec", "Fed cut in December?", "0.7600",
                     "123456.7", "2026-12-10"]]
    with pytest.raises(ValueError):
        md.parse_polymarket({"a": 1}, "d")
    with pytest.raises(ValueError):
        md.parse_polymarket([{"slug": "x"}], "d")


def test_fred_skips_missing_values_and_keeps_the_vintage():
    payload = {"observations": [{"date": "2026-10-01", "value": "4.33", "realtime_start": "2026-11-01"},
                                {"date": "2026-10-02", "value": ".", "realtime_start": "2026-11-01"}]}
    assert md.parse_fred(payload, "FEDFUNDS") == [["FEDFUNDS|2026-10-01|2026-11-01", "FEDFUNDS", "2026-10-01", "4.33", "2026-11-01"]]
    with pytest.raises(ValueError):
        md.parse_fred({"x": 1}, "S")
    with pytest.raises(ValueError):
        md.parse_fred({"observations": [{"date": "2026-10-02", "value": "."}]}, "S")


FACTS = {"facts": {"us-gaap": {"Assets": {"units": {"USD": [
    {"end": "2026-06-30", "val": 350000000000, "form": "10-Q", "filed": "2026-08-01"},
    {"end": "2019-06-30", "val": 1, "form": "10-K", "filed": "2019-08-01"},                  # prea vechi
    {"end": "2026-03-31", "val": "nan", "form": "10-Q", "filed": "2026-05-01"}]}},
    "Unrelated": {"units": {"USD": [{"end": "2026-06-30", "val": 5, "filed": "2026-08-01"}]}}}}}


def test_edgar_keeps_chosen_tags_with_filing_dates_and_drops_old_or_invalid_values():
    rows = md.parse_edgar_facts(FACTS, "AAPL", NOW)
    assert rows == [["AAPL|Assets|2026-06-30|2026-08-01", "AAPL", "Assets", "2026-06-30", "3.5e+11", "10-Q", "2026-08-01"]]
    with pytest.raises(ValueError):
        md.parse_edgar_facts({"facts": {"us-gaap": {}}}, "AAPL", NOW)
    assert md.parse_edgar_tickers({"0": {"cik_str": 320193, "ticker": "aapl"}}) == {"AAPL": "0000320193"}
    with pytest.raises(ValueError):
        md.parse_edgar_tickers([1])


def test_us_tickers_come_from_the_universe_and_exclude_foreign_listings():
    tickers = md.us_tickers()
    assert {"AAPL", "MSFT", "LMT", "RTX"} <= set(tickers)
    assert not any(t.endswith((".DE", ".L", ".PA", ".MI", ".ST", ".OL")) for t in tickers)


# --- colectare -----------------------------------------------------------------------------

def fake_fetch(url, **kwargs):
    if "polymarket" in url:
        return POLY
    if "stlouisfed" in url:
        return {"observations": [{"date": "2026-10-01", "value": "1.5", "realtime_start": "2026-11-01"}]}
    if "company_tickers" in url:
        return {"0": {"cik_str": 320193, "ticker": "AAPL"}}
    if "companyfacts" in url:
        return FACTS
    raise ValueError("neașteptat " + url)


def test_collect_writes_archives_and_survives_one_failing_source(tmp_path):
    status = md.collect(tmp_path, fetch_json=fake_fetch, now=NOW, fred_key="k", tickers=["AAPL", "NOPE"])
    assert all(v["ok"] for v in status["sources"].values())
    assert status["sources"]["edgar"]["missing"] == ["NOPE"]
    assert (tmp_path / "macro" / "polymarket.csv").exists() and (tmp_path / "macro" / "edgar.csv").exists()
    assert len(list(csv.DictReader((tmp_path / "macro" / "fred.csv").open()))) == len(md.FRED_SERIES)

    def failing(url, **kw):
        if "polymarket" in url:
            raise ValueError("nu răspunde")
        return fake_fetch(url)
    status = md.collect(tmp_path, fetch_json=failing, now=NOW, fred_key=None, tickers=["AAPL"])
    assert not status["sources"]["polymarket"]["ok"] and "fără cheie" in status["sources"]["fred"]["error"]
    assert status["sources"]["edgar"]["ok"]
    assert json.loads((tmp_path / "macro" / "status.json").read_text())["sources"]["polymarket"]["ok"] is False


def test_collect_is_idempotent_and_read_edgar_feeds_the_point_in_time_filter(tmp_path):
    md.collect(tmp_path, ("edgar",), fetch_json=fake_fetch, now=NOW, tickers=["AAPL"])
    md.collect(tmp_path, ("edgar",), fetch_json=fake_fetch, now=NOW, tickers=["AAPL"])
    rows = md.read_edgar(tmp_path / "macro" / "edgar.csv")
    assert len(rows) == 1
    assert pit.filed_as_of(rows, "2026-07-31") == [] and len(pit.filed_as_of(rows, "2026-08-02")) == 1


def test_cli_reports_failures_as_warnings_but_exits_zero(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(md, "collect", lambda out, only, fred_key=None: {"sources": {"polymarket": {"ok": False, "error": "rețea"}}})
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert md.main(["--out", str(tmp_path), "--only", "polymarket"]) == 0
    assert "::warning::sursa polymarket" in capsys.readouterr().out


def test_edgar_user_agent_comes_from_the_environment_and_empty_falls_back(monkeypatch):
    import importlib
    monkeypatch.setenv("EDGAR_USER_AGENT", "BND research contact@example.org")
    assert importlib.reload(md).USER_AGENT == "BND research contact@example.org"
    monkeypatch.setenv("EDGAR_USER_AGENT", "  ")
    assert "github.com" in importlib.reload(md).USER_AGENT
    monkeypatch.delenv("EDGAR_USER_AGENT")
    importlib.reload(md)
