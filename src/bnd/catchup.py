"""Plasă de siguranță pentru rulările zilnice pe care GitHub nu le mai pornește la timp (16.11.2026).

Din 12.11 programatorul GitHub întârzie cu ore sau sare rulările programate (consiliul pornea pe la 01:20 UTC în loc
de 21:40, rezumatul de dimineață la 12:38 în loc de 04:05). Bucla de prețuri rulează sigur o dată pe oră; la fiecare
ciclu întreabă acest modul ce rulări zilnice au întârziat și le pornește ea (workflow_dispatch). Programele din
fișierele .yml rămân ca rezervă.

Reguli (fixe, fără rețea; bucla dă listele de rulări):
- o rulare zilnică e „întârziată” dacă a trecut ora ei + GRACE și azi (UTC) nu există nicio rulare creată după acea
  oră (programată sau manuală, în orice stare) — deci nu se pornește de două ori;
- conturile pornesc doar după un consiliu reușit azi (aceleași voturi ca la rularea programată);
- consiliul și conturile își păstrează propria protecție la dublare (consiliul nu plătește a doua oară o piață
  decisă azi; ordinele au id-ul zilei).

    python -m src.bnd.catchup --runs-dir out/cu --now 2026-11-16T22:40:00Z
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

GRACE = timedelta(minutes=30)
STATUS_EVERY = timedelta(minutes=90)
LAST_DAY = "2026-11-30"          # consiliul și conturile zilnice ale testului se opresc după 30.11

# fișier, ora UTC, de ce depinde (fișier), câmpuri pentru workflow_dispatch, doar până la sfârșitul testului
DAILY = (
    ("consiliu-umbra.yml", "21:40", None, {"mode": "daily"}, True),
    ("cont-unic.yml", "22:25", "consiliu-umbra.yml", {}, True),
    ("cont-control.yml", "22:35", "consiliu-umbra.yml", {}, True),
    ("formatii-ai.yml", "22:50", "consiliu-umbra.yml", {}, True),
    ("dimineata.yml", "04:05", None, {}, False),
    ("health-check.yml", "05:47", None, {}, False),
    ("date-macro.yml", "06:20", None, {}, False),
)


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _at(now: datetime, hhmm: str) -> datetime:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def plan(runs: dict, now: datetime) -> list:
    """runs = {fișier: [{createdAt, status, conclusion}, ...]} → [(fișier, câmpuri)] de pornit acum."""
    now = now.astimezone(timezone.utc)
    out = []
    for name, hhmm, dep, fields, test_only in DAILY:
        if test_only and now.date().isoformat() > LAST_DAY:
            continue
        if name not in runs:
            continue                                       # fără listă sigură de rulări nu pornim nimic
        due = _at(now, hhmm)
        if now < due + GRACE:
            continue
        if any(_time(r["createdAt"]) >= due for r in runs.get(name, [])):
            continue                                       # a pornit deja azi (programat sau manual)
        if dep:
            dep_due = _at(now, next(h for n, h, *_ in DAILY if n == dep))
            if not any(_time(r["createdAt"]) >= dep_due and r.get("status") == "completed"
                       and r.get("conclusion") == "success" for r in runs.get(dep, [])):
                continue                                   # fără consiliu reușit azi, contul așteaptă
        out.append((name, fields))
    status = runs.get("status.yml")
    if status is not None and not any(now - _time(r["createdAt"]) < STATUS_EVERY for r in status):
        out.append(("status.yml", {}))
    return out


def files() -> list:
    return [name for name, *_ in DAILY] + ["status.yml"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="catchup")
    parser.add_argument("--runs-dir", help="câte un <fișier>.json cu rulările lui (gh run list --json)")
    parser.add_argument("--now", help="ora UTC (implicit acum)")
    parser.add_argument("--list", action="store_true", help="doar fișierele urmărite")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(files()))
        return 0
    runs = {}
    for name in files():
        path = Path(args.runs_dir) / f"{name}.json"
        try:
            runs[name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue                                       # fără listă sigură nu pornim nimic pentru el
    now = _time(args.now) if args.now else datetime.now(timezone.utc)
    for name, fields in plan(runs, now):
        print(name + "".join(f" -f inputs[{k}]={v}" for k, v in fields.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
