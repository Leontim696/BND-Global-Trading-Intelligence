"""Laborator de cercetare offline pentru experimentele din registru (doar date istorice, zero cost).

Trei experimente, fiecare cu criteriul scris ÎNAINTE în ``experimente/registru.jsonl``:

- ``capital``: aceleași semnale, trei metode de dimensionare (egal, volatilitate-țintă, Kelly fracționat);
- ``meta``: alegerea strategiei pe piață ȘI regim, față de strategii fixe;
- ``descoperire``: cât de des o procedură de „descoperire” (cea mai bună dintre multe variante) găsește
  un câștigător fals pe piețe aleatorii, fără nicio regularitate de găsit.

Reguli comune: semnalul din ziua t-1 se aplică randamentului din t (fără informație din viitor); costuri
de tranzacționare pe schimbarea ponderilor; finanțare pe expunerea peste capital; perioada de test e
ultima parte, neatinsă la alegerea parametrilor; compararea cu bootstrap pe blocuri
(``significance.bootstrap_difference``) și cu pragul corectat pentru teste multiple din registru.
Verdictul se calculează din regula scrisă dinainte, nu din ce arată rezultatul.

    python -m src.bnd.research_lab capital --id E-001 --data-dir date --registru experimente/registru.jsonl
"""

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from math import sqrt
from pathlib import Path
from statistics import mean, stdev

from . import experiments, regimes, strategies
from .market_data import Candle, load_csv
from .portfolio import _History
from .significance import bootstrap_difference

DAYS = 252
TEST_SHARE = 0.4
COST_BPS = 5.0
FINANCING = 0.05
MAX_LEVERAGE = 2.0
TARGET_VOL = 0.15
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
WARMUP = 130


# --- date și semnale ---------------------------------------------------------------------

def load_markets(folder, names=None) -> dict:
    folder = Path(folder)
    names = names or sorted(p.stem for p in folder.glob("*.csv"))
    return {n: load_csv(folder / f"{n}.csv") for n in names if (folder / f"{n}.csv").exists()}


def common_axis(data: dict):
    """(zile comune sortate, {piață: {zi: index în seria proprie}})."""
    index = {n: {c.open_time: i for i, c in enumerate(cs)} for n, cs in data.items()}
    days = sorted(set.intersection(*[set(m) for m in index.values()]))
    return days, index


def signal_series(candles: list, strategy) -> list:
    """Expunerea (după închiderea fiecărei zile), tăiată la long/flat [0, 1]."""
    out = []
    for i in range(len(candles)):
        out.append(max(0.0, min(1.0, float(strategy(_History(candles, i + 1))))))
    return out


def prepare(data: dict, strategy_factory) -> dict:
    days, index = common_axis(data)
    names = sorted(data)
    close = {n: [data[n][index[n][d]].close for d in days] for n in names}
    ret = {n: [0.0] + [close[n][t] / close[n][t - 1] - 1 for t in range(1, len(days))] for n in names}
    sig = {}
    for n in names:
        full = signal_series(data[n], strategy_factory())
        sig[n] = [full[index[n][d]] for d in days]
    return {"days": days, "names": names, "ret": ret, "sig": sig, "candles": data, "index": index}


# --- simulare ------------------------------------------------------------------------------

def simulate(world: dict, weights_for_day, start: int, end: int | None = None,
             cost_bps: float = COST_BPS, financing: float = FINANCING) -> dict:
    """Curba de capital pentru zilele [start, end); ponderile zilei t folosesc doar date până la t-1."""
    names, days = world["names"], world["days"]
    end = end or len(days)
    equity, curve, previous, turnover_sum = 1.0, [(days[start - 1], 1.0)], {n: 0.0 for n in names}, 0.0
    rets = []
    for t in range(start, end):
        w = weights_for_day(t)
        gross = sum(abs(v) for v in w.values())
        turnover = sum(abs(w.get(n, 0.0) - previous[n]) for n in names)
        day = sum(w.get(n, 0.0) * world["ret"][n][t] for n in names)
        day -= turnover * cost_bps / 1e4 + max(0.0, gross - 1.0) * financing / DAYS
        equity *= 1 + day
        curve.append((days[t], equity))
        rets.append(day)
        previous = {n: w.get(n, 0.0) for n in names}
        turnover_sum += turnover
    return {"curve": curve, "returns": rets, "turnover_per_year": turnover_sum / max(1, len(rets)) * DAYS}


def metrics(result: dict) -> dict:
    r, curve = result["returns"], result["curve"]
    if len(r) < 30:
        return {"days": len(r)}
    vol = stdev(r) * sqrt(DAYS)
    peak, drawdown = 1.0, 0.0
    for _, value in curve:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    final = curve[-1][1]
    return {"days": len(r), "cagr_pct": 100 * (final ** (DAYS / len(r)) - 1), "vol_pct": 100 * vol,
            "sharpe": mean(r) * DAYS / vol if vol > 0 else None, "max_drawdown_pct": 100 * drawdown,
            "turnover_per_year": result["turnover_per_year"]}


# --- dimensionare (experimentul capital) -----------------------------------------------------

def _trailing(world, n, t, lookback):
    return world["ret"][n][max(1, t - lookback):t]


def sizing_equal(world):
    def weights(t):
        N = len(world["names"])
        return {n: world["sig"][n][t - 1] / N for n in world["names"]}
    return weights


def sizing_vol_target(world, lookback=60, target=TARGET_VOL, max_leverage=MAX_LEVERAGE):
    def weights(t):
        raw = {}
        for n in world["names"]:
            s = world["sig"][n][t - 1]
            hist = _trailing(world, n, t, lookback)
            sd = stdev(hist) if len(hist) > 5 else 0.0
            raw[n] = s / sd if s and sd > 0 else 0.0
        total = sum(raw.values())
        if total <= 0:
            return {}
        w0 = {n: v / total for n, v in raw.items()}
        series = [sum(w0[n] * world["ret"][n][k] for n in w0) for k in range(max(1, t - lookback), t)]
        sd = stdev(series) if len(series) > 5 else 0.0
        if sd <= 0:
            return {}
        scale = min(max_leverage, target / sqrt(DAYS) / sd)
        return {n: v * scale for n, v in w0.items()}
    return weights


def sizing_kelly(world, lookback=120, fraction=KELLY_FRACTION, cap=KELLY_CAP, max_leverage=MAX_LEVERAGE):
    def weights(t):
        w = {}
        for n in world["names"]:
            hist = _trailing(world, n, t, lookback)
            if world["sig"][n][t - 1] and len(hist) > 20:
                sd, mu = stdev(hist), mean(hist)
                if sd > 0 and mu > 0:
                    w[n] = min(cap, fraction * mu / (sd * sd))
        gross = sum(w.values())
        if gross > max_leverage:
            w = {n: v * max_leverage / gross for n, v in w.items()}
        return w
    return weights


def run_capital(data: dict, family_size: int = 1) -> dict:
    world = prepare(data, lambda: strategies.sma_crossover(20, 50))
    T = len(world["days"])
    split = int(T * (1 - TEST_SHARE))
    methods = {"egal": sizing_equal(world), "volatilitate_tinta": sizing_vol_target(world),
               "kelly_fractionat": sizing_kelly(world)}
    results = {}
    for name, fn in methods.items():
        results[name] = {"train": simulate(world, fn, WARMUP, split), "test": simulate(world, fn, split)}
    summary = {name: {part: metrics(res[part]) for part in res} for name, res in results.items()}
    test = {k: v["test"]["curve"] for k, v in results.items()}
    bootstrap = {}
    for rival in ("volatilitate_tinta", "egal"):
        bootstrap[f"kelly_vs_{rival}"] = bootstrap_difference(test["kelly_fractionat"], test[rival],
                                                                samples=1000, periods_per_year=DAYS)
    main = bootstrap["kelly_vs_volatilitate_tinta"]
    sharpe = {part: (summary["kelly_fractionat"][part].get("sharpe"), summary["volatilitate_tinta"][part].get("sharpe"))
              for part in ("train", "test")}
    wins = {part: a is not None and b is not None and a > b for part, (a, b) in sharpe.items()}
    threshold = experiments.ALPHA / max(1, family_size)
    # Regula (scrisă în registru): acceptat doar dacă Kelly bate volatilitatea-țintă la Sharpe în AMBELE
    # perioade și în test cu p corectat; respins dacă pierde în test; altfel neconcludent (rezultat instabil).
    if wins["train"] and wins["test"] and main["p_not_better"] <= threshold:
        verdict = "acceptat"
    elif main["mean_difference_pct_annual"] <= 0:
        verdict = "respins"
    else:
        verdict = "neconcludent"
    return {"summary": summary, "bootstrap": bootstrap, "verdict": verdict, "p": main["p_not_better"],
            "days": {"total": T, "test": T - split},
            "periods": {"train": [str(world["days"][WARMUP])[:10], str(world["days"][split - 1])[:10]],
                        "test": [str(world["days"][split])[:10], str(world["days"][-1])[:10]]}}


# --- meta-strategie pe piață × regim (experimentul meta) --------------------------------------

MEMBERS = {"sma_crossover": lambda: strategies.sma_crossover(20, 50),
           "momentum": lambda: strategies.momentum(120),
           "donchian": lambda: strategies.donchian_breakout(55, 20),
           "buy_and_hold": strategies.buy_and_hold}


def run_meta(data: dict, family_size: int = 1, lookback: int = 252, min_obs: int = 30) -> dict:
    members = {}
    for name, factory in MEMBERS.items():
        members[name] = prepare(data, factory)
    world = members["buy_and_hold"]
    T, names = len(world["days"]), world["names"]
    split = int(T * (1 - TEST_SHARE))
    labels = {n: regimes.label_regimes(data[n]) for n in names}
    label_at = {n: [labels[n].get(data[n][world["index"][n][d]].open_time) for d in world["days"]] for n in names}
    strat_ret = {m: {n: [members[m]["sig"][n][t - 1] * world["ret"][n][t] if t else 0.0 for t in range(T)]
                     for n in names} for m in members}

    def meta_weights(t):
        w = {}
        for n in names:
            regime = label_at[n][t - 1]
            best, best_mean = None, 0.0
            for m in members:
                sample = [strat_ret[m][n][k] for k in range(max(1, t - lookback), t) if label_at[n][k - 1] == regime]
                if regime is not None and len(sample) >= min_obs and mean(sample) > best_mean:
                    best, best_mean = m, mean(sample)
            if best:
                w[n] = members[best]["sig"][n][t - 1] / len(names)
        return w

    def fixed(m):
        return lambda t: {n: members[m]["sig"][n][t - 1] / len(names) for n in names}

    def combo(t):
        return {n: sum(members[m]["sig"][n][t - 1] for m in MEMBERS if m != "buy_and_hold") / 3 / len(names)
                for n in names}

    start = max(WARMUP, 230)                           # regimurile cer ~230 de zile de istoric
    train_sims = {m: simulate(world, fixed(m), start, split) for m in MEMBERS}
    best_fixed = max(train_sims, key=lambda m: (metrics(train_sims[m]).get("sharpe") or -9))
    runs = {"meta_regim": meta_weights, "combo": combo, "buy_and_hold": fixed("buy_and_hold"),
            f"fixa_aleasa_in_antrenare({best_fixed})": fixed(best_fixed)}
    test = {k: simulate(world, fn, split) for k, fn in runs.items()}
    summary = {k: metrics(v) for k, v in test.items()}
    rivals = [k for k in test if k != "meta_regim"]
    boot = {f"meta_vs_{k}": bootstrap_difference(test["meta_regim"]["curve"], test[k]["curve"],
                                                   samples=1000, periods_per_year=DAYS) for k in rivals}
    threshold = experiments.ALPHA / max(1, family_size)
    beats_all = all((summary["meta_regim"].get("sharpe") or -9) > (summary[k].get("sharpe") or -9) for k in rivals)
    worst_p = max(b["p_not_better"] for b in boot.values())
    if beats_all and worst_p <= threshold:
        verdict = "acceptat"
    elif all(b["mean_difference_pct_annual"] <= 0 for b in boot.values()):
        verdict = "respins"
    else:
        verdict = "neconcludent"
    return {"summary": summary, "bootstrap": boot, "verdict": verdict, "p": worst_p,
            "best_fixed_in_train": best_fixed, "days": {"total": T, "test": T - split}}


# --- controlul falselor descoperiri (experimentul descoperire) --------------------------------

def _variants():
    out = {}
    for fast in (5, 10, 20, 30):
        for slow in (40, 50, 100, 150, 200):
            out[f"sma_{fast}_{slow}"] = (lambda f=fast, s=slow: strategies.sma_crossover(f, s))
    for look in (20, 40, 60, 90, 120, 180):
        out[f"mom_{look}"] = (lambda L=look: strategies.momentum(L))
    for entry, exit_ in ((20, 10), (40, 20), (55, 20), (90, 30)):
        out[f"donchian_{entry}_{exit_}"] = (lambda a=entry, b=exit_: strategies.donchian_breakout(a, b))
    return out


def synthetic_universe(seed: int, markets: int = 6, days: int = 600) -> dict:
    """Piețe aleatorii (fără tendință, fără regularitate de găsit)."""
    rng = random.Random(seed)
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    data = {}
    for m in range(markets):
        price, candles = 100.0, []
        vol = 0.008 + 0.01 * rng.random()
        for d in range(days):
            new = price * (1 + rng.gauss(0.0003, vol))
            candles.append(Candle(start + timedelta(days=d), price,
                                  max(price, new), min(price, new), new, 1.0))
            price = new
        data[f"S{m}"] = candles
    return data


def run_discovery(universes: int = 12, markets: int = 6, days: int = 600, alpha: float = experiments.ALPHA) -> dict:
    variants = _variants()
    k = len(variants)
    naive_train = bonf_train = oos_pass = bonf_and_oos = 0
    for u in range(universes):
        data = synthetic_universe(1000 + u, markets, days)
        worlds = {name: prepare(data, factory) for name, factory in variants.items()}
        world = next(iter(worlds.values()))
        T = len(world["days"])
        split = int(T * (1 - TEST_SHARE))
        start = max(WARMUP, 60)

        def equal_weights(w):
            return lambda t: {n: w["sig"][n][t - 1] / len(w["names"]) for n in w["names"]}

        base = {"ret": world["ret"], "names": world["names"], "days": world["days"],
                "sig": {n: [1.0] * T for n in world["names"]}}
        bh_train = simulate(base, equal_weights(base), start, split)
        bh_test = simulate(base, equal_weights(base), split)
        train = {name: simulate(w, equal_weights(w), start, split) for name, w in worlds.items()}
        best = max(train, key=lambda name: (metrics(train[name]).get("sharpe") or -9))
        p_train = bootstrap_difference(train[best]["curve"], bh_train["curve"], samples=300, periods_per_year=DAYS)["p_not_better"]
        test = simulate(worlds[best], equal_weights(worlds[best]), split)
        p_test = bootstrap_difference(test["curve"], bh_test["curve"], samples=300, periods_per_year=DAYS)["p_not_better"]
        naive_train += p_train <= alpha
        bonf_train += p_train <= alpha / k
        oos_pass += p_test <= alpha
        bonf_and_oos += (p_train <= alpha / k) and (p_test <= alpha)
    return {"universes": universes, "variants": k, "naive_train_pass": naive_train / universes,
            "bonferroni_train_pass": bonf_train / universes, "oos_pass_of_selected": oos_pass / universes,
            "bonferroni_and_oos_pass": bonf_and_oos / universes}


def wilson_upper(rate: float, n: int, z: float = 1.96) -> float:
    """Limita superioară Wilson (95%) pentru o proporție observată: cât de rău poate fi cu n universuri."""
    if n <= 0:
        return 1.0
    centre = rate + z * z / (2 * n)
    margin = z * sqrt(rate * (1 - rate) / n + z * z / (4 * n * n))
    return (centre + margin) / (1 + z * z / n)


def discovery_verdict(result: dict, max_false_rate: float = 0.07, use_upper_bound: bool = False) -> str:
    """Procedura (Bonferroni în antrenare + confirmare în test) are voie să dea cel mult `max_false_rate` fals pozitive.

    Cu `use_upper_bound`, pragul se aplică limitei superioare Wilson 95%, nu doar ratei observate
    (cu puține universuri, 0 din 12 nu dovedește că rata reală e mică)."""
    rate = result["bonferroni_and_oos_pass"]
    value = wilson_upper(rate, result["universes"]) if use_upper_bound else rate
    return "acceptat" if value <= max_false_rate else "respins"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="research_lab")
    parser.add_argument("what", choices=["capital", "meta", "descoperire"])
    parser.add_argument("--id", required=True)
    parser.add_argument("--data-dir")
    parser.add_argument("--registru", default=str(experiments.DEFAULT_PATH))
    parser.add_argument("--markets")
    parser.add_argument("--universes", type=int, default=12)
    parser.add_argument("--no-register", action="store_true")
    parser.add_argument("--upper-bound", type=float, help="descoperire: prag aplicat limitei superioare Wilson 95%")
    args = parser.parse_args(argv)
    state = experiments.experiments(args.registru)
    if args.id not in state:
        print(f"Eroare: {args.id} nu e propus în registru (criteriul se scrie înainte)", file=sys.stderr)
        return 2
    family = experiments.family_count(state, state[args.id]["familie"])
    if args.what == "descoperire":
        result = run_discovery(args.universes)
        if args.upper_bound:
            verdict = discovery_verdict(result, args.upper_bound, use_upper_bound=True)
            result["wilson_upper_95"] = wilson_upper(result["bonferroni_and_oos_pass"], result["universes"])
        else:
            verdict = discovery_verdict(result)
        p = None
    else:
        if not args.data_dir:
            print("Eroare: --data-dir e obligatoriu", file=sys.stderr)
            return 2
        names = args.markets.split(",") if args.markets else None
        data = load_markets(args.data_dir, names)
        result = (run_capital if args.what == "capital" else run_meta)(data, family)
        verdict, p = result["verdict"], result["p"]
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    if not args.no_register:
        experiments.finish(args.registru, id=args.id, verdict=verdict,
                           concluzie=f"Verdict calculat din regula scrisă dinainte: {verdict}. Detalii în metrici.",
                           metrici=result, p_valoare=p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
