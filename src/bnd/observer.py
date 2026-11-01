"""Instanță OBSERVER-ONLY (ex. Proxmox): citește o copie a contului și scrie un status JSON.

Nu importă motorul de tranzacționare și nu scrie în cont: SQLite se deschide `mode=ro`, iar sincronizarea
(`deploy/observer/sync.sh`) aduce doar fișiere de pe ramura `cont-unic`. Pornește DOAR cu
`BND_OBSERVER_ONLY=true`, ține un lacăt (două instanțe pe aceeași oglindă sunt refuzate) și scrie
`status.json` atomic, fără SQLite, ca să fie sigur de servit către Home Assistant.

Coduri de ieșire: 0 ok · 1 probleme de integritate · 2 oglindă veche · 4 altă instanță rulează ·
5 BND_OBSERVER_ONLY lipsește · 6 oglinda lipsește.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import audit_log
from .safety import observer_only

try:
    import fcntl
except ImportError:      # pragma: no cover
    fcntl = None

STALE_HOURS = 36.0
EXIT = {"ok": 0, "integrity": 1, "stale": 2, "locked": 4, "not_observer": 5, "missing": 6}


def _read_account(db_path: Path) -> dict:
    out: dict = {"problems": []}
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    except sqlite3.Error as exc:
        out["problems"].append(f"paper.sqlite: nu se poate deschide ({exc})")
        return out
    try:
        if [r[0] for r in db.execute("PRAGMA integrity_check")] != ["ok"]:
            out["problems"].append("paper.sqlite: integrity_check a eșuat")
            return out
        row = db.execute("SELECT currency, initial_capital, cash, kill_switch, kill_reason "
                         "FROM account WHERE id=1").fetchone()
        if row is None:
            out["problems"].append("paper.sqlite: nu există rândul contului")
            return out
        out.update(currency=row[0], initial_capital=row[1], cash=row[2],
                   kill_switch=bool(row[3]), kill_reason=row[4])
        out["open_positions"] = db.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        out["orders"] = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        out["fills"] = db.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
    except sqlite3.Error as exc:
        out["problems"].append(f"paper.sqlite: eroare SQLite ({exc})")
    finally:
        db.close()
    return out


def observe(mirror: Path, now: datetime | None = None, stale_hours: float = STALE_HOURS) -> tuple[dict, str]:
    """(status, verdict) pentru oglinda din `mirror`; nu scrie nimic."""
    now = now or datetime.now(timezone.utc)
    status: dict = {"observer_only": True, "generated": now.isoformat(timespec="seconds"), "problems": []}
    db_path, audit_path = mirror / "paper.sqlite", mirror / "audit.jsonl"
    if not db_path.is_file() or not audit_path.is_file():
        status["problems"].append("oglinda nu conține paper.sqlite și audit.jsonl (rulează sync.sh)")
        status["ok"] = False
        return status, "missing"
    account = _read_account(db_path)
    status["problems"] += account.pop("problems")
    status.update(account)
    ok, message = audit_log.verify(audit_path)
    status["audit"] = {"ok": ok, "message": message}
    if not ok:
        status["problems"].append("audit.jsonl: " + message)
    last = None
    for line in reversed(audit_path.read_text(encoding="utf-8").splitlines()):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("kind") == "daily_run":
            last = row
            break
    if last:
        data = last.get("data", {})
        equity = data.get("equity")
        good = isinstance(equity, (int, float)) and math.isfinite(equity)
        status["last_run"] = {"time": last.get("time"), "equity": equity if good else None,
                              "orders": data.get("orders"), "kill_switch": data.get("kill_switch")}
        try:
            age = (now - datetime.fromisoformat(last["time"])).total_seconds() / 3600
            status["last_run"]["age_hours"] = round(age, 1)
            status["stale"] = age > stale_hours
        except (ValueError, KeyError, TypeError):
            status["problems"].append("audit.jsonl: ora ultimei rulări nu poate fi citită")
    else:
        status["problems"].append("audit.jsonl: nu există nicio rulare zilnică")
    status["ok"] = not status["problems"]
    if status["problems"]:
        return status, "integrity"
    return status, "stale" if status.get("stale") else "ok"


def write_status(path: Path, status: dict) -> None:
    """Scriere atomică: cititorul vede fie versiunea veche, fie cea nouă, niciodată una pe jumătate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mirror", required=True, help="folderul cu paper.sqlite și audit.jsonl copiate de sync.sh")
    parser.add_argument("--out", required=True, help="status.json de publicat (fără SQLite)")
    parser.add_argument("--stale-hours", type=float, default=STALE_HOURS)
    args = parser.parse_args(argv)
    if not observer_only():
        print("Refuz: lipsește BND_OBSERVER_ONLY=true (unealta rulează doar în modul observator).", file=sys.stderr)
        return EXIT["not_observer"]
    mirror = Path(args.mirror)
    if not mirror.is_dir():
        print("Oglinda lipsește:", mirror, file=sys.stderr)
        return EXIT["missing"]
    lock = open(mirror / ".observer.lock", "a+")            # noqa: SIM115 - ținut deschis cât rulează
    if fcntl:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("Altă instanță observer rulează pe această oglindă; ies.", file=sys.stderr)
            return EXIT["locked"]
    status, verdict = observe(mirror, stale_hours=args.stale_hours)
    status["verdict"] = verdict
    write_status(Path(args.out), status)
    print(json.dumps({k: status.get(k) for k in ("verdict", "ok", "problems")}, ensure_ascii=False))
    return EXIT[verdict]


if __name__ == "__main__":
    sys.exit(main())
