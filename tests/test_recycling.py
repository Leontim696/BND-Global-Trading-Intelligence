"""Adaptive Position Recycling: pauza după TP/stop, reciclarea cu protecții și blocările."""

from datetime import datetime, timedelta, timezone

from src.bnd import recycling as rc
from src.bnd.market_data import Candle

NOW = datetime(2026, 11, 5, 23, 0, tzinfo=timezone.utc)


def _candles(steps, start=100.0):
    out, p = [], start
    t0 = NOW - timedelta(days=len(steps) + 1)
    for i, r in enumerate(steps):
        p *= 1 + r
        out.append(Candle(t0 + timedelta(days=i), p, p, p, p, 1.0))
    return out


def _noise(seed, n=80):
    import random
    rng = random.Random(seed)
    return [rng.gauss(0, 0.02) for _ in range(n)]


def test_iesirile_recente_si_directia():
    fills = [{"symbol": "BTC", "quantity": -1.0, "reason": "take_profit", "time": (NOW - timedelta(days=1)).isoformat()},
             {"symbol": "ETH", "quantity": 2.0, "reason": "stop_loss", "time": (NOW - timedelta(days=2)).isoformat()},
             {"symbol": "SOL", "quantity": -1.0, "reason": "order", "time": NOW.isoformat()},
             {"symbol": "XRP", "quantity": -1.0, "reason": "stop_loss", "time": (NOW - timedelta(days=9)).isoformat()}]
    assert rc.recent_exits(fills, NOW, 5) == {"BTC": 1, "ETH": -1}


def test_obisnuit_lasa_capitalul_lichid():
    rules = rc.RecycleRules(mode="obisnuit")
    w, info = rc.adjust({"BTC": 0.2, "ETH": 0.1}, {"BTC": 1, "ETH": 1, "GOLD": 1}, {}, {"BTC": 1}, rules, 0.25, 2.0)
    assert w["BTC"] == 0.0 and w["ETH"] == 0.1 and "GOLD" not in w
    assert info["freed"] == 0.2 and info["reassigned"] == 0.0


def test_reciclare_muta_capitalul_pe_semnalul_urmator():
    data = {m: _candles(_noise(i)) for i, m in enumerate(("BTC", "ETH", "GOLD", "OIL"))}
    rules = rc.RecycleRules(mode="reciclare")
    w, info = rc.adjust({"BTC": 0.2, "ETH": 0.1}, {"BTC": 1, "ETH": 0.5, "GOLD": 1, "OIL": -1},
                        data, {"BTC": 1}, rules, 0.25, 2.0)
    assert w["BTC"] == 0.0
    assert abs(info["reassigned"] - 0.2) < 1e-9
    assert set(info["added"]) <= {"GOLD", "OIL", "ETH"}
    assert sum(abs(v) for v in w.values()) <= 2.0 + 1e-9 and all(abs(v) <= 0.25 + 1e-9 for v in w.values())


def test_protectie_la_corelatie():
    base = _noise(1)
    data = {"A": _candles(base), "B": _candles(base), "X": _candles(_noise(2))}   # A și B identice
    rules = rc.RecycleRules(mode="reciclare", max_cluster=0.3)
    w, info = rc.adjust({"A": 0.3, "X": 0.2}, {"A": 1, "B": 1, "X": 1}, data, {"X": 1}, rules, 0.25, 2.0)
    assert "B" in info["skipped_correlation"] and "B" not in info["added"]


def test_blocari():
    rules = rc.RecycleRules(mode="reciclare")
    assert rc.guard([100, 97.5], 100, rules).startswith("pierdere zilnică")
    assert "ultimele 10" in rc.guard([100, 99.5, 99, 98.5, 98.4, 98, 97.6, 97.3, 97, 96.95, 96.9], 100, rules)
    assert "sub vârf" in rc.guard([92, 91.9], 100, rules)
    assert rc.guard([100, 100.5], 101, rules) is None
    w, info = rc.adjust({"BTC": 0.2}, {"BTC": 1, "GOLD": 1}, {"GOLD": _candles(_noise(3))}, {"BTC": 1},
                        rules, 0.25, 2.0, blocked="pierdere zilnică ≥ 2%")
    assert info["blocked"] and info["reassigned"] == 0.0 and "GOLD" not in w
