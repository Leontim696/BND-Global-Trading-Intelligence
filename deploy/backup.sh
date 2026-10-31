#!/usr/bin/env bash
# Copie consistentă a contului virtual (SQLite .backup) + jurnalul de audit, cu rotație.
set -euo pipefail
STATE="${BND_STATE_DIR:-/var/lib/bnd}"
DEST="${BND_BACKUP_DIR:-/var/backups/bnd}"
KEEP="${BND_BACKUP_KEEP:-30}"
mkdir -p "$DEST"
stamp=$(date -u +%Y%m%d_%H%M%S)
sqlite3 "$STATE/paper.sqlite" ".backup '$DEST/paper_$stamp.sqlite'"
[ -f "$STATE/audit.jsonl" ] && cp "$STATE/audit.jsonl" "$DEST/audit_$stamp.jsonl"
# shellcheck disable=SC2012  # nume generate de noi (marcaj de timp)
ls -1t "$DEST"/paper_*.sqlite | tail -n +$((KEEP + 1)) | xargs -r rm -f
# shellcheck disable=SC2012  # nume generate de noi (marcaj de timp)
ls -1t "$DEST"/audit_*.jsonl 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "Backup: $DEST/paper_$stamp.sqlite"
