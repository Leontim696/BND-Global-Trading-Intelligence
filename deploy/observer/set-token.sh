#!/usr/bin/env bash
# Salvează tokenul de CITIRE GitHub fără să-l pună în argumente, URL, variabile exportate sau istoricul shell.
#   sudo bash set-token.sh        (te întreabă tokenul, fără ecou; sau îl citește de pe stdin dintr-un fișier/pipe)
# Fișierul: root:bnd-observer, mod 0640 => serviciul (utilizatorul bnd-observer) îl poate citi, nimeni altcineva.
set -euo pipefail
umask 077
dest="${BND_TOKEN_FILE:-/etc/bnd-observer/github-read-token}"
if [ -t 0 ]; then
  read -r -s -p "Token GitHub fine-grained (Contents: Read, doar acest repo): " token; echo
else
  read -r token
fi
[ -n "$token" ] || { echo "Token gol; nu scriu nimic." >&2; exit 1; }
case "$token" in
  ghp_*|gho_*) echo "ATENȚIE: token clasic (acces larg). Folosește unul fine-grained (github_pat_...) cu Contents: Read." >&2 ;;
esac
install -d -m 0750 "$(dirname "$dest")"
tmp="$(mktemp "$dest.XXXXXX")"
printf '%s\n' "$token" > "$tmp"
unset token
if [ "$(id -u)" = 0 ] && getent group bnd-observer >/dev/null; then
  chown root:bnd-observer "$tmp"; chmod 0640 "$tmp"
else
  chmod 0600 "$tmp"
fi
mv "$tmp" "$dest"
echo "Token salvat în $dest ($(stat -c '%U:%G %a' "$dest")). Verifică cu: sudo bash $(dirname "$0")/check-token.sh"
