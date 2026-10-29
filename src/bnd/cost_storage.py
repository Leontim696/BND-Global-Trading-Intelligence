
"""Persistent SQLite storage for BND AI cost accounting.

Stores usage records and budget reservations across restarts.
All timestamps are stored in UTC.

This module does not make API calls or place trading orders.
"""

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import RLock

from .cost_tracker import (
    BudgetExceeded,
    BudgetLimits,
    UsageRecord,
    money,
)
from .fusion_council import AGENTS


def utc_time(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("Timezone-aware timestamp required")

    return value.astimezone(timezone.utc)


class SQLiteCostStorage:
    """Persistent accounting with atomic budget reservations."""

    def __init__(self, database_path, limits: BudgetLimits):
        self.database_path = str(Path(database_path))
        self.limits = limits
        self._lock = RLock()
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
        )
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cost_usd TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount_usd TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_usage_timestamp
                ON usage_records(timestamp)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_reservation_timestamp
                ON reservations(timestamp)
                """
            )

    @staticmethod
    def _totals(connection, now):
        day = now.date()
        month = (now.year, now.month)

        daily = Decimal("0")
        monthly = Decimal("0")

        for table, column in (
            ("usage_records", "cost_usd"),
            ("reservations", "amount_usd"),
        ):
            rows = connection.execute(
                f"SELECT {column}, timestamp FROM {table}"
            ).fetchall()

            for amount_text, timestamp_text in rows:
                timestamp = utc_time(
                    datetime.fromisoformat(timestamp_text)
                )
                amount = money(amount_text)

                if timestamp.date() == day:
                    daily += amount

                if (
                    timestamp.year,
                    timestamp.month,
                ) == month:
                    monthly += amount

        return daily, monthly

    def reserve(self, estimated_cost_usd, now=None):
        """Atomically reserve budget across processes."""

        amount = money(estimated_cost_usd)
        now = utc_time(
            now or datetime.now(timezone.utc)
        )

        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            daily, monthly = self._totals(
                connection, now
            )

            if daily + amount > self.limits.daily_usd:
                raise BudgetExceeded(
                    "Daily AI budget exceeded"
                )

            if monthly + amount > self.limits.monthly_usd:
                raise BudgetExceeded(
                    "Monthly AI budget exceeded"
                )

            cursor = connection.execute(
                """
                INSERT INTO reservations
                    (amount_usd, timestamp)
                VALUES (?, ?)
                """,
                (str(amount), now.isoformat()),
            )

            return cursor.lastrowid

    def finalize(self, reservation_id, record: UsageRecord):
        """Replace a reservation with actual usage."""

        timestamp = utc_time(record.timestamp)

        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            row = connection.execute(
                """
                SELECT amount_usd, timestamp
                FROM reservations
                WHERE id = ?
                """,
                (reservation_id,),
            ).fetchone()

            if row is None:
                raise ValueError("Unknown reservation")

            reserved_amount = money(row[0])
            reserved_at = utc_time(
                datetime.fromisoformat(row[1])
            )

            if timestamp < reserved_at:
                raise ValueError(
                    "Usage timestamp precedes reservation"
                )

            daily, monthly = self._totals(
                connection, timestamp
            )

            if reserved_at.date() == timestamp.date():
                daily -= reserved_amount

            if (
                reserved_at.year,
                reserved_at.month,
            ) == (
                timestamp.year,
                timestamp.month,
            ):
                monthly -= reserved_amount

            if daily + record.cost_usd > self.limits.daily_usd:
                raise BudgetExceeded(
                    "Actual usage exceeds daily budget"
                )

            if monthly + record.cost_usd > self.limits.monthly_usd:
                raise BudgetExceeded(
                    "Actual usage exceeds monthly budget"
                )

            connection.execute(
                """
                INSERT INTO usage_records (
                    agent, model, input_tokens,
                    output_tokens, cost_usd, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.agent,
                    record.model,
                    record.input_tokens,
                    record.output_tokens,
                    str(record.cost_usd),
                    timestamp.isoformat(),
                ),
            )

            connection.execute(
                "DELETE FROM reservations WHERE id = ?",
                (reservation_id,),
            )

    def release(self, reservation_id):
        """Release a reservation after a failed request."""

        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            cursor = connection.execute(
                "DELETE FROM reservations WHERE id = ?",
                (reservation_id,),
            )

            if cursor.rowcount == 0:
                raise ValueError("Unknown reservation")

    def summary(self, now=None):
        """Return persisted spending and reservations."""

        now = utc_time(
            now or datetime.now(timezone.utc)
        )

        with self._lock, self._connect() as connection:
            daily, monthly = self._totals(
                connection, now
            )

            by_agent = {
                agent: Decimal("0")
                for agent in AGENTS
            }

            rows = connection.execute(
                """
                SELECT agent, cost_usd
                FROM usage_records
                """
            ).fetchall()

            for agent, cost in rows:
                if agent in by_agent:
                    by_agent[agent] += money(cost)

            record_count = connection.execute(
                "SELECT COUNT(*) FROM usage_records"
            ).fetchone()[0]

            active_reservations = connection.execute(
                "SELECT COUNT(*) FROM reservations"
            ).fetchone()[0]

            return {
                "daily_committed_usd": daily,
                "monthly_committed_usd": monthly,
                "daily_limit_usd": self.limits.daily_usd,
                "monthly_limit_usd": self.limits.monthly_usd,
                "by_agent_usd": by_agent,
                "record_count": record_count,
                "active_reservations": active_reservations,
            }
