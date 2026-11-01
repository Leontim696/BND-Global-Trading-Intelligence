"""Fear & Greed și funding: colectare best-effort, fără rețea în test."""

import json
from datetime import datetime, timezone

import pytest

from src.bnd import context_data as cd

FNG = {"data": [{"value": "25", "value_classification": "Extreme Fear", "timestamp": "1761868800"},
                {"value": "31", "value_classification": "Fear", "timestamp": "1761782400"}]}
OKX = {"data": [{"fundingTime": "1761897600000", "fundingRate": "0.0001"},
                {"fundingTime": "1761868800000", "fundingRate": "-0.00005"}]}


def fake_json(url, timeout=30.0):
    if "alternative.me" in url:
        return FNG
    if "okx.com" in url:
        return OKX
    raise ValueError("necunoscut")


def blocked_binance(symbol, days=10, timeout=30.0):
    raise ValueError("Binance nu răspunde pentru funding")


def test_parsers_validate_and_sort():
    assert cd.parse_fear_greed(FNG)[0][1] == 31 and cd.parse_fear_greed(FNG)[-1][1] == 25
    assert cd.parse_okx(OKX)[0][1] == -0.00005
    with pytest.raises(ValueError):
        cd.parse_fear_greed({"data": [{"value": "150", "timestamp": "1"}]})
    with pytest.raises(ValueError):
        cd.parse_okx({"oops": 1})


def test_blocked_binance_falls_back_to_okx_and_files_grow_without_duplicates(tmp_path):
    first = cd.collect(tmp_path, fake_json, blocked_binance)
    second = cd.collect(tmp_path, fake_json, blocked_binance)

    assert first["sources"]["fear_greed"]["ok"] and first["sources"]["funding_BITCOIN"]["source"] == "okx"
    assert "binance_error" in first["sources"]["funding_BITCOIN"]
    assert second["sources"]["funding_BITCOIN"]["added"] == 0           # fără dubluri
    lines = (tmp_path / "funding" / "BITCOIN.csv").read_text().splitlines()
    assert lines[0] == "time,rate,source" and len(lines) == 3
    assert len((tmp_path / "sentiment" / "fear_greed.csv").read_text().splitlines()) == 3


def test_binance_is_used_when_it_works_and_one_failed_source_does_not_stop_the_rest(tmp_path):
    def binance(symbol, days=10, timeout=30.0):
        return [(datetime(2026, 11, 1, tzinfo=timezone.utc), 0.0002)]

    def partly_down(url, timeout=30.0):
        if "alternative.me" in url:
            raise ValueError("căzut")
        return OKX

    status = cd.collect(tmp_path, partly_down, binance)

    assert not status["sources"]["fear_greed"]["ok"]
    assert status["sources"]["funding_XRP"]["source"] == "binance"
    assert json.loads((tmp_path / "context-status.json").read_text())["sources"]["fear_greed"]["ok"] is False


def test_everything_down_still_writes_a_status_file(tmp_path):
    def dead(url, timeout=30.0):
        raise ValueError("fără rețea")

    status = cd.collect(tmp_path, dead, blocked_binance)

    assert not any(v["ok"] for v in status["sources"].values())
    assert (tmp_path / "context-status.json").exists()
