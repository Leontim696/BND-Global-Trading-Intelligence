
"""BND Debate Engine — structured AI debate and dissent tracking."""

from dataclasses import dataclass, field
from enum import Enum

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


@dataclass
class DebateEngine:
    council: FusionCouncil
    arguments: list[DebateArgument] = field(default_factory=list)
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
            raise ValueError("All six agents must vote first")
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

    def next_round(self) -> None:
        if self.status != DebateStatus.OPEN:
            raise ValueError("Debate is not open")
        if self.round_number >= self.max_rounds:
            raise ValueError("Maximum debate rounds reached")
        self.round_number += 1

    def close(self) -> None:
        if self.status != DebateStatus.OPEN:
            raise ValueError("Debate is not open")
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
            "council": self.council.audit_log(),
        }
