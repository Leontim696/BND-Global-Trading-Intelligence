"""Orchestratorul AI: cine face ce, cu ce buget, și ce se întâmplă dacă pică.

Pentru o listă de sarcini (vot de consiliu, rezumat, revizuire de cod...), alege
pentru fiecare cel mai ieftin model suficient de bun (``ai_budgets.TASKS``), ține
două modele de rezervă în ordinea costului (un model local gratuit apare primul
la sarcinile simple) și verifică dacă bugetul zilnic al scopului acoperă planul.
Doar planifică: nu apelează niciun model.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from .ai_budgets import BudgetSet, ModelOption, ranked_models

TASK_PURPOSE = {"council_vote": "research", "debate_reply": "research",
                "news_summary": "research", "code_review": "development",
                "commit_message": "development"}


@dataclass(frozen=True)
class Assignment:
    task: str
    purpose: str
    model: str
    fallbacks: tuple
    estimated_usd: Decimal
    allowed: bool
    reason: str


def plan(tasks: list, options: list[ModelOption], budgets: BudgetSet | None = None,
         now: datetime | None = None) -> list[Assignment]:
    """Un plan pe sarcină; sarcinile din același scop consumă împreună bugetul zilei."""
    now = now or datetime.now(timezone.utc)
    spent_in_plan: dict = {}
    plan_rows = []
    for task in tasks:
        if task not in TASK_PURPOSE:
            raise ValueError(f"Unknown task {task!r}")
        purpose = TASK_PURPOSE[task]
        ranked = ranked_models(task, options)
        model, cost = ranked[0]
        allowed, reason = True, "în buget"
        if cost > 0:
            try:
                summary = budgets.storage(purpose).summary(now) if budgets else None
            except ValueError:
                allowed, reason = False, f"nu există buget pentru «{purpose}»"
            else:
                if summary is not None:
                    left = (summary["daily_limit_usd"] - summary["daily_committed_usd"]
                            - spent_in_plan.get(purpose, Decimal("0")))
                    if cost > left:
                        allowed, reason = False, f"bugetul zilei pentru «{purpose}» nu acoperă {cost:.4f} $"
            if allowed:
                spent_in_plan[purpose] = spent_in_plan.get(purpose, Decimal("0")) + cost
        plan_rows.append(Assignment(task, purpose, model, tuple(m for m, _ in ranked[1:3]),
                                    cost, allowed, reason))
    return plan_rows


def total_cost(rows: list[Assignment]) -> Decimal:
    return sum((r.estimated_usd for r in rows if r.allowed), Decimal("0"))
