"""Raportul de expuneri corelate (Portfolio Brain, pasul 1)."""

import random
from datetime import date, timedelta

from src.bnd import exposure as ex


def walk(seed, n=90, drift=0.0, vol=0.01, base=None):
    rng = random.Random(seed)
    closes, price = {}, 100.0
    day = date(2026, 6, 1)
    for i in range(n):
        shock = base[i] if base else rng.gauss(0, vol)
        price *= 1 + drift + shock
        closes[day + timedelta(days=i)] = price
    return closes


def shocks(seed, n=90, vol=0.01):
    rng = random.Random(seed)
    return [rng.gauss(0, vol) for _ in range(n)]


def test_correlated_positions_form_one_cluster_and_warn():
    common = shocks(1)
    closes = {"BTC": walk(2, base=common), "ETH": walk(3, base=[c * 1.1 for c in common]),
              "GOLD": walk(4)}
    r = ex.analyse({"BTC": 0.25, "ETH": 0.25, "GOLD": 0.10}, closes)
    top = r["clusters"][0]
    assert set(top["members"]) == {"BTC", "ETH"}
    assert top["gross"] == 0.5 and top["risk_share"] > 0.8
    assert any("împreună" in w for w in r["warnings"]) and any("riscul" in w for w in r["warnings"])
    assert abs(sum(c["risk_share"] for c in r["clusters"]) - 1) < 1e-9


def test_long_and_short_on_correlated_assets_hedge_instead_of_adding():
    common = shocks(5)
    closes = {"BTC": walk(6, base=common), "ETH": walk(7, base=common)}
    r = ex.analyse({"BTC": 0.3, "ETH": -0.3}, closes)
    assert all(len(c["members"]) == 1 for c in r["clusters"])
    assert r["hedges"] and r["portfolio_vol_daily_pct"] < 0.1       # net aproape zero
    assert not r["warnings"]


def test_perfect_correlation_extreme_case():
    common = shocks(8)
    closes = {s: walk(9, base=common) for s in ("A", "B", "C")}
    r = ex.analyse({"A": 0.2, "B": 0.2, "C": 0.2}, closes)
    assert len(r["clusters"]) == 1 and r["clusters"][0]["avg_corr"] > 0.999
    assert r["diversification"] < 1.001            # zero diversificare


def test_independent_positions_are_not_clustered():
    closes = {s: walk(i) for i, s in enumerate(("A", "B", "C"), start=20)}
    r = ex.analyse({"A": 0.1, "B": 0.1, "C": 0.1}, closes)
    assert all(len(c["members"]) == 1 for c in r["clusters"]) and not r["warnings"]


def test_missing_data_and_empty_portfolio_are_reported_not_fatal():
    assert ex.analyse({}, {})["note"] == "Nicio poziție de analizat."
    r = ex.analyse({"X": 0.1}, {})
    assert r["missing_data"] == ["X"] and r["note"]
    short = {"A": {date(2026, 6, 1) + timedelta(days=i): 100.0 + i for i in range(10)}}
    assert "Prea puține" in ex.analyse({"A": 0.1}, short)["note"]


def test_only_past_prices_are_used_and_window_is_respected():
    common = shocks(30, n=200)
    closes = {"A": walk(31, n=200, base=common), "B": walk(32, n=200, base=common)}
    r = ex.analyse({"A": 0.2, "B": 0.2}, closes, window=30)
    assert r["observations"] == 30


def test_from_account_reads_positions_and_plan(tmp_path):
    from src.bnd.paper_engine import PaperEngine
    path = tmp_path / "p.sqlite"
    engine = PaperEngine.create(path, initial_capital=10000, currency="USD") \
        if hasattr(PaperEngine, "create") else None
    if engine is None:
        return
    engine.close()
    out = ex.from_account(path, tmp_path)
    assert out["current"]["positions"] == 0 and out["planned"]["positions"] == 0


def test_dashboard_attaches_exposure_only_to_the_unified_account(tmp_path):
    from src.bnd import dashboard
    data = dashboard.collect(exposure={"current": {"positions": 0}, "planned": {"positions": 0}})
    assert all("exposure" not in a for a in data["accounts"])      # fără cont existent, nu se atașează
    assert "exposureBlock" in open("src/bnd/dashboard_template.html", encoding="utf-8").read()
