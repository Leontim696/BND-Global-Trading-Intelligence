"""Patru strategii noi, testate pe istoric (cerut de proprietar pe 4.11.2026). Zero cost, fără AI.

Fiecare are parametrii fixați DINAINTE, din literatura de specialitate (nu căutați pe datele noastre), și criteriul
scris în registrul de experimente înainte de rulare (E-013 … E-016):

    momentum_crypto     (E-013) momentum în timp pe crypto: o monedă se ține doar dacă a urcat în ultimele 14 zile
                        ȘI Bitcoin e peste media lui pe 50 de zile (piața crypto „pornită”); altfel bani lichizi.
                        (Liu & Tsyvinski 2021: momentum pe 1–4 săptămâni în crypto.)
    rotatie_crypto      (E-014) rotație săptămânală: cele mai puternice 10 monede după randamentul pe 28 de zile,
                        cumpărate în părți egale, doar cu Bitcoin peste media pe 50 de zile.
    final_de_luna       (E-015) efectul de final/început de lună pe indicii americani (S&P 500, Nasdaq 100): cumpărat
                        din ultima zi de tranzacționare a lunii până în a treia zi a lunii următoare, altfel lichid.
                        (Lakonishok & Smidt 1988, McConnell & Xu 2008.)
    rsi2_revenire       (E-016) revenirea după scăderi scurte (Connors): cumpără un indice când RSI pe 2 zile < 10
                        și prețul e peste media pe 200 de zile; vinde când închide peste media pe 5 zile.

Toate: doar long (fără short), fără leverage (expunere ≤ 1), costuri reale pe clasă (comision + alunecare + carry,
ca în motorul de paper), semnalul din închiderea zilei t-1 se execută la deschiderea zilei t. Reperul e „cumperi tot
în părți egale și ții”, adus la ACEEAȘI volatilitate ca strategia (o strategie care stă des în bani lichizi are
risc mai mic, deci trebuie comparată pe același risc).

    python -m src.bnd.strategii_noi --c50 crypto50/ --d12 date-12-ani/ --out rezultate.json
"""

import argparse
import json
import sys
from pathlib import Path
from statistics import mean, stdev

from . import research_lab as lab
from .significance import bootstrap_difference
from .strategies import buy_and_hold

MIN_ROWS_CRYPTO = 1090        # monede cu ~3 ani de istoric complet (aceleași zile pentru toate)
INDICES = ("SP500", "NASDAQ100")
FAMILY = 4                    # 4 strategii testate deodată → prag p < 0,05 / 4
ALPHA = 0.05 / FAMILY


def world_for(data: dict) -> dict:
    world = lab.prepare(data, buy_and_hold)
    days, index = world["days"], world["index"]
    world["close"] = {n: [data[n][index[n][d]].close for d in days] for n in world["names"]}
    return world


def _sma(values, t, n):
    """Media ultimelor n închideri până la t inclusiv; None dacă nu sunt destule."""
    return mean(values[t - n + 1:t + 1]) if t + 1 >= n else None


def _rsi2(closes, t, n=2):
    if t < n:
        return None
    gains = [max(0.0, closes[i] - closes[i - 1]) for i in range(t - n + 1, t + 1)]
    losses = [max(0.0, closes[i - 1] - closes[i]) for i in range(t - n + 1, t + 1)]
    g, l = mean(gains), mean(losses)
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


# --- strategiile (ponderi pentru ziua t, doar din date până la t-1) -------------------------------------

def momentum_crypto(world, lookback=14, regime=50, anchor="BTC"):
    names, close = world["names"], world["close"]
    n = len(names)

    def weights(t):
        d = t - 1
        btc = close.get(anchor)
        sma = _sma(btc, d, regime) if btc else None
        if sma is None or btc[d] <= sma or d < lookback:
            return {}
        return {m: 1.0 / n for m in names if close[m][d] > close[m][d - lookback]}
    return weights


def rotatie_crypto(world, lookback=28, top=10, regime=50, every=7, anchor="BTC"):
    names, close = world["names"], world["close"]
    held = {"since": None, "w": {}}

    def weights(t):
        d = t - 1
        btc = close.get(anchor)
        sma = _sma(btc, d, regime) if btc else None
        if sma is None or btc[d] <= sma or d < lookback:
            held["since"], held["w"] = None, {}
            return {}
        if held["since"] is None or t - held["since"] >= every:
            ranked = sorted(names, key=lambda m: close[m][d] / close[m][d - lookback], reverse=True)[:top]
            held["since"], held["w"] = t, {m: 1.0 / top for m in ranked}
        return held["w"]
    return weights


def final_de_luna(world, before=1, after=3):
    """Ziua t e în fereastră dacă e printre ultimele `before` zile de tranzacționare ale lunii sau primele `after`
    ale lunii următoare. Calendarul e cunoscut dinainte, deci nu e informație din viitor."""
    days, names = world["days"], world["names"]
    months = {}
    for i, d in enumerate(days):
        months.setdefault((d.year, d.month), []).append(i)
    inside = set()
    for idx in months.values():
        inside.update(idx[:after])
        inside.update(idx[-before:])

    def weights(t):
        return {m: 1.0 / len(names) for m in names} if t in inside else {}
    return weights


def rsi2_revenire(world, entry=10.0, trend=200, exit_sma=5):
    names, close = world["names"], world["close"]
    holding = {m: False for m in names}

    def weights(t):
        d = t - 1
        for m in names:
            c = close[m]
            long_trend, short = _sma(c, d, trend), _sma(c, d, exit_sma)
            if long_trend is None:
                holding[m] = False
                continue
            if holding[m]:
                if c[d] > short or c[d] < long_trend:
                    holding[m] = False
            else:
                r = _rsi2(c, d)
                if r is not None and r < entry and c[d] > long_trend:
                    holding[m] = True
        return {m: 1.0 / len(names) for m in names if holding[m]}
    return weights


def equal_weight(world, scale=1.0):
    names = world["names"]
    return lambda t: {m: scale / len(names) for m in names}


# --- evaluarea ----------------------------------------------------------------------------------------

def evaluate(world, make_weights, start) -> dict:
    """Strategia față de reperul cu aceeași volatilitate, pe toată perioada și pe cele două jumătăți (60/40)."""
    days = world["days"]
    end = len(days)
    split = start + int((end - start) * (1 - lab.TEST_SHARE))
    full = lab.simulate(world, make_weights(world), start, end)
    bench_raw = lab.simulate(world, equal_weight(world), start, end)
    vs, vb = stdev(full["returns"]), stdev(bench_raw["returns"])
    scale = vs / vb if vb > 0 else 1.0
    bench = lab.simulate(world, equal_weight(world, scale), start, end)
    parts = {}
    for label, (a, b) in {"antrenare": (start, split), "test": (split, end)}.items():
        s = lab.metrics(lab.simulate(world, make_weights(world), a, b))
        r = lab.metrics(lab.simulate(world, equal_weight(world, scale), a, b))
        parts[label] = {"strategie": s, "reper": r}
    boot = bootstrap_difference(full["curve"], bench["curve"], periods_per_year=full["ppy"])
    exposure = mean(sum(abs(v) for v in make_weights(world)(t).values()) for t in range(start, end))
    sh = lambda p, k: (parts[p][k].get("sharpe") or 0.0)
    passed = (boot["p_not_better"] < ALPHA
              and sh("antrenare", "strategie") > sh("antrenare", "reper")
              and sh("test", "strategie") > sh("test", "reper"))
    return {"perioada": [str(days[start].date()), str(days[-1].date())], "zile": end - start,
            "strategie": lab.metrics(full), "reper_aceeasi_volatilitate": lab.metrics(bench),
            "reper_1x": lab.metrics(bench_raw), "scala_reper": round(scale, 3),
            "expunere_medie": round(exposure, 3), "jumatati": parts,
            "bootstrap": boot, "prag_p": ALPHA, "verdict": "acceptat" if passed else "respins"}


def run(c50_dir, d12_dir) -> dict:
    crypto = {n: c for n, c in lab.load_markets(c50_dir).items() if len(c) >= MIN_ROWS_CRYPTO}
    out = {}
    if crypto and "BTC" in crypto:
        w = world_for(crypto)
        out["E-013 momentum_crypto"] = {**evaluate(w, momentum_crypto, lab.WARMUP), "monede": len(crypto)}
        out["E-014 rotatie_crypto"] = {**evaluate(w, rotatie_crypto, lab.WARMUP), "monede": len(crypto)}
    idx = lab.load_markets(d12_dir, list(INDICES))
    if len(idx) == len(INDICES):
        w = world_for(idx)
        out["E-015 final_de_luna"] = evaluate(w, final_de_luna, 1)
        out["E-016 rsi2_revenire"] = evaluate(w, rsi2_revenire, 201)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="strategii_noi")
    parser.add_argument("--c50", required=True, help="folderul crypto50 (date-piete)")
    parser.add_argument("--d12", required=True, help="folderul cu istoricul pe 12 ani (date-12-ani)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    result = run(args.c50, args.d12)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    for name, r in result.items():
        s, b = r["strategie"], r["reper_aceeasi_volatilitate"]
        print(f"{name}: {r['verdict']} | CAGR {s['cagr_pct']:.1f}% Sharpe {s['sharpe']:.2f} DD {s['max_drawdown_pct']:.1f}% "
              f"expunere {r['expunere_medie']:.2f} | reper {b['cagr_pct']:.1f}% Sharpe {b['sharpe']:.2f} "
              f"DD {b['max_drawdown_pct']:.1f}% | p={r["bootstrap"]["p_not_better"]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
