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
from datetime import date, timedelta
import sqlite3
import sys
from math import comb, isfinite

from .decision_rules import AgentScorebook
from .fusion_council import AGENTS, Vote

HOLD_BAND = 0.01          # HOLD e „corect” dacă prețul s-a mișcat sub 1% în 5 zile
MIN_SAMPLE = 20           # sub atâtea decizii încheiate, concluziile sunt doar orientative
SIDE = {"BUY": 1, "SELL": -1, "HOLD": 0}


def _asset_class(symbol: str) -> str:
    from .council_daily import ASSET_CLASS
    return ASSET_CLASS.get(symbol, "alta")


def _incomplete_ids(db) -> set:
    """Deciziile cu runda incompletă (un agent a lipsit): nu sunt decizii ale consiliului, nu intră în statistici.

    Un răspuns care lipsește nu e un HOLD: tratat ca HOLD ar îngroșa artificial rata de „abținere corectă”."""
    ids = set()
    for decision_id, meta in db.execute("SELECT id, meta FROM decisions"):
        try:
            if json.loads(meta or "{}").get("complete") is False:
                ids.add(decision_id)
        except ValueError:
            continue
    return ids


def _rows(path, include_incomplete: bool = False):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        skip = set() if include_incomplete else _incomplete_ids(db)
        decisions = {r[0]: {"symbol": r[1], "vote": r[2], "uncertain": bool(r[3]),
                            "outcome": r[4], "meta": json.loads(r[5] or "{}"), "votes": {},
                            "day": r[0][:10], "horizon": r[6]}
                     for r in db.execute("SELECT id, symbol, vote, uncertain, outcome_return, meta,"
                                         " horizon_days FROM decisions WHERE settled_at IS NOT NULL"
                                         " AND outcome_return IS NOT NULL")}
        for key in skip:
            decisions.pop(key, None)
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
                                           "bins": {}, "by_class": {}, "by_market": {},
                                           "declared": 0.0, "brier": 0.0})
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
                entry["declared"] += confidence
                entry["brier"] += (confidence - (1.0 if hit else 0.0)) ** 2
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
            # Pozitiv = mai încrezător decât merită (încrederea medie minus rata reală).
            "overconfidence": (e["declared"] / e["calls"] - e["hits"] / e["calls"]) if e["calls"] else None,
            "mean_brier": e["brier"] / e["calls"] if e["calls"] else None,
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


def _vote(stages, stage):
    pair = stages.get(stage) or stages.get("final") or stages.get("initial")
    return pair if pair else ("HOLD", 0.0)


def by_regime(decisions: dict) -> dict:
    """Rata fiecărui agent (și a înclinației consiliului) pe regimul pieței la decizie.

    Regimul vine din ``meta["regime"]`` (decizii noi) sau lipsește („necunoscut”).
    Nu se trag concluzii sub MIN_SAMPLE apeluri pe celulă: ``reliable`` spune dacă s-a atins."""
    cells = {}
    for d in decisions.values():
        regime = d["meta"].get("regime") or "necunoscut"
        out = d["outcome"]
        for agent, stages in d["votes"].items():
            side = SIDE[_vote(stages, "initial")[0]]
            if side and out:
                cell = cells.setdefault(agent, {}).setdefault(regime, [0, 0])
                cell[0] += 1
                cell[1] += side * out > 0
    return {agent: {reg: {"calls": n, "hit_rate": h / n, "reliable": n >= MIN_SAMPLE}
                    for reg, (n, h) in regs.items()} for agent, regs in cells.items()}


def by_horizon(decisions: dict) -> dict:
    """Înclinația consiliului (BUY minus SELL, voturi inițiale) pe orizontul deciziei."""
    cells = {}
    for d in decisions.values():
        net = sum(SIDE[_vote(st, "initial")[0]] for st in d["votes"].values())
        if net and d["outcome"]:
            cell = cells.setdefault(d["horizon"], [0, 0, 0.0])
            side = 1 if net > 0 else -1
            cell[0] += 1
            cell[1] += side * d["outcome"] > 0
            cell[2] += side * d["outcome"]
    return {f"{h} zile": {"calls": n, "hit_rate": hits / n, "mean_return_pct": 100 * net / n,
                           "reliable": n >= MIN_SAMPLE} for h, (n, hits, net) in sorted(cells.items())}


def revision_value(decisions: dict) -> dict:
    """Înainte/după revizuire: dacă schimbarea de vot a ajutat (gol cât timp nu există dezbatere)."""
    changed = better = worse = 0
    for d in decisions.values():
        out = d["outcome"]
        if not out:
            continue
        for stages in d["votes"].values():
            if "initial" in stages and "final" in stages and stages["initial"][0] != stages["final"][0]:
                changed += 1
                before, after = (SIDE[stages[k][0]] * out for k in ("initial", "final"))
                better += after > before
                worse += after < before
    return {"changed_votes": changed, "improved": better, "worsened": worse,
            "note": None if changed else "Nicio revizuire de vot încă (producția face o singură rundă)."}


def before_after(decisions: dict) -> dict:
    """Aceleași piețe, înainte și după dezbatere: înclinația inițială față de cea finală.

    Merge pe registrul de dezbatere (voturile `initial` și `final`). Se numără doar piețele unde
    înclinația s-a schimbat ca să se vadă dacă dezbaterea a ajutat; cele rămase la fel nu spun nimic."""
    rows = {"initial": [], "final": []}
    flipped = better = worse = 0
    for d in decisions.values():
        out = d["outcome"]
        if not out:
            continue
        lean = {}
        for stage in rows:
            net = sum(SIDE[st[stage][0]] for st in d["votes"].values() if stage in st)
            lean[stage] = (net > 0) - (net < 0)
            if lean[stage]:
                rows[stage].append(lean[stage] * out)
        if lean["initial"] != lean["final"]:
            flipped += 1
            a, b = lean["initial"] * out, lean["final"] * out
            better += b > a
            worse += b < a
    stat = lambda xs: {"calls": len(xs), "hit_rate": _rate(sum(x > 0 for x in xs), len(xs)),
                       "mean_return_pct": 100 * sum(xs) / len(xs) if xs else None}
    return {"initial": stat(rows["initial"]), "final": stat(rows["final"]), "lean_changed": flipped,
            "improved": better, "worsened": worse,
            "note": None if flipped else "Nicio schimbare de înclinație încă."}


def alpha_report(decisions: dict) -> dict:
    """Aceeași înclinație (BUY minus SELL din voturile inițiale), măsurată în trei feluri.

    - ``raw``: randamentul de la prețul deciziei (cum se măsura până acum);
    - ``entry_next``: intrare la prima închidere de după data deciziei;
    - ``alpha``: randament minus benchmark (SP500 / BITCOIN), cu intrarea la prima închidere de după decizie.
    Dacă rata brută e mare, dar alpha e slab, consiliul a prins doar direcția pieței. Doar decizii cu ``meta.settle``."""
    buckets = {"raw": [], "entry_next": [], "alpha_next": [], "alpha_raw": []}
    for d in decisions.values():
        info = d["meta"].get("settle")
        if not info:
            continue
        net = sum(SIDE[_vote(st, "initial")[0]] for st in d["votes"].values())
        side = (net > 0) - (net < 0)
        if not side:
            continue
        buckets["raw"].append(side * d["outcome"])
        for key, source in (("entry_next", "entry_next_return"), ("alpha_next", "alpha_next"), ("alpha_raw", "alpha_raw")):
            if info.get(source) is not None:
                buckets[key].append(side * info[source])
    stat = lambda xs: {"calls": len(xs), "hit_rate": _rate(sum(x > 0 for x in xs), len(xs)),
                       "mean_return_pct": 100 * sum(xs) / len(xs) if xs else None,
                       "reliable": len(xs) >= MIN_SAMPLE}
    out = {k: stat(v) for k, v in buckets.items()}
    out["note"] = (None if out["alpha_next"]["calls"] else
                   "Încă nicio decizie decontată cu detalii de alpha (apar de la primele decontări, ~6.11).")
    return out


def penalized_weights(decisions: dict) -> dict:
    """Ponderi calculate cu penalizarea supraîncrederii (doar raportate, nu folosite în decizii).

    pondere ∝ ponderea după Brier netezit × (1 − penalizare), penalizare = supraîncrederea
    tăiată la [0, 0,5]. Un agent care declară 0,8 și nimerește 0,5 pierde 0,3 din pondere."""
    board = agent_scoreboard(decisions)
    book = AgentScorebook()
    for d in decisions.values():
        if not d["outcome"]:
            continue
        for agent, stages in d["votes"].items():
            vote, conf = _vote(stages, "initial")
            if agent in AGENTS and vote != "HOLD" and isfinite(conf) and 0 <= conf <= 1:
                book.record(agent, Vote(vote), conf, d["outcome"] > 0)
    base = book.weights()
    raw = {a: base[a] * (1 - min(0.5, max(0.0, (board.get(a, {}).get("overconfidence") or 0.0))))
           for a in AGENTS}
    total = sum(raw.values())
    return {"base": base, "penalized": {a: v / total for a, v in raw.items()}}


def _sign_test_p(wins: int, losses: int) -> float | None:
    n = wins + losses
    if n == 0:
        return None
    k = min(wins, losses)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def out_of_sample_weighting(decisions: dict, train_share: float = 0.6, min_days: int = 8) -> dict:
    """Ponderarea după istoric bate votul egal pe zile NEVĂZUTE?

    Zilele se ordonează în timp; primele ``train_share`` calculează ponderile (Brier netezit),
    ultimele sunt de test. Pe testul nevăzut se compară direcția voturilor ponderate (pondere ×
    încredere) cu a celor egale. ``sign_test_p`` privește doar cazurile în care cele două
    metode au ales direcții diferite. Valid doar cu multe zile; sub ``min_days`` nu se concluzionează."""
    days = sorted({d["day"] for d in decisions.values()})
    if len(days) < min_days:
        return {"evaluated": False, "days": len(days),
                "note": f"Doar {len(days)} zile cu decizii încheiate (minim {min_days}): nu se poate "
                        "testa ponderarea pe date nevăzute."}
    cut = days[max(1, int(len(days) * train_share)) - 1]
    train = {k: d for k, d in decisions.items() if d["day"] <= cut}
    # Embargo: rezultatul unei decizii din antrenare se află abia după `horizon` zile. Deciziile de test
    # luate înainte să treacă acest interval nu aveau cum să folosească acele ponderi, deci se exclud.
    horizon = max((d["horizon"] for d in train.values()), default=0)
    first_test = (date.fromisoformat(cut) + timedelta(days=horizon)).isoformat()
    test = [d for d in decisions.values() if d["day"] > first_test and d["outcome"]]
    if not test:
        return {"evaluated": False, "days": len(days),
                "note": f"După embargo ({horizon} zile) nu rămâne nicio decizie de test."}
    weights = penalized_weights(train)["base"]
    stats = {"equal": [0, 0, 0.0], "weighted": [0, 0, 0.0]}
    wins = losses = 0
    for d in test:
        eq = sum(SIDE[_vote(st, "initial")[0]] for st in d["votes"].values())
        wt = sum(weights.get(a, 0.0) * SIDE[_vote(st, "initial")[0]] * _vote(st, "initial")[1]
                 for a, st in d["votes"].items())
        sides = {"equal": (eq > 0) - (eq < 0), "weighted": (wt > 0) - (wt < 0)}
        for name, side in sides.items():
            if side:
                stats[name][0] += 1
                stats[name][1] += side * d["outcome"] > 0
                stats[name][2] += side * d["outcome"]
        if sides["equal"] and sides["weighted"] and sides["equal"] != sides["weighted"]:
            wins += sides["weighted"] * d["outcome"] > 0
            losses += sides["weighted"] * d["outcome"] < 0
    out = {name: {"calls": n, "hit_rate": _rate(h, n), "mean_return_pct": 100 * net / n if n else None}
           for name, (n, h, net) in stats.items()}
    p = _sign_test_p(wins, losses)
    return {"evaluated": True, "train_days": len([x for x in days if x <= cut]),
            "test_days": len({d["day"] for d in test}), "embargo_days": horizon, "weights_from_train": weights, **out,
            "disagreements": wins + losses, "weighted_right": wins, "sign_test_p": p,
            "verdict": ("neconcludent" if p is None or p > 0.05 or wins + losses < MIN_SAMPLE else
                        "ponderarea bate votul egal" if wins > losses else "votul egal bate ponderarea"),
            "note": "Deciziile din aceeași zi sunt corelate între piețe: p e optimist, tratează-l ca limită."}


def analyse(path, cost_per_agent: dict | None = None) -> dict:
    decisions = _rows(path)
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        excluded = len(_incomplete_ids(db))
    return {"incomplete_excluded": excluded, "settled": len(decisions), "enough_data": len(decisions) >= MIN_SAMPLE,
            "note": None if len(decisions) >= MIN_SAMPLE else
            f"Doar {len(decisions)} decizii încheiate (sub {MIN_SAMPLE}): rezultatele sunt orientative, nu concluzii.",
            "agents": agent_scoreboard(decisions), "disagreement": disagreement(decisions),
            "strategies": strategy_comparison(decisions),
            "cost_to_value": cost_to_value(decisions, cost_per_agent),
            "by_regime": by_regime(decisions), "by_horizon": by_horizon(decisions),
            "alpha": alpha_report(decisions),
            "revision": revision_value(decisions), "before_after": before_after(decisions), "weights": penalized_weights(decisions),
            "out_of_sample": out_of_sample_weighting(decisions)}


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
