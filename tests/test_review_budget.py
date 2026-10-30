from decimal import Decimal
import pytest

from src.bnd.review_budget import CallAllowance, approve_preflight


def allowance(agent, price="1"):
    return CallAllowance(agent, 1000, 1000, Decimal(price), Decimal(price))


def test_small_preflight_is_accepted():
    assert approve_preflight((allowance("gpt"), allowance("claude"),
                              allowance("gpt"))) == Decimal("0.006")


def test_expensive_preflight_rejected():
    with pytest.raises(ValueError, match="exceeds"):
        approve_preflight((allowance("gpt", "200"), allowance("claude", "200"),
                           allowance("gpt", "200")))


def test_missing_call_rejected():
    with pytest.raises(ValueError, match="exactly"):
        approve_preflight((allowance("gpt"), allowance("claude")))


def test_invalid_price_rejected():
    with pytest.raises(ValueError, match="Prices"):
        approve_preflight((allowance("gpt", "NaN"), allowance("claude"),
                           allowance("gpt")))


def test_cannot_raise_approved_cap():
    with pytest.raises(ValueError, match="at most"):
        approve_preflight((allowance("gpt"), allowance("claude"),
                           allowance("gpt")), Decimal("1"))
