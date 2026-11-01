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
from math import erfc, sqrt
from pathlib import Path
from statistics import mean, stdev

from . import experiments, regimes, strategies
from .universe import UNIVERSES
from .market_data import Candle, load_csv
from .portfolio import _History
from .significance import bootstrap_difference, daily_returns

DAYS = 252
TEST_SHARE = 0.4
COST_BPS = 15.0              # 10 bps comision + 5 bps alunecare, pe valoarea tranzacționată
FINANCING = 0.05
MAX_LEVERAGE = 2.0
TARGET_VOL = 0.15

def market_costs(name: str) -> tuple[float, float]:
    """(cost în bps pe valoarea tranzacționată, carry anual în %) din clasa de activ a pieței, ca în motorul de paper.

    Piețele necunoscute (de exemplu cele sintetice) primesc costul plat COST_BPS și zero carry."""
    for markets in UNIVERSES.values():
        for market in markets:
            if market.name == name:
                return 100 * (market.fee_pct + market.slippage_pct), market.carry_pct_annual
    return COST_BPS, 0.0


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
    # Semnalul din închiderea t-1 se execută la DESCHIDEREA zilei t: profitul unei poziții luate la deschiderea t
    # e deschidere(t+1)/deschidere(t) - 1 (ultima zi: până la închidere). `ret` (închidere-închidere) rămâne doar
    # pentru statistici disponibile la momentul deciziei.
    opn = {n: [data[n][index[n][d]].open for d in days] for n in names}
    T = len(days)
    pnl = {n: [opn[n][t + 1] / opn[n][t] - 1 if t + 1 < T else close[n][t] / opn[n][t] - 1 for t in range(T)]
           for n in names}
    years = max(1e-9, (days[-1] - days[0]).days / 365.25)
    ppy = (T - 1) / years                 # ~252 pentru zile lucrătoare, ~365 dacă toate piețele sunt cripto
    sig = {}
    for n in names:
        full = signal_series(data[n], strategy_factory())
        sig[n] = [full[index[n][d]] for d in days]
    return {"days": days, "names": names, "ret": ret, "pnl": pnl, "ppy": ppy, "sig": sig, "candles": data,
            "index": index, "costs": {n: market_costs(n) for n in names}}


# --- simulare ------------------------------------------------------------------------------

def simulate(world: dict, weights_for_day, start: int, end: int | None = None,
             cost_bps: float | None = None, financing: float = FINANCING) -> dict:
    """Curba de capital pentru zilele [start, end); ponderile zilei t folosesc doar date până la t-1.

    Costuri: implicit pe clasa fiecărei piețe (comision + alunecare la fiecare tranzacție, carry anual cât timp
    poziția e deschisă, cum face motorul de paper). `cost_bps` dat explicit = cost plat pe toate piețele, fără carry."""
    names, days = world["names"], world["days"]
    ppy = world.get("ppy", DAYS)
    end = end or len(days)
    equity, curve, previous, turnover_sum = 1.0, [(days[start - 1], 1.0)], {n: 0.0 for n in names}, 0.0
    rets = []
    for t in range(start, end):
        w = weights_for_day(t)
        gross = sum(abs(v) for v in w.values())
        moves = {n: abs(w.get(n, 0.0) - previous[n]) for n in names}
        turnover = sum(moves.values())
        day = sum(w.get(n, 0.0) * world["pnl"][n][t] for n in names)
        before_costs = day
        if cost_bps is None:
            trading = sum(moves[n] * world["costs"][n][0] for n in names) / 1e4
            carry = sum(abs(w.get(n, 0.0)) * world["costs"][n][1] for n in names) / 100 / ppy
        else:
            trading, carry = turnover * cost_bps / 1e4, 0.0
        day -= trading + carry + max(0.0, gross - 1.0) * financing / ppy
        equity *= 1 + day
        curve.append((days[t], equity))
        rets.append(day)
        # Ponderile derivă cu prețurile: rebalansarea de a doua zi plătește și deriva, nu doar schimbarea țintei.
        previous = {n: w.get(n, 0.0) * (1 + world["pnl"][n][t]) / (1 + before_costs) for n in names}
        turnover_sum += turnover
    return {"curve": curve, "returns": rets, "ppy": ppy,
            "turnover_per_year": turnover_sum / max(1, len(rets)) * ppy}


def metrics(result: dict) -> dict:
    r, curve = result["returns"], result["curve"]
    if len(r) < 30:
        return {"days": len(r)}
    ppy = result.get("ppy", DAYS)
    vol = stdev(r) * sqrt(ppy)
    peak, drawdown = 1.0, 0.0
    for _, value in curve:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    final = curve[-1][1]
    return {"days": len(r), "cagr_pct": 100 * (final ** (ppy / len(r)) - 1), "vol_pct": 100 * vol,
            "sharpe": mean(r) * ppy / vol if vol > 0 else None, "max_drawdown_pct": 100 * drawdown,
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
        scale = min(max_leverage, target / sqrt(world.get("ppy", DAYS)) / sd)
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
                                                                samples=1000, periods_per_year=world["ppy"])
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
                        "test": [str(world["days"][split])[:10], str(world["days"][-1])[:10]]},
            "plan": {"execution": "deschidere_urmatoare", "costs": "pe_clasa", "financing": FINANCING,
                     "kelly_fraction": KELLY_FRACTION, "kelly_cap": KELLY_CAP, "max_leverage": MAX_LEVERAGE,
                     "vol_target": TARGET_VOL, "markets": len(world["names"]),
                     "antrenare": f"{str(world['days'][WARMUP])[:10]}:{str(world['days'][split - 1])[:10]}",
                     "test": f"{str(world['days'][split])[:10]}:{str(world['days'][-1])[:10]}"}}


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
                                                   samples=1000, periods_per_year=world["ppy"]) for k in rivals}
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
            "best_fixed_in_train": best_fixed, "days": {"total": T, "test": T - split},
            "plan": {"execution": "deschidere_urmatoare", "costs": "pe_clasa", "financing": FINANCING,
                     "lookback": lookback, "min_obs": min_obs, "markets": len(names),
                     "antrenare": f"{str(world['days'][start])[:10]}:{str(world['days'][split - 1])[:10]}",
                     "test": f"{str(world['days'][split])[:10]}:{str(world['days'][-1])[:10]}"}}


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


def synthetic_universe(seed: int, markets: int = 6, days: int = 600, edge: float = 0.0) -> dict:
    """Piețe aleatorii fără drift. `edge` > 0 plantează o regularitate reală: regimuri persistente (în medie
    60 de zile) de urcare/scădere cu drift zilnic ±edge = control pozitiv, pe care o regulă de tendință o poate găsi."""
    rng = random.Random(seed)
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    data = {}
    for m in range(markets):
        price, candles, direction = 100.0, [], 1.0
        vol = 0.008 + 0.01 * rng.random()
        for d in range(days):
            if rng.random() < 1 / 60:
                direction = -direction
            # Gap peste noapte: deschiderea diferă de închiderea precedentă (altfel execuția la deschidere
            # nu poate fi testată); regularitatea plantată se află în mișcarea din timpul zilei.
            opening = price * (1 + rng.gauss(0.0, 0.5 * vol))
            new = opening * (1 + edge * direction + rng.gauss(0.0, vol))
            candles.append(Candle(start + timedelta(days=d), opening,
                                  max(opening, new), min(opening, new), new, 1.0))
            price = new
        data[f"S{m}"] = candles
    return data


def block_t_pvalue(curve_a, curve_b, block: int = 10) -> float | None:
    """p (A nu bate B) dintr-un test t pe medii de blocuri de zile (aproximare normală).

    Spre deosebire de un bootstrap cu puține reeșantionări, p nu are un prag de rezoluție (1/samples):
    valorile mici, necesare la corecția Bonferroni, pot apărea efectiv."""
    a, b = daily_returns(curve_a), daily_returns(curve_b)
    days = sorted(set(a) & set(b))
    diffs = [a[d] - b[d] for d in days]
    means = [mean(diffs[i:i + block]) for i in range(0, len(diffs) - block + 1, block)]
    if len(means) < 5:
        return None
    sd = stdev(means)
    if sd == 0:
        return 0.0 if mean(means) > 0 else 1.0
    t = mean(means) / (sd / sqrt(len(means)))
    return 0.5 * erfc(t / sqrt(2))


def _discovery_universe(data: dict, variants: dict, alpha: float):
    k = len(variants)
    worlds = {name: prepare(data, factory) for name, factory in variants.items()}
    world = next(iter(worlds.values()))
    T = len(world["days"])
    split = int(T * (1 - TEST_SHARE))
    start = max(WARMUP, 60)

    def equal_weights(w):
        return lambda t: {n: w["sig"][n][t - 1] / len(w["names"]) for n in w["names"]}

    base = {**world, "sig": {n: [1.0] * T for n in world["names"]}}
    bh_train, bh_test = simulate(base, equal_weights(base), start, split), simulate(base, equal_weights(base), split)
    train = {name: simulate(w, equal_weights(w), start, split) for name, w in worlds.items()}
    best = max(train, key=lambda name: (metrics(train[name]).get("sharpe") or -9))
    p_train = block_t_pvalue(train[best]["curve"], bh_train["curve"])
    test = simulate(worlds[best], equal_weights(worlds[best]), split)
    p_test = block_t_pvalue(test["curve"], bh_test["curve"])
    p_train = 1.0 if p_train is None else p_train
    p_test = 1.0 if p_test is None else p_test
    return {"naive_train": p_train <= alpha, "bonf_train": p_train <= alpha / k, "oos": p_test <= alpha,
            "bonf_and_oos": (p_train <= alpha / k) and (p_test <= alpha)}


def run_discovery(universes: int = 12, markets: int = 6, days: int = 600, alpha: float = experiments.ALPHA,
                  edge: float = 0.0) -> dict:
    """Rata de 'descoperiri' pe universuri sintetice. edge=0: nimic de găsit (fals pozitive);
    edge>0: o regularitate reală (putere: procedura trebuie să o poată găsi)."""
    variants = _variants()
    outcomes = [_discovery_universe(synthetic_universe(1000 + u, markets, days, edge), variants, alpha)
                for u in range(universes)]
    rate = lambda key: sum(o[key] for o in outcomes) / universes
    return {"universes": universes, "variants": len(variants), "edge": edge,
            "naive_train_pass": rate("naive_train"), "bonferroni_train_pass": rate("bonf_train"),
            "oos_pass_of_selected": rate("oos"), "bonferroni_and_oos_pass": rate("bonf_and_oos")}


def wilson_upper(rate: float, n: int, z: float = 1.96) -> float:
    """Limita superioară Wilson (95%) pentru o proporție observată: cât de rău poate fi cu n universuri."""
    if n <= 0:
        return 1.0
    centre = rate + z * z / (2 * n)
    margin = z * sqrt(rate * (1 - rate) / n + z * z / (4 * n * n))
    return (centre + margin) / (1 + z * z / n)


POWER_EDGES = (0.001, 0.0025, 0.005)      # drift zilnic al regimului plantat (≈ 25%, 63%, 126% pe an)
REALISTIC_EDGE = POWER_EDGES[0]           # cel mai mic avantaj realist (≈ 25% pe an): pe el se decide verdictul


def run_discovery_control(null_universes: int = 80, power_universes: int = 40, days: int = 900,
                          power_edge: float = 0.005, edges=POWER_EDGES) -> dict:
    """Fără regularitate: câte descoperiri false trec? Cu regularități plantate de mărimi diferite: le găsește?

    Rezultatul include curba de putere și cea mai mică regularitate găsită în >= 80% din universuri
    (`min_detectable_edge_annual_pct`): arată cât de mare trebuie să fie un avantaj ca procedura să-l vadă."""
    null = run_discovery(null_universes, 6, days, edge=0.0)
    curve = {e: run_discovery(power_universes, 6, days, edge=e) for e in sorted(set(edges) | {power_edge})}
    power = curve[power_edge]
    realistic = curve[min(curve)]
    found = [e for e, r in curve.items() if r["bonferroni_and_oos_pass"] >= 0.8]
    return {"null": null, "power": power,
            "power_curve": {f"{e}": r["bonferroni_and_oos_pass"] for e, r in curve.items()},
            "min_detectable_edge_annual_pct": 100 * min(found) * 252 if found else None,
            "false_positive_upper_95": wilson_upper(null["bonferroni_and_oos_pass"], null["universes"]),
            "power_rate": power["bonferroni_and_oos_pass"],
            "realistic_edge": min(curve), "realistic_power_rate": realistic["bonferroni_and_oos_pass"],
            "naive_false_rate": null["naive_train_pass"]}


def control_verdict(result: dict, max_false_upper: float = 0.10, min_power: float = 0.80) -> str:
    """Acceptat doar dacă procedura NU halucinează (limita superioară a falselor pozitive) ȘI vede avantajele
    REALISTE (putere pe cel mai mic avantaj, ≈25%/an), nu doar pe unul uriaș (≈126%/an).

    Dacă vede doar avantaje mari, verdictul e „neconcludent”: nu produce falsuri, dar e oarbă la ce contează."""
    if result["false_positive_upper_95"] > max_false_upper:
        return "respins"
    power = result.get("realistic_power_rate", result["power_rate"])
    return "acceptat" if power >= min_power else "neconcludent"


def plan_deviations(entry: dict, plan: dict) -> list[str]:
    """Diferențe între ce a fost înregistrat dinainte (parametri, perioade) și ce a rulat de fapt."""
    out = []
    for key, value in (entry.get("parametri") or {}).items():
        if key in plan:
            a, b = value, plan[key]
            same = abs(a - b) < 1e-9 if isinstance(a, (int, float)) and isinstance(b, (int, float)) else a == b
            if not same:
                out.append(f"{key}: înregistrat {a}, rulat {b}")
    for key in ("antrenare", "test"):
        if entry.get(key) and plan.get(key) and entry[key] != plan[key]:
            out.append(f"{key}: înregistrat {entry[key]}, rulat {plan[key]}")
    return out


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
    parser.add_argument("--accept-deviation", help="motivul pentru care rularea diferă de planul înregistrat")
    parser.add_argument("--control", action="store_true", help="descoperire: rată de fals pozitive + putere (planul E-007)")
    parser.add_argument("--upper-bound", type=float, help="descoperire: prag aplicat limitei superioare Wilson 95%")
    args = parser.parse_args(argv)
    state = experiments.experiments(args.registru)
    if args.id not in state:
        print(f"Eroare: {args.id} nu e propus în registru (criteriul se scrie înainte)", file=sys.stderr)
        return 2
    family = experiments.family_count(state, state[args.id]["familie"])
    if args.what == "descoperire" and args.control:
        result = run_discovery_control()
        verdict, p = control_verdict(result), None
    elif args.what == "descoperire":
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
    deviations = plan_deviations(state[args.id], result["plan"]) if "plan" in result else []
    if deviations and not args.accept_deviation:
        print("Eroare: rularea diferă de planul înregistrat:\n  " + "\n  ".join(deviations)
              + "\nPropune un experiment nou sau folosește --accept-deviation cu motivul.", file=sys.stderr)
        return 2
    if deviations:
        result["deviations"] = {"list": deviations, "reason": args.accept_deviation}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    if not args.no_register:
        note = f" Abatere acceptată de la plan: {args.accept_deviation}." if deviations else ""
        experiments.finish(args.registru, id=args.id, verdict=verdict,
                           concluzie=f"Verdict calculat din regula scrisă dinainte: {verdict}. Detalii în metrici.{note}",
                           metrici=result, p_valoare=p,
                           justificare_fara_p="Control pe date sintetice, fără test statistic unic: regula folosește "
                                              "limita Wilson și puterea." if (verdict == "acceptat" and p is None) else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
