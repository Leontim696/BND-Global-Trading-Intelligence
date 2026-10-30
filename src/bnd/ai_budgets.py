"""Separate AI budgets per purpose, and the cheapest adequate model per task.

Purposes: research (analysis, debates), development (code review, tooling)
and trading (council votes for paper decisions). Each has its own SQLite
cost file and daily/monthly limits, so a long code review cannot spend
the money set aside for trading decisions.

Model choice: every task needs a minimum quality tier (1 cheap, 2 standard,
3 strongest). Among the configured models of at least that tier, the one
with the lowest cost for the task's typical token use is chosen. Model
names and prices come from the owner's configuration; nothing here calls
a model.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .cost_storage import SQLiteCostStorage
from .cost_tracker import BudgetLimits, CostTracker, ModelPricing

PURPOSES = ("research", "development", "trading")

# Minimum tier and typical tokens (input, output) per task.
TASKS = {
    "council_vote": (3, 3000, 600),     # trading decisions: strongest models only
    "debate_reply": (2, 4000, 800),
    "news_summary": (1, 6000, 500),
    "code_review": (2, 12000, 1500),
    "commit_message": (1, 1500, 200),
}


class BudgetSet:
    """One cost storage per purpose, each with its own limits."""

    def __init__(self, folder, limits: dict):
        unknown = set(limits) - set(PURPOSES)
        if unknown:
            raise ValueError("Unknown purpose: " + ", ".join(sorted(unknown)))
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        self._storages = {
            purpose: SQLiteCostStorage(folder / f"ai-costs-{purpose}.sqlite", purpose_limits)
            for purpose, purpose_limits in limits.items()
        }

    def storage(self, purpose: str) -> SQLiteCostStorage:
        if purpose not in self._storages:
            raise ValueError(f"No budget configured for {purpose!r}: it may not spend")
        return self._storages[purpose]

    def summary(self) -> dict:
        return {purpose: storage.summary() for purpose, storage in self._storages.items()}


@dataclass(frozen=True)
class ModelOption:
    model: str
    tier: int
    pricing: ModelPricing

    def __post_init__(self):
        if self.tier not in (1, 2, 3) or not self.model.strip():
            raise ValueError("Model needs a name and a tier of 1, 2 or 3")


def choose_model(task: str, options) -> tuple[str, Decimal]:
    """Cheapest model good enough for ``task`` and its estimated cost in USD."""
    if task not in TASKS:
        raise ValueError(f"Unknown task {task!r}")
    tier, tokens_in, tokens_out = TASKS[task]
    candidates = [
        (CostTracker.estimate_cost(tokens_in, tokens_out, option.pricing), option.model)
        for option in options if option.tier >= tier
    ]
    if not candidates:
        raise ValueError(f"No configured model reaches tier {tier} for {task}")
    cost, model = min(candidates)
    return model, cost


def limits(daily_usd, monthly_usd) -> BudgetLimits:
    return BudgetLimits(Decimal(str(daily_usd)), Decimal(str(monthly_usd)))
