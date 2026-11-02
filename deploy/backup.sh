#!/usr/bin/env bash
# Copie consistentă a contului virtual (API-ul de backup SQLite, din Python: nu cere pachetul sqlite3) + jurnalul de
# audit, cu rotație. Copia se scrie sub un nume temporar, se verifică (integrity_check) și abia apoi capătă numele
# final: o copie întreruptă sau stricată nu ajunge niciodată în rotație și nu poate scoate o copie bună.
set -euo pipefail
STATE="${BND_STATE_DIR:-/var/lib/bnd}"
DEST="${BND_BACKUP_DIR:-/var/backups/bnd}"
KEEP="${BND_BACKUP_KEEP:-30}"
mkdir -p "$DEST"
stamp=$(date -u +%Y%m%d_%H%M%S)
tmp="$DEST/.paper_$stamp.sqlite.tmp"
trap 'rm -f "$tmp"' EXIT
python3 - "$STATE/paper.sqlite" "$tmp" <<'PY'
import sqlite3, sys
source, target = sys.argv[1], sys.argv[2]
src = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
dst = sqlite3.connect(target)
try:
    src.backup(dst)
    result = [row[0] for row in dst.execute("PRAGMA integrity_check")]
    if result != ["ok"]:
        raise SystemExit("copia nu trece integrity_check: " + "; ".join(result[:3]))
finally:
    dst.close()
    src.close()
PY
mv "$tmp" "$DEST/paper_$stamp.sqlite"
if [ -f "$STATE/audit.jsonl" ]; then cp "$STATE/audit.jsonl" "$DEST/audit_$stamp.jsonl"; fi
# shellcheck disable=SC2012  # nume generate de noi (marcaj de timp)
ls -1t "$DEST"/paper_*.sqlite | tail -n +$((KEEP + 1)) | xargs -r rm -f
# shellcheck disable=SC2012  # nume generate de noi (marcaj de timp)
ls -1t "$DEST"/audit_*.jsonl 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "Backup: $DEST/paper_$stamp.sqlite"
