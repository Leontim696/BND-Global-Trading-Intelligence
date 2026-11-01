"""Instanță OBSERVER-ONLY (ex. Proxmox): citește o copie a contului și scrie un status JSON.

Nu importă motorul de tranzacționare și nu scrie în cont: SQLite se deschide `mode=ro`, iar sincronizarea
(`deploy/observer/sync.sh`) aduce doar fișiere de pe ramura `cont-unic`. Pornește DOAR cu
`BND_OBSERVER_ONLY=true`, ține un lacăt (două instanțe pe aceeași oglindă sunt refuzate) și scrie
`status.json` atomic, fără SQLite, ca să fie sigur de servit către Home Assistant.

Sănătatea DATELOR (integritate, vechime) e separată de sănătatea SINCRONIZĂRII (`sync_ok`,
`last_successful_sync`, `mirror_commit`): un eșec GitHub nu apare niciodată ca sincronizare reușită.
`ok` = date valide ȘI ultima sincronizare reușită ȘI oglinda proaspătă.

Coduri de ieșire: 0 ok · 1 probleme de integritate · 2 oglindă veche · 4 altă instanță rulează ·
5 BND_OBSERVER_ONLY lipsește · 6 oglinda lipsește · 7 ultima sincronizare a eșuat (datele din oglindă sunt valide).
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
EXIT = {"ok": 0, "integrity": 1, "stale": 2, "locked": 4, "not_observer": 5, "missing": 6, "sync_failed": 7}
SYNC_STALE_HOURS = 3.0      # timerul rulează la 30 de minute: peste 3 ore fără sincronizare reușită e o problemă


def record_sync(data_dir, ok: bool, reason: str = "", now: datetime | None = None) -> dict:
    """Scrie `sync.json` (atomic). La eșec păstrează `last_successful_sync` și `mirror_commit` de la ultima reușită."""
    data_dir = Path(data_dir)
    now = now or datetime.now(timezone.utc)
    path = data_dir / "sync.json"
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    commit_file = data_dir / "mirror" / "COMMIT"
    commit = commit_file.read_text(encoding="utf-8").strip() if commit_file.is_file() else previous.get("mirror_commit")
    state = {"sync_ok": bool(ok), "last_attempt": now.isoformat(timespec="seconds"),
             "last_successful_sync": now.isoformat(timespec="seconds") if ok else previous.get("last_successful_sync"),
             "mirror_commit": commit, "sync_error": None if ok else (reason or "necunoscut"),
             "consecutive_failures": 0 if ok else int(previous.get("consecutive_failures") or 0) + 1}
    write_status(path, state)
    return state


def _sync_info(sync_file, now: datetime) -> dict:
    """Câmpurile de sincronizare pentru status; fără sync.json = nu s-a sincronizat niciodată sub acest sistem."""
    try:
        state = json.loads(Path(sync_file).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"sync_ok": False, "last_successful_sync": None, "mirror_commit": None,
                "sync_error": "nicio sincronizare înregistrată (lipsește sync.json)"}
    info = {k: state.get(k) for k in ("sync_ok", "last_attempt", "last_successful_sync", "mirror_commit",
                                      "sync_error", "consecutive_failures")}
    try:
        age = (now - datetime.fromisoformat(state["last_successful_sync"])).total_seconds() / 3600
        info["sync_age_hours"] = round(age, 1)
    except (KeyError, ValueError, TypeError):
        info["sync_age_hours"] = None
    return info


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


def observe(mirror: Path, now: datetime | None = None, stale_hours: float = STALE_HOURS,
            sync_file=None, sync_stale_hours: float = SYNC_STALE_HOURS) -> tuple[dict, str]:
    """(status, verdict) pentru oglinda din `mirror`; nu scrie nimic.

    `verdict` descrie datele (ok/stale/integrity/missing); dacă datele sunt valide dar sincronizarea e căzută
    sau veche, verdictul e `sync_failed`. `data_ok` și `sync_ok` sunt câmpuri separate."""
    now = now or datetime.now(timezone.utc)
    status: dict = {"observer_only": True, "generated": now.isoformat(timespec="seconds"), "problems": []}
    db_path, audit_path = mirror / "paper.sqlite", mirror / "audit.jsonl"
    if not db_path.is_file() or not audit_path.is_file():
        status["problems"].append("oglinda nu conține paper.sqlite și audit.jsonl (rulează sync.sh)")
        status["data_ok"] = False
        status["ok"] = False
        status["sync_ok"] = False                       # fără oglindă nu există o sincronizare sănătoasă
        if sync_file is not None:
            status.update({k: v for k, v in _sync_info(sync_file, now).items() if k != "sync_ok"})
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
    status["data_ok"] = not status["problems"]
    sync = _sync_info(sync_file, now) if sync_file is not None else None
    if sync is not None:
        status.update(sync)
        sync_bad = (not sync["sync_ok"]) or (sync.get("sync_age_hours") is None) or sync["sync_age_hours"] > sync_stale_hours
        status["sync_ok"] = not sync_bad
        if sync_bad and sync["sync_ok"]:
            status["sync_error"] = f"ultima sincronizare reușită e veche ({sync.get('sync_age_hours')} h)"
    else:
        status["sync_ok"] = None
    status["ok"] = bool(status["data_ok"] and status["sync_ok"] is not False and not status.get("stale"))
    if status["problems"]:
        return status, "integrity"
    if status.get("stale"):
        return status, "stale"
    return status, "sync_failed" if status["sync_ok"] is False else "ok"


def write_status(path: Path, status: dict) -> None:
    """Scriere atomică: cititorul vede fie versiunea veche, fie cea nouă, niciodată una pe jumătate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mirror", help="folderul cu paper.sqlite și audit.jsonl copiate de sync.sh")
    parser.add_argument("--out", help="status.json de publicat (fără SQLite)")
    parser.add_argument("--stale-hours", type=float, default=STALE_HOURS)
    parser.add_argument("--sync-file", help="sync.json scris de sync.sh (altfel câmpurile de sincronizare lipsesc)")
    parser.add_argument("--sync-stale-hours", type=float, default=SYNC_STALE_HOURS)
    parser.add_argument("--record-sync", choices=["ok", "fail"], help="doar scrie sync.json în --data-dir și iese")
    parser.add_argument("--reason", default="")
    parser.add_argument("--data-dir")
    args = parser.parse_args(argv)
    if args.record_sync:
        if not args.data_dir:
            print("--record-sync cere --data-dir", file=sys.stderr)
            return 2
        record_sync(args.data_dir, args.record_sync == "ok", args.reason)
        return 0
    if not args.mirror or not args.out:
        parser.error("--mirror și --out sunt obligatorii")
    if not observer_only():
        print("Refuz: lipsește BND_OBSERVER_ONLY=true (unealta rulează doar în modul observator).", file=sys.stderr)
        return EXIT["not_observer"]
    mirror = Path(args.mirror)
    if not mirror.is_dir():
        # Prima sincronizare a eșuat: tot publicăm un status (data_ok/sync_ok false), ca să se vadă și în Home Assistant.
        print("Oglinda lipsește:", mirror, file=sys.stderr)
        status, verdict = observe(mirror, stale_hours=args.stale_hours, sync_file=args.sync_file,
                                  sync_stale_hours=args.sync_stale_hours)
        status["verdict"] = verdict
        write_status(Path(args.out), status)
        return EXIT["missing"]
    lock = open(mirror / ".observer.lock", "a+")            # noqa: SIM115 - ținut deschis cât rulează
    if fcntl:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("Altă instanță observer rulează pe această oglindă; ies.", file=sys.stderr)
            return EXIT["locked"]
    status, verdict = observe(mirror, stale_hours=args.stale_hours, sync_file=args.sync_file,
                              sync_stale_hours=args.sync_stale_hours)
    status["verdict"] = verdict
    write_status(Path(args.out), status)
    print(json.dumps({k: status.get(k) for k in ("verdict", "ok", "problems")}, ensure_ascii=False))
    return EXIT[verdict]


if __name__ == "__main__":
    sys.exit(main())
