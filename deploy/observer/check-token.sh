#!/usr/bin/env bash
# Verifică tokenul fără să-l afișeze: permisiuni, citibil de bnd-observer, doar citire în rețea, urme în istoric.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
file="${BND_TOKEN_FILE:-/etc/bnd-observer/github-read-token}"
remote="${BND_REMOTE:-https://github.com/Leontim696/BND-Global-Trading-Intelligence.git}"
bad=0
fail() { echo "NU: $*"; bad=1; }
ok() { echo "OK: $*"; }
[ -f "$file" ] || { echo "NU: lipsește $file (rulează set-token.sh)"; exit 1; }
mode="$(stat -c '%a' "$file")"; owner="$(stat -c '%U:%G' "$file")"
case "$mode" in
  600|640|400|440) ok "permisiuni $mode ($owner)" ;;
  *) fail "permisiuni $mode (nu trebuie să fie citibil de toți: chmod 0640, root:bnd-observer)" ;;
esac
[ "$(( 8#$mode & 8#007 ))" = 0 ] || fail "tokenul e citibil de 'alții' (mod $mode)"
if id bnd-observer >/dev/null 2>&1 && [ "$(id -u)" = 0 ] && command -v runuser >/dev/null; then
  if runuser -u bnd-observer -- test -r "$file"; then ok "utilizatorul bnd-observer poate citi tokenul"
  else fail "bnd-observer NU poate citi $file: serviciul ar încerca fără autentificare (fix: chown root:bnd-observer, chmod 0640)"; fi
else
  echo "(sar peste testul de citire ca bnd-observer: rulează ca root pe serverul instalat)"
fi
head_line="$(head -c 11 "$file")"
case "$head_line" in
  github_pat_) ok "token fine-grained" ;;
  ghp_*|gho_*) fail "token clasic (acces larg): înlocuiește-l cu unul fine-grained, Contents: Read" ;;
esac
# shellcheck source=deploy/observer/gitauth.sh
source "$here/gitauth.sh"
export BND_TOKEN_FILE="$file"
if git_net ls-remote --exit-code "$remote" "refs/heads/cont-unic" >/dev/null 2>&1; then ok "citirea ramurii cont-unic funcționează (doar ls-remote, nu se scrie nimic)"
else fail "nu pot citi ramura cont-unic cu acest token (permisiune Contents: Read lipsă, token expirat sau repo greșit)"; fi
for hist in /root/.bash_history "${HOME:-/root}/.bash_history"; do
  if [ -f "$hist" ] && grep -qE 'github_pat_|ghp_|x-access-token:[A-Za-z0-9_]{10,}' "$hist" 2>/dev/null; then
    fail "pare să existe un token în $hist: șterge linia (history -c) și REVOCĂ tokenul"
  fi
done
exit "$bad"
