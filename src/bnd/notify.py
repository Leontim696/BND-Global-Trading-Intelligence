"""Notificări pe telefon prin ntfy (https://ntfy.sh), fără cont și fără parolă.

Pe iPhone instalezi aplicația „ntfy” și te abonezi la un subiect (topic) greu de
ghicit, de exemplu `bnd-<cod-lung-aleatoriu>`. Subiectul se pune ca secret
GitHub `NTFY_TOPIC`; oricine îl știe poate citi sau scrie mesajele, deci
trebuie tratat ca o parolă. Fără secret, nu se trimite nimic și nu e o eroare.

    NTFY_TOPIC=... python -m src.bnd.notify --title "Alertă" --message "Text" --priority high
"""

import argparse
import json
import os
import re
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

TOPIC = re.compile(r"[A-Za-z0-9_-]{8,64}")
PRIORITIES = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}


class NotifyError(Exception):
    """Mesajul nu a putut fi trimis."""


def send(topic: str, title: str, message: str, priority: str = "default",
         server: str = "https://ntfy.sh", opener=urlopen) -> None:
    if not TOPIC.fullmatch(topic or ""):
        raise NotifyError("Subiect invalid: 8-64 de litere, cifre, - sau _")
    if not server.startswith("https://"):
        raise NotifyError("Serverul trebuie să folosească https")
    if priority not in PRIORITIES:
        raise NotifyError("Prioritate necunoscută: " + priority)
    body = json.dumps({"topic": topic, "title": title[:120], "message": message[:3000],
                       "priority": PRIORITIES[priority]}, ensure_ascii=False).encode("utf-8")
    request = Request(server, data=body, method="POST",
                      headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        # Reviewed: https only, checked above; the topic is not logged.
        with opener(request, timeout=20) as response:  # nosec B310
            if not 200 <= response.status < 300:
                raise NotifyError(f"ntfy a răspuns {response.status}")
    except (URLError, TimeoutError, OSError) as exc:
        raise NotifyError("ntfy nu poate fi contactat") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="notify")
    parser.add_argument("--title", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--priority", default="default", choices=sorted(PRIORITIES))
    parser.add_argument("--require", action="store_true",
                        help="o alertă importantă: fără subiect se afișează un avertisment vizibil în GitHub Actions")
    args = parser.parse_args(argv)
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        if args.require:
            print("::warning::NTFY_TOPIC nu e setat: alerta NU a fost trimisă pe telefon (vezi issue-ul de alertă).")
        else:
            print("NTFY_TOPIC nu e setat: nu se trimite nicio notificare.")
        return 0
    try:
        send(topic, args.title, args.message, args.priority)
    except NotifyError as exc:
        print("Eroare:", exc, file=sys.stderr)
        return 2
    print("Notificare trimisă.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
