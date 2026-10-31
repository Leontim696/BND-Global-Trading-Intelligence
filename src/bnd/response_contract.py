"""Contractul comun de răspuns al agenților AI (validare strictă, dezactivat pentru testul activ).

Un răspuns complet are: vot, încredere, argumente, dovezi, riscuri și, dacă votul
e HOLD, motivul abținerii. Validatorul întoarce probleme explicite și marchează
răspunsul INCOMPLET sau INVALID; nu corectează și nu completează nimic. Consiliul
activ NU folosește încă acest contract (promptul lui rămâne neschimbat ca să nu
influențeze evaluarea de 16 zile); contractul e pregătit pentru etapa următoare.
"""

from dataclasses import dataclass, field
from math import isfinite

VOTES = ("BUY", "SELL", "HOLD")
LIST_FIELDS = ("arguments", "evidence", "risks")
VALID, INCOMPLETE, INVALID = "VALID", "INCOMPLET", "INVALID"

PROMPT_SUFFIX = (
    "Răspunde DOAR cu JSON: {\"vote\": \"BUY|SELL|HOLD\", \"confidence\": 0..1, "
    "\"arguments\": [\"...\"], \"evidence\": [\"cifre din date\"], \"risks\": [\"...\"], "
    "\"abstention_reason\": \"obligatoriu dacă vote=HOLD\"}. Nu inventa date care nu sunt în întrebare."
)


@dataclass(frozen=True)
class Checked:
    status: str
    problems: tuple = ()
    data: dict = field(default_factory=dict)


def validate(payload) -> Checked:
    if not isinstance(payload, dict):
        return Checked(INVALID, ("răspunsul nu e un obiect",))
    problems, soft = [], []
    vote = payload.get("vote")
    if vote not in VOTES:
        problems.append("vot lipsă sau necunoscut")
    confidence = payload.get("confidence")
    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not isfinite(confidence) or not 0.0 <= confidence <= 1.0):
        problems.append("încredere lipsă sau în afara [0, 1]")
    for name in LIST_FIELDS:
        value = payload.get(name)
        if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
            problems.append(f"{name}: listă de texte cerută")
        elif not value:
            soft.append(f"{name}: gol")
    if vote == "HOLD" and not str(payload.get("abstention_reason") or "").strip():
        soft.append("HOLD fără motivul abținerii")
    if problems:
        return Checked(INVALID, tuple(problems + soft))
    if soft:
        return Checked(INCOMPLETE, tuple(soft), dict(payload))
    return Checked(VALID, (), dict(payload))
