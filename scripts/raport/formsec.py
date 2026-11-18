"""Clasamentul formațiilor și leverage-ul fiecăreia (doar citire, până la 16.11)."""
import sys, json, sqlite3, math
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).parent))
from src.bnd import final_report as fr, formations as fm
from src.bnd.market_data import load_csv
import longshort as L

W = Path(sys.argv[1]); END = date.fromisoformat(__import__("os").environ.get("BND_END", "2026-11-16"))
spx = {c.open_time.date(): c.close for c in load_csv(W / "dp/zilnic/SP500.csv")}
sd = sorted(spx); up_days = {b for a, b in zip(sd, sd[1:]) if spx[b] > spx[a]}

def curve_stats(path):
    acc = fr.account(path, END)
    vals = [acc["initial"]] + [v for _, v in acc["curve"]]
    days = [None] + [date.fromisoformat(d) for d, _ in acc["curve"]]
    up_gain = sum(vals[i] - vals[i-1] for i in range(1, len(vals)) if days[i] and (days[i] - __import__("datetime").timedelta(days=1)) in up_days)
    return acc, up_gain

rows = []
official, _ = curve_stats(W / "unic.sqlite")
titles = {f["key"]: f for f in fm.FORMATIONS}
for d in sorted((W / "f").iterdir()):
    p = d / "paper.sqlite"
    if not p.exists() or d.name not in titles:
        continue
    acc, upg = curve_stats(p)
    ls = L.analyse(p)
    rows.append({"key": d.name, "title": titles[d.name]["title"], "start": acc["curve"][0][0] if acc["curve"] else None,
                 "return_pct": acc["return_pct"], "pnl": acc["final"] - acc["initial"], "final": acc["final"],
                 "dd": acc["max_drawdown_pct"], "up_gain": upg, "days": acc["days"],
                 "long_net": ls["sides"]["long"]["net"], "short_net": ls["sides"]["short"]["net"]})
rows.sort(key=lambda r: -(r["return_pct"] or -1e9))
for r in rows:
    r["eligible"] = r["dd"] <= official["max_drawdown_pct"] + 1e-9 and r["up_gain"] > 0

# leverage pe formații din deciziile încheiate ale consiliului (orizont 5 zile)
db = sqlite3.connect(f"file:{W/'registry.sqlite'}?mode=ro", uri=True)
dec = {}
for i, sym, ret, meta, settled in db.execute("select id, symbol, outcome_return, meta, settled_at from decisions"):
    m = json.loads(meta or "{}")
    dec[i] = (sym, ret if settled else None, m.get("bot_signal"), m.get("complete", True))
votes = {}
for did, agent, stage, vote in sorted(db.execute("select decision_id, agent, stage, vote from votes").fetchall(), key=lambda r: r[2] != "initial"):
    votes.setdefault(did, {})[agent] = vote
db.close()

def sign_p(w, l):
    n = w + l
    if n == 0: return None
    k = max(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)

LEVS = (2, 5, 10); FIN = 0.05 * 5 / 365; STAKE = 100.0; BASE = 10_000.0
lev_rows = []
for f in fm.FORMATIONS:
    if f["kind"] in ("meta", "intarziere"):
        lev_rows.append({"key": f["key"], "note": "nu se poate simula din voturi (meta / întârziere)"}); continue
    res = {s: {"n": 0, "w": 0, "pnl": {l: 0.0 for l in LEVS}, "liq": {l: 0 for l in LEVS}, "peak": {l: 0.0 for l in LEVS}, "dd": {l: 0.0 for l in LEVS}} for s in ("long", "short", "ambele")}
    try:
        for day in sorted({k[:10] for k in votes if k[:10] <= str(END)}):
            ids = [k for k in votes if k[:10] == day and k in dec and dec[k][3] is not False]
            todays = {dec[k][0]: votes[k] for k in ids}
            rules = {dec[k][0]: dec[k][2] for k in ids}
            sig = fm.signals_for(f, todays, fm.agent_weights(str(W/'registry.sqlite'), day), rules)
            for k in ids:
                sym, ret, _, _ = dec[k]
                s = sig.get(sym)
                if not s or ret is None or abs(ret) > 0.8 or ret == 0:
                    continue
                side = "long" if s > 0 else "short"
                mv = (1 if s > 0 else -1) * ret
                for grp in (side, "ambele"):
                    g = res[grp]; g["n"] += 1; g["w"] += mv > 0
                    for l in LEVS:
                        if mv <= -(0.9 / l):
                            g["pnl"][l] -= STAKE; g["liq"][l] += 1
                        else:
                            g["pnl"][l] += STAKE * l * mv - STAKE * (l - 1) * FIN
                        g["peak"][l] = max(g["peak"][l], g["pnl"][l])
                        g["dd"][l] = max(g["dd"][l], (g["peak"][l] - g["pnl"][l]) / (BASE + g["peak"][l]))
    except Exception as exc:
        lev_rows.append({"key": f["key"], "note": f"nu se poate simula din voturi ({type(exc).__name__})"}); continue
    row = {"key": f["key"]}
    for side in ("long", "short", "ambele"):
        g = res[side]; n, w = g["n"], g["w"]; p = sign_p(w, n - w)
        ok1 = n >= 20 and n and w / n > 0.55 and p is not None and p < 0.05
        choice = 2
        for l in (5, 10):
            if ok1 and g["liq"][l] == 0 and g["dd"][l] <= 0.25 and g["pnl"][l] > g["pnl"][2]:
                choice = l; break
        row[side] = {"n": n, "rata": (100 * w / n) if n else None, "p": p, "pnl": {l: round(g["pnl"][l], 0) for l in LEVS},
                     "lichidari": {l: g["liq"][l] for l in LEVS}, "dd": {l: round(100 * g["dd"][l], 1) for l in LEVS}, "alege": choice}
    lev_rows.append(row)
json.dump({"official": {"return_pct": official["return_pct"], "dd": official["max_drawdown_pct"]}, "rank": rows, "lev": lev_rows},
          open(W / "formsec.json", "w"), ensure_ascii=False, indent=1, default=str)
print(len(rows), "formații;", sum(r["eligible"] for r in rows), "eligibile")
for r in rows[:8]: print(r["key"], round(r["return_pct"], 2), round(r["dd"], 2), r["eligible"])
