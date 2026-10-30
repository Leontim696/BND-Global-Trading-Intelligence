"""Fail-closed preflight budget for a three-call GPT/Claude review.

This is an estimate guard, not a provider-side hard spending cap.
Live calls must additionally have a provider-enforced $0.50 key limit.
"""
from dataclasses import dataclass
from decimal import Decimal

MAX_TEST_USD = Decimal("0.50")


@dataclass(frozen=True)
class CallAllowance:
    agent: str
    max_input_tokens: int
    max_output_tokens: int
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal

    def maximum_cost(self) -> Decimal:
        if self.agent not in ("gpt", "claude"):
            raise ValueError("Unsupported agent")
        if (not isinstance(self.max_input_tokens, int)
                or isinstance(self.max_input_tokens, bool)
                or self.max_input_tokens <= 0
                or not isinstance(self.max_output_tokens, int)
                or isinstance(self.max_output_tokens, bool)
                or self.max_output_tokens <= 0):
            raise ValueError("Token limits must be positive integers")
        prices = (self.input_usd_per_million, self.output_usd_per_million)
        if any(not isinstance(p, Decimal) or not p.is_finite() or p < 0 for p in prices):
            raise ValueError("Prices must be nonnegative finite Decimal values")
        return (
            self.input_usd_per_million * self.max_input_tokens
            + self.output_usd_per_million * self.max_output_tokens
        ) / Decimal(1_000_000)


def approve_preflight(allowances: tuple[CallAllowance, ...],
                      limit: Decimal = MAX_TEST_USD) -> Decimal:
    """Reject missing/extra calls and estimates exceeding approved budget."""
    if not isinstance(limit, Decimal) or not limit.is_finite() or not 0 < limit <= MAX_TEST_USD:
        raise ValueError("Limit must be positive and at most $0.50")
    if len(allowances) != 3 or tuple(a.agent for a in allowances) != (
        "gpt", "claude", "gpt"
    ):
        raise ValueError("Expected exactly GPT, Claude, GPT")
    estimate = sum((a.maximum_cost() for a in allowances), Decimal("0"))
    if estimate > limit:
        raise ValueError("Worst-case estimated cost exceeds approved budget")
    return estimate
