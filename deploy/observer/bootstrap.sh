#!/usr/bin/env bash
# Primul clone al repo-ului PRIVAT pe LXC, fără token în URL, în argumente sau în istoricul shell.
# Cerință: tokenul salvat înainte cu set-token.sh. Alternativă fără token pe server: vezi docs/PROXMOX.md (arhivă).
set -euo pipefail
dest="${1:-/root/bnd}"
export BND_TOKEN_FILE="${BND_TOKEN_FILE:-/etc/bnd-observer/github-read-token}"
remote="${BND_REMOTE:-https://github.com/Leontim696/BND-Global-Trading-Intelligence.git}"
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/observer/gitauth.sh
source "$here/gitauth.sh"
[ -r "$BND_TOKEN_FILE" ] || { echo "Nu pot citi $BND_TOKEN_FILE; rulează întâi set-token.sh." >&2; exit 1; }
[ ! -e "$dest" ] || { echo "$dest există deja; nu suprascriu." >&2; exit 1; }
git_net clone --quiet --depth=1 "$remote" "$dest"
git -C "$dest" remote -v | grep -qi 'x-access-token\|@' && { echo "URL-ul remote conține credențiale; refuz." >&2; exit 1; }
echo "Clonat în $dest (fără credențiale în config)."
