"""Regression tests: a successful HTTP response must include a usable proposal."""
import pytest

from scripts.overnight_five_agent_council import validated_proposal


def test_valid_proposal_is_trimmed():
    payload = {"choices": [{"message": {"content": "  Check stop-loss tests.  "}}]}
    assert validated_proposal(payload) == "Check stop-loss tests."


@pytest.mark.parametrize("payload", [
    None,
    {},
    {"choices": []},
    {"choices": [{}]},
    {"choices": [{"message": {}}]},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": ""}}]},
    {"choices": [{"message": {"content": "   "}}]},
    {"choices": [{"message": {"content": []}}]},
])
def test_missing_or_empty_proposal_is_rejected(payload):
    with pytest.raises(ValueError):
        validated_proposal(payload)
