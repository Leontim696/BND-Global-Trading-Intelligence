
"""Tests for persistent BND AI cost storage.

Uses temporary SQLite databases. No API calls or real money.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.bnd.cost_storage import SQLiteCostStorage
from src.bnd.cost_tracker import (
    BudgetExceeded,
    BudgetLimits,
    UsageRecord,
)
from src.bnd.fusion_council import AGENTS


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def make_storage(tmp_path, daily="5", monthly="50"):
    return SQLiteCostStorage(
        tmp_path / "bnd_costs.sqlite3",
        BudgetLimits(daily, monthly),
    )


def make_record(
    cost="0.50",
    agent="gpt",
    timestamp=NOW,
):
    return UsageRecord(
        agent=agent,
        model="test/model",
        input_tokens=100,
        output_tokens=50,
        cost_usd=cost,
        timestamp=timestamp,
    )


def commit_usage(
    storage,
    cost="0.50",
    agent="gpt",
    timestamp=NOW,
):
    reservation = storage.reserve(cost, now=timestamp)
    storage.finalize(
        reservation,
        make_record(
            cost=cost,
            agent=agent,
            timestamp=timestamp,
        ),
    )


def test_database_created(tmp_path):
    storage = make_storage(tmp_path)

    assert (tmp_path / "bnd_costs.sqlite3").exists()
    assert storage.summary(NOW)["record_count"] == 0


def test_initial_summary(tmp_path):
    storage = make_storage(tmp_path)

    summary = storage.summary(NOW)

    assert summary["daily_committed_usd"] == Decimal("0")
    assert summary["monthly_committed_usd"] == Decimal("0")
    assert summary["record_count"] == 0
    assert summary["active_reservations"] == 0


def test_reservation_persists_after_restart(tmp_path):
    storage = make_storage(tmp_path, daily="1")
    reservation = storage.reserve("0.75", now=NOW)

    reopened = make_storage(tmp_path, daily="1")

    assert reopened.summary(NOW)[
        "active_reservations"
    ] == 1

    with pytest.raises(BudgetExceeded):
        reopened.reserve("0.30", now=NOW)

    reopened.release(reservation)


def test_usage_persists_after_restart(tmp_path):
    storage = make_storage(tmp_path)
    commit_usage(storage, "0.75")

    reopened = make_storage(tmp_path)
    summary = reopened.summary(NOW)

    assert summary["record_count"] == 1
    assert summary["daily_committed_usd"] == Decimal("0.75")
    assert summary["by_agent_usd"]["gpt"] == Decimal("0.75")


def test_reservation_ids_unique(tmp_path):
    storage = make_storage(tmp_path)

    first = storage.reserve("0.10", now=NOW)
    second = storage.reserve("0.10", now=NOW)

    assert first != second


def test_daily_limit(tmp_path):
    storage = make_storage(
        tmp_path, daily="1", monthly="10"
    )

    storage.reserve("0.80", now=NOW)

    with pytest.raises(BudgetExceeded, match="Daily"):
        storage.reserve("0.21", now=NOW)


def test_monthly_limit(tmp_path):
    storage = make_storage(
        tmp_path, daily="10", monthly="1"
    )

    storage.reserve("0.80", now=NOW)

    with pytest.raises(BudgetExceeded, match="Monthly"):
        storage.reserve("0.21", now=NOW)


def test_exact_limit_allowed(tmp_path):
    storage = make_storage(
        tmp_path, daily="1", monthly="1"
    )

    storage.reserve("1", now=NOW)

    assert storage.summary(NOW)[
        "daily_committed_usd"
    ] == Decimal("1")


def test_failed_reservation_does_not_insert(tmp_path):
    storage = make_storage(tmp_path, daily="1")

    storage.reserve("0.90", now=NOW)

    with pytest.raises(BudgetExceeded):
        storage.reserve("0.20", now=NOW)

    assert storage.summary(NOW)[
        "active_reservations"
    ] == 1


def test_release_reservation(tmp_path):
    storage = make_storage(tmp_path, daily="1")

    reservation = storage.reserve("1", now=NOW)
    storage.release(reservation)

    assert storage.summary(NOW)[
        "active_reservations"
    ] == 0

    storage.reserve("1", now=NOW)


def test_release_unknown_reservation(tmp_path):
    storage = make_storage(tmp_path)

    with pytest.raises(
        ValueError, match="Unknown reservation"
    ):
        storage.release(999)


def test_finalize_usage(tmp_path):
    storage = make_storage(tmp_path)

    reservation = storage.reserve("0.50", now=NOW)
    storage.finalize(
        reservation,
        make_record(cost="0.50"),
    )

    summary = storage.summary(NOW)

    assert summary["record_count"] == 1
    assert summary["active_reservations"] == 0
    assert summary["daily_committed_usd"] == Decimal("0.50")


def test_finalize_unknown_reservation(tmp_path):
    storage = make_storage(tmp_path)

    with pytest.raises(
        ValueError, match="Unknown reservation"
    ):
        storage.finalize(999, make_record())


def test_finalize_twice_rejected(tmp_path):
    storage = make_storage(tmp_path)

    reservation = storage.reserve("0.50", now=NOW)
    record = make_record()

    storage.finalize(reservation, record)

    with pytest.raises(
        ValueError, match="Unknown reservation"
    ):
        storage.finalize(reservation, record)


def test_actual_cost_lower_than_reserved(tmp_path):
    storage = make_storage(tmp_path, daily="1")

    reservation = storage.reserve("0.80", now=NOW)
    storage.finalize(
        reservation,
        make_record(cost="0.50"),
    )

    assert storage.summary(NOW)[
        "daily_committed_usd"
    ] == Decimal("0.50")


def test_actual_cost_higher_within_budget(tmp_path):
    storage = make_storage(tmp_path, daily="2")

    reservation = storage.reserve("0.50", now=NOW)
    storage.finalize(
        reservation,
        make_record(cost="1.50"),
    )

    assert storage.summary(NOW)[
        "daily_committed_usd"
    ] == Decimal("1.50")


def test_actual_cost_exceeds_daily_limit(tmp_path):
    storage = make_storage(tmp_path, daily="1")

    reservation = storage.reserve("0.50", now=NOW)

    with pytest.raises(BudgetExceeded, match="daily"):
        storage.finalize(
            reservation,
            make_record(cost="1.50"),
        )

    summary = storage.summary(NOW)

    assert summary["record_count"] == 0
    assert summary["active_reservations"] == 1


def test_actual_cost_exceeds_monthly_limit(tmp_path):
    storage = make_storage(
        tmp_path, daily="10", monthly="1"
    )

    reservation = storage.reserve("0.50", now=NOW)

    with pytest.raises(BudgetExceeded, match="monthly"):
        storage.finalize(
            reservation,
            make_record(cost="1.50"),
        )

    assert storage.summary(NOW)["record_count"] == 0


def test_daily_reset(tmp_path):
    storage = make_storage(
        tmp_path, daily="1", monthly="10"
    )

    commit_usage(storage, "1", timestamp=NOW)

    tomorrow = NOW + timedelta(days=1)

    storage.reserve("1", now=tomorrow)

    assert storage.summary(tomorrow)[
        "daily_committed_usd"
    ] == Decimal("1")


def test_monthly_reset(tmp_path):
    storage = make_storage(
        tmp_path, daily="1", monthly="1"
    )

    commit_usage(storage, "1", timestamp=NOW)

    next_month = datetime(
        2026, 11, 1, 12, 0,
        tzinfo=timezone.utc,
    )

    storage.reserve("1", now=next_month)

    assert storage.summary(next_month)[
        "monthly_committed_usd"
    ] == Decimal("1")


def test_utc_day_boundary(tmp_path):
    storage = make_storage(
        tmp_path, daily="1", monthly="10"
    )

    late = datetime(
        2026, 10, 29, 23, 59,
        tzinfo=timezone.utc,
    )
    early = datetime(
        2026, 10, 30, 0, 1,
        tzinfo=timezone.utc,
    )

    commit_usage(storage, "1", timestamp=late)
    storage.reserve("1", now=early)

    assert storage.summary(early)[
        "daily_committed_usd"
    ] == Decimal("1")


def test_naive_reservation_time_rejected(tmp_path):
    storage = make_storage(tmp_path)

    with pytest.raises(
        ValueError, match="Timezone-aware"
    ):
        storage.reserve(
            "1",
            now=datetime(2026, 10, 29),
        )


def test_finalize_before_reservation_rejected(tmp_path):
    storage = make_storage(tmp_path)

    reservation = storage.reserve("1", now=NOW)

    earlier = NOW - timedelta(seconds=1)

    with pytest.raises(
        ValueError, match="precedes reservation"
    ):
        storage.finalize(
            reservation,
            make_record(
                cost="1",
                timestamp=earlier,
            ),
        )


def test_all_agents_in_summary(tmp_path):
    storage = make_storage(tmp_path)

    assert set(storage.summary(NOW)["by_agent_usd"]) == set(
        AGENTS
    )


def test_spending_by_agent(tmp_path):
    storage = make_storage(tmp_path)

    commit_usage(storage, "0.50", agent="gpt")
    commit_usage(storage, "0.75", agent="claude")

    summary = storage.summary(NOW)

    assert summary["by_agent_usd"]["gpt"] == Decimal("0.50")
    assert summary["by_agent_usd"]["claude"] == Decimal("0.75")
    assert summary["record_count"] == 2


def test_multiple_instances_share_budget(tmp_path):
    first = make_storage(tmp_path, daily="1")
    second = make_storage(tmp_path, daily="1")

    first.reserve("0.75", now=NOW)

    with pytest.raises(BudgetExceeded):
        second.reserve("0.30", now=NOW)


def test_concurrent_reservations(tmp_path):
    database = tmp_path / "bnd_costs.sqlite3"
    limits = BudgetLimits("1", "10")

    def attempt(_):
        storage = SQLiteCostStorage(database, limits)

        try:
            storage.reserve("0.20", now=NOW)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, range(20)))

    assert sum(results) == 5

    storage = SQLiteCostStorage(database, limits)

    assert storage.summary(NOW)[
        "active_reservations"
    ] == 5
    assert storage.summary(NOW)[
        "daily_committed_usd"
    ] == Decimal("1.00")


def test_failed_finalize_preserves_reservation(tmp_path):
    storage = make_storage(tmp_path, daily="1")

    reservation = storage.reserve("0.50", now=NOW)

    with pytest.raises(BudgetExceeded):
        storage.finalize(
            reservation,
            make_record(cost="2"),
        )

    reopened = make_storage(tmp_path, daily="1")

    assert reopened.summary(NOW)[
        "active_reservations"
    ] == 1
    assert reopened.summary(NOW)["record_count"] == 0


def test_finalize_after_restart(tmp_path):
    storage = make_storage(tmp_path)

    reservation = storage.reserve("0.50", now=NOW)

    reopened = make_storage(tmp_path)
    reopened.finalize(
        reservation,
        make_record(cost="0.50"),
    )

    assert reopened.summary(NOW)["record_count"] == 1


def test_release_after_restart(tmp_path):
    storage = make_storage(tmp_path)

    reservation = storage.reserve("0.50", now=NOW)

    reopened = make_storage(tmp_path)
    reopened.release(reservation)

    assert reopened.summary(NOW)[
        "active_reservations"
    ] == 0
