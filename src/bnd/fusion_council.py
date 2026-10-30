
"""BND Fusion Council — independent AI voting and audit history."""

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite


# Active AI agents.
# Local AI can be added later.
AGENTS = (
    "gpt",
    "claude",
    "gemini",
    "grok",
    "deepseek",
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
            raise ValueError("Unknown AI agent")

        if not isinstance(self.vote, Vote):
            raise ValueError("Invalid vote")

        if not isinstance(self.reasoning, str) or not self.reasoning.strip():
            raise ValueError("Reasoning is required")

        if (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not isfinite(self.confidence)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("Confidence must be between 0 and 1")


@dataclass
class FusionCouncil:
    initial_opinions: dict[str, Opinion] = field(default_factory=dict)
    revisions: list[Opinion] = field(default_factory=list)

    def submit(self, opinion: Opinion) -> None:
        """Register one independent initial opinion per agent."""

        if opinion.agent in self.initial_opinions:
            raise ValueError("Agent already submitted an initial opinion")

        self.initial_opinions[opinion.agent] = opinion

    def revise(self, opinion: Opinion) -> None:
        """Preserve initial votes while recording later revisions."""

        if len(self.initial_opinions) != len(AGENTS):
            raise ValueError("All agents must vote before revisions")

        if opinion.agent not in self.initial_opinions:
            raise ValueError("Agent has no initial opinion")

        self.revisions.append(opinion)

    def current_opinions(self) -> dict[str, Opinion]:
        """Return each agent's most recent opinion."""

        current = dict(self.initial_opinions)

        for opinion in self.revisions:
            current[opinion.agent] = opinion

        return current

    def decision(self) -> Vote | None:
        """Return a strict majority decision, otherwise None."""

        current = self.current_opinions()

        if len(current) != len(AGENTS):
            return None

        threshold = len(AGENTS) // 2 + 1

        for vote in Vote:
            count = sum(
                opinion.vote == vote
                for opinion in current.values()
            )

            if count >= threshold:
                return vote

        return None

    def dissent(self) -> list[Opinion]:
        """Return opinions that disagree with the majority."""

        majority = self.decision()

        if majority is None:
            return list(self.current_opinions().values())

        return [
            opinion
            for opinion in self.current_opinions().values()
            if opinion.vote != majority
        ]

    def audit_log(self) -> dict:
        """Return initial votes, revisions and current decision."""

        decision = self.decision()

        return {
            "agents": list(AGENTS),
            "majority_threshold": len(AGENTS) // 2 + 1,
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
            "current_decision": (
                decision.value if decision is not None else None
            ),
        }
