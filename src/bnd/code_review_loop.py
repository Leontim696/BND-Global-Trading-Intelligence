"""GPT/Claude sequential coding review with explicit opt-in and no trade execution.

The caller supplies providers. This module makes no network requests itself.
"""
from dataclasses import dataclass

from .ai_gateway import AIRequest, AIProvider, AIResponse


@dataclass(frozen=True)
class ReviewRound:
    gpt_initial: AIResponse
    claude_review: AIResponse
    gpt_revision: AIResponse


def run_code_review(task: str, providers: dict[str, AIProvider]) -> ReviewRound:
    """GPT proposes, Claude critiques, GPT revises, preserving all three."""
    if not isinstance(task, str) or not task.strip():
        raise ValueError("A nonempty coding task is required")
    if set(providers) != {"gpt", "claude"}:
        raise ValueError("Exactly GPT and Claude providers are required")

    def ask(agent: str, context: str) -> AIResponse:
        response = providers[agent].analyze(
            AIRequest(agent=agent, market="SOFTWARE", symbol="CODE-REVIEW",
                      context=context)
        )
        if response.agent != agent:
            raise ValueError("Provider agent mismatch")
        return response

    first = ask("gpt", "Propose a safe implementation for: " + task)
    second = ask(
        "claude",
        "Critique the following GPT proposal, including security, tests, "
        "and correctness. Original task: " + task +
        "\nGPT proposal: " + first.reasoning,
    )
    third = ask(
        "gpt",
        "Revise your proposal in response to Claude's critique. "
        "Original task: " + task +
        "\nOriginal proposal: " + first.reasoning +
        "\nClaude critique: " + second.reasoning,
    )
    return ReviewRound(first, second, third)
