import pytest

from src.bnd.ai_gateway import AIRequest, AIResponse
from src.bnd.code_review_loop import run_code_review
from src.bnd.fusion_council import Vote


class RecordingProvider:
    def __init__(self, agent):
        self.agent = agent
        self.requests = []

    def analyze(self, request: AIRequest) -> AIResponse:
        self.requests.append(request.context)
        return AIResponse(agent=self.agent, vote=Vote.HOLD,
                          reasoning=f"{self.agent} response {len(self.requests)}",
                          confidence=0.5, model="mock")


def test_three_step_exchange_preserves_critique():
    gpt, claude = RecordingProvider("gpt"), RecordingProvider("claude")
    result = run_code_review("Add tests", {"gpt": gpt, "claude": claude})
    assert result.gpt_initial.agent == "gpt"
    assert result.claude_review.agent == "claude"
    assert result.gpt_revision.agent == "gpt"
    assert "gpt response 1" in claude.requests[0]
    assert "claude response 1" in gpt.requests[1]
    assert len(gpt.requests) == 2
    assert len(claude.requests) == 1


def test_rejects_missing_provider():
    with pytest.raises(ValueError, match="Exactly"):
        run_code_review("Task", {"gpt": RecordingProvider("gpt")})


def test_rejects_blank_task():
    with pytest.raises(ValueError):
        run_code_review(" ", {"gpt": RecordingProvider("gpt"),
                              "claude": RecordingProvider("claude")})
