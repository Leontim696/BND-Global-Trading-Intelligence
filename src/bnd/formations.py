"""Formații AI: 14 conturi-umbră virtuale construite din voturile pe care consiliul le-a dat DEJA.

Cerut de proprietar pe 4.11.2026. Nu face niciun apel AI: citește din registrul consiliului
(registry.sqlite, tabelul votes) votul fiecărui agent pe fiecare piață și îl combină pe formații:

    P1  GPT + Grok             cu reguli  (50% regime_switch + 50% votul formației, ca în contul unic)
    P2  GPT + Grok             fără reguli (100% votul formației)
    P3  fiecare AI singur      cu reguli  (5 conturi)
    P4  fiecare AI singur      fără reguli (5 conturi)
    P5  GPT + Claude + Grok    cu reguli
    P6  GPT + Claude + Grok    fără reguli

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

    def add(point, key, members, rules):
        names = " + ".join(LABEL[m] for m in members)
        out.append({"key": key, "point": point, "members": tuple(members), "rules": rules,
                    "strategy": "hibrid" if rules else "ai_council",
                    "title": f"{names}, {'cu reguli' if rules else 'fără reguli'}"})

    add(1, "p1-gpt-grok", ("gpt", "grok"), True)
    add(2, "p2-gpt-grok-liber", ("gpt", "grok"), False)
    for agent in AGENTS:
        add(3, f"p3-{agent}", (agent,), True)
    for agent in AGENTS:
        add(4, f"p4-{agent}-liber", (agent,), False)
    add(5, "p5-gpt-claude-grok", ("gpt", "claude", "grok"), True)
    add(6, "p6-gpt-claude-grok-liber", ("gpt", "claude", "grok"), False)
    return out


FORMATIONS = _formations()
SIDE = {"BUY": 1, "SELL": -1}


def threshold(members: int) -> int:
    return max(1, round(0.4 * members))


def formation_signal(votes: dict, members) -> float:
    """votes = {agent: vot}; doar membrii contează."""
    net = sum(SIDE.get(votes.get(m, "HOLD"), 0) for m in members)
    if net == 0:
        return 0.0
    return (1.0 if net > 0 else -1.0) * min(1.0, abs(net) / threshold(len(members)))


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
    return {f["key"]: {"date": day, "formation": f["title"], "members": list(f["members"]),
                       "signals": {coin: formation_signal(v, f["members"]) for coin, v in votes.items()},
                       "missing": missing}
            for f in FORMATIONS}


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
