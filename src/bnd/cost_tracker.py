
"""BND Token & Cost Tracker.

Tracks AI usage, estimates costs and reserves budget
before requests. Uses Decimal for financial calculations.

This initial implementation is in-memory only.
It does not yet connect to OpenRouter.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from threading import RLock

from .fusion_council import AGENTS


class BudgetExceeded(Exception):
    """Raised when a request would exceed its budget."""


def money(value) -> Decimal:
    """Convert a finite, nonnegative value to Decimal."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid monetary amount") from exc

    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid monetary amount")

    return amount


@dataclass(frozen=True)
class ModelPricing:
    """USD price per one million input/output tokens."""

    input_per_million: Decimal
    output_per_million: Decimal

    def __post_init__(self):
        object.__setattr__(
            self,
            "input_per_million",
            money(self.input_per_million),
        )
        object.__setattr__(
            self,
            "output_per_million",
            money(self.output_per_million),
        )


@dataclass(frozen=True)
class UsageRecord:
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    timestamp: datetime

    def __post_init__(self):
        if self.agent not in AGENTS:
            raise ValueError("Unknown AI agent")

        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Model is required")

        for tokens in (self.input_tokens, self.output_tokens):
            if (
                not isinstance(tokens, int)
                or isinstance(tokens, bool)
                or tokens < 0
            ):
                raise ValueError("Invalid token usage")

        object.__setattr__(
            self, "cost_usd", money(self.cost_usd)
        )

        if (
            not isinstance(self.timestamp, datetime)
            or self.timestamp.tzinfo is None
            or self.timestamp.utcoffset() is None
        ):
            raise ValueError("Timezone-aware timestamp required")


@dataclass(frozen=True)
class BudgetLimits:
    daily_usd: Decimal
    monthly_usd: Decimal

    def __post_init__(self):
        object.__setattr__(
            self, "daily_usd", money(self.daily_usd)
        )
        object.__setattr__(
            self, "monthly_usd", money(self.monthly_usd)
        )


@dataclass
class CostTracker:
    limits: BudgetLimits
    records: list[UsageRecord] = field(default_factory=list)
    reservations: dict[int, tuple[datetime, Decimal]] = (
        field(default_factory=dict)
    )
    next_reservation_id: int = 1
    _lock: RLock = field(
        default_factory=RLock,
        repr=False,
        compare=False,
    )

    @staticmethod
    def estimate_cost(
        input_tokens: int,
        output_tokens: int,
        pricing: ModelPricing,
    ) -> Decimal:
        for tokens in (input_tokens, output_tokens):
            if (
                not isinstance(tokens, int)
                or isinstance(tokens, bool)
                or tokens < 0
            ):
                raise ValueError("Invalid token usage")

        million = Decimal("1000000")

        return (
            Decimal(input_tokens)
            * pricing.input_per_million
            / million
            + Decimal(output_tokens)
            * pricing.output_per_million
            / million
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _totals(
        self, now: datetime
    ) -> tuple[Decimal, Decimal]:
        daily = Decimal("0")
        monthly = Decimal("0")

        for record in self.records:
            timestamp = record.timestamp.astimezone(timezone.utc)

            if timestamp.date() == now.date():
                daily += record.cost_usd

            if (
                timestamp.year == now.year
                and timestamp.month == now.month
            ):
                monthly += record.cost_usd

        for timestamp, amount in self.reservations.values():
            timestamp = timestamp.astimezone(timezone.utc)

            if timestamp.date() == now.date():
                daily += amount

            if (
                timestamp.year == now.year
                and timestamp.month == now.month
            ):
                monthly += amount

        return daily, monthly

    def reserve(
        self,
        estimated_cost_usd,
        now: datetime | None = None,
    ) -> int:
        """Reserve budget before an API request."""

        amount = money(estimated_cost_usd)
        now = now or self._now()

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Timezone-aware timestamp required")

        now = now.astimezone(timezone.utc)

        with self._lock:
            daily, monthly = self._totals(now)

            if daily + amount > self.limits.daily_usd:
                raise BudgetExceeded("Daily AI budget exceeded")

            if monthly + amount > self.limits.monthly_usd:
                raise BudgetExceeded("Monthly AI budget exceeded")

            reservation_id = self.next_reservation_id
            self.next_reservation_id += 1

            self.reservations[reservation_id] = (now, amount)

            return reservation_id

    def finalize(
        self,
        reservation_id: int,
        record: UsageRecord,
    ) -> None:
        """Replace a reservation with recorded usage."""

        with self._lock:
            if reservation_id not in self.reservations:
                raise ValueError("Unknown reservation")

            reserved_at, reserved_amount = (
                self.reservations[reservation_id]
            )

            if record.timestamp.astimezone(timezone.utc) < reserved_at:
                raise ValueError(
                    "Usage timestamp precedes reservation"
                )

            daily, monthly = self._totals(
                record.timestamp.astimezone(timezone.utc)
            )

            # Remove this reservation from totals only if
            # it belongs to the same accounting period.
            reserved_day = reserved_at.date()
            record_day = record.timestamp.astimezone(
                timezone.utc
            ).date()

            if reserved_day == record_day:
                daily -= reserved_amount

            if (
                reserved_at.year
                == record.timestamp.astimezone(timezone.utc).year
                and reserved_at.month
                == record.timestamp.astimezone(timezone.utc).month
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

            del self.reservations[reservation_id]
            self.records.append(record)

    def release(self, reservation_id: int) -> None:
        """Release unused budget after a failed request."""

        with self._lock:
            if reservation_id not in self.reservations:
                raise ValueError("Unknown reservation")

            del self.reservations[reservation_id]

    def summary(
        self, now: datetime | None = None
    ) -> dict:
        """Return current UTC spending and reserved amounts."""

        now = now or self._now()

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Timezone-aware timestamp required")

        now = now.astimezone(timezone.utc)

        with self._lock:
            daily, monthly = self._totals(now)

            by_agent = {
                agent: Decimal("0")
                for agent in AGENTS
            }

            for record in self.records:
                by_agent[record.agent] += record.cost_usd

            return {
                "daily_committed_usd": daily,
                "monthly_committed_usd": monthly,
                "daily_limit_usd": self.limits.daily_usd,
                "monthly_limit_usd": self.limits.monthly_usd,
                "by_agent_usd": by_agent,
                "record_count": len(self.records),
                "active_reservations": len(
                    self.reservations
                ),
            }
