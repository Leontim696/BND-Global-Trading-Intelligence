#!/usr/bin/env bash
# Un ciclu observer: sincronizare read-only + status JSON. NU pornește runnerul de tranzacționare.
set -uo pipefail
DATA="${BND_DATA_DIR:-/var/lib/bnd-observer}"
export BND_OBSERVER_ONLY=true BND_TRADING_MODE=PAPER BND_ALLOW_LIVE_AI=false
cd "$(dirname "$0")/../.." || exit 1
sync_rc=0
bash deploy/observer/sync.sh || sync_rc=$?
[ "$sync_rc" = 0 ] || echo "Sincronizarea a eșuat (cod $sync_rc): statusul arată sync_ok=false; datele rămân din ultima oglindă."
mkdir -p "$DATA/public"
python3 -m src.bnd.observer --mirror "$DATA/mirror" --out "$DATA/public/status.json" --sync-file "$DATA/sync.json"
