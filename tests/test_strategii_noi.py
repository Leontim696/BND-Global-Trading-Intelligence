"""Strategiile noi din 4.11: fără informație din viitor și logica de bază, pe date sintetice."""

from datetime import datetime, timedelta, timezone

from src.bnd import strategii_noi as sn
from src.bnd.market_data import Candle


def _series(prices, start=datetime(2020, 1, 1, tzinfo=timezone.utc)):
    return [Candle(start + timedelta(days=i), p, p * 1.01, p * 0.99, p, 1000.0) for i, p in enumerate(prices)]


def _world(prices_by_name):
    return sn.world_for({n: _series(p) for n, p in prices_by_name.items()})


def test_momentum_crypto_doar_cu_bitcoin_peste_medie():
    up = [100 * 1.01 ** i for i in range(120)]
    down = [100 * 0.99 ** i for i in range(120)]
    w = _world({"BTC": up, "A": up, "B": down})
    weights = sn.momentum_crypto(w)(100)
    assert set(weights) == {"BTC", "A"} and abs(weights["A"] - 1 / 3) < 1e-12
    w2 = _world({"BTC": down, "A": up, "B": up})
    assert sn.momentum_crypto(w2)(100) == {}            # Bitcoin sub media: bani lichizi


def test_rotatie_tine_ponderile_o_saptamana():
    prices = {f"C{i}": [100 * (1 + 0.001 * i) ** k for k in range(120)] for i in range(12)}
    prices["BTC"] = [100 * 1.01 ** k for k in range(120)]
    w = _world(prices)
    f = sn.rotatie_crypto(w)
    first = f(100)
    assert len(first) == 10 and f(103) == first


def test_final_de_luna_fereastra_si_semnal_din_trecut():
    w = _world({"SP500": [100 + i for i in range(80)], "NASDAQ100": [100 + i for i in range(80)]})
    f = sn.final_de_luna(w)
    days = w["days"]
    inside = [t for t in range(len(days)) if f(t)]
    assert all(days[t].day <= 3 or t + 1 == len(days) or days[t + 1].month != days[t].month for t in inside)


def test_rsi2_cumpara_dupa_scadere_in_trend():
    prices = [100 * 1.003 ** i for i in range(260)]
    prices[250], prices[251] = prices[249] * 0.97, prices[249] * 0.95
    w = _world({"SP500": prices, "NASDAQ100": [100 * 1.003 ** i for i in range(260)]})
    f = sn.rsi2_revenire(w)
    held = [f(t) for t in range(201, 255)]
    assert any("SP500" in h for h in held)
    assert not any("SP500" in h for h in held[:50])      # nimic înainte de scădere
