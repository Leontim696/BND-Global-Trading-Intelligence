#!/usr/bin/env bash
# Test de restaurare: ia cea mai nouă copie din $BND_BACKUP_DIR (făcută de deploy/backup.sh), o restaurează
# într-un folder TEMPORAR și o verifică (integritate SQLite + lanț audit). Nu atinge contul și nu suprascrie nimic.
set -euo pipefail
DEST="${BND_BACKUP_DIR:-/var/backups/bnd}"
# shellcheck disable=SC2012  # nume generate de noi (marcaj de timp)
db="$(ls -1t "$DEST"/paper_*.sqlite 2>/dev/null | head -n1 || true)"
[ -n "$db" ] || { echo "Nu există nicio copie în $DEST"; exit 1; }
stamp="${db##*/paper_}"; stamp="${stamp%.sqlite}"
audit="$DEST/audit_$stamp.jsonl"
[ -f "$audit" ] || { echo "Lipsește $audit"; exit 1; }
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
cp "$db" "$tmp/paper.sqlite"; cp "$audit" "$tmp/audit.jsonl"
cd "$(dirname "$0")/../.." || exit 1
BND_OBSERVER_ONLY=true python3 -m src.bnd.observer --mirror "$tmp" --out "$tmp/status.json" --stale-hours 100000
echo "Copia $stamp se restaurează corect (integritate + audit)."
