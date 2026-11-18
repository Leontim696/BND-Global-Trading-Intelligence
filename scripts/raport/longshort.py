"""Long față de short pe un cont virtual (doar citire), până la sfârșitul zilei END."""
import json, sqlite3, sys
from collections import defaultdict

import os
END = os.environ.get("BND_END", "2026-11-16")

def analyse(path, end=END):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cls = {s: json.loads(sp).get("asset_class", "?") for s, sp in db.execute("select symbol, spec from instruments")}
    fills = db.execute("select symbol, quantity, price, fee, time from fills where substr(time,1,10) <= ? order by time, id", (end,)).fetchall()
    closes = {}
    for s, t, p in db.execute("select symbol, time, price from closes where substr(time,1,10) <= ? order by time", (end,)):
        closes[s] = p
    start = db.execute("select initial_capital from account").fetchone()[0]
    db.close()
    pos = defaultdict(lambda: [0.0, 0.0])        # qty, avg
    out = {side: {"realized": 0.0, "unrealized": 0.0, "fees": 0.0, "win": 0, "loss": 0} for side in ("long", "short")}
    by_class = defaultdict(lambda: {"long": 0.0, "short": 0.0})
    trades = defaultdict(float)                 # (symbol, side, episode) -> pnl
    episode = defaultdict(int)
    for s, q, p, fee, t in fills:
        qty, avg = pos[s]
        side_now = "long" if qty > 0 else "short" if qty < 0 else None
        if qty == 0 or (qty > 0) == (q > 0):    # deschide / mărește
            new = qty + q
            avg = (avg * abs(qty) + p * abs(q)) / abs(new) if new else 0.0
            side = "long" if new > 0 else "short"
            out[side]["fees"] += fee
            if qty == 0:
                episode[s] += 1
            pos[s] = [new, avg]
            trades[(s, side, episode[s])] += -fee
            continue
        close = min(abs(q), abs(qty))
        pnl = close * (p - avg) * (1 if qty > 0 else -1)
        out[side_now]["realized"] += pnl
        out[side_now]["fees"] += fee * close / abs(q)
        by_class[cls.get(s, "?")][side_now] += pnl
        trades[(s, side_now, episode[s])] += pnl - fee * close / abs(q)
        rest = qty + q
        if abs(rest) < 1e-12:
            pos[s] = [0.0, 0.0]
        elif (rest > 0) == (qty > 0):
            pos[s] = [rest, avg]
        else:                                    # trece pe partea cealaltă
            side = "long" if rest > 0 else "short"
            episode[s] += 1
            out[side]["fees"] += fee * (abs(q) - close) / abs(q)
            pos[s] = [rest, p]
    for s, (qty, avg) in pos.items():
        if qty == 0 or s not in closes:
            continue
        side = "long" if qty > 0 else "short"
        u = qty * (closes[s] - avg)
        out[side]["unrealized"] += u
        by_class[cls.get(s, "?")][side] += u
        trades[(s, side, episode[s])] += u
    for (s, side, _), v in trades.items():
        out[side]["win" if v > 0 else "loss"] += 1
    for side in out:
        o = out[side]
        o["net"] = o["realized"] + o["unrealized"] - o["fees"]
    return {"start": start, "sides": out, "by_class": dict(by_class)}

def market_baseline(path, start="2026-10-31", end=END):
    """«Long pe tot» / «short pe tot», ponderi egale, pe piețele tranzacționate de cont, aceleași zile."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    syms = [s for (s,) in db.execute("select distinct symbol from fills")]
    rets = []
    for s in syms:
        rows = db.execute("select time, price from closes where symbol=? and substr(time,1,10) between ? and ? order by time",
                          (s, "2026-10-29", end)).fetchall()
        before = [p for t, p in rows if t[:10] < start]
        after = [p for t, p in rows if t[:10] <= end]
        if before and after:
            rets.append(after[-1] / before[-1] - 1)
    db.close()
    m = sum(rets) / len(rets) if rets else 0.0
    return {"markets": len(rets), "long_all_pct": 100 * m, "short_all_pct": -100 * m,
            "up": sum(r > 0 for r in rets), "down": sum(r < 0 for r in rets)}

if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, json.dumps(analyse(p), indent=1)[:2000])
