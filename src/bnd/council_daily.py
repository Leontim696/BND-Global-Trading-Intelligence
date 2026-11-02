"""Consiliul AI în umbră: o rundă pe zi, fără să tranzacționeze nimic.

Pentru fiecare piață aleasă: construiește întrebarea din prețuri reale
(``council_context``), întreabă cei 5 agenți independent (``CouncilRunner``,
cu buget pe rundă), decide prin majoritate, notează votul fiecăruia în
registru și, după orizont (5 zile), închide decizia cu prețul real. Raportul
compară consiliul cu regula simplă a botului și cu „doar cumpără”.

Moduri: ``mock`` (agenți simulați, gratuit) și ``live`` (plătit prin OpenRouter;
cere BND_ALLOW_LIVE_AI=true, cheie, autorizare cu termen și plafoane de cost).

    python -m src.bnd.council_daily --data-dir data --registry registry.sqlite \\
        --mode mock --report raport.md
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from . import audit_log
from .ai_budgets import BudgetSet
from .ai_gateway import (
    AIGateway,
    AIResponse,
    GatewayMode,
    LiveAuthorization,
)
from .council_context import HORIZON_DAYS, bot_signal, build_context
from .council_runner import CouncilRunner
from .cost_tracker import BudgetLimits, ModelPricing
from .decision_registry import DecisionRegistry
from .decision_rules import DecisionRule, decide
from .fusion_council import AGENTS, Vote
from .market_data import MarketDataError, load_csv
from .regimes import label_regimes
from .openrouter_adapter import OpenRouterAdapter
from .openrouter_models import fetch, parse

# Ten markets from five asset classes: a round costs about 0.02 USD per market,
# and more markets give more decisions to compare in 16 days.
DEFAULT_MARKETS = ("SP500", "NASDAQ100", "GOLD", "SILVER", "CRUDE_OIL", "BITCOIN",
                   "ETHEREUM", "EURUSD", "USDJPY", "US10Y_NOTE")
ASSET_CLASS = {"SP500": "index", "NASDAQ100": "index", "GOLD": "commodity",
               "SILVER": "commodity", "CRUDE_OIL": "commodity", "BITCOIN": "crypto",
               "ETHEREUM": "crypto", "EURUSD": "forex", "USDJPY": "forex",
               "US10Y_NOTE": "bond", "SOLANA": "crypto", "BNB": "crypto", "XRP": "crypto"}
# Piețele consiliului la începutul testului: contextul fiecărei piețe arată mișcarea doar a acestora,
# chiar dacă se adaugă monede noi, ca să nu se schimbe întrebarea pusă pentru piețele vechi.
BASE_PEERS = DEFAULT_MARKETS + ("SOLANA", "BNB", "XRP")


def _extend_asset_classes() -> None:
    from .crypto50 import COINS
    from .universe import DEFENSE_NAMES, STOCK_NAMES
    for name in STOCK_NAMES:
        ASSET_CLASS.setdefault(name, "stock")
    for name, _, meme in COINS:
        ASSET_CLASS.setdefault(name, "memecoin" if meme else "crypto")
    for name in DEFENSE_NAMES:
        ASSET_CLASS.setdefault(name, "armament")


_extend_asset_classes()
DEFAULT_MODELS = {
    # The flagship, as the owner chose. Measured: a nine-market round with Astra
    # was counted at 0.27 USD in total, and the owner's key total matched the
    # ledger exactly. The ledger now uses the cost OpenRouter actually billed.
    "gpt": "openai/gpt-6-astra",
    "claude": "anthropic/claude-opus-5.5",
    "gemini": "google/gemini-4-argon",
    "grok": "x-ai/grok-4.7",
    "deepseek": "deepseek/deepseek-v4-pro",
}
# Reservation per call: what a typical question and answer use, with margin.
ESTIMATED_INPUT_TOKENS = 3500
ESTIMATED_OUTPUT_TOKENS = 1500
LABEL = {Vote.BUY: "CUMPĂRĂ", Vote.SELL: "VINDE", Vote.HOLD: "NU TRANZACȚIONA"}


class SimulatedProvider:
    """Agent simulat: vot deterministic din (agent, piață, întrebare); gratuit."""

    def __init__(self, agent: str):
        self.agent = agent

    def expected_model(self) -> str:
        return f"simulat-{self.agent}"

    def analyze(self, request) -> AIResponse:
        digest = hashlib.sha256(f"{self.agent}|{request.symbol}|{request.context}".encode()).digest()
        vote = (Vote.BUY, Vote.SELL, Vote.HOLD)[digest[0] % 3]
        return AIResponse(self.agent, vote, f"Simulare pentru {request.symbol}.",
                          round(0.6 + digest[1] / 255 * 0.3, 2), f"simulat-{self.agent}", 0, 0)


def simulated_gateway() -> AIGateway:
    gateway = AIGateway(GatewayMode.MOCK)
    for agent in AGENTS:
        gateway.register(agent, SimulatedProvider(agent))
    return gateway


def pricing_from_catalogue(models: dict, catalogue: dict | None = None) -> dict:
    """Prețurile de azi ale modelelor alese, din catalogul public OpenRouter."""
    rows = {row["id"]: row for row in parse(catalogue if catalogue is not None else fetch())}
    missing = [m for m in models.values() if m not in rows]
    if missing:
        raise ValueError("Modele negăsite în catalogul OpenRouter: " + ", ".join(missing))
    return {m: ModelPricing(rows[m]["input_per_million"], rows[m]["output_per_million"])
            for m in models.values()}


def live_gateway(models: dict, pricing: dict, costs_path, now: datetime,
                 round_budget: Decimal, daily_usd: Decimal, monthly_usd: Decimal) -> AIGateway:
    """Gateway plătit: autorizare cu termen de 3 ore, costuri păstrate între rulări."""
    # The council is research: it spends from its own purpose budget, kept in
    # the same file as before so earlier spending still counts.
    costs_path = Path(costs_path)
    storage = BudgetSet(costs_path.parent, {"research": BudgetLimits(daily_usd, monthly_usd)},
                        files={"research": costs_path.name}).storage("research")
    gateway = AIGateway(
        GatewayMode.LIVE,
        cost_storage=storage,
        pricing=pricing,
        estimated_input_tokens=ESTIMATED_INPUT_TOKENS,
        estimated_output_tokens=ESTIMATED_OUTPUT_TOKENS,
        live_authorization=LiveAuthorization(
            approved_by="proprietar (Dorel)", max_round_usd=round_budget,
            expires_at=now + timedelta(hours=3), reference="consiliu-in-umbra"),
    )
    for agent in AGENTS:
        gateway.register(agent, OpenRouterAdapter(
            agent=agent, model=models[agent], timeout=100, allow_live=True,
            max_tokens=4000, reasoning_effort="low"))
    return gateway


def _regime_now(candles):
    """Regimul pieței la ultima închidere (doar din date până atunci); None dacă istoricul e scurt."""
    try:
        return label_regimes(candles).get(candles[-1].open_time)
    except (ValueError, ZeroDivisionError):
        return None


# Peste atâtea zile fără lumânare nouă piața se sare (TON a fost votată pe prețuri din iunie).
# 5 acoperă weekendul și sărbătorile bursiere.
MAX_DATA_AGE_DAYS = 5


def run_markets(data: dict, markets, gateway: AIGateway, registry: DecisionRegistry,
                now: datetime, round_budget: Decimal, horizon_days: int = HORIZON_DAYS,
                sleep=None, peers=None) -> dict:
    """O rundă pe piață; o piață deja decisă azi nu se mai plătește a doua oară."""
    runner = CouncilRunner(gateway, max_attempts=2, backoff_seconds=2.0,
                           **({"sleep": sleep} if sleep else {}))
    settled = registry.settle_from_candles(data, now)
    weights = registry.scorebook().weights()
    results = []
    for market in markets:
        candles = data[market]
        decision_id = f"{now.date().isoformat()}:{market}"
        if registry.has(decision_id):
            results.append({"market": market, "status": "deja_facut"})
            continue
        age = (now.date() - candles[-1].open_time.date()).days
        if age > MAX_DATA_AGE_DAYS:             # piață delistată sau feed oprit: nu votăm pe prețuri vechi
            results.append({"market": market, "status": "date_insuficiente",
                            "error": f"ultima lumânare e din {candles[-1].open_time.date()} ({age} zile)"})
            continue
        others = data if peers is None else {k: v for k, v in data.items() if k in peers}
        try:
            context = build_context(market, candles, others)
        except ValueError as exc:               # prea puține zile de date: se sare piața, restul merge
            results.append({"market": market, "status": "date_insuficiente", "error": str(exc)})
            continue
        outcome = runner.run_round(ASSET_CLASS.get(market, "market"), market, context, round_budget)
        council = outcome["council"]
        majority = decide(council, DecisionRule.MAJORITY)
        weighted = decide(council, DecisionRule.WEIGHTED, weights)
        opinions = council.current_opinions().values()
        trace = {
            # Metadate pentru audit; nu intră în nicio decizie.
            "at": now.isoformat(), "data_through": candles[-1].open_time.isoformat(),
            "context_sha256": hashlib.sha256(context.encode("utf-8")).hexdigest(),
            "agents": {a: {"status": r.get("status"), "model": r.get("model"),
                           "provider": r.get("provider"), "latency_s": r.get("latency_s"),
                           "cost_usd": r.get("cost_usd"), "attempts": len(r.get("attempts", [])),
                           "input_tokens": r.get("input_tokens"),
                           "output_tokens": r.get("output_tokens"),
                           "request_sha256": r.get("request_sha256")}
                       for a, r in outcome["agents"].items()}}
        buys = sum(o.vote == Vote.BUY for o in opinions)
        sells = sum(o.vote == Vote.SELL for o in opinions)
        lean = (buys > sells) - (sells > buys)       # +1 / -1 / 0, HOLD votes ignored
        registry.record(decision_id, now, market, candles[-1].close, council, majority,
                        horizon_days, meta={"bot_signal": bot_signal(candles),
                                            "lean": lean,
                                            "net": buys - sells,
                                            "regime": _regime_now(candles),
                                            "voters": len(opinions),
                                            "weighted": weighted.vote.value,
                                            "weighted_uncertain": weighted.uncertain,
                                            "complete": outcome["complete"],
                                            "trace": trace})
        results.append({
            "market": market, "status": "ok" if outcome["complete"] else "incomplet",
            "price": candles[-1].close, "last_candle": candles[-1].open_time.date().isoformat(),
            "decision": majority.vote.value, "uncertain": majority.uncertain, "lean": lean,
            "reasons": list(majority.reasons), "weighted": weighted.vote.value,
            "bot_signal": bot_signal(candles), "cost_usd": outcome["spent_usd"],
            "agents": {a: {"status": r.get("status"), "vote": (council.current_opinions().get(a).vote.value
                                                              if a in council.current_opinions() else None),
                           "confidence": (council.current_opinions().get(a).confidence
                                          if a in council.current_opinions() else None),
                           "reasoning": (council.current_opinions().get(a).reasoning
                                         if a in council.current_opinions() else None),
                           "model": r.get("model"), "cost_usd": r.get("cost_usd")}
                       for a, r in outcome["agents"].items()},
        })
    return {"time": now.isoformat(), "settled_today": settled, "markets": results,
            "comparison": registry.comparison(), "performance": registry.performance()}


def render(report: dict) -> str:
    when = report["time"][:16].replace("T", " ")
    spent = sum(Decimal(m.get("cost_usd") or "0") for m in report["markets"])
    lines = [f"# Consiliul AI în umbră, {when} UTC", "",
             "Cei 5 agenți votează independent; **nu se tranzacționează nimic**, "
             "doar notăm și comparăm după 5 zile.", ""]
    for m in report["markets"]:
        if m["status"] == "deja_facut":
            lines.append(f"- {m['market']}: decis deja azi (nu s-a plătit a doua oară).")
            continue
        if m["status"] == "date_insuficiente":
            lines.append(f"- {m['market']}: sărită, date insuficiente ({m['error']}).")
            continue
        verdict = LABEL[Vote(m["decision"])]
        note = "" if m["status"] == "ok" else " (rundă incompletă: cineva nu a răspuns)"
        tilt = {1: "înclină spre cumpărare", -1: "înclină spre vânzare", 0: "fără înclinație"}[m["lean"]]
        lines += ["", f"## {m['market']}: **{verdict}** ({tilt})" + note,
                  f"Preț {m['price']:.4f} (închidere {m['last_candle']}); regula simplă a botului: "
                  + {1: "cumpără", -1: "vinde", 0: "nimic"}[m["bot_signal"]]
                  + f"; cost {Decimal(m['cost_usd']):.3f} $.", "",
                  "| Agent | Vot | Încredere | Motiv |", "|---|---|---:|---|"]
        for agent, a in m["agents"].items():
            if a["vote"]:
                lines.append(f"| {agent} | {a['vote']} | {a['confidence']:.2f} | {a['reasoning']} |")
            else:
                lines.append(f"| {agent} | – | – | n-a răspuns ({a['status']}) |")
    if report.get("no_data"):
        lines += ["", "Fără date azi (sărite, nu s-a plătit nimic): " + ", ".join(report["no_data"]) + "."]
    lines += ["", f"Cost total azi: **{spent:.3f} $**.", ""]
    comparison = report["comparison"]
    if comparison["settled_decisions"]:
        lines += ["## Cine a ghicit mai des (decizii încheiate)", "",
                  "| | Apeluri | Au ieșit bine | Câștig mediu pe apel |", "|---|---:|---:|---:|"]
        for name, label in (("council", "Consiliul AI (majoritate clară)"),
                            ("lean", "Înclinația consiliului (fără voturile HOLD)"),
                            ("bot", "Regula simplă a botului"), ("always_long", "Doar cumpără")):
            c = comparison[name]
            hit = "–" if c["hit_rate"] is None else f"{100 * c['hit_rate']:.0f}%"
            mean = "–" if c["mean_return_pct"] is None else f"{c['mean_return_pct']:+.2f}%"
            lines.append(f"| {label} | {c['calls']} | {hit} | {mean} |")
        lines += ["", "_Câștigul mediu e mișcarea prețului în direcția aleasă, fără costuri. "
                      "Cu puține decizii, diferențele pot fi noroc._", ""]
        agents = report["performance"]["agents"]
        if any(a["calls"] for a in agents.values()):
            lines += ["## Pe agenți (doar când au votat BUY sau SELL)", "",
                      "| Agent | Păreri | Au ieșit bine | Eroare medie (Brier) |", "|---|---:|---:|---:|"]
            for name, a in agents.items():
                hit = "–" if a["hit_rate"] is None else f"{100 * a['hit_rate']:.0f}%"
                brier = "–" if a["mean_brier"] is None else f"{a['mean_brier']:.2f}"
                lines.append(f"| {name} | {a['calls']} | {hit} | {brier} |")
            lines.append("")
    else:
        lines += ["_Nicio decizie încheiată încă: prima se închide după "
                  f"{HORIZON_DAYS} zile._", ""]
    return "\n".join(lines)


def render_short(report: dict) -> str:
    """Varianta scurtă: o linie pe piață (decizie, voturi, cost). Raportul complet cu motive rămâne separat."""
    when = report["time"][:16].replace("T", " ")
    spent = sum(Decimal(m.get("cost_usd") or "0") for m in report["markets"])
    lines = [f"# Consiliul AI în umbră (scurt), {when} UTC", "",
             "| Piață | Decizie | Înclinație | BUY | SELL | HOLD | Cost $ |", "|---|---|---|---:|---:|---:|---:|"]
    for m in report["markets"]:
        if m["status"] == "deja_facut":
            lines.append(f"| {m['market']} | deja decis azi | | | | | |")
            continue
        if m["status"] == "date_insuficiente":
            lines.append(f"| {m['market']} | sărită (date insuficiente) | | | | | |")
            continue
        votes = [a["vote"] for a in m["agents"].values() if a["vote"]]
        tilt = {1: "cumpără", -1: "vinde", 0: "–"}[m["lean"]]
        lines.append(f"| {m['market']} | {LABEL[Vote(m['decision'])]} | {tilt} | {votes.count('BUY')} | "
                     f"{votes.count('SELL')} | {votes.count('HOLD')} | {Decimal(m['cost_usd']):.3f} |")
    if report.get("no_data"):
        lines += ["", "Fără date azi: " + ", ".join(report["no_data"]) + "."]
    lines += ["", f"Cost total: **{spent:.3f} $**. Motivele fiecărui agent sunt în raportul complet.", ""]
    return "\n".join(lines)


def _decimal(text: str, name: str) -> Decimal:
    try:
        value = Decimal(text)
    except Exception as exc:
        raise ValueError(f"{name} invalid") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} trebuie să fie pozitiv")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="council_daily")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--costs", help="fișier SQLite cu costurile (obligatoriu în modul live)")
    parser.add_argument("--markets", default=",".join(DEFAULT_MARKETS))
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--round-budget", default="0.60", help="plafon pe rundă (o piață), dolari")
    parser.add_argument("--daily-budget", default="3.00")
    parser.add_argument("--monthly-budget", default="38")
    parser.add_argument("--report")
    parser.add_argument("--report-short", help="rezumat pe o linie per piață (pentru multe piețe)")
    parser.add_argument("--json")
    parser.add_argument("--audit-log", help="append a hash-chained audit entry here")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
        if not markets or len(set(markets)) != len(markets):
            raise ValueError("Lista de piețe e goală sau are duplicate")
        if not all(re.fullmatch(r"[A-Z0-9_]{1,20}", m) for m in markets):
            raise ValueError("Numele piețelor pot avea doar litere mari, cifre și _")
        data, no_data = {}, []
        for market in markets:
            path = Path(args.data_dir) / f"{market}.csv"
            if not path.exists():
                no_data.append(market)          # o sursă căzută nu oprește consiliul pe restul piețelor
                continue
            data[market] = load_csv(path)
        if not data:
            raise ValueError("Nu există date pentru nicio piață: " + ", ".join(no_data))
        markets = [m for m in markets if m in data]
        if args.mode == "live":
            if not args.costs:
                raise ValueError("Modul live cere --costs")
            models = {a: os.getenv(f"BND_MODEL_{a.upper()}", "").strip() or DEFAULT_MODELS[a]
                      for a in AGENTS}
            gateway = live_gateway(models, pricing_from_catalogue(models), args.costs, now,
                                   _decimal(args.round_budget, "round-budget"),
                                   _decimal(args.daily_budget, "daily-budget"),
                                   _decimal(args.monthly_budget, "monthly-budget"))
        else:
            gateway = simulated_gateway()
        registry = DecisionRegistry(args.registry)
        report = run_markets(data, markets, gateway, registry, now,
                             _decimal(args.round_budget, "round-budget"), peers=BASE_PEERS)
        report["no_data"] = no_data
    except (MarketDataError, ValueError, OSError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    if args.audit_log:
        audit_log.append(args.audit_log, "council_run", {
            "mode": args.mode, "markets": markets,
            "decided": sum(m["status"] not in ("deja_facut", "date_insuficiente") for m in report["markets"]),
            "incomplete": sum(m["status"] == "incomplet" for m in report["markets"]),
            "cost_usd": str(sum(Decimal(m.get("cost_usd") or "0") for m in report["markets"])),
            "settled": report["settled_today"]}, now)
    text = render(report)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    if args.report_short:
        Path(args.report_short).write_text(render_short(report), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
