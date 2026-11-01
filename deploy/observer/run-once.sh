#!/usr/bin/env bash
# Un ciclu observer: sincronizare read-only + status JSON. NU pornește runnerul de tranzacționare.
set -uo pipefail
DATA="${BND_DATA_DIR:-/var/lib/bnd-observer}"
export BND_OBSERVER_ONLY=true BND_TRADING_MODE=PAPER BND_ALLOW_LIVE_AI=false
cd "$(dirname "$0")/../.."
bash deploy/observer/sync.sh || echo "Sincronizarea a eșuat; raportez din ultima oglindă."
mkdir -p "$DATA/public"
python3 -m src.bnd.observer --mirror "$DATA/mirror" --out "$DATA/public/status.json"
