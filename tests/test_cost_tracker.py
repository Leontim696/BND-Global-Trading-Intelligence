
"""Tests for BND AI Token & Cost Tracker."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.bnd.cost_tracker import (
    BudgetExceeded,
    BudgetLimits,
    CostTracker,
    ModelPricing,
    UsageRecord,
    money,
)
from src.bnd.fusion_council import AGENTS


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def make_tracker(daily="5", monthly="50"):
    return CostTracker(
        limits=BudgetLimits(
            daily_usd=Decimal(daily),
            monthly_usd=Decimal(monthly),
        )
    )


def make_record(
    agent="gpt",
    cost="0.50",
    timestamp=NOW,
    input_tokens=100,
    output_tokens=50,
):
    return UsageRecord(
        agent=agent,
        model="test/model",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=Decimal(cost),
        timestamp=timestamp,
    )


def commit_usage(
    tracker,
    cost="0.50",
    agent="gpt",
    timestamp=NOW,
):
    reservation = tracker.reserve(
        cost,
        now=timestamp,
    )
    tracker.finalize(
        reservation,
        make_record(
            agent=agent,
            cost=cost,
            timestamp=timestamp,
        ),
    )


def test_five_agents():
    assert len(AGENTS) == 5


def test_money_conversion():
    assert money("1.25") == Decimal("1.25")
    assert money(0.5) == Decimal("0.5")


@pytest.mark.parametrize(
    "value",
    [-1, "invalid", "NaN", "Infinity", None],
)
def test_invalid_money_rejected(value):
    with pytest.raises(ValueError):
        money(value)


def test_model_pricing():
    pricing = ModelPricing(
        input_per_million="2.50",
        output_per_million="10.00",
    )

    assert pricing.input_per_million == Decimal("2.50")
    assert pricing.output_per_million == Decimal("10.00")


def test_estimate_cost():
    pricing = ModelPricing(
        input_per_million="2",
        output_per_million="8",
    )

    cost = CostTracker.estimate_cost(
        input_tokens=1000,
        output_tokens=500,
        pricing=pricing,
    )

    assert cost == Decimal("0.006")


@pytest.mark.parametrize(
    "tokens",
    [-1, 1.5, True],
)
def test_invalid_token_count_rejected(tokens):
    pricing = ModelPricing("1", "1")

    with pytest.raises(ValueError):
        CostTracker.estimate_cost(
            tokens, 100, pricing
        )


def test_zero_token_cost():
    pricing = ModelPricing("5", "15")

    assert (
        CostTracker.estimate_cost(0, 0, pricing)
        == Decimal("0")
    )


def test_budget_limits():
    limits = BudgetLimits("5", "50")

    assert limits.daily_usd == Decimal("5")
    assert limits.monthly_usd == Decimal("50")


def test_reserve_budget():
    tracker = make_tracker()

    reservation = tracker.reserve("1.25", now=NOW)

    assert reservation == 1
    assert len(tracker.reservations) == 1


def test_reservation_ids_are_unique():
    tracker = make_tracker()

    first = tracker.reserve("1", now=NOW)
    second = tracker.reserve("1", now=NOW)

    assert first != second


def test_daily_limit_rejected():
    tracker = make_tracker(daily="2")

    tracker.reserve("1.50", now=NOW)

    with pytest.raises(
        BudgetExceeded,
        match="Daily",
    ):
        tracker.reserve("0.51", now=NOW)


def test_monthly_limit_rejected():
    tracker = make_tracker(
        daily="10",
        monthly="2",
    )

    tracker.reserve("1.50", now=NOW)

    with pytest.raises(
        BudgetExceeded,
        match="Monthly",
    ):
        tracker.reserve("0.51", now=NOW)


def test_exact_budget_allowed():
    tracker = make_tracker(
        daily="2",
        monthly="2",
    )

    tracker.reserve("2", now=NOW)

    assert len(tracker.reservations) == 1


def test_release_reservation():
    tracker = make_tracker(daily="1")

    reservation = tracker.reserve("1", now=NOW)
    tracker.release(reservation)

    assert tracker.reservations == {}
    assert tracker.reserve("1", now=NOW) == 2


def test_unknown_reservation_rejected():
    tracker = make_tracker()

    with pytest.raises(
        ValueError,
        match="Unknown reservation",
    ):
        tracker.release(999)


def test_finalize_usage():
    tracker = make_tracker()

    reservation = tracker.reserve("0.50", now=NOW)
    tracker.finalize(
        reservation,
        make_record(cost="0.50"),
    )

    assert len(tracker.records) == 1
    assert len(tracker.reservations) == 0


def test_finalize_unknown_reservation():
    tracker = make_tracker()

    with pytest.raises(
        ValueError,
        match="Unknown reservation",
    ):
        tracker.finalize(999, make_record())


def test_actual_cost_below_estimate():
    tracker = make_tracker(daily="1")

    reservation = tracker.reserve("0.80", now=NOW)
    tracker.finalize(
        reservation,
        make_record(cost="0.50"),
    )

    assert tracker.summary(NOW)[
        "daily_committed_usd"
    ] == Decimal("0.50")


def test_actual_cost_above_estimate_within_budget():
    tracker = make_tracker(daily="2")

    reservation = tracker.reserve("0.50", now=NOW)
    tracker.finalize(
        reservation,
        make_record(cost="1.50"),
    )

    assert tracker.summary(NOW)[
        "daily_committed_usd"
    ] == Decimal("1.50")


def test_actual_cost_exceeds_budget():
    tracker = make_tracker(daily="1")

    reservation = tracker.reserve("0.50", now=NOW)

    with pytest.raises(
        BudgetExceeded,
        match="daily",
    ):
        tracker.finalize(
            reservation,
            make_record(cost="1.50"),
        )

    assert reservation in tracker.reservations
    assert tracker.records == []


def test_monthly_actual_cost_exceeds_budget():
    tracker = make_tracker(
        daily="10",
        monthly="1",
    )

    reservation = tracker.reserve("0.50", now=NOW)

    with pytest.raises(
        BudgetExceeded,
        match="monthly",
    ):
        tracker.finalize(
            reservation,
            make_record(cost="1.50"),
        )


def test_daily_reset():
    tracker = make_tracker(
        daily="1",
        monthly="10",
    )

    commit_usage(tracker, "1", timestamp=NOW)

    tomorrow = NOW + timedelta(days=1)

    reservation = tracker.reserve(
        "1",
        now=tomorrow,
    )

    assert reservation == 2


def test_monthly_reset():
    tracker = make_tracker(
        daily="1",
        monthly="1",
    )

    commit_usage(tracker, "1", timestamp=NOW)

    next_month = datetime(
        2026, 11, 1, 12, 0, tzinfo=timezone.utc
    )

    reservation = tracker.reserve(
        "1",
        now=next_month,
    )

    assert reservation == 2


def test_utc_day_boundary():
    tracker = make_tracker(
        daily="1",
        monthly="10",
    )

    late = datetime(
        2026, 10, 29, 23, 59,
        tzinfo=timezone.utc,
    )
    early = datetime(
        2026, 10, 30, 0, 1,
        tzinfo=timezone.utc,
    )

    commit_usage(tracker, "1", timestamp=late)

    assert tracker.reserve("1", now=early) == 2


def test_naive_reservation_time_rejected():
    tracker = make_tracker()

    with pytest.raises(
        ValueError,
        match="Timezone-aware",
    ):
        tracker.reserve(
            "1",
            now=datetime(2026, 10, 29),
        )


def test_naive_record_time_rejected():
    with pytest.raises(
        ValueError,
        match="Timezone-aware",
    ):
        make_record(
            timestamp=datetime(2026, 10, 29)
        )


def test_record_before_reservation_rejected():
    tracker = make_tracker()

    reservation = tracker.reserve("1", now=NOW)

    earlier = NOW - timedelta(seconds=1)

    with pytest.raises(
        ValueError,
        match="precedes reservation",
    ):
        tracker.finalize(
            reservation,
            make_record(
                cost="1",
                timestamp=earlier,
            ),
        )


def test_summary():
    tracker = make_tracker()

    commit_usage(
        tracker, "0.50", agent="gpt"
    )
    commit_usage(
        tracker, "0.75", agent="claude"
    )

    tracker.reserve("1.00", now=NOW)

    summary = tracker.summary(NOW)

    assert summary["daily_committed_usd"] == Decimal("2.25")
    assert summary["monthly_committed_usd"] == Decimal("2.25")
    assert summary["by_agent_usd"]["gpt"] == Decimal("0.50")
    assert summary["by_agent_usd"]["claude"] == Decimal("0.75")
    assert summary["record_count"] == 2
    assert summary["active_reservations"] == 1


def test_all_agents_have_summary_entry():
    tracker = make_tracker()

    summary = tracker.summary(NOW)

    assert set(summary["by_agent_usd"]) == set(AGENTS)


def test_concurrent_reservations_respect_budget():
    tracker = make_tracker(
        daily="1",
        monthly="10",
    )

    def attempt(_):
        try:
            tracker.reserve("0.20", now=NOW)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, range(20)))

    assert sum(results) == 5
    assert len(tracker.reservations) == 5
    assert tracker.summary(NOW)[
        "daily_committed_usd"
    ] == Decimal("1.00")


def test_invalid_record_agent():
    with pytest.raises(
        ValueError,
        match="Unknown AI agent",
    ):
        make_record(agent="local_ai")


def test_empty_record_model():
    with pytest.raises(
        ValueError,
        match="Model is required",
    ):
        UsageRecord(
            agent="gpt",
            model="   ",
            input_tokens=100,
            output_tokens=50,
            cost_usd="0.50",
            timestamp=NOW,
        )


@pytest.mark.parametrize(
    "tokens",
    [-1, 1.5, True],
)
def test_invalid_record_tokens(tokens):
    with pytest.raises(ValueError):
        make_record(input_tokens=tokens)


def test_finalize_same_reservation_twice():
    tracker = make_tracker()

    reservation = tracker.reserve("0.50", now=NOW)
    record = make_record(cost="0.50")

    tracker.finalize(reservation, record)

    with pytest.raises(
        ValueError,
        match="Unknown reservation",
    ):
        tracker.finalize(reservation, record)
