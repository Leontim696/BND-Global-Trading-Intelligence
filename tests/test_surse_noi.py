"""Surse noi (5.11): Deribit, poziționare OKX, COT CFTC, DefiLlama — doar colectare, cu răspunsuri simulate."""

import csv
import json
from datetime import datetime, timezone

from src.bnd import surse_noi as sn

NOW = datetime(2026, 11, 5, 23, 45, tzinfo=timezone.utc)
MS = int(datetime(2026, 11, 4, tzinfo=timezone.utc).timestamp() * 1000)


def _fake(url):
    if "get_volatility_index_data" in url:
        return {"result": {"data": [[MS, 50, 52, 49, 51.234], [MS - 86400000, 48, 50, 47, 49.0]]}}
    if "get_book_summary_by_currency" in url:
        return {"result": [{"instrument_name": "BTC-27DEC26-100000-C", "open_interest": 300, "volume": 20},
                           {"instrument_name": "BTC-27DEC26-80000-P", "open_interest": 150, "volume": 30}]}
    if "open-interest-volume" in url:
        return {"code": "0", "data": [[str(MS), "1000", "500"]]}
    if "long-short-account-ratio" in url:
        return {"code": "0", "data": [[str(MS), "1.8"]]}
    if "taker-volume" in url:
        return {"code": "0", "data": [[str(MS), "40", "60"]]}
    if "publicreporting.cftc.gov" in url:
        if "088691" not in url:
            return []
        return [{"report_date_as_yyyy_mm_dd": "2026-11-03T00:00:00.000", "open_interest_all": "500000",
                 "noncomm_positions_long_all": "250000", "noncomm_positions_short_all": "50000",
                 "comm_positions_long_all": "100000", "comm_positions_short_all": "300000"}]
    if "stablecoincharts" in url:
        return [{"date": str(MS // 1000), "totalCirculatingUSD": {"peggedUSD": 3.1e11}}]
    if "historicalChainTvl" in url:
        return [{"date": MS // 1000, "tvl": 1.2e11}]
    raise ValueError("necunoscut")


def _rows(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


def test_colectare_completa(tmp_path):
    status = sn.collect(tmp_path, _fake, NOW)
    s = status["sources"]
    assert s["deribit_dvol_BTC"]["ok"] and s["deribit_optiuni_ETH"]["ok"] and s["pozitionare_DOGE"]["ok"]
    assert s["cot_GOLD"]["ok"] and not s["cot_SILVER"]["ok"] and s["defi_tvl"]["ok"]
    assert _rows(tmp_path / "deribit" / "dvol_BTC.csv")[-1] == ["2026-11-04", "51.23"]
    assert _rows(tmp_path / "deribit" / "optiuni_BTC.csv")[1] == ["2026-11-05", "0.5", "1.5", "450.0"]
    assert _rows(tmp_path / "pozitionare" / "BITCOIN.csv")[1] == ["2026-11-04", "1000", "500", "1.8", "60", "40"]
    assert _rows(tmp_path / "cot" / "GOLD.csv")[1][4] == "200000.0"
    assert json.loads((tmp_path / "surse-noi-status.json").read_text())["time"].startswith("2026-11-05")


def test_a_doua_rulare_nu_dubleaza(tmp_path):
    sn.collect(tmp_path, _fake, NOW)
    status = sn.collect(tmp_path, _fake, NOW)
    assert status["sources"]["deribit_dvol_BTC"]["added"] == 0
    assert len(_rows(tmp_path / "defi" / "stablecoins.csv")) == 2


def test_o_sursa_cazuta_nu_le_opreste_pe_celelalte(tmp_path):
    def broken(url):
        if "deribit" in url:
            raise ValueError("deribit nu răspunde")
        return _fake(url)
    s = sn.collect(tmp_path, broken, NOW)["sources"]
    assert not s["deribit_dvol_BTC"]["ok"] and "deribit" in s["deribit_dvol_BTC"]["error"]
    assert s["pozitionare_BITCOIN"]["ok"] and s["defi_stablecoins"]["ok"]


def test_okx_eroare_si_cftc_url():
    import pytest
    with pytest.raises(ValueError):
        sn.parse_okx_rows({"code": "51001", "msg": "Instrument ID does not exist", "data": []})
    url = sn.cot_url("13874A", "2023-11-05")
    assert url.startswith(sn.CFTC) and "13874A" in url and "%24where" in url


def test_main_raporteaza_fara_sa_pice(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sn, "_get_json", lambda url: (_ for _ in ()).throw(ValueError("offline")))
    monkeypatch.setattr(sn.collect, "__defaults__", (lambda url: (_ for _ in ()).throw(ValueError("offline")), None))
    assert sn.main(["--out", str(tmp_path)]) == 0
    assert "::warning::" in capsys.readouterr().out
