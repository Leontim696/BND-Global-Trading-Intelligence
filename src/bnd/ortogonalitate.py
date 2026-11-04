"""R02 (lista BND 2.0, implementat pe 4.11.2026): cât de independente sunt de fapt cele 5 AI din consiliu.

Fără apeluri AI: citește voturile deja salvate (registry.sqlite) și răspunde la:
- cât de des votează fiecare pereche la fel (acord) și cât de mult peste întâmplare (kappa lui Cohen);
- corelația voturilor (BUY=+1, HOLD=0, SELL=-1) pe perechi și „numărul efectiv de AI independente”
  (N² / suma corelațiilor; 5 = complet independente, 1 = toate spun același lucru);
- contribuția marginală a fiecărui AI: cât se schimbă semnalul consiliului dacă îl scoți și dacă, fără el,
  scorul pe rezultate (decizii încheiate, sau provizoriu la prețul de acum) e mai bun sau mai slab.

Deciziile cu runda incompletă sau luate pe date vechi sunt excluse, ca în council_analytics.
Rezultatul e o măsurătoare, nu o recomandare automată: scoaterea unui AI se decide de proprietar, după 30.11.

    python -m src.bnd.ortogonalitate --registry registry.sqlite [--quotes quotes.json] --out ortogonalitate.json
"""

import argparse
import json
import sqlite3
import sys
from itertools import combinations
from pathlib import Path
from statistics import mean

from .council_analytics import _incomplete_ids, _stale_ids
from .formations import AGENTS, SIDE, formation_signal

VOTE = {"BUY": 1, "SELL": -1, "HOLD": 0}


def load(registry: str) -> dict:
    """{decizie: {"symbol", "price", "outcome", "votes": {agent: vot}}} doar pentru rundele complete și proaspete."""
    db = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    try:
        skip = _incomplete_ids(db) | _stale_ids(db)
        out = {}
        for did, sym, price, outcome in db.execute("SELECT id, symbol, price, outcome_return FROM decisions"):
            if did not in skip:
                out[did] = {"symbol": sym, "price": price, "outcome": outcome, "votes": {}}
        for did, agent, stage, vote in sorted(db.execute("SELECT decision_id, agent, stage, vote FROM votes"),
                                              key=lambda r: r[2] != "initial"):
            if did in out:
                out[did]["votes"][agent] = vote
    finally:
        db.close()
    return {k: v for k, v in out.items() if all(a in v["votes"] for a in AGENTS)}


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = mean(xs), mean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _kappa(a, b):
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    labels = set(a) | set(b)
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in labels)
    return None if pe >= 1 else (po - pe) / (1 - pe)


def pairs(decisions: dict) -> dict:
    out = {}
    for x, y in combinations(AGENTS, 2):
        a = [d["votes"][x] for d in decisions.values()]
        b = [d["votes"][y] for d in decisions.values()]
        out[f"{x}-{y}"] = {"acord": round(sum(p == q for p, q in zip(a, b)) / len(a), 3) if a else None,
                           "kappa": _round(_kappa(a, b)),
                           "corelatie": _round(_corr([VOTE[v] for v in a], [VOTE[v] for v in b]))}
    return out


def effective_agents(pair_stats: dict) -> float | None:
    """N² / (N + 2·suma corelațiilor pe perechi); corelațiile lipsă (un AI care votează mereu la fel) contează 0."""
    rhos = [max(0.0, p["corelatie"] or 0.0) for p in pair_stats.values()]
    n = len(AGENTS)
    return round(n * n / (n + 2 * sum(rhos)), 2) if rhos else None


def _outcome(d: dict, quotes: dict) -> tuple[float | None, str]:
    if d["outcome"] is not None:
        return d["outcome"], "încheiat"
    now = (quotes.get(d["symbol"]) or [0])[0]
    if now and d["price"] and d["price"] > 0 and abs(now / d["price"] - 1) <= 0.8:
        return now / d["price"] - 1, "provizoriu"
    return None, ""


def _score(decisions: dict, quotes: dict, members) -> dict:
    calls = hits = 0
    total = 0.0
    for d in decisions.values():
        s = formation_signal(d["votes"], members)
        r, _ = _outcome(d, quotes)
        if not s or r is None:
            continue
        side = 1 if s > 0 else -1
        calls += 1
        hits += side * r > 0
        total += side * r
    return {"semnale": calls, "corecte_pct": round(100 * hits / calls, 1) if calls else None,
            "medie_pct": round(100 * total / calls, 3) if calls else None}


def marginal(decisions: dict, quotes: dict) -> dict:
    """Pentru fiecare AI: cât de des scoaterea lui schimbă direcția consiliului, și scorul consiliului fără el."""
    full = _score(decisions, quotes, AGENTS)
    out = {"toti_5": full}
    for agent in AGENTS:
        rest = tuple(a for a in AGENTS if a != agent)
        changed = sum(1 for d in decisions.values()
                      if (formation_signal(d["votes"], AGENTS) > 0) != (formation_signal(d["votes"], rest) > 0)
                      or (formation_signal(d["votes"], AGENTS) < 0) != (formation_signal(d["votes"], rest) < 0))
        out[f"fara_{agent}"] = {**_score(decisions, quotes, rest),
                                "directie_schimbata_pct": round(100 * changed / len(decisions), 1) if decisions else None}
    return out


MIN_CALLS_HALF = 30


def negative_alpha(decisions: dict, quotes: dict) -> dict:
    """R09: un AI e „candidat pentru inversare” DOAR dacă a greșit în medie în AMBELE jumătăți ale perioadei
    (prima jumătate a zilelor, apoi a doua), cu ≥ 30 de voturi BUY/SELL în fiecare. Și atunci e doar candidat:
    cu 5 AI testate, un rezultat negativ persistent poate fi tot noroc; inversarea se testează separat, înainte.
    Folosește doar decizii încheiate (rezultatul la 5 zile), nu prețul de acum."""
    days = sorted({k[:10] for k in decisions})
    if len(days) < 2:
        return {"nota": "prea puține zile"}
    cut = days[len(days) // 2]
    out = {}
    for agent in AGENTS:
        halves = {"prima": [], "a_doua": []}
        for k, d in decisions.items():
            side = VOTE[d["votes"][agent]]
            # Doar decizii ÎNCHEIATE (rezultatul la 5 zile): cu prețul de acum, ambele jumătăți s-ar măsura față de
            # aceeași mișcare a pieței și o singură zi de revenire ar face orice AI „greșit constant”.
            r = d["outcome"]
            if side and r is not None:
                halves["prima" if k[:10] < cut else "a_doua"].append(side * r)
        stats = {h: {"voturi": len(v), "medie_pct": round(100 * mean(v), 3) if v else None} for h, v in halves.items()}
        enough = all(len(v) >= MIN_CALLS_HALF for v in halves.values())
        negative = enough and all(mean(v) < 0 for v in halves.values())
        out[agent] = {**stats, "candidat_inversare": bool(negative),
                      "motiv": ("negativ în ambele jumătăți" if negative else
                                "prea puține voturi" if not enough else "nu e negativ constant")}
    return {"taiere": cut, "agenti": out}


def analyse(registry: str, quotes: dict | None = None) -> dict:
    decisions = load(registry)
    quotes = quotes or {}
    settled = sum(1 for d in decisions.values() if d["outcome"] is not None)
    p = pairs(decisions)
    holds = {a: round(100 * sum(d["votes"][a] == "HOLD" for d in decisions.values()) / len(decisions), 1)
             for a in AGENTS} if decisions else {}
    return {"decizii": len(decisions), "incheiate": settled, "hold_pct": holds, "perechi": p,
            "ai_independente_efectiv": effective_agents(p), "contributie": marginal(decisions, quotes),
            "alfa_negativ": negative_alpha(decisions, quotes),
            "nota": ("Scorul folosește deciziile încheiate (5 zile) unde există, altfel prețul de acum (provizoriu). "
                     "Cu puține decizii încheiate, diferențele dintre variante sunt în mare zgomot.")}


def _round(x):
    return None if x is None else round(x, 3)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ortogonalitate")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--quotes", help="quotes.json (prețurile de acum), pentru scorul provizoriu")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    quotes = json.loads(Path(args.quotes).read_text())["quotes"] if args.quotes and Path(args.quotes).exists() else {}
    result = analyse(args.registry, quotes)
    Path(args.out).write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("decizii", "incheiate", "ai_independente_efectiv", "hold_pct")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
