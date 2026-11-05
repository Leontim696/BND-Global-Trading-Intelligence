"""P24–P25 (cerute pe 5.11): take profit +7%/+10%, stop −2%/−3%, reciclare și redeschidere după 1 zi."""

from datetime import timedelta

import pytest

from src.bnd import formations as fm, paper_runner, recycling as rc
from tests.test_idei_4_11 import _run
from tests.test_recycling import NOW


def test_p24_p25_definite():
    by = {f["key"]: f for f in fm.FORMATIONS}
    p24, p25 = by["p24-tp7-sl2-reciclare"], by["p25-tp10-sl3-reciclare"]
    assert "--take-profit-pct 7 --stop-pct 2 --recycle reciclare --recycle-cooldown 1" in p24["settings"]
    assert "--take-profit-pct 10 --stop-pct 3 --recycle reciclare --recycle-cooldown 1" in p25["settings"]
    assert p24["members"] == p25["members"] == fm.AGENTS and p24["strategy"] == "hibrid"


@pytest.mark.parametrize("key,tp,sl", [("p24-tp7-sl2-reciclare", 7, 2), ("p25-tp10-sl3-reciclare", 10, 3)])
def test_contul_se_creeaza_cu_setarile(tmp_path, monkeypatch, key, tp, sl):
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    report = _run(tmp_path, key)
    s = report["settings"]
    assert s["take_profit_pct"] == tp and s["stop_pct"] == sl
    assert s["recycle"] == "reciclare" and s["recycle_cooldown"] == 1
    order = next(o for o in report["orders"] if o["market"] == "GOLD")
    assert order["take_profit"] == pytest.approx(order["price"] * (1 + tp / 100))
    assert order["stop_loss"] == pytest.approx(order["price"] * (1 - sl / 100))


def test_pauza_de_o_zi_permite_redeschiderea():
    fills = [{"symbol": "BTC", "quantity": -1.0, "reason": "take_profit", "time": (NOW - timedelta(hours=20)).isoformat()},
             {"symbol": "ETH", "quantity": -1.0, "reason": "take_profit", "time": (NOW - timedelta(days=2)).isoformat()}]
    # Ieșirea de ieri stă în pauză azi (capitalul ei se reciclează), cea de acum 2 zile se poate redeschide.
    assert rc.recent_exits(fills, NOW, 1) == {"BTC": 1}
    assert rc.recent_exits(fills, NOW, 5) == {"BTC": 1, "ETH": 1}


def test_pauza_negativa_respinsa():
    with pytest.raises(ValueError):
        paper_runner.RunnerConfig(recycle="reciclare", recycle_cooldown=-1)
