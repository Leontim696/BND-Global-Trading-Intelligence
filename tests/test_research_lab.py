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
