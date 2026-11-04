"""Formații AI: 14 conturi-umbră virtuale construite din voturile pe care consiliul le-a dat DEJA.

Cerut de proprietar pe 4.11.2026. Nu face niciun apel AI: citește din registrul consiliului
(registry.sqlite, tabelul votes) votul fiecărui agent pe fiecare piață și îl combină pe formații:

    P1  GPT + Grok             cu reguli  (50% regime_switch + 50% votul formației, ca în contul unic)
    P2  GPT + Grok             fără reguli (100% votul formației)
    P3  fiecare AI singur      cu reguli  (5 conturi)
    P4  fiecare AI singur      fără reguli (5 conturi)
    P5  GPT + Claude + Grok    cu reguli
    P6  GPT + Claude + Grok    fără reguli
    P7  toți 5, ponderați după rezultate  cu reguli (ponderea fiecărui AI = cât a ghicit pe deciziile deja încheiate)
    P8  toți 5, doar la consens 4/5       cu reguli (consiliul contează doar când ≥4 din 5 votează la fel)
    P9  toți 5, doar la crypto/memecoin   cu reguli (la restul piețelor doar regulile)

Semnalul unei formații cu n membri pe o piață:
    net = voturi BUY − voturi SELL ale membrilor (votul final; dacă lipsește, cel inițial; HOLD = 0)
    prag = max(1, round(0,4 × n))       # 5 membri -> 2 (exact ca în contul unic), 3 -> 1, 2 -> 1, 1 -> 1
    semnal = semn(net) × min(1, |net| / prag)
O piață fără decizie azi nu apare în fișier: contul își lasă poziția cum e (la fel ca în contul unic).
Doar bani virtuali.

    python -m src.bnd.formations --registry registry.sqlite --coins A,B --out-dir semnale
    python -m src.bnd.formations --list          # nume<TAB>strategie<TAB>titlu, câte una pe rând
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

AGENTS = ("gpt", "grok", "claude", "gemini", "deepseek")
LABEL = {"gpt": "GPT", "grok": "Grok", "claude": "Claude", "gemini": "Gemini", "deepseek": "DeepSeek"}


def _formations() -> list[dict]:
    out = []

    def add(point, key, members, rules, kind="fix", title=None):
        names = " + ".join(LABEL[m] for m in members)
        out.append({"key": key, "point": point, "members": tuple(members), "rules": rules, "kind": kind,
                    "strategy": "hibrid" if rules else "ai_council",
                    "title": title or f"{names}, {'cu reguli' if rules else 'fără reguli'}"})

    add(1, "p1-gpt-grok", ("gpt", "grok"), True)
    add(2, "p2-gpt-grok-liber", ("gpt", "grok"), False)
    for agent in AGENTS:
        add(3, f"p3-{agent}", (agent,), True)
    for agent in AGENTS:
        add(4, f"p4-{agent}-liber", (agent,), False)
    add(5, "p5-gpt-claude-grok", ("gpt", "claude", "grok"), True)
    add(6, "p6-gpt-claude-grok-liber", ("gpt", "claude", "grok"), False)
    add(7, "p7-ponderat", AGENTS, True, "ponderat", "Toți 5, ponderați după rezultate, cu reguli")
    add(8, "p8-consens", AGENTS, True, "consens", "Toți 5, doar la consens 4/5, cu reguli")
    add(9, "p9-doar-crypto", AGENTS, True, "crypto", "Toți 5 doar la crypto și memecoin, cu reguli")
    return out


FORMATIONS = _formations()
SIDE = {"BUY": 1, "SELL": -1}
CONSENSUS = 4            # P8: câți din 5 trebuie să voteze la fel
MIN_SETTLED = 20         # P7: sub atâtea apeluri încheiate pentru FIECARE agent, ponderile rămân egale
CRYPTO_CLASSES = ("crypto", "memecoin")


def threshold(members: int) -> int:
    return max(1, round(0.4 * members))


def formation_signal(votes: dict, members) -> float:
    """votes = {agent: vot}; doar membrii contează."""
    net = sum(SIDE.get(votes.get(m, "HOLD"), 0) for m in members)
    if net == 0:
        return 0.0
    return (1.0 if net > 0 else -1.0) * min(1.0, abs(net) / threshold(len(members)))


def weighted_signal(votes: dict, weights: dict) -> float:
    """P7: media ponderată a voturilor; cu ponderi egale e exact formula contului unic (net/2 la 5 agenți)."""
    total = sum(weights.get(a, 0.0) for a in AGENTS)
    if total <= 0:
        return 0.0
    mean = sum(weights.get(a, 0.0) * SIDE.get(votes.get(a, "HOLD"), 0) for a in AGENTS) / total
    return max(-1.0, min(1.0, mean / (threshold(len(AGENTS)) / len(AGENTS))))


def agent_weights(registry: str, day: str) -> dict:
    """P7: ponderea fiecărui AI = avantajul lui (rata de reușită − 50%) pe deciziile ÎNCHEIATE înainte de `day`.
    Doar informație din trecut. Până când fiecare agent are MIN_SETTLED apeluri încheiate, ponderile sunt egale."""
    db = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT v.agent, v.stage, v.vote, d.outcome_return, d.id FROM votes v JOIN decisions d"
                          " ON d.id = v.decision_id WHERE d.settled_at IS NOT NULL AND d.outcome_return IS NOT NULL"
                          " AND d.settled_at < ?", (day,)).fetchall()
    finally:
        db.close()
    final = {}
    for agent, stage, vote, outcome, did in sorted(rows, key=lambda r: r[1] != "initial"):
        final[(agent, did)] = (vote, outcome)
    calls, hits = dict.fromkeys(AGENTS, 0), dict.fromkeys(AGENTS, 0)
    for (agent, _), (vote, outcome) in final.items():
        side = SIDE.get(vote, 0)
        if agent in calls and side:
            calls[agent] += 1
            hits[agent] += side * outcome > 0
    if any(calls[a] < MIN_SETTLED for a in AGENTS):
        return dict.fromkeys(AGENTS, 1.0)
    edge = {a: max(0.0, hits[a] / calls[a] - 0.5) for a in AGENTS}
    return edge if sum(edge.values()) > 0 else dict.fromkeys(AGENTS, 1.0)


def _asset_class(symbol: str) -> str:
    from .council_daily import ASSET_CLASS
    return ASSET_CLASS.get(symbol, "alta")


def signals_for(f: dict, votes: dict, weights: dict) -> dict:
    """Semnalele unei formații; o piață care lipsește din rezultat = contul hibrid urmează doar regula acolo."""
    if f["kind"] == "ponderat":
        return {c: weighted_signal(v, weights) for c, v in votes.items()}
    if f["kind"] == "consens":
        out = {}
        for c, v in votes.items():
            net = sum(SIDE.get(v.get(a, "HOLD"), 0) for a in AGENTS)
            if abs(net) >= CONSENSUS:
                out[c] = 1.0 if net > 0 else -1.0
        return out
    if f["kind"] == "crypto":
        return {c: formation_signal(v, AGENTS) for c, v in votes.items() if _asset_class(c) in CRYPTO_CLASSES}
    return {c: formation_signal(v, f["members"]) for c, v in votes.items()}


def day_votes(registry: str, coins, day: str) -> tuple[dict, list]:
    """{piață: {agent: vot}} pentru deciziile din ziua dată; votul final are prioritate față de cel inițial."""
    db = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    try:
        found, missing = {}, []
        for coin in coins:
            rows = db.execute("SELECT agent, stage, vote FROM votes WHERE decision_id = ?",
                              (f"{day}:{coin}",)).fetchall()
            exists = db.execute("SELECT 1 FROM decisions WHERE id = ?", (f"{day}:{coin}",)).fetchone()
            if not exists:
                missing.append(coin)
                continue
            votes = {}
            for agent, stage, vote in sorted(rows, key=lambda r: r[1] != "initial"):   # initial întâi, final peste
                votes[agent] = vote
            found[coin] = votes
    finally:
        db.close()
    return found, missing


def build_all(registry: str, coins, day: str) -> dict:
    votes, missing = day_votes(registry, coins, day)
    weights = agent_weights(registry, day)
    return {f["key"]: {"date": day, "formation": f["title"], "members": list(f["members"]),
                       "signals": signals_for(f, votes, weights), "missing": missing,
                       **({"weights": weights} if f["kind"] == "ponderat" else {})}
            for f in FORMATIONS}


def vote_score(registry: str, quotes: dict, f: dict) -> dict | None:
    """Scor provizoriu, din date reale: fiecare semnal al formației (din 31.10 încoace) comparat cu prețul de acum.
    Câte un pariu virtual pe semnal, fără leverage și fără reguli; doar ca să se vadă ceva din prima zi."""
    if not registry or not Path(registry).exists():
        return None
    db = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    try:
        decisions = {i: (sym, price) for i, sym, price in db.execute("SELECT id, symbol, price FROM decisions")}
        by = {}
        for did, agent, stage, vote in sorted(db.execute("SELECT decision_id, agent, stage, vote FROM votes").fetchall(),
                                              key=lambda r: r[2] != "initial"):
            by.setdefault(did, {})[agent] = vote
    finally:
        db.close()
    calls, hits, total = 0, 0, 0.0
    for day in sorted({did[:10] for did in by}):
        todays = {decisions[d][0]: v for d, v in by.items() if d[:10] == day and d in decisions}
        for coin, signal in signals_for(f, todays, agent_weights(registry, day)).items():
            price = decisions.get(f"{day}:{coin}", (None, 0))[1]
            now = (quotes.get(coin) or [0])[0]
            if not signal or not price or price <= 0 or not now:
                continue
            move = now / price - 1
            if abs(move) > 0.8:          # preț greșit (ex. memecoin cu 0,0000), nu îl socotim
                continue
            calls += 1
            hits += signal * move > 0
            total += (1 if signal > 0 else -1) * move
    if not calls:
        return {"calls": 0}
    return {"calls": calls, "hit_rate": hits / calls, "mean_pct": 100 * total / calls}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="formations")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--registry")
    parser.add_argument("--coins", default="")
    parser.add_argument("--day", help="AAAA-LL-ZZ (UTC), implicit azi")
    parser.add_argument("--out-dir")
    args = parser.parse_args(argv)
    if args.list:
        for f in FORMATIONS:
            print(f"{f['key']}\t{f['strategy']}\t{f['title']}")
        return 0
    if not args.registry or not args.out_dir:
        parser.error("--registry și --out-dir sunt obligatorii")
    if not Path(args.registry).exists():
        print("Error: registrul consiliului lipsește", file=sys.stderr)
        return 2
    day = args.day or datetime.now(timezone.utc).date().isoformat()
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        print("Error: --day trebuie să fie AAAA-LL-ZZ", file=sys.stderr)
        return 2
    coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]
    result = build_all(args.registry, coins, day)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for key, payload in result.items():
        (out / f"{key}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    first = next(iter(result.values()))
    print(f"{len(result)} formații, {len(first['signals'])} piețe cu decizie azi, {len(first['missing'])} fără")
    if coins and len(first["missing"]) / len(coins) > 0.2:
        print(f"::warning::Consiliul nu are decizii pentru {len(first['missing'])} din {len(coins)} piețe în ziua {day}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
