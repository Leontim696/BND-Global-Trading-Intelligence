
"""BND Debate Engine — structured debate with participation gates."""

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite

from .fusion_council import (
    AGENTS,
    FusionCouncil,
    Opinion,
    Vote,
)


class DebateStatus(str, Enum):
    WAITING = "WAITING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class DebateArgument:
    agent: str
    claim: str
    evidence: str
    challenges: tuple[str, ...] = ()

    def __post_init__(self):
        if self.agent not in AGENTS:
            raise ValueError("Unknown agent")
        if not self.claim.strip():
            raise ValueError("Argument claim is required")
        if not self.evidence.strip():
            raise ValueError("Supporting evidence is required")
        if any(name not in AGENTS for name in self.challenges):
            raise ValueError("Unknown challenged agent")


@dataclass(frozen=True)
class DebateResponse:
    agent: str
    reasoning: str
    vote: Vote
    confidence: float

    def __post_init__(self):
        if self.agent not in AGENTS:
            raise ValueError("Unknown agent")
        if not isinstance(self.reasoning, str) or not self.reasoning.strip():
            raise ValueError("Response reasoning is required")
        if not isinstance(self.vote, Vote):
            raise ValueError("Invalid vote")
        if (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not isfinite(self.confidence)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("Confidence must be between 0 and 1")


@dataclass
class DebateEngine:
    council: FusionCouncil
    arguments: list[DebateArgument] = field(default_factory=list)
    responses: list[DebateResponse] = field(default_factory=list)
    status: DebateStatus = DebateStatus.WAITING
    round_number: int = 0
    max_rounds: int = 3

    def __post_init__(self):
        if self.max_rounds < 1:
            raise ValueError("At least one debate round is required")

    def start(self) -> None:
        if self.status != DebateStatus.WAITING:
            raise ValueError("Debate already started")
        if len(self.council.initial_opinions) != len(AGENTS):
            raise ValueError("All agents must vote first")
        self.status = DebateStatus.OPEN
        self.round_number = 1

    def submit_argument(self, argument: DebateArgument) -> None:
        if self.status != DebateStatus.OPEN:
            raise ValueError("Debate is not open")
        self.arguments.append(argument)

    def revise_vote(self, opinion: Opinion) -> None:
        if self.status != DebateStatus.OPEN:
            raise ValueError("Debate is not open")
        if not self.arguments:
            raise ValueError("At least one argument is required")
        self.council.revise(opinion)

    def submit_response(self, response: DebateResponse) -> None:
        if self.status != DebateStatus.OPEN:
            raise ValueError("Debate is not open")

        if not self.arguments:
            raise ValueError("Arguments must be submitted first")

        current = self.council.current_opinions()

        if response.agent not in current:
            raise ValueError("Agent has no initial opinion")

        existing = current[response.agent]

        if (
            existing.vote != response.vote
            or existing.confidence != response.confidence
        ):
            self.council.revise(
                Opinion(
                    agent=response.agent,
                    vote=response.vote,
                    reasoning=response.reasoning,
                    confidence=response.confidence,
                )
            )

        self.responses.append(response)

    def next_round(self) -> None:
        if self.status != DebateStatus.OPEN:
            raise ValueError("Debate is not open")
        if self.round_number >= self.max_rounds:
            raise ValueError("Maximum debate rounds reached")
        self.round_number += 1

    def missing_arguments(self) -> list[str]:
        participants = {item.agent for item in self.arguments}
        return [agent for agent in AGENTS if agent not in participants]

    def missing_responses(self) -> list[str]:
        participants = {item.agent for item in self.responses}
        return [agent for agent in AGENTS if agent not in participants]

    def close(self) -> None:
        if self.status != DebateStatus.OPEN:
            raise ValueError("Debate is not open")

        missing_args = self.missing_arguments()
        if missing_args:
            raise ValueError(
                "Missing arguments from: " + ", ".join(missing_args)
            )

        missing_resp = self.missing_responses()
        if missing_resp:
            raise ValueError(
                "Missing responses from: " + ", ".join(missing_resp)
            )

        self.status = DebateStatus.CLOSED

    def unresolved_dissent(self) -> list[Opinion]:
        return self.council.dissent()

    def audit_log(self) -> dict:
        return {
            "status": self.status.value,
            "round_number": self.round_number,
            "arguments": [
                {
                    "agent": item.agent,
                    "claim": item.claim,
                    "evidence": item.evidence,
                    "challenges": list(item.challenges),
                }
                for item in self.arguments
            ],
            "responses": [
                {
                    "agent": item.agent,
                    "reasoning": item.reasoning,
                    "vote": item.vote.value,
                    "confidence": item.confidence,
                }
                for item in self.responses
            ],
            "missing_arguments": self.missing_arguments(),
            "missing_responses": self.missing_responses(),
            "council": self.council.audit_log(),
        }
