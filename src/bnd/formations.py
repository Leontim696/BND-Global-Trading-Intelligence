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
    P20 „Idee nebună”: P17 + P16 + P18 + take profit +5% + reciclare, toate deodată
    P16 frână la pierderi; P17 contra mulțimii pe crypto (funding); P18 prudență înaintea anunțurilor din SUA;
    P19 meta-formație (copiază cele mai bune 3 formații din ultimele 7 zile)
    P14/P15 pereche: take profit +5%, capitalul eliberat lăsat lichid (14) sau reciclat cu protecții (15)
    P12 ca oficial + take profit +5% și stop −1%; P13 ca oficial + take profit +5% cu stopul normal (3×ATR)
    P11 la fel ca P10, dar agresiv: până la 3x (plafonul motorului), 50% pe piață, volatilitate-țintă 30%
    P10 miză după convingere: toți 5 + regula; semnal puternic (≥4/5 AI și regula în aceeași direcție) = miză
        întreagă (până la 25% din cont pe piață), semnal mediu = jumătate, slab sau contradictoriu = nimic

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


# Setările conturilor-umbră (la creare). Standard = exact ca în contul unic.
STANDARD = "--max-leverage 2 --max-weight 0.25 --max-sector 60 --portfolio-vol 15 --financing 5"
# P11 agresiv (cerut pe 4.11): plafonul motorului e 3x, iar marjele ESMA (crypto 50%, acțiuni 20%) limitează oricum
# leverage-ul pe piață; opririle de siguranță (−5% pe zi, −25% de la vârf) rămân aceleași.
AGGRESSIVE = "--max-leverage 3 --max-weight 0.5 --max-sector 100 --portfolio-vol 30 --financing 5"


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
    out.append({"key": "p10-convingere", "point": 10, "members": AGENTS, "rules": True, "kind": "convingere",
                "strategy": "ai_council", "title": "Miză după convingere (toți 5 + regula)"})
    out.append({"key": "p11-convingere-agresiv", "point": 11, "members": AGENTS, "rules": True, "kind": "convingere",
                "strategy": "ai_council", "title": "Miză după convingere, agresiv (până la 3x)",
                "settings": AGGRESSIVE})
    # P12–P13 (cerut pe 4.11): aceleași semnale ca în contul oficial (toți 5 AI + regula), dar cu take profit.
    out.append({"key": "p12-tp5-sl1", "point": 12, "members": AGENTS, "rules": True, "kind": "fix",
                "strategy": "hibrid", "title": "Ca oficial, cu take profit +5% și stop −1%",
                "settings": STANDARD + " --take-profit-pct 5 --stop-pct 1"})
    out.append({"key": "p13-tp5-stop-normal", "point": 13, "members": AGENTS, "rules": True, "kind": "fix",
                "strategy": "hibrid", "title": "Ca oficial, cu take profit +5% (stop normal 3×ATR)",
                "settings": STANDARD + " --take-profit-pct 5"})
    # P14–P15 (cerut pe 4.11): test pereche pentru reciclarea capitalului, ACELEAȘI limite de risc și semnale.
    out.append({"key": "p14-tp-obisnuit", "point": 14, "members": AGENTS, "rules": True, "kind": "fix",
                "strategy": "hibrid", "title": "Take profit +5%, capital eliberat lăsat lichid (obișnuit)",
                "settings": STANDARD + " --take-profit-pct 5 --recycle obisnuit"})
    out.append({"key": "p15-tp-reciclare", "point": 15, "members": AGENTS, "rules": True, "kind": "fix",
                "strategy": "hibrid", "title": "Take profit +5%, capital eliberat reciclat (Adaptive Position Recycling)",
                "settings": STANDARD + " --take-profit-pct 5 --recycle reciclare"})
    # P16–P19 (propuse de Claude, aprobate pe 4.11): aceleași semnale de bază ca oficialul, câte o regulă în plus.
    out.append({"key": "p16-frana-pierderi", "point": 16, "members": AGENTS, "rules": True, "kind": "fix",
                "strategy": "hibrid", "title": "Ca oficial + frână: expunere pe jumătate sub −3% de la vârf",
                "settings": STANDARD + " --dd-brake-pct 3"})
    out.append({"key": "p17-contra-funding", "point": 17, "members": AGENTS, "rules": True, "kind": "funding",
                "strategy": "ai_council", "title": "Ca oficial + contra mulțimii pe crypto (funding)"})
    out.append({"key": "p18-prudenta-anunturi", "point": 18, "members": AGENTS, "rules": True, "kind": "fix",
                "strategy": "hibrid", "title": "Ca oficial + expunere pe jumătate înaintea anunțurilor mari din SUA",
                "settings": STANDARD + " --event-cut 0.5"})
    out.append({"key": "p19-meta-top3", "point": 19, "members": AGENTS, "rules": True, "kind": "meta",
                "strategy": "hibrid", "title": "Meta-formație: copiază cele mai bune 3 formații din ultimele 7 zile"})
    # P20 „Idee nebună” (cerută pe 4.11): toate ingredientele deodată — semnalele oficialului cu filtrul de funding (P17),
    # frâna la pierderi (P16), prudența la anunțuri (P18), take profit +5% cu stop normal (P13) și reciclarea (P15).
    out.append({"key": "p20-idee-nebuna", "point": 20, "members": AGENTS, "rules": True, "kind": "funding",
                "strategy": "ai_council", "title": "Idee nebună (funding + frână + anunțuri + take profit + reciclare)",
                "settings": STANDARD + " --take-profit-pct 5 --recycle reciclare --dd-brake-pct 3 --event-cut 0.5"})
    return out


FORMATIONS = _formations()
SIDE = {"BUY": 1, "SELL": -1}
CONSENSUS = 4            # P8: câți din 5 trebuie să voteze la fel
MIN_SETTLED = 20         # P7: sub atâtea apeluri încheiate pentru FIECARE agent, ponderile rămân egale
CRYPTO_CLASSES = ("crypto", "memecoin")
STAKE_USD = 100.0                         # scorul din voturi: miza (marja) pusă pe fiecare semnal
LEVERAGES = (1, 2, 5, 10)                 # coloana „agresiv”: aceeași miză, cu leverage de la 2x în sus
MAINTENANCE = 0.1                         # lichidare când pierderea atinge ~90% din marjă (mișcare adversă ≈ 0,9 / L)


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


def conviction_signal(votes: dict, rule: float | None) -> float:
    """P10: puternic (≥4/5 AI și regula în aceeași direcție) = ±1; mediu (AI 2–3 net în direcția regulii, sau ≥4/5 cu
    regula neutră) = ±0,5; slab sau contradictoriu = 0. Fără semnalul regulii nu se ia nicio poziție nouă."""
    if rule is None:
        return 0.0
    net = sum(SIDE.get(votes.get(a, "HOLD"), 0) for a in AGENTS)
    if abs(net) < 2:
        return 0.0
    side = 1.0 if net > 0 else -1.0
    r = 0 if abs(rule) < 1e-9 else (1 if rule > 0 else -1)
    if r == -side:
        return 0.0                                   # AI și regula se contrazic
    if abs(net) >= CONSENSUS and r == side:
        return side
    return 0.5 * side


def rule_signals(data_dir, coins) -> dict:
    """Semnalul regulii (regime_switch, la fel ca în contul unic) pe fiecare piață, din lumânările zilnice."""
    from .backtest_cli import _factory
    from .market_data import load_csv
    from .portfolio import _History, strategy_for
    from .universe import select as select_markets
    factory = _factory("regime_switch", {})
    wanted = set(coins)
    out = {}
    for market in select_markets([], [], "unic"):
        path = Path(data_dir) / f"{market.name}.csv"
        if market.name not in wanted or not path.exists():
            continue
        candles = load_csv(path)
        strategy, signal = strategy_for(factory, market), 0.0
        for end in range(1, len(candles) + 1):
            signal = strategy(_History(candles, end))
        out[market.name] = float(signal)
    return out


# P17: rata de finanțare pe 8 ore (media ultimelor 3) peste care „toată lumea e pe long” (~0,03% ≈ 33%/an, de 3 ori
# nivelul obișnuit de 0,01%); sub 0 = „toată lumea e pe short”.
CROWDED_LONG = 0.0003
CROWDED_SHORT = 0.0
# P19: formațiile din care se alege (cele cu semnal AI propriu, cu reguli) și fereastra de clasament.
META_POOL = ("p1-gpt-grok", "p3-gpt", "p3-grok", "p3-claude", "p3-gemini", "p3-deepseek", "p5-gpt-claude-grok",
             "p7-ponderat", "p8-consens", "p9-doar-crypto")
META_DAYS, META_TOP = 7, 3


def load_funding(folder) -> dict:
    """{piață: media ultimelor 3 rate de finanțare} din CSV-urile date-piete/funding/ (time,rate,source)."""
    import csv
    out = {}
    if not folder or not Path(folder).is_dir():
        return out
    for path in sorted(Path(folder).glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            rates = [float(r["rate"]) for r in csv.DictReader(handle) if r.get("rate") not in (None, "")]
        if len(rates) >= 3:
            out[path.stem] = sum(rates[-3:]) / 3
    return out


def funding_clip(signal: float, rate: float | None) -> float:
    if rate is None:
        return signal
    if rate >= CROWDED_LONG:
        return min(signal, 0.0)            # mulțimea e pe long: niciun long nou
    if rate < CROWDED_SHORT:
        return max(signal, 0.0)            # mulțimea e pe short: niciun short nou
    return signal


def meta_top(state_dir, day: str, days: int = META_DAYS, n: int = META_TOP) -> list | None:
    """Cele mai bune n formații din META_POOL după randamentul pe ultimele `days` zile (din jurnalul conturilor).
    None dacă nu există încă un clasament (prea puține rulări sau toate egale)."""
    from datetime import date, timedelta as _td
    from .paper_engine import PaperEngine
    if not state_dir:
        return None
    since = (date.fromisoformat(day) - _td(days=days)).isoformat()
    scores = {}
    for key in META_POOL:
        path = Path(state_dir) / key / "paper.sqlite"
        if not path.exists():
            continue
        engine = PaperEngine.open(path)
        try:
            runs = [(e["payload"]["time"][:10], e["payload"]["equity"]) for e in engine.journal("daily_run")]
        finally:
            engine.close()
        window = [eq for d, eq in runs if d >= since] or [eq for _, eq in runs]
        if len(window) >= 2 and window[0] > 0:
            scores[key] = window[-1] / window[0] - 1
    if len(scores) < n or len({round(v, 9) for v in scores.values()}) == 1:
        return None
    return sorted(scores, key=lambda k: (-scores[k], k))[:n]


def signals_for(f: dict, votes: dict, weights: dict, rules: dict | None = None,
                funding: dict | None = None, top: list | None = None) -> dict:
    """Semnalele unei formații; o piață care lipsește din rezultat = contul hibrid urmează doar regula acolo."""
    if f["kind"] == "funding":
        out = {}
        for c, r in (rules or {}).items():
            if r is None:
                continue
            s = 0.5 * r + 0.5 * formation_signal(votes[c], AGENTS) if c in votes else r
            out[c] = max(-1.0, min(1.0, funding_clip(s, (funding or {}).get(c))))
        return out
    if f["kind"] == "meta":
        if not top:
            return {c: formation_signal(v, AGENTS) for c, v in votes.items()}
        by = {x["key"]: x for x in FORMATIONS}
        parts = [signals_for(by[k], votes, weights, rules) for k in top if k in by]
        coins = set().union(*parts) if parts else set()
        return {c: sum(p.get(c, 0.0) for p in parts) / len(parts) for c in coins}
    if f["kind"] == "convingere":
        return {c: conviction_signal(v, (rules or {}).get(c)) for c, v in votes.items() if (rules or {}).get(c) is not None}
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


def build_all(registry: str, coins, day: str, rules: dict | None = None, funding: dict | None = None,
              top: list | None = None) -> dict:
    votes, missing = day_votes(registry, coins, day)
    weights = agent_weights(registry, day)
    return {f["key"]: {"date": day, "formation": f["title"], "members": list(f["members"]),
                       "signals": signals_for(f, votes, weights, rules, funding, top), "missing": missing,
                       **({"top": top} if f["kind"] == "meta" else {}),
                       **({"funding": funding} if f["kind"] == "funding" else {}),
                       **({"weights": weights} if f["kind"] == "ponderat" else {})}
            for f in FORMATIONS}


def vote_score(registry: str, quotes: dict, f: dict) -> dict | None:
    """Scor provizoriu, din date reale: fiecare semnal al formației (din 31.10 încoace) comparat cu prețul de acum.
    Câte un pariu virtual pe semnal, fără leverage și fără reguli; doar ca să se vadă ceva din prima zi."""
    if not registry or not Path(registry).exists():
        return None
    db = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    try:
        decisions, bots = {}, {}
        for i, sym, price, meta in db.execute("SELECT id, symbol, price, meta FROM decisions"):
            decisions[i] = (sym, price)
            try:
                bots[i] = json.loads(meta or "{}").get("bot_signal")
            except ValueError:
                bots[i] = None
        by = {}
        for did, agent, stage, vote in sorted(db.execute("SELECT decision_id, agent, stage, vote FROM votes").fetchall(),
                                              key=lambda r: r[2] != "initial"):
            by.setdefault(did, {})[agent] = vote
    finally:
        db.close()
    calls, hits, total = 0, 0, 0.0
    pnl, liquidated = dict.fromkeys(LEVERAGES, 0.0), dict.fromkeys(LEVERAGES, 0)
    for day in sorted({did[:10] for did in by}):
        todays = {decisions[d][0]: v for d, v in by.items() if d[:10] == day and d in decisions}
        # P10: regula de atunci nu e salvată; se folosește semnalul simplu SMA 20/50 salvat la decizie (aproximare).
        rules = {decisions[d][0]: bots.get(d) for d in by if d[:10] == day and d in decisions}
        for coin, signal in signals_for(f, todays, agent_weights(registry, day), rules).items():
            price = decisions.get(f"{day}:{coin}", (None, 0))[1]
            now = (quotes.get(coin) or [0])[0]
            if not signal or not price or price <= 0 or not now:
                continue
            move = now / price - 1
            if abs(move) > 0.8:          # preț greșit (ex. memecoin cu 0,0000), nu îl socotim
                continue
            calls += 1
            hits += signal * move > 0
            side_move = (1 if signal > 0 else -1) * move
            total += side_move
            for lev in LEVERAGES:
                if lev > 1 and side_move <= -(1 - MAINTENANCE) / lev:     # lichidat: se pierde toată miza
                    pnl[lev] -= STAKE_USD
                    liquidated[lev] += 1
                else:
                    pnl[lev] += STAKE_USD * lev * side_move
    if not calls:
        return {"calls": 0}
    return {"calls": calls, "hit_rate": hits / calls, "mean_pct": 100 * total / calls,
            "stake": STAKE_USD, "pnl": {str(k): round(v, 2) for k, v in pnl.items()},
            "liquidated": {str(k): v for k, v in liquidated.items() if k > 1}}


def snapshot(folder, quotes: dict, now: str) -> list[dict]:
    """Instantaneul orar al conturilor-umbră (valoare la prețul de acum), ca la raportul orar al contului unic."""
    from .dashboard import read_formations
    rows = []
    for r in read_formations(folder, quotes):
        if not r.get("exists"):
            continue
        value = r["live_equity"] if r.get("live") else r["equity"]
        rows.append({"time": now, "key": r["key"], "title": r["title"], "value": round(value, 2),
                     "pnl": round(value - r["initial"], 2), "return_pct": round(100 * (value / r["initial"] - 1), 4),
                     "positions": r["positions"], "longs": r["longs"], "shorts": r["shorts"],
                     "leverage": round(r["leverage"], 4), "drawdown_pct": round(r["drawdown_pct"], 4),
                     "kill_switch": r["kill_switch"]})
    return rows


CSV_COLUMNS = ("time", "key", "value", "pnl", "return_pct", "positions", "longs", "shorts", "leverage",
               "drawdown_pct", "kill_switch")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="formations")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--registry")
    parser.add_argument("--coins", default="")
    parser.add_argument("--day", help="AAAA-LL-ZZ (UTC), implicit azi")
    parser.add_argument("--out-dir")
    parser.add_argument("--data-dir", help="lumânările zilnice (pentru semnalul regulii la P10)")
    parser.add_argument("--funding-dir", help="date-piete/funding (P17)")
    parser.add_argument("--state-dir", help="folderul cu conturile formațiilor (clasamentul pentru P19)")
    parser.add_argument("--snapshot", help="folderul ramurii formatii-ai: scrie instantaneul orar (JSON + rânduri CSV)")
    parser.add_argument("--quotes", help="quotes.json (prețurile de acum), pentru --snapshot")
    parser.add_argument("--out", help="fișierul JSON pentru --snapshot; rândurile CSV merg alături (.csv)")
    args = parser.parse_args(argv)
    if args.snapshot:
        quotes = json.loads(Path(args.quotes).read_text())["quotes"] if args.quotes and Path(args.quotes).exists() else {}
        now = datetime.now(timezone.utc).isoformat(timespec="minutes")
        rows = snapshot(args.snapshot, quotes, now)
        out = Path(args.out)
        out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
        out.with_suffix(".csv").write_text("".join(",".join(str(r[c]) for c in CSV_COLUMNS) + "\n" for r in rows),
                                           encoding="utf-8")
        print(f"{len(rows)} conturi în instantaneu")
        return 0
    if args.list:
        for f in FORMATIONS:
            print(f"{f['key']}\t{f['strategy']}\t{f['title']}\t{f.get('settings', STANDARD)}")
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
    rules = rule_signals(args.data_dir, coins) if args.data_dir else None
    top = meta_top(args.state_dir, day)
    result = build_all(args.registry, coins, day, rules, load_funding(args.funding_dir), top)
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
