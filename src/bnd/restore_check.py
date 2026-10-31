"""Verifică o copie de siguranță a contului: se deschide, e întreagă și contabilitatea se potrivește.

Caută cea mai nouă copie `paper_*.sqlite` (și jurnalul `audit_*.jsonl` cu același marcaj),
rulează `PRAGMA integrity_check`, reconcilierea independentă și verificarea lanțului de
audit, pe o copie temporară (originalul nu se atinge). Cod de ieșire 0 = restaurabil.

    python -m src.bnd.restore_check --backup-dir /var/backups/bnd
"""

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from . import audit_log
from .paper_engine import PaperEngine, PaperEngineError
from .reconcile import reconcile


def check(backup_dir) -> dict:
    folder = Path(backup_dir)
    copies = sorted(folder.glob("paper_*.sqlite"))
    if not copies:
        return {"ok": False, "problems": ["nicio copie paper_*.sqlite în " + str(folder)]}
    newest = copies[-1]
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "paper.sqlite"
        shutil.copy2(newest, work)
        try:
            db = sqlite3.connect(work)
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            db.close()
        except sqlite3.Error as exc:
            integrity = f"nu se poate deschide: {exc}"
        if integrity != "ok":
            problems.append("integritatea SQLite: " + str(integrity))
        else:
            try:
                engine = PaperEngine.open(work)
                try:
                    report = reconcile(engine)
                finally:
                    engine.close()
                problems += [c["check"] for c in report["checks"] if not c["ok"]]
            except PaperEngineError as exc:
                problems.append(str(exc))
    audit = folder / newest.name.replace("paper_", "audit_").replace(".sqlite", ".jsonl")
    if audit.exists():
        ok, message = audit_log.verify(audit)
        if not ok:
            problems.append("jurnal de audit: " + message)
    return {"ok": not problems, "backup": newest.name, "audit_checked": audit.exists(),
            "problems": problems}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="restore_check")
    parser.add_argument("--backup-dir", required=True)
    args = parser.parse_args(argv)
    result = check(args.backup_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
