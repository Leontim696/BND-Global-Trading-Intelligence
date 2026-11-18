"""Simulare pe istoric (gratuită, fără AI): semnalele regulii regime_switch pe piețele din date-piete/zilnic."""
import sys, json
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.bnd.market_data import load_csv
from src.bnd.strategies import regime_switch

DIR = sys.argv[1]
MARKETS = ["SP500", "NASDAQ100", "GOLD", "SILVER", "CRUDE_OIL", "BITCOIN", "ETHEREUM", "EURUSD", "USDJPY",
           "US10Y_NOTE", "SOLANA", "BNB", "XRP"]
FIN = 0.05 / 365

series = {}
for m in MARKETS:
    c = load_csv(f"{DIR}/{m}.csv")
    strat = regime_switch()
    sig = {}
    for i in range(len(c)):
        sig[c[i].open_time.date()] = strat(c[: i + 1])
    closes = {x.open_time.date(): x.close for x in c}
    series[m] = (closes, sig)
days = sorted(set().union(*[set(s[0]) for s in series.values()]))
# randamente zilnice și semnalul din ziua anterioară
rows = []
for a, b in zip(days, days[1:]):
    r = {}
    for m, (cl, sg) in series.items():
        if a in cl and b in cl and a in sg and cl[a] > 0:
            r[m] = (cl[b] / cl[a] - 1, sg[a])
    if r:
        rows.append((b, r))
spx = series["SP500"][0]

def stats(daily, label, extra=None):
    eq, peak, dd, months = 1.0, 1.0, 0.0, defaultdict(lambda: 1.0)
    for d, x in daily:
        eq *= 1 + x
        peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
        months[(d.year, d.month)] *= 1 + x
    mret = [v - 1 for v in months.values()]
    xs = [x for _, x in daily]
    out = {"varianta": label, "zile": len(xs), "castig_mediu_luna_pct": 100 * sum(mret) / len(mret),
           "cea_mai_buna_zi_pct": 100 * max(xs), "cea_mai_rea_zi_pct": 100 * min(xs),
           "pierdere_maxima_pct": 100 * dd, "total_pct": 100 * (eq - 1)}
    if extra: out.update(extra)
    return out

results = []
# prudent / ca acum / agresiv: long+short, expunere brută 0,6 / 1,2 / 2,4 împărțită egal pe piețele cu semnal
for label, gross in (("prudent (0,6×)", 0.6), ("ca acum (1,2×)", 1.2), ("agresiv (2,4×)", 2.4)):
    daily, fin_tot = [], 0.0
    for d, r in rows:
        act = {m: (ret, s) for m, (ret, s) in r.items() if s}
        if not act:
            daily.append((d, 0.0)); continue
        w = gross / len(r)
        x = sum(w * s * ret for ret, s in act.values())
        g = w * sum(abs(s) for _, s in act.values())
        fin = max(0.0, g - 1) * FIN
        fin_tot += fin
        daily.append((d, x - fin))
    results.append(stats(daily, label, {"cost_finantare_pct": 100 * fin_tot}))

# 5x / 10x doar long sau doar short: fiecare piață are 1/N din cont; lichidare = mizia piețe pierdută și NU se reface
for side in (1, -1):
    for lev in (5, 10):
        thr = -(1 - 0.1) / lev
        sleeve = {m: 1.0 / len(MARKETS) for m in MARKETS}
        liq, fin_tot, daily, up_pnl, down_pnl = 0, 0.0, [], 0.0, 0.0
        eq_prev = 1.0
        for d, r in rows:
            for m, (ret, s) in r.items():
                if sleeve[m] <= 0 or s * side <= 0:
                    continue
                move = side * ret
                fin = (lev - 1) * FIN * sleeve[m]
                fin_tot += fin
                if move <= thr:
                    sleeve[m] = 0.0; liq += 1
                else:
                    sleeve[m] = max(0.0, sleeve[m] * (1 + lev * move) - fin)
            eq = sum(sleeve.values())
            x = eq / eq_prev - 1 if eq_prev > 0 else 0.0
            pm = [p for p in spx if p <= d]
            if len(pm) >= 21 and spx[pm[-1]] > spx[pm[-21]]:
                up_pnl += eq - eq_prev
            else:
                down_pnl += eq - eq_prev
            daily.append((d, x)); eq_prev = eq
        results.append(stats(daily, f"{lev}x doar {'long' if side > 0 else 'short'}",
                             {"lichidari": liq, "cost_finantare_pct": 100 * fin_tot,
                              "in_luni_cu_SP500_in_crestere_pct": 100 * up_pnl,
                              "in_luni_cu_SP500_in_scadere_pct": 100 * down_pnl,
                              "cont_ramas_pct": 100 * eq_prev}))
print(json.dumps({"de_la": str(rows[0][0]), "pana_la": str(rows[-1][0]), "piete": MARKETS, "rezultate": results},
                 ensure_ascii=False, indent=1))
