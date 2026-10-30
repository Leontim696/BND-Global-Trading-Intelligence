"""Per-purpose AI budgets and model choice by task: offline, no calls."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.bnd.ai_budgets import BudgetSet, ModelOption, choose_model, limits
from src.bnd.cost_tracker import BudgetExceeded, ModelPricing

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
OPTIONS = [
    ModelOption("cheap", 1, ModelPricing(Decimal("0.1"), Decimal("0.4"))),
    ModelOption("standard", 2, ModelPricing(Decimal("1"), Decimal("4"))),
    ModelOption("strong-a", 3, ModelPricing(Decimal("5"), Decimal("20"))),
    ModelOption("strong-b", 3, ModelPricing(Decimal("3"), Decimal("15"))),
]


def test_purposes_have_separate_budgets(tmp_path):
    budgets = BudgetSet(tmp_path, {"development": limits(1, 10), "trading": limits(5, 50)})

    budgets.storage("development").reserve("0.9", NOW)
    with pytest.raises(BudgetExceeded):
        budgets.storage("development").reserve("0.2", NOW)
    # Development ran out; trading money is untouched.
    assert budgets.storage("trading").reserve("4", NOW)
    summary = budgets.summary()
    assert summary["trading"]["daily_limit_usd"] == Decimal("5")


def test_purpose_without_budget_cannot_spend(tmp_path):
    budgets = BudgetSet(tmp_path, {"trading": limits(5, 50)})

    with pytest.raises(ValueError, match="may not spend"):
        budgets.storage("research")
    with pytest.raises(ValueError, match="Unknown purpose"):
        BudgetSet(tmp_path, {"gambling": limits(1, 1)})


def test_cheapest_adequate_model_per_task():
    model, cost = choose_model("commit_message", OPTIONS)
    assert model == "cheap" and cost == Decimal("0.00023")

    assert choose_model("code_review", OPTIONS)[0] == "standard"
    # Trading votes never go to a cheaper tier, whatever the price.
    assert choose_model("council_vote", OPTIONS)[0] == "strong-b"


def test_no_adequate_model_is_an_error():
    with pytest.raises(ValueError, match="tier 3"):
        choose_model("council_vote", OPTIONS[:2])
    with pytest.raises(ValueError, match="Unknown task"):
        choose_model("guess_lottery", OPTIONS)
    with pytest.raises(ValueError):
        ModelOption("x", 4, OPTIONS[0].pricing)
