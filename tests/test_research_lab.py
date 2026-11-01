"""Laboratorul de cercetare: fără informație din viitor, plafoane de dimensionare, verdict din regulă."""

import copy

from src.bnd import experiments as ex
from src.bnd import research_lab as rl


def world(markets=4, days=500, seed=3):
    data = rl.synthetic_universe(seed, markets=markets, days=days)
    from src.bnd import strategies
    return rl.prepare(data, lambda: strategies.sma_crossover(20, 50)), data


def test_weights_for_a_day_do_not_depend_on_later_data():
    w, _ = world()
    t = 300
    for build in (rl.sizing_equal, rl.sizing_vol_target, rl.sizing_kelly):
        before = build(w)(t)
        future = copy.deepcopy(w)
        for n in future["names"]:
            future["ret"][n][t:] = [0.5 if (i % 2) else -0.4 for i in range(len(future["ret"][n][t:]))]
            future["sig"][n][t:] = [1.0] * len(future["sig"][n][t:])
        assert build(future)(t) == before


def test_sizing_caps_hold():
    w, _ = world(markets=8)
    for t in range(250, 400, 10):
        k = rl.sizing_kelly(w)(t)
        assert all(0 <= v <= rl.KELLY_CAP + 1e-12 for v in k.values()) and sum(k.values()) <= rl.MAX_LEVERAGE + 1e-9
        v = rl.sizing_vol_target(w)(t)
        assert sum(v.values()) <= rl.MAX_LEVERAGE + 1e-9
        e = rl.sizing_equal(w)(t)
        assert sum(e.values()) <= 1 + 1e-9


def test_simulation_charges_costs_and_financing():
    w, _ = world(markets=2, days=300)
    free = rl.simulate(w, rl.sizing_equal(w), 100, cost_bps=0, financing=0)
    costly = rl.simulate(w, rl.sizing_equal(w), 100, cost_bps=50, financing=0)
    assert costly["curve"][-1][1] < free["curve"][-1][1]
    levered = lambda t: {n: 2.0 / len(w["names"]) * 1.5 for n in w["names"]}      # brut 3.0
    a = rl.simulate(w, levered, 100, cost_bps=0, financing=0)
    b = rl.simulate(w, levered, 100, cost_bps=0, financing=0.5)
    assert b["curve"][-1][1] < a["curve"][-1][1]


def test_metrics_shape():
    w, _ = world(markets=2, days=300)
    m = rl.metrics(rl.simulate(w, rl.sizing_equal(w), 100))
    assert {"cagr_pct", "sharpe", "max_drawdown_pct", "turnover_per_year"} <= set(m)
    assert rl.metrics({"returns": [0.0] * 5, "curve": [], "turnover_per_year": 0}) == {"days": 5}


def test_capital_and_meta_return_a_rule_based_verdict_on_random_data():
    _, data = world(markets=5, days=700)
    for run in (rl.run_capital, rl.run_meta):
        out = run(data, family_size=3)
        assert out["verdict"] in ex.VERDICTS and 0 <= out["p"] <= 1


def test_discovery_rates_are_fractions_and_naive_beats_corrected():
    out = rl.run_discovery(universes=3, markets=3, days=420)
    assert out["variants"] == 30
    rates = [out[k] for k in ("naive_train_pass", "bonferroni_train_pass", "oos_pass_of_selected", "bonferroni_and_oos_pass")]
    assert all(0 <= r <= 1 for r in rates)
    assert out["bonferroni_train_pass"] <= out["naive_train_pass"]
    assert out["bonferroni_and_oos_pass"] <= out["bonferroni_train_pass"]
    assert rl.discovery_verdict({"bonferroni_and_oos_pass": 0.03}) == "acceptat"
    assert rl.discovery_verdict({"bonferroni_and_oos_pass": 0.30}) == "respins"


def test_cli_refuses_unregistered_experiment(tmp_path, capsys):
    assert rl.main(["capital", "--id", "E-001", "--data-dir", str(tmp_path), "--registru", str(tmp_path / "r.jsonl")]) == 2
    capsys.readouterr()


def test_wilson_bound_and_upper_bound_verdict():
    assert rl.wilson_upper(0.0, 12) > 0.2                  # 0 din 12 nu dovedește o rată mică
    assert rl.wilson_upper(0.0, 80) < 0.05
    result = {"bonferroni_and_oos_pass": 0.0, "universes": 12}
    assert rl.discovery_verdict(result) == "acceptat"
    assert rl.discovery_verdict(result, 0.10, use_upper_bound=True) == "respins"
    assert rl.discovery_verdict({**result, "universes": 80}, 0.10, use_upper_bound=True) == "acceptat"


# --- audit #9, #12, #13, #26 ---------------------------------------------------------------

def test_execution_is_at_the_next_open_not_at_the_signal_close():
    from datetime import datetime, timedelta, timezone
    from src.bnd.market_data import Candle
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # deschidere de a doua zi cu gap față de închiderea anterioară: P&L trebuie să pornească de la deschidere
    candles = [Candle(start + timedelta(days=i), 100 + i * 2 + 1, 100 + i * 2 + 2, 100 + i * 2, 100 + i * 2 + 1.5, 1.0)
               for i in range(40)]
    w = rl.prepare({"A": candles}, lambda: __import__("src.bnd.strategies", fromlist=["x"]).buy_and_hold())
    t = 10
    assert abs(w["pnl"]["A"][t] - (candles[t + 1].open / candles[t].open - 1)) < 1e-12
    assert abs(w["pnl"]["A"][t] - w["ret"]["A"][t]) > 1e-6          # nu e randamentul închidere-închidere
    assert abs(w["pnl"]["A"][-1] - (candles[-1].close / candles[-1].open - 1)) < 1e-12


def test_costs_are_charged_on_drift_rebalancing_and_default_is_fifteen_bps():
    assert rl.COST_BPS == 15.0
    w, _ = world(markets=2, days=300)
    hold = lambda t: {n: 0.5 for n in w["names"]}                  # țintă constantă, dar prețurile derivă
    free = rl.simulate(w, hold, 100, cost_bps=0, financing=0)
    costly = rl.simulate(w, hold, 100, cost_bps=15, financing=0)
    assert costly["turnover_per_year"] > 0.5 * w["ppy"] * 0.001      # deriva generează tranzacții
    assert costly["curve"][-1][1] < free["curve"][-1][1]


def test_periods_per_year_follow_the_calendar_of_the_axis():
    from datetime import datetime, timedelta, timezone
    from src.bnd.market_data import Candle
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)                # luni
    every_day = [Candle(start + timedelta(days=i), 100, 101, 99, 100, 1.0) for i in range(730)]
    weekdays = [c for c in every_day if c.open_time.weekday() < 5]
    from src.bnd import strategies
    assert 360 < rl.prepare({"A": every_day}, strategies.buy_and_hold)["ppy"] < 370
    assert 250 < rl.prepare({"A": weekdays}, strategies.buy_and_hold)["ppy"] < 262


def test_block_t_pvalue_has_no_resolution_floor():
    from datetime import datetime, timedelta, timezone
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    import random
    rng = random.Random(1)
    a, b, ea, eb = [], [], 1.0, 1.0
    for i in range(600):
        ea *= 1 + 0.004 + rng.gauss(0, 0.005)
        eb *= 1 + rng.gauss(0, 0.005)
        a.append((start + timedelta(days=i), ea)); b.append((start + timedelta(days=i), eb))
    p = rl.block_t_pvalue(a, b)
    assert p is not None and p < 1e-5                              # sub orice prag Bonferroni (0,05/30)
    assert rl.block_t_pvalue(a[:20], b[:20]) is None


def test_control_verdict_needs_both_no_hallucination_and_power():
    ok = {"false_positive_upper_95": 0.05, "power_rate": 0.9}
    assert rl.control_verdict(ok) == "acceptat"
    assert rl.control_verdict({**ok, "power_rate": 0.1}) == "neconcludent"           # oarbă
    assert rl.control_verdict({**ok, "false_positive_upper_95": 0.3}) == "respins"   # halucinează


def test_planted_edge_is_found_more_often_than_noise():
    noise = rl.run_discovery(6, 4, 700, edge=0.0)
    strong = rl.run_discovery(6, 4, 700, edge=0.006)
    assert strong["naive_train_pass"] > noise["naive_train_pass"]


def test_plan_deviations_are_detected():
    entry = {"parametri": {"cost_bps": 5, "markets": 9, "execution": "deschidere_urmatoare"},
             "antrenare": "2015-04-16:2021-12-22", "test": "2021-12-23:2026-10-30"}
    plan = {"cost_bps": 15.0, "markets": 9, "execution": "deschidere_urmatoare",
            "antrenare": "2015-04-16:2021-12-22", "test": "2021-12-23:2026-10-30"}
    assert plan_dev(entry, plan) == ["cost_bps: înregistrat 5, rulat 15.0"]
    assert plan_dev({**entry, "parametri": {**entry["parametri"], "cost_bps": 15}}, plan) == []
    moved = plan_dev({**entry, "parametri": {**entry["parametri"], "cost_bps": 15}, "test": "2022-01-01:2026-10-30"}, plan)
    assert len(moved) == 1 and moved[0].startswith("test:")


def plan_dev(entry, plan):
    return rl.plan_deviations(entry, plan)


def test_cli_refuses_a_run_that_differs_from_the_registered_plan(tmp_path, capsys):
    registry = tmp_path / "r.jsonl"
    ex.propose(registry, titlu="t", ipoteza="i", familie="capital", tip="backtest", criteriu="c",
               parametri={"costs": "plat"}, antrenare=None, test=None)
    data = tmp_path / "d"
    data.mkdir()
    from src.bnd.market_data import save_csv
    for name, candles in rl.synthetic_universe(5, markets=3, days=700).items():
        save_csv(candles, data / f"{name}.csv")
    args = ["capital", "--id", "E-001", "--data-dir", str(data), "--registru", str(registry)]
    assert rl.main(args) == 2 and "costs: înregistrat plat, rulat pe_clasa" in capsys.readouterr().err
    assert rl.main(args + ["--accept-deviation", "costuri pe clasă"]) == 0
    state = ex.experiments(registry)["E-001"]
    assert state["stare"] == "încheiat" and "Abatere acceptată" in state["rezultat"]["concluzie"]
    capsys.readouterr()


# --- audit #19, #20 ------------------------------------------------------------------------

def test_costs_follow_the_asset_class_like_the_paper_engine():
    forex, forex_carry = rl.market_costs("EURUSD")
    index, _ = rl.market_costs("SP500")
    crypto, crypto_carry = rl.market_costs("BITCOIN")
    assert forex < index < crypto                                   # 0,7 < 3 < 15 bps
    assert abs(forex - 0.7) < 1e-9 and abs(crypto - 15.0) < 1e-9
    assert forex_carry == 0 and crypto_carry == 10.0                # carry doar la cripto
    assert rl.market_costs("NECUNOSCUT") == (rl.COST_BPS, 0.0)


def test_class_costs_and_crypto_carry_are_charged_in_the_simulation():
    from datetime import datetime, timedelta, timezone
    from src.bnd import strategies
    from src.bnd.market_data import Candle
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    flat = lambda: [Candle(start + timedelta(days=i), 100, 100, 100, 100, 1.0) for i in range(300)]
    w = rl.prepare({"BITCOIN": flat(), "EURUSD": flat()}, strategies.buy_and_hold)
    hold = lambda t: {"BITCOIN": 0.5, "EURUSD": 0.5}
    result = rl.simulate(w, hold, 100, financing=0)
    # prețuri plate: tot ce se pierde sunt costurile; carry 10%/an pe jumătate din capital ≈ 5%/an
    years = len(result["returns"]) / w["ppy"]
    loss = 1 - result["curve"][-1][1]
    assert 0.04 * years < loss < 0.07 * years
    flat_cost = rl.simulate(w, hold, 100, cost_bps=15.0, financing=0)
    assert result["curve"][-1][1] != flat_cost["curve"][-1][1]       # costul plat explicit rămâne posibil


def test_synthetic_markets_have_overnight_gaps_so_open_execution_is_testable():
    data = rl.synthetic_universe(3, markets=2, days=200)
    candles = data["S0"]
    gaps = [abs(b.open / a.close - 1) for a, b in zip(candles, candles[1:])]
    assert max(gaps) > 0.002 and all(g > 0 for g in gaps)
    w = rl.prepare(data, lambda: __import__("src.bnd.strategies", fromlist=["x"]).buy_and_hold())
    diffs = [abs(w["pnl"]["S0"][t] - w["ret"]["S0"][t]) for t in range(1, 150)]
    assert max(diffs) > 1e-4                                         # P&L la deschidere ≠ închidere-închidere


def test_power_curve_reports_the_smallest_detectable_edge():
    out = rl.run_discovery_control(null_universes=4, power_universes=4, days=600, power_edge=0.006, edges=(0.0005, 0.006))
    assert set(out["power_curve"]) == {"0.0005", "0.006"}
    assert out["power_curve"]["0.006"] >= out["power_curve"]["0.0005"]
    assert out["min_detectable_edge_annual_pct"] in (None, 0.006 * 100 * 252)
