#!/usr/bin/env bash
# Instalare IDEMPOTENTĂ a observerului pe un LXC Debian. NU se rulează automat; rulează-l tu, ca root.
#   install.sh --dry-run   arată ce ar face, fără să modifice nimic
# Nu pornește și nu activează bnd-paper.timer; refuză dacă acesta e activ (două instanțe = cont dublat).
set -euo pipefail
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi; }
here="$(cd "$(dirname "$0")" && pwd)"; repo="$(cd "$here/../.." && pwd)"
if systemctl is-enabled bnd-paper.timer >/dev/null 2>&1 || systemctl is-active bnd-paper.timer >/dev/null 2>&1; then
  echo "REFUZ: bnd-paper.timer e activ. Observerul nu se instalează lângă un runner de tranzacționare." >&2; exit 1
fi
command -v python3 >/dev/null || { echo "Lipsește python3 (apt install python3 git)." >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { echo "Cere Python >= 3.11." >&2; exit 1; }
id bnd-observer >/dev/null 2>&1 || run useradd --system --home-dir /var/lib/bnd-observer --shell /usr/sbin/nologin bnd-observer
run install -d -o bnd-observer -g bnd-observer -m 0750 /var/lib/bnd-observer /var/lib/bnd-observer/public
run install -d -m 0755 /opt/bnd-observer
run cp -a "$repo/src" "$repo/deploy" /opt/bnd-observer/
run install -d -m 0750 /etc/bnd-observer
[ -f /etc/bnd-observer/env ] || run install -m 0640 "$here/env.example" /etc/bnd-observer/env
run install -m 0644 "$here"/bnd-observer.service "$here"/bnd-observer.timer "$here"/bnd-observer-http.service /etc/systemd/system/
run systemctl daemon-reload
run systemctl enable --now bnd-observer.timer
echo "Gata. Verifică: systemctl list-timers bnd-observer.timer; bash /opt/bnd-observer/deploy/observer/healthcheck.sh"
