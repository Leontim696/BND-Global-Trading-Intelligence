"""Regression tests: HTTP 200 is not enough without complete JSON proposals."""
import pytest

from scripts.overnight_five_agent_council import validated_proposal


def test_valid_proposal_is_trimmed():
    payload = {"choices": [{"message": {"content": '  {"finding":"ok"}  '}}]}
    assert validated_proposal(payload) == '{"finding":"ok"}'


def test_markdown_fenced_json_is_accepted():
    payload = {"choices": [{"message": {"content": '```json\n{"finding":"ok"}\n```'}}]}
    assert validated_proposal(payload).startswith("```json")


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
    {"choices": [{"message": {"content": "Check stop-loss tests."}}]},
    {"choices": [{"message": {"content": '{"finding": "incomplete'}}]},
    {"choices": [{"message": {"content": '[1, 2]'}}]},
    {"choices": [{"message": {"content": '```json\n{"finding":"ok"}'}}]},
    {"choices": [{"finish_reason": "length", "message": {"content": '{"finding":"ok"}'}}]},
])
def test_invalid_or_incomplete_proposal_is_rejected(payload):
    with pytest.raises(ValueError):
        validated_proposal(payload)
