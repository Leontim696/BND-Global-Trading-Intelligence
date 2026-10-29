"""Offline orchestration for five independent council opinions."""
from dataclasses import dataclass
from .fusion_council import AGENTS, FusionCouncil, Opinion, Vote

@dataclass(frozen=True)
class RoundResult:
    audit: dict
    decision: Vote | None

def run_round(initial_fn, revision_fn=None):
    council = FusionCouncil()
    for agent in AGENTS:
        opinion = initial_fn(agent)
        if not isinstance(opinion, Opinion) or opinion.agent != agent:
            raise ValueError("Invalid independent opinion")
        council.submit(opinion)
    if revision_fn is not None:
        snapshot = dict(council.initial_opinions)
        proposed = []
        for agent in AGENTS:
            revision = revision_fn(agent, snapshot[agent], dict(snapshot))
            if revision is not None:
                if not isinstance(revision, Opinion) or revision.agent != agent:
                    raise ValueError("Invalid revision")
                proposed.append(revision)
        for revision in proposed:
            council.revise(revision)
    return RoundResult(council.audit_log(), council.decision())
