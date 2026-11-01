#!/usr/bin/env bash
# Exit 0 doar dacă status.json există, e recent (< 2 ore), ok=true și observer_only=true.
set -euo pipefail
f="${BND_DATA_DIR:-/var/lib/bnd-observer}/public/status.json"
[ -f "$f" ] || { echo "status.json lipsește"; exit 1; }
age=$(( $(date +%s) - $(stat -c %Y "$f") ))
[ "$age" -le 7200 ] || { echo "status.json e vechi (${age}s): observerul nu rulează"; exit 1; }
python3 - "$f" <<'P'
import json, sys
s = json.load(open(sys.argv[1]))
assert s.get("observer_only") is True, "nu e în mod observer"
assert s.get("ok") is True and s.get("verdict") == "ok", f"verdict={s.get('verdict')} probleme={s.get('problems')}"
P
