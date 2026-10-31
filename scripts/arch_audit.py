"""Matricea de integrare: ce modul ce folosește, cine îl folosește și dacă rulează în producție.

Citește doar codul (importuri, workflow-uri, rutine documentate) și scrie
docs/MATRICE_INTEGRARE.md. Nu rulează nimic din proiect.

    python scripts/arch_audit.py > docs/MATRICE_INTEGRARE.md
"""

import ast
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "bnd"

LAYERS = {
    "Date de piață": ["market_data", "universe", "calendars", "instruments", "funding", "intraday",
                      "rolls", "quotes_snapshot"],
    "Strategii și cercetare": ["strategies", "regimes", "signal_pipeline", "cross_sectional",
                               "walk_forward", "portfolio", "portfolio_walk_forward", "backtester",
                               "backtest_cli", "backtest_summary", "robustness", "significance",
                               "compare_wfo", "quant_backtest", "quant_evaluation", "quant_metrics",
                               "quant_report"],
    "Motor de trading virtual și risc": ["paper_engine", "paper_runner", "risk_engine", "scenarios",
                                         "safety", "trade_coordinator", "audit_log", "paper_demo"],
    "Consiliul AI": ["council_daily", "council_context", "council_runner", "council_round",
                     "council_orchestrator", "fusion_council", "debate_engine", "decision_rules",
                     "decision_registry", "crypto_signals", "live_council_bridge"],
    "Furnizori AI și costuri": ["ai_gateway", "ai_budgets", "ai_cache", "ai_smoke_test", "cost_tracker",
                                "cost_storage", "cost_report", "openrouter_adapter", "openrouter_models",
                                "multi_ai_providers", "local_ai", "orchestrator", "review_budget",
                                "code_review_loop", "manual_live_review", "three_agents_live"],
    "Rapoarte, monitorizare, aplicație": ["report_card", "report_html", "health_check", "notify",
                                          "dashboard"],
}
# Rulate de rutinele programate ale sesiunii (nu apar în workflow-uri).
ROUTINES = {"report_html", "dashboard"}


def imports():
    mods = {p.stem for p in SRC.glob("*.py") if p.stem != "__init__"}
    uses = defaultdict(set)
    for path in SRC.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                names = [node.module.split(".")[0]] if node.module else [a.name for a in node.names]
                uses[path.stem].update(n for n in names if n in mods)
    return mods, uses


def main() -> None:
    mods, uses = imports()
    used_by = defaultdict(set)
    for user, deps in uses.items():
        for dep in deps:
            used_by[dep].add(user)
    runtime = " ".join(p.read_text(encoding="utf-8") for p in (ROOT / ".github" / "workflows").glob("*.yml"))
    runtime += " ".join(p.read_text(encoding="utf-8") for p in (ROOT / "scripts").glob("*.py"))
    tests = " ".join(p.read_text(encoding="utf-8") for p in (ROOT / "tests").glob("*.py"))
    layer_of = {m: layer for layer, names in LAYERS.items() for m in names}
    unknown = sorted(mods - set(layer_of))
    print("# Matrice de integrare (generată de `scripts/arch_audit.py`)\n")
    print("Coloana „Producție” = rulat direct de un workflow sau script; „Rutină” = rulat de rutinele "
          "programate ale sesiunii; „Doar import” = folosit doar de alt modul; „Neconectat” = nu e "
          "apelat de nimic în afară de teste.\n")
    for layer, names in LAYERS.items():
        print(f"## {layer}\n\n| Modul | Folosit de | Producție | Teste |\n|---|---|---|---|")
        for name in sorted(names):
            if name not in mods:
                continue
            direct = bool(re.search(r"src\.bnd\." + name + r"\b", runtime))
            users = sorted(used_by[name])
            if direct:
                status = "da (workflow/script)"
            elif name in ROUTINES:
                status = "rutină"
            elif users:
                status = "doar import"
            else:
                status = "**neconectat**"
            tested = "da" if re.search(r"\b" + name + r"\b", tests) else "**nu**"
            print(f"| {name} | {', '.join(users) or '–'} | {status} | {tested} |")
        print()
    if unknown:
        print("## Module neclasificate\n\n" + ", ".join(unknown) + "\n")


if __name__ == "__main__":
    main()
