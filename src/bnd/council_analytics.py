"""Analiza deciziilor încheiate ale consiliului AI: doar citire, nu tranzacționează.

Pornește din registrul de decizii (voturi inițiale și finale, rezultatul la 5 zile)
și răspunde la: cine a avut dreptate (pe piață și clasă), cât ar fi câștigat
recomandările lui, cât de bine e calibrată încrederea declarată, când HOLD a fost
corect, ce valoare au adus opiniile minoritare și dacă dezacordul dintre agenți
anunță mișcări mari sau pierderi. Compară și botul pe reguli, consiliul și varianta
hibridă (consiliul doar când e de acord cu botul). Nicio informație din viitor nu e
folosită la momentul deciziei: rezultatul se citește doar după închidere.

    python -m src.bnd.council_analytics --registry registry.sqlite
"""

import argparse
import json
import sqlite3
import sys
from math import isfinite

HOLD_BAND = 0.01          # HOLD e „corect” dacă prețul s-a mișcat sub 1% în 5 zile
MIN_SAMPLE = 20           # sub atâtea decizii încheiate, concluziile sunt doar orientative
SIDE = {"BUY": 1, "SELL": -1, "HOLD": 0}


def _asset_class(symbol: str) -> str:
    from .council_daily import ASSET_CLASS
    return ASSET_CLASS.get(symbol, "alta")


def _rows(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        decisions = {r[0]: {"symbol": r[1], "vote": r[2], "uncertain": bool(r[3]),
                            "outcome": r[4], "meta": json.loads(r[5] or "{}"), "votes": {}}
                     for r in db.execute("SELECT id, symbol, vote, uncertain, outcome_return, meta"
                                         " FROM decisions WHERE settled_at IS NOT NULL"
                                         " AND outcome_return IS NOT NULL")}
        for decision_id, agent, stage, vote, confidence in db.execute(
                "SELECT decision_id, agent, stage, vote, confidence FROM votes"):
            if decision_id in decisions:
                decisions[decision_id]["votes"].setdefault(agent, {})[stage] = (vote, confidence)
    finally:
        db.close()
    return decisions


def _rate(hits, calls):
    return hits / calls if calls else None


def agent_scoreboard(decisions: dict) -> dict:
    """Pe agent: rată, profit virtual, calibrare, HOLD corect, contribuții minoritare."""
    out = {}
    for d in decisions.values():
        outcome = d["outcome"]
        majority = SIDE[d["vote"]]
        for agent, stages in d["votes"].items():
            vote, confidence = stages.get("initial", stages.get("final", ("HOLD", 0.0)))
            entry = out.setdefault(agent, {"calls": 0, "hits": 0, "net": 0.0, "holds": 0,
                                           "holds_right": 0, "minority": 0, "minority_right": 0,
                                           "bins": {}, "by_class": {}, "by_market": {}})
            side = SIDE[vote]
            if side == 0:
                entry["holds"] += 1
                entry["holds_right"] += abs(outcome) < HOLD_BAND
                continue
            hit = side * outcome > 0
            entry["calls"] += 1
            entry["hits"] += hit
            entry["net"] += side * outcome
            if isfinite(confidence):
                bucket = min(int(confidence * 10), 9) / 10
                b = entry["bins"].setdefault(bucket, [0, 0, 0.0])
                b[0] += 1
                b[1] += hit
                b[2] += confidence
            for key, label in (("by_class", _asset_class(d["symbol"])), ("by_market", d["symbol"])):
                cell = entry[key].setdefault(label, [0, 0])
                cell[0] += 1
                cell[1] += hit
            if side != majority:
                entry["minority"] += 1
                entry["minority_right"] += hit
    result = {}
    for agent, e in out.items():
        bins = [{"confidence_bucket": f"{k:.1f}-{k + 0.1:.1f}", "calls": n, "hit_rate": h / n,
                 "declared": c / n} for k, (n, h, c) in sorted(e["bins"].items())]
        # Eroare de calibrare = diferența medie dintre încrederea declarată și rata reală.
        gap = (sum(abs(b["declared"] - b["hit_rate"]) * b["calls"] for b in bins) / e["calls"]
               if e["calls"] else None)
        result[agent] = {
            "calls": e["calls"], "hit_rate": _rate(e["hits"], e["calls"]),
            "mean_net_return_pct": 100 * e["net"] / e["calls"] if e["calls"] else None,
            "holds": e["holds"], "hold_correct_rate": _rate(e["holds_right"], e["holds"]),
            "minority_calls": e["minority"], "minority_right": e["minority_right"],
            "calibration_gap": gap, "calibration": bins,
            "by_class": {k: {"calls": n, "hit_rate": h / n} for k, (n, h) in e["by_class"].items()},
            "by_market": {k: {"calls": n, "hit_rate": h / n} for k, (n, h) in e["by_market"].items()},
        }
    return result


def disagreement(decisions: dict) -> dict:
    """Dezacordul (câte opinii diferă de majoritate, 0..1) față de mișcarea reală."""
    buckets = {"scazut": [], "mediu": [], "ridicat": []}
    for d in decisions.values():
        final = [v["final"][0] for v in d["votes"].values() if "final" in v]
        if len(final) < 2:
            continue
        top = max(final.count(x) for x in set(final))
        level = 1 - top / len(final)
        key = "scazut" if level < 0.2 else "mediu" if level < 0.5 else "ridicat"
        buckets[key].append(abs(d["outcome"]))
    return {k: {"decisions": len(v), "mean_abs_move_pct": 100 * sum(v) / len(v) if v else None,
                "share_big_moves": (sum(x > 0.03 for x in v) / len(v)) if v else None}
            for k, v in buckets.items()}


def strategy_comparison(decisions: dict) -> dict:
    """Botul pe reguli, consiliul (majoritate), înclinația și hibridul (consiliul când e de acord cu botul)."""
    sides = {"bot": [], "council": [], "lean": [], "hybrid": []}
    for d in decisions.values():
        out = d["outcome"]
        if out == 0:
            continue
        bot = d["meta"].get("bot_signal") or 0
        lean = d["meta"].get("lean")
        if lean is None:
            lean = (lambda t: (t > 0) - (t < 0))(sum(SIDE[v["final"][0]] for v in d["votes"].values() if "final" in v))
        if bot:
            sides["bot"].append((1 if bot > 0 else -1, out))
        if d["vote"] != "HOLD" and not d["uncertain"]:
            sides["council"].append((SIDE[d["vote"]], out))
        if lean:
            sides["lean"].append((lean, out))
        if lean and bot and (lean > 0) == (bot > 0):
            sides["hybrid"].append((lean, out))
    result = {}
    for name, calls in sides.items():
        result[name] = {"calls": len(calls),
                        "hit_rate": _rate(sum(s * o > 0 for s, o in calls), len(calls)),
                        "mean_return_pct": 100 * sum(s * o for s, o in calls) / len(calls) if calls else None}
    return result


def cost_to_value(decisions: dict, cost_per_agent: dict | None = None) -> dict:
    """Ce aduc 5, 3 sau 1 agenți, din aceleași voturi salvate (fără apeluri noi).

    Pentru fiecare grup de agenți se ia „înclinația” (BUY minus SELL, HOLD ignorat) a
    grupului și se măsoară rata și câștigul mediu la 5 zile, plus costul pe decizie din
    costurile medii ale agenților. Grupul de 3 = cei trei cu cea mai bună rată proprie
    (alegere pe aceleași date: orientativ, nu out-of-sample). Doar citire.
    """
    cost_per_agent = cost_per_agent or {}
    board = agent_scoreboard(decisions)
    agents = sorted(board)
    ranked = sorted(agents, key=lambda a: (board[a]["hit_rate"] if board[a]["hit_rate"] is not None else -1),
                    reverse=True)
    groups = {"toți": agents, "primii 3": ranked[:3], **{f"doar {a}": [a] for a in agents}}
    result = {}
    for name, members in groups.items():
        calls = []
        for d in decisions.values():
            if d["outcome"] == 0:
                continue
            net = sum(SIDE[d["votes"][a]["initial"][0]] for a in members
                      if a in d["votes"] and "initial" in d["votes"][a])
            if net:
                calls.append((1 if net > 0 else -1, d["outcome"]))
        result[name] = {"agents": members, "calls": len(calls),
                        "hit_rate": _rate(sum(s * o > 0 for s, o in calls), len(calls)),
                        "mean_return_pct": 100 * sum(s * o for s, o in calls) / len(calls) if calls else None,
                        "cost_per_decision_usd": sum(cost_per_agent.get(a, 0.0) for a in members)}
    return result


def analyse(path, cost_per_agent: dict | None = None) -> dict:
    decisions = _rows(path)
    return {"settled": len(decisions), "enough_data": len(decisions) >= MIN_SAMPLE,
            "note": None if len(decisions) >= MIN_SAMPLE else
            f"Doar {len(decisions)} decizii încheiate (sub {MIN_SAMPLE}): rezultatele sunt orientative, nu concluzii.",
            "agents": agent_scoreboard(decisions), "disagreement": disagreement(decisions),
            "strategies": strategy_comparison(decisions),
            "cost_to_value": cost_to_value(decisions, cost_per_agent)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="council_analytics")
    parser.add_argument("--registry", required=True)
    args = parser.parse_args(argv)
    try:
        report = analyse(args.registry)
    except sqlite3.Error as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
