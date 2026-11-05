"""Divizări (split) la acțiuni/ETF (5.11.2026, ITA ~3:1): poziția, stopul și ordinele se ajustează, fără câștig fals."""

from datetime import datetime, timedelta, timezone

import pytest

from src.bnd import paper_runner, splits
from src.bnd.market_data import Candle
from src.bnd.paper_engine import EngineLimits, Instrument, OrderRequest, PaperEngine

T = datetime(2026, 11, 3, tzinfo=timezone.utc)


def _c(t, price):
    return Candle(t, price, price * 1.01, price * 0.99, price, 1e6)


def _engine(tmp_path):
    e = PaperEngine.create(tmp_path / "paper.sqlite", 10000.0, currency="USD", limits=EngineLimits(), now=T)
    e.register_instrument(Instrument("ITA", "stock", sector="aparare"))
    e.on_bar("ITA", _c(T, 210.0))
    e.submit_order(OrderRequest("o1", "ITA", "SELL", 5, stop_loss=231.0, take_profit=189.0), T)
    e.on_bar("ITA", _c(T + timedelta(days=1), 212.0))          # short 5 la 212 (deschiderea)
    return e


def test_split_3_la_1_fara_castig_fals(tmp_path):
    e = _engine(tmp_path)
    try:
        before = e.equity()
        # Istoricul descărcat a doua zi e ajustat de sursă: ziua deja procesată apare la 212/3.
        data = {"ITA": [_c(T, 70.0), _c(T + timedelta(days=1), 212.0 / 3), _c(T + timedelta(days=2), 70.0)]}
        found = splits.detect(e, data)
        assert found["ITA"]["factor"] == 3
        splits.apply(e, "ITA", 3, T + timedelta(days=2), found["ITA"])
        assert e.equity() == pytest.approx(before)
        pos = e.positions()[0]
        assert pos["quantity"] == pytest.approx(-15) and pos["avg_price"] == pytest.approx(212 / 3, rel=1e-3)
        assert pos["stop_loss"] == pytest.approx(77.0) and pos["take_profit"] == pytest.approx(63.0)
        paper_runner.feed_new_candles(e, data)                    # ziua nouă, la 70: mișcare reală −1%, nu −67%
        assert abs(e.equity() - before) < 15
        assert e.journal("split")[-1]["payload"]["factor"] == 3
        from src.bnd.reconcile import reconcile
        report = reconcile(e)
        assert report["ok"], [c for c in report["checks"] if not c["ok"]]
    finally:
        e.close()


def test_fara_split_la_miscari_normale_sau_cotatii_gresite(tmp_path):
    e = _engine(tmp_path)
    try:
        normal = {"ITA": [_c(T + timedelta(days=1), 212.0 * 0.97), _c(T + timedelta(days=2), 200.0)]}
        assert splits.detect(e, normal) == {}
        # o scădere mare, dar fără raport de split (−58%), nu e luată drept split
        crash = {"ITA": [_c(T + timedelta(days=1), 212.0), _c(T + timedelta(days=2), 90.0)]}
        assert splits.detect(e, crash) == {}
    finally:
        e.close()


def test_factor_invalid(tmp_path):
    e = _engine(tmp_path)
    try:
        with pytest.raises(Exception):
            splits.apply(e, "ITA", 1.0, T)
    finally:
        e.close()


def test_runner_aplica_splitul_inainte_de_lumanarile_noi(tmp_path, monkeypatch):
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    e = _engine(tmp_path)
    try:
        data = {"ITA": [_c(T, 70.0), _c(T + timedelta(days=1), 212.0 / 3), _c(T + timedelta(days=2), 70.0)]}
        before = e.equity()
        # pasul zilnic: split detectat și aplicat, apoi lumânarea nouă
        found = splits.detect(e, data)
        for name, info in found.items():
            splits.apply(e, name, info["factor"], T + timedelta(days=2), info)
        paper_runner.feed_new_candles(e, data)
        assert abs(e.equity() - before) < 15
    finally:
        e.close()


def test_ordin_in_asteptare_peste_split(tmp_path):
    from src.bnd.reconcile import reconcile
    e = _engine(tmp_path)
    try:
        e.submit_order(OrderRequest("o2", "ITA", "SELL", 2, stop_loss=231.0), T + timedelta(days=1))
        found = splits.detect(e, {"ITA": [_c(T + timedelta(days=1), 212.0 / 3)]})
        splits.apply(e, "ITA", found["ITA"]["factor"], T + timedelta(days=2), found["ITA"])
        order = e.order("o2")
        assert order["quantity"] == pytest.approx(6) and order["stop_loss"] == pytest.approx(77.0)
        paper_runner.feed_new_candles(e, {"ITA": [_c(T + timedelta(days=2), 70.0)]})
        assert e.positions()[0]["quantity"] == pytest.approx(-21)       # 5×3 vechi + 6 noi
        report = reconcile(e)
        assert report["ok"], [c for c in report["checks"] if not c["ok"]]
    finally:
        e.close()


def test_aplicatia_ignora_pretul_live_de_split(tmp_path):
    from src.bnd import dashboard
    e = _engine(tmp_path)
    e.close()
    a = dashboard.read_account(tmp_path, "x", "x", "", {"ITA": [212.0 / 3, "2026-11-05T15:00:00+00:00"]})
    assert a["positions"][0]["last"] == a["positions"][0]["close"]
    b = dashboard.read_account(tmp_path, "x", "x", "", {"ITA": [205.0, "2026-11-05T15:00:00+00:00"]})
    assert b["positions"][0]["last"] == 205.0


def test_aplicatia_split_cu_miscare_in_aceeasi_zi(tmp_path):
    from src.bnd import dashboard
    e = _engine(tmp_path)
    e.close()
    a = dashboard.read_account(tmp_path, "x", "x", "", {"ITA": [212.0 / 3 * 0.967, "2026-11-05T15:00:00+00:00"]})
    assert a["positions"][0]["last"] == a["positions"][0]["close"]          # split 3:1 + −3,3% în ziua respectivă
    b = dashboard.read_account(tmp_path, "x", "x", "", {"ITA": [212.0 * 0.85, "2026-11-05T15:00:00+00:00"]})
    assert b["positions"][0]["last"] == pytest.approx(212.0 * 0.85)         # o scădere reală de 15% rămâne


def test_rezerva_salt_la_deschidere_cand_istoricul_nu_e_ajustat(tmp_path):
    from src.bnd.reconcile import reconcile
    e = _engine(tmp_path)
    try:
        before = e.equity()
        # Istoricul NEajustat (ziua procesată tot la 212), dar ziua nouă deschide la ~70,6 (split 3:1 + −0,1%).
        data = {"ITA": [_c(T + timedelta(days=1), 212.0), Candle(T + timedelta(days=2), 70.6, 71.0, 69.5, 70.0, 1e6)]}
        found = splits.detect(e, data)
        assert found["ITA"]["factor"] == 3 and found["ITA"]["metoda"] == "salt la deschidere"
        splits.apply(e, "ITA", 3, T + timedelta(days=2), found["ITA"])
        paper_runner.feed_new_candles(e, data)
        assert abs(e.equity() - before) < 15
        assert reconcile(e)["ok"]
    finally:
        e.close()


def test_rezerva_nu_se_aplica_la_crypto_sau_la_injumatatire(tmp_path):
    e = _engine(tmp_path)
    try:
        half = {"ITA": [_c(T + timedelta(days=1), 212.0), _c(T + timedelta(days=2), 106.0)]}
        assert splits.detect(e, half) == {}                     # −50% poate fi real: nu e tratat ca split
        e.register_instrument(Instrument("PEPE", "memecoin"))
        e.on_bar("PEPE", _c(T + timedelta(days=1), 3.0))
        assert splits.detect(e, {"PEPE": [_c(T + timedelta(days=1), 3.0), _c(T + timedelta(days=2), 1.0)]}) == {}
    finally:
        e.close()
