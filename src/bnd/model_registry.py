"""Registrul modelelor folosite de cei cinci agenți: configurație, cost, latență, disponibilitate.

Configurația vine din `council_daily.DEFAULT_MODELS` (și variabilele BND_MODEL_*).
Costurile vin din registrul de costuri; latența și disponibilitatea din urma
(`trace`) pe care o lasă fiecare analiză în registrul de decizii (există de la
analizele făcute după introducerea ei). Doar citire.

    python -m src.bnd.model_registry --registry registry.sqlite --costs costs.sqlite
"""

import argparse
import json
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

from .council_daily import DEFAULT_MODELS

PROVIDERS = {"gpt": "OpenAI", "claude": "Anthropic", "gemini": "Google", "grok": "xAI",
             "deepseek": "DeepSeek"}
ROUTER = "OpenRouter (https://openrouter.ai), cheie în secretul OPENROUTER_API_KEY"
CONFIG = {"reasoning_effort": "low", "max_tokens": 4000, "timeout_s": 100, "attempts": 2}


def _connect(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True) if path and Path(path).exists() else None


def build(registry=None, costs=None) -> dict:
    stats = {a: {"calls": 0, "ok": 0, "latencies": [], "cost": Decimal("0"), "tokens_in": 0,
                 "tokens_out": 0, "models": set()} for a in DEFAULT_MODELS}
    db = _connect(costs)
    if db is not None:
        try:
            for agent, model, tin, tout, cost in db.execute(
                    "SELECT agent, model, input_tokens, output_tokens, cost_usd FROM usage_records"):
                if agent in stats:
                    s = stats[agent]
                    s["cost"] += Decimal(cost)
                    s["tokens_in"] += tin
                    s["tokens_out"] += tout
                    s["models"].add(model)
                    s["paid_calls"] = s.get("paid_calls", 0) + 1
        finally:
            db.close()
    db = _connect(registry)
    traced = 0
    if db is not None:
        try:
            for (meta,) in db.execute("SELECT meta FROM decisions"):
                trace = json.loads(meta or "{}").get("trace")
                if not trace:
                    continue
                traced += 1
                for agent, a in trace["agents"].items():
                    if agent in stats:
                        stats[agent]["calls"] += 1
                        stats[agent]["ok"] += a.get("status") == "ok"
                        if a.get("latency_s") is not None:
                            stats[agent]["latencies"].append(a["latency_s"])
        finally:
            db.close()
    rows = {}
    for agent, model in DEFAULT_MODELS.items():
        s = stats[agent]
        paid = s.get("paid_calls", 0)
        rows[agent] = {
            "provider": PROVIDERS[agent], "model": model, "via": ROUTER, "config": CONFIG,
            "paid_calls": paid, "total_cost_usd": float(s["cost"]),
            "mean_cost_usd": float(s["cost"] / paid) if paid else None,
            "tokens_in": s["tokens_in"], "tokens_out": s["tokens_out"],
            "models_seen": sorted(s["models"]),
            "traced_calls": s["calls"],
            "availability": s["ok"] / s["calls"] if s["calls"] else None,
            "mean_latency_s": sum(s["latencies"]) / len(s["latencies"]) if s["latencies"] else None,
        }
    return {"agents": rows, "traced_decisions": traced}


def render(data: dict) -> str:
    lines = ["| Agent | Furnizor | Model exact | Apeluri plătite | Cost total | Cost mediu | Disponibilitate | Latență medie |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for agent, r in data["agents"].items():
        avail = "–" if r["availability"] is None else f"{100 * r['availability']:.0f}%"
        lat = "–" if r["mean_latency_s"] is None else f"{r['mean_latency_s']:.1f} s"
        mean = "–" if r["mean_cost_usd"] is None else f"{r['mean_cost_usd']:.4f} $"
        lines.append(f"| {agent} | {r['provider']} | `{r['model']}` | {r['paid_calls']} | "
                     f"{r['total_cost_usd']:.3f} $ | {mean} | {avail} | {lat} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="model_registry")
    parser.add_argument("--registry")
    parser.add_argument("--costs")
    args = parser.parse_args(argv)
    data = build(args.registry, args.costs)
    print(render(data), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
