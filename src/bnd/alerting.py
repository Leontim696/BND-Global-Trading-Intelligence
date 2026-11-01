"""Alerte fără repetiții: aceeași problemă nu se trimite iar înainte de o pauză.

Primește lista de alerte curente (de exemplu din `dashboard`) și o stare salvată
într-un fișier JSON. O alertă nouă sau una care persistă după pauză (implicit 12 ore)
e trimisă; una rezolvată se uită, ca să poată reapărea. Dacă topicul de notificări nu
e setat, nu se trimite nimic și nu e o eroare. Doar notificări: nu atinge conturile.

    python -m src.bnd.alerting --status status.json --state alerte.json
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import notify

COOLDOWN = timedelta(hours=12)


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def due(alerts, state: dict, now: datetime, cooldown: timedelta = COOLDOWN):
    """(de trimis acum, starea nouă). Alertele rezolvate dispar din stare."""
    fresh, new_state = [], {}
    for text in dict.fromkeys(alerts):               # fără dubluri în aceeași listă
        key = _key(text)
        last = state.get(key)
        if last is None or now - datetime.fromisoformat(last) >= cooldown:
            fresh.append(text)
            new_state[key] = now.isoformat()
        else:
            new_state[key] = last
    return fresh, new_state


def once_due(items, state: dict, now: datetime):
    """Alerte de tip „eveniment”: se trimit o singură dată, nu se repetă după pauză. (de trimis, starea nouă)"""
    fresh, new_state = [], dict(state)
    for text in dict.fromkeys(items):
        key = "o:" + _key(text)
        if key not in state:
            fresh.append(text)
            new_state[key] = now.isoformat()
    return fresh, new_state


def main(argv=None, sender=notify.send) -> int:
    parser = argparse.ArgumentParser(prog="alerting")
    parser.add_argument("--status", required=True, help="JSON de la dashboard --status-json")
    parser.add_argument("--state", required=True)
    parser.add_argument("--extra", help="JSON cu {\"once\": [...]}: alerte trimise o singură dată")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        alerts = json.loads(Path(args.status).read_text(encoding="utf-8")).get("alerts", [])
        state_path = Path(args.state)
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except (OSError, ValueError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    kept_once = {k: v for k, v in state.items() if k.startswith("o:")}
    fresh, state = due(alerts, {k: v for k, v in state.items() if not k.startswith("o:")}, now)
    state.update(kept_once)
    if args.extra and Path(args.extra).exists():
        try:
            once = json.loads(Path(args.extra).read_text(encoding="utf-8")).get("once", [])
        except (OSError, ValueError):
            once = []
        new_once, state = once_due([str(x) for x in once], state, now)
        fresh += new_once
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if fresh and topic:
        try:
            sender(topic, f"BND: {len(fresh)} alertă(e)", "\n".join(fresh)[:2500], "high")
        except notify.NotifyError as exc:
            print("Notificarea nu a plecat:", exc, file=sys.stderr)
            return 1                               # starea nu se salvează: se reîncearcă data viitoare
    state_path.write_text(json.dumps(state), encoding="utf-8")
    print(json.dumps({"sent": fresh if topic else [], "pending_without_topic": [] if topic else fresh}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
