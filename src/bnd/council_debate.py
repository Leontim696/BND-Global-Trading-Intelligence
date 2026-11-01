"""Dezbatere în umbră (Fusion Council 2.0): runda a doua, doar pe piețele cu obiecții reale.

Runda 1 (producția) rămâne neatinsă: cinci agenți votează independent. Aici, pentru un subset mic de
piețe unde există o obiecție serioasă, agenții primesc părerile celorlalți și pot REVIZUI votul doar
dacă un argument concret îi convinge. Voturile inițiale și cele revizuite se păstrează ambele, într-un
registru SEPARAT (``debate-registry.sqlite``), deci contul și evaluarea consiliului nu se schimbă.
După 5 zile se compară, pe aceleași piețe, înainte și după dezbatere
(``council_analytics.before_after``).

Declanșator (nu orice dezacord: 81% dintre piețe au măcar un vot diferit):
- opoziție directă: există și BUY, și SELL;
- vot izolat puternic: un BUY sau SELL cu încredere >= 0,70 când majoritatea agenților a votat HOLD.
Se aleg cele mai puternice cel mult ``--max`` piețe. Costul: ~5 apeluri pe piață, cu prompt mai lung.

Rulează doar manual (workflow cu confirmarea RUN-PAID-TEST pentru live). ``mock`` și ``--settle-only``
sunt gratuite.

    python -m src.bnd.council_debate --mode mock --report LATEST.json --data-dir data \
        --registry state/debate-registry.sqlite --max 12
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .council_context import build_context
from .council_daily import (ASSET_CLASS, BASE_PEERS, DEFAULT_MODELS, _decimal, _regime_now,
                            live_gateway, pricing_from_catalogue, simulated_gateway)
from .council_runner import CouncilRunner
from .decision_registry import DecisionRegistry
from .decision_rules import DecisionRule, decide
from .fusion_council import AGENTS, FusionCouncil, Opinion, Vote
from .market_data import load_csv

STRONG_CONFIDENCE = 0.70
DEFAULT_MAX = 12
REASON_CHARS = 500


def opinions_from_market(entry: dict) -> dict:
    """agent -> Opinion din rândul unei piețe din raport.json (doar agenții cu vot valid)."""
    out = {}
    for agent, cell in (entry.get("agents") or {}).items():
        try:
            out[agent] = Opinion(agent, Vote(cell["vote"]), (cell.get("reasoning") or "fără motiv").strip() or "fără motiv",
                                 float(cell["confidence"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def trigger(opinions: dict) -> dict | None:
    """Motivul dezbaterii și puterea lui, sau None dacă nu merită o rundă plătită."""
    if len(opinions) != len(AGENTS):
        return None
    votes = list(opinions.values())
    buys = [o for o in votes if o.vote == Vote.BUY]
    sells = [o for o in votes if o.vote == Vote.SELL]
    if buys and sells:
        return {"reason": "opoziție directă BUY–SELL",
                "strength": 1.0 + min(max(o.confidence for o in buys), max(o.confidence for o in sells))}
    # Fără opoziție directă: un vot direcțional izolat, dar sigur pe el, împotriva liniei HOLD a celorlalți.
    holds = sum(o.vote == Vote.HOLD for o in votes)
    directional = buys + sells
    strong = [o for o in directional if o.confidence >= STRONG_CONFIDENCE]
    if strong and holds > len(directional):
        return {"reason": "vot izolat puternic împotriva HOLD", "strength": max(o.confidence for o in strong)}
    return None


def select(report: dict, limit: int = DEFAULT_MAX, skip=()) -> list[dict]:
    """Cele mai puternice piețe cu declanșator: [{market, opinions, trigger}]."""
    found = []
    for entry in report.get("markets", []):
        if entry.get("status") != "ok" or entry["market"] in skip:
            continue
        opinions = opinions_from_market(entry)
        why = trigger(opinions)
        if why:
            found.append({"market": entry["market"], "entry": entry, "opinions": opinions, "trigger": why})
    found.sort(key=lambda f: -f["trigger"]["strength"])
    return found[:limit]


def debate_context(base: str, opinions: dict) -> str:
    lines = [base, "", "DEZBATERE (runda 2). Mai jos sunt părerile din runda 1 ale celor 5 agenți, inclusiv a ta.",
             "Reconsideră-ți votul. Schimbă-l DOAR dacă un argument concret al altui agent te convinge; nu "
             "schimba doar pentru că majoritatea e de altă părere. Dacă îți păstrezi votul, spune ce obiecție "
             "ai respins și de ce. Răspunde în același format ca înainte."]
    for agent in AGENTS:
        o = opinions.get(agent)
        if o:
            lines.append(f"- {agent}: {o.vote.value} (încredere {o.confidence:.2f}). "
                         f"{o.reasoning[:REASON_CHARS]}")
    return "\n".join(lines)


def run_debates(report: dict, data: dict, gateway, registry: DecisionRegistry, now: datetime,
                round_budget: Decimal, limit: int = DEFAULT_MAX) -> dict:
    day = report["time"][:10]
    runner = CouncilRunner(gateway)
    settled = registry.settle_from_candles(data, now)
    skip = {m["market"] for m in report.get("markets", []) if registry.has(f"{day}:{m['market']}")}
    chosen = select(report, limit, skip)
    results = []
    for item in chosen:
        market, entry, initial = item["market"], item["entry"], item["opinions"]
        candles = [c for c in data.get(market, ())
                   if c.open_time.date().isoformat() <= entry.get("last_candle", "9999")]
        peers = {k: [c for c in v if c.open_time.date().isoformat() <= entry.get("last_candle", "9999")]
                 for k, v in data.items() if k in BASE_PEERS}
        try:
            base = build_context(market, candles, peers)
        except ValueError as exc:
            results.append({"market": market, "status": "date_insuficiente", "error": str(exc)})
            continue
        outcome = runner.run_round(ASSET_CLASS.get(market, "market"), market,
                                   debate_context(base, initial), round_budget)
        council = FusionCouncil()
        for opinion in initial.values():
            council.submit(opinion)
        changed = []
        for agent, revised in outcome["council"].current_opinions().items():
            before = initial[agent]
            if revised.vote != before.vote:
                changed.append({"agent": agent, "from": before.vote.value, "to": revised.vote.value})
            if revised.vote != before.vote or revised.confidence != before.confidence:
                council.revise(Opinion(agent, revised.vote, revised.reasoning, revised.confidence))
        final = council.current_opinions().values()
        buys = sum(o.vote == Vote.BUY for o in final)
        sells = sum(o.vote == Vote.SELL for o in final)
        majority = decide(council, DecisionRule.MAJORITY)
        i_buys = sum(o.vote == Vote.BUY for o in initial.values())
        i_sells = sum(o.vote == Vote.SELL for o in initial.values())
        registry.record(f"{day}:{market}", now, market, candles[-1].close, council, majority,
                        meta={"shadow": "debata", "trigger": item["trigger"]["reason"],
                              "initial_lean": (i_buys > i_sells) - (i_sells > i_buys),
                              "lean": (buys > sells) - (sells > buys), "net": buys - sells,
                              "bot_signal": entry.get("bot_signal"), "regime": _regime_now(candles),
                              "complete": outcome["complete"]})
        results.append({"market": market, "status": "ok" if outcome["complete"] else "incomplet",
                        "trigger": item["trigger"]["reason"], "changed": changed,
                        "cost_usd": outcome["spent_usd"]})
    return {"time": now.isoformat(), "report_day": day, "settled": settled, "candidates": len(chosen),
            "markets": results}


def render(result: dict) -> str:
    spent = sum(Decimal(m.get("cost_usd") or "0") for m in result["markets"])
    lines = [f"# Dezbatere în umbră, {result['time'][:16].replace('T', ' ')} UTC (piețe din {result['report_day']})", "",
             "Nu se tranzacționează nimic; contul și consiliul principal nu sunt atinse.", "",
             "| Piață | Declanșator | Voturi schimbate | Cost $ |", "|---|---|---|---|"]
    for m in result["markets"]:
        change = ", ".join(f"{c['agent']} {c['from']}→{c['to']}" for c in m.get("changed", [])) or "–"
        lines.append(f"| {m['market']} | {m.get('trigger', m.get('status'))} | {change} | {m.get('cost_usd', '–')} |")
    lines += ["", f"Cost total: **{spent} $**. Decizii închise azi: {result['settled']}."]
    return "\n".join(lines) + "\n"


def needed(report: dict, registry: DecisionRegistry, now: datetime, limit: int = DEFAULT_MAX) -> list[str]:
    """Piețele pentru care trebuie lumânări: cele de dezbătut, cele de închis și cele de context."""
    day = report["time"][:10]
    skip = {m["market"] for m in report.get("markets", []) if registry.has(f"{day}:{m['market']}")}
    names = {c["market"] for c in select(report, limit, skip)} | {r["symbol"] for r in registry.due(now)}
    return sorted(names | set(BASE_PEERS))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="council_debate")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--settle-only", action="store_true", help="doar închide deciziile scadente (gratuit)")
    parser.add_argument("--needed", action="store_true", help="afișează piețele pentru care trebuie date (gratuit)")
    parser.add_argument("--report", help="raport.json al consiliului (cu motivele agenților)")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--costs")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX)
    parser.add_argument("--round-budget", default="0.60")
    parser.add_argument("--daily-budget", default="1.60")
    parser.add_argument("--monthly-budget", default="12")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        if not 1 <= args.max <= 30:
            raise ValueError("--max trebuie să fie între 1 și 30")
        registry = DecisionRegistry(args.registry)
        report = json.loads(Path(args.report).read_text(encoding="utf-8")) if args.report else {"markets": [], "time": now.isoformat()}
        if args.needed:
            print(",".join(needed(report, registry, now, args.max)))
            return 0
        names = {m["market"] for m in report.get("markets", [])} | {r["symbol"] for r in registry.due(now)} \
            | set(BASE_PEERS)
        data = {}
        for name in names:
            path = Path(args.data_dir) / f"{name}.csv"
            if path.exists():
                data[name] = load_csv(path)
        if args.settle_only:
            print(f"Închise: {registry.settle_from_candles(data, now)}")
            return 0
        if not args.report:
            raise ValueError("--report e obligatoriu (în afară de --settle-only)")
        if args.mode == "live":
            if not args.costs:
                raise ValueError("Modul live cere --costs")
            models = {a: os.getenv(f"BND_MODEL_{a.upper()}", "").strip() or DEFAULT_MODELS[a] for a in AGENTS}
            gateway = live_gateway(models, pricing_from_catalogue(models), args.costs, now,
                                   _decimal(args.round_budget, "round-budget"),
                                   _decimal(args.daily_budget, "daily-budget"),
                                   _decimal(args.monthly_budget, "monthly-budget"))
        else:
            gateway = simulated_gateway()
        result = run_debates(report, data, gateway, registry, now,
                             _decimal(args.round_budget, "round-budget"), args.max)
    except (ValueError, OSError, KeyError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    text = render(result)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
