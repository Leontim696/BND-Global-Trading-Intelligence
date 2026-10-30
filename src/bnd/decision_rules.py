"""Fusion Council decision rules: majority, weighted consensus, unanimity.

Every rule returns HOLD unless the evidence is strong enough, so NO TRADE
is the default outcome. Votes are never changed here: initial and
revised opinions stay in the council's history.

Weights come from each agent's measured track record (Brier score of
its directional calls), shrunk towards equal weights until enough
outcomes exist, so a reputation alone never earns extra weight.
"""

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite

from .fusion_council import AGENTS, FusionCouncil, Vote


class DecisionRule(str, Enum):
    MAJORITY = "MAJORITY"
    WEIGHTED = "WEIGHTED"
    UNANIMITY = "UNANIMITY"


@dataclass(frozen=True)
class CouncilDecision:
    vote: Vote
    rule: DecisionRule
    support: dict          # vote value -> share of weighted support
    agreeing: tuple        # agents whose current vote equals the decision
    dissenting: tuple      # agents voting otherwise (kept, never discarded)
    uncertain: bool
    reasons: tuple

    def to_dict(self) -> dict:
        return {
            "vote": self.vote.value,
            "rule": self.rule.value,
            "support": self.support,
            "agreeing": list(self.agreeing),
            "dissenting": list(self.dissenting),
            "uncertain": self.uncertain,
            "reasons": list(self.reasons),
        }


@dataclass
class AgentScorebook:
    """Track record per agent: Brier score of BUY/SELL calls.

    A call's probability that the market moved its way is taken from its
    confidence. HOLD calls are not scored. ``prior_outcomes`` equal-weight
    pseudo-observations stop a few lucky calls from dominating.
    """

    prior_outcomes: int = 20
    minimum_weight: float = 0.25
    scores: dict = field(default_factory=lambda: {agent: [] for agent in AGENTS})

    def record(self, agent: str, vote: Vote, confidence: float, market_went_up: bool) -> None:
        if agent not in AGENTS:
            raise ValueError("Unknown AI agent")
        if vote == Vote.HOLD:
            return
        if not isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        correct = (vote == Vote.BUY) == market_went_up
        self.scores[agent].append((confidence - (1.0 if correct else 0.0)) ** 2)

    def weights(self) -> dict:
        """Normalised weights; skill 1 = perfect, 0 = coin flip or worse."""
        raw = {}
        for agent in AGENTS:
            briers = self.scores[agent]
            # Brier 0.25 is an uninformed 50% forecast.
            skill = max(0.0, 1 - (sum(briers) / len(briers)) / 0.25) if briers else 0.5
            shrunk = (len(briers) * skill + self.prior_outcomes * 0.5) / (
                len(briers) + self.prior_outcomes)
            raw[agent] = max(self.minimum_weight, shrunk)
        total = sum(raw.values())
        return {agent: value / total for agent, value in raw.items()}

    def to_dict(self) -> dict:
        return {"prior_outcomes": self.prior_outcomes,
                "minimum_weight": self.minimum_weight, "scores": self.scores}

    @classmethod
    def from_dict(cls, data: dict) -> "AgentScorebook":
        book = cls(data["prior_outcomes"], data["minimum_weight"])
        for agent in AGENTS:
            book.scores[agent] = [float(x) for x in data["scores"].get(agent, [])]
        return book


def decide(
    council: FusionCouncil,
    rule: DecisionRule = DecisionRule.MAJORITY,
    weights: dict | None = None,
    min_support: float = 0.6,
    min_confidence: float = 0.55,
) -> CouncilDecision:
    """Decide from each agent's current opinion; HOLD when uncertain.

    MAJORITY: strict majority of agents.
    WEIGHTED: sum of weight x confidence per vote; the winner needs at
        least ``min_support`` of the total.
    UNANIMITY: every agent must agree.
    Any rule returns HOLD when the agents backing a trade have average
    confidence below ``min_confidence``.
    """

    current = council.current_opinions()
    if len(current) != len(AGENTS):
        return CouncilDecision(Vote.HOLD, rule, {}, (), tuple(current), True,
                               ("Not every agent has voted",))

    weights = weights or {agent: 1 / len(AGENTS) for agent in AGENTS}
    if set(weights) != set(AGENTS) or any(w < 0 for w in weights.values()):
        raise ValueError("A nonnegative weight is required for every agent")

    use_confidence = rule == DecisionRule.WEIGHTED
    scores = {vote: 0.0 for vote in Vote}
    for agent, opinion in current.items():
        scores[opinion.vote] += weights[agent] * (opinion.confidence if use_confidence else 1)
    total = sum(scores.values())
    support = {vote.value: (scores[vote] / total if total else 0.0) for vote in Vote}

    reasons = []
    counts = {vote: sum(o.vote == vote for o in current.values()) for vote in Vote}
    if rule == DecisionRule.MAJORITY:
        winner = next((v for v in Vote if counts[v] > len(AGENTS) / 2), None)
        if winner is None:
            reasons.append("No strict majority")
    elif rule == DecisionRule.UNANIMITY:
        winner = next((v for v in Vote if counts[v] == len(AGENTS)), None)
        if winner is None:
            reasons.append("Agents are not unanimous")
    else:
        leader = max(Vote, key=lambda v: scores[v])
        winner = leader if support[leader.value] >= min_support else None
        if winner is None:
            reasons.append(
                f"Weighted support {support[leader.value]:.2f} for {leader.value} "
                f"is below {min_support:.2f}")

    if winner in (Vote.BUY, Vote.SELL):
        backers = [o.confidence for o in current.values() if o.vote == winner]
        average = sum(backers) / len(backers)
        if average < min_confidence:
            reasons.append(
                f"Average confidence {average:.2f} of {winner.value} voters is below "
                f"{min_confidence:.2f}")
            winner = None

    decided = winner or Vote.HOLD
    if winner is None:
        reasons.append("Insufficient evidence: HOLD / NO TRADE")
    return CouncilDecision(
        vote=decided,
        rule=rule,
        support=support,
        agreeing=tuple(a for a, o in current.items() if o.vote == decided),
        dissenting=tuple(a for a, o in current.items() if o.vote != decided),
        uncertain=winner is None,
        reasons=tuple(reasons),
    )
