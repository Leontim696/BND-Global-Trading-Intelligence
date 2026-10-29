
"""BND Fusion Council — auditable multi-agent voting core."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


AGENTS = (
    "gpt",
    "claude",
    "gemini",
    "grok",
    "deepseek",
    "local_ai",
)


class Vote(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class Opinion:
    agent: str
    vote: Vote
    reasoning: str
    confidence: float

    def __post_init__(self):
        if self.agent not in AGENTS:
            raise ValueError("Unknown agent")
        if not isinstance(self.vote, Vote):
            raise ValueError("Invalid vote")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0 and 1")
        if not self.reasoning.strip():
            raise ValueError("Reasoning is required")


@dataclass
class FusionCouncil:
    initial_opinions: dict[str, Opinion] = field(default_factory=dict)
    revisions: list[Opinion] = field(default_factory=list)

    def submit(self, opinion: Opinion) -> None:
        if opinion.agent in self.initial_opinions:
            raise ValueError("Initial opinion already submitted")
        self.initial_opinions[opinion.agent] = opinion

    def revise(self, opinion: Opinion) -> None:
        if opinion.agent not in self.initial_opinions:
            raise ValueError("Agent must vote before revising")
        if len(self.initial_opinions) != len(AGENTS):
            raise ValueError("All agents must vote before debate")
        self.revisions.append(opinion)

    def current_opinions(self) -> dict[str, Opinion]:
        current = dict(self.initial_opinions)
        for opinion in self.revisions:
            current[opinion.agent] = opinion
        return current

    def dissent(self) -> list[Opinion]:
        result = self.decision()
        if result is None:
            return []
        return [
            opinion
            for opinion in self.current_opinions().values()
            if opinion.vote != result
        ]

    def decision(self) -> Optional[Vote]:
        if len(self.initial_opinions) != len(AGENTS):
            return None

        counts = {vote: 0 for vote in Vote}
        for opinion in self.current_opinions().values():
            counts[opinion.vote] += 1

        winner = max(counts, key=counts.get)
        if counts[winner] <= len(AGENTS) // 2:
            return None

        return winner

    def audit_log(self) -> dict:
        return {
            "initial_votes": [
                {
                    "agent": opinion.agent,
                    "vote": opinion.vote.value,
                    "reasoning": opinion.reasoning,
                    "confidence": opinion.confidence,
                }
                for opinion in self.initial_opinions.values()
            ],
            "revisions": [
                {
                    "agent": opinion.agent,
                    "vote": opinion.vote.value,
                    "reasoning": opinion.reasoning,
                    "confidence": opinion.confidence,
                }
                for opinion in self.revisions
            ],
            "decision": (
                self.decision().value if self.decision() else None
            ),
        }
