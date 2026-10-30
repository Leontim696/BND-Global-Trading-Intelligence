
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
    # Submission order of every argument and response, so a reply can be
    # checked to come after the objection it answers.
    argument_order: list[int] = field(default_factory=list)
    response_order: list[int] = field(default_factory=list)
    _sequence: int = field(default=0, repr=False)

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
        self.argument_order.append(self._next())

    def _next(self) -> int:
        self._sequence += 1
        return self._sequence

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
        self.response_order.append(self._next())

    def unanswered_objections(self) -> list[dict]:
        """Objections that a challenged agent has not yet answered.

        An argument that challenges agents currently voting differently
        from its author is an objection. Each of those agents must submit
        a response after it (keeping or changing their vote) before the
        debate can close, so a single well-argued dissenter forces the
        majority to reconsider without anyone being forced to agree.
        """

        current = self.council.current_opinions()
        open_items = []
        for argument, order in zip(self.arguments, self.argument_order):
            author = current.get(argument.agent)
            for challenged in argument.challenges:
                target = current.get(challenged)
                if author is None or target is None or target.vote == author.vote:
                    continue
                answered = any(
                    response.agent == challenged and response_order > order
                    for response, response_order in zip(self.responses, self.response_order)
                )
                if not answered:
                    open_items.append({
                        "objector": argument.agent,
                        "challenged": challenged,
                        "claim": argument.claim,
                    })
        return open_items

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

        unanswered = self.unanswered_objections()
        if unanswered:
            raise ValueError(
                "Unanswered objections: " + ", ".join(
                    f"{item['challenged']} to {item['objector']}" for item in unanswered
                )
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
            "unanswered_objections": self.unanswered_objections(),
            "council": self.council.audit_log(),
        }
