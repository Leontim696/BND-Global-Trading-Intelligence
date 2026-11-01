#!/usr/bin/env bash
# Restaurează fișiere de pe o ramură de stare, FĂRĂ să confunde „ramura nu există” cu „descărcarea a eșuat”.
#   restore_branch.sh RAMURĂ DESTINAȚIE [fișier ...]
# Fără fișiere se extrage tot arborele. Ramura inexistentă (prima rulare) e ok; orice altă eroare oprește jobul,
# ca să nu se publice un istoric nou peste cel real. Un fișier cerut dar lipsit pe o ramură existentă dă avertisment.
set -euo pipefail
branch="$1"; dest="$2"; shift 2
mkdir -p "$dest"
rc=0
git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1 || rc=$?
if [ "$rc" = 2 ]; then
  echo "Ramura $branch nu există încă (prima rulare)."
  exit 0
elif [ "$rc" != 0 ]; then
  echo "::error::Nu pot verifica ramura $branch (ls-remote cod $rc); mă opresc ca să nu pierd istoricul."
  exit 1
fi
fetched=0
for attempt in 1 2 3; do
  if git fetch -q --depth=1 origin "$branch"; then fetched=1; break; fi
  sleep $((attempt * 3))
done
if [ "$fetched" != 1 ]; then
  echo "::error::Nu pot descărca ramura $branch; mă opresc ca să nu pierd istoricul."
  exit 1
fi
if [ "$#" = 0 ]; then
  git archive FETCH_HEAD | tar -x -C "$dest"
else
  for f in "$@"; do
    if git cat-file -e "FETCH_HEAD:$f" 2>/dev/null; then
      git show "FETCH_HEAD:$f" > "$dest/$(basename "$f")"
    else
      echo "::warning::$f lipsește pe ramura $branch."
    fi
  done
fi
