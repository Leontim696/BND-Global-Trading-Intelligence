#!/usr/bin/env bash
# Restaurează fișiere de pe o ramură de stare, FĂRĂ să confunde „ramura nu există” cu „descărcarea a eșuat”.
#   restore_branch.sh RAMURĂ DESTINAȚIE [fișier ...]
# Fără fișiere se extrage tot arborele. Ramura inexistentă (prima rulare) e ok; orice altă eroare oprește jobul,
# ca să nu se publice un istoric nou peste cel real. Un fișier cerut dar lipsit pe o ramură existentă dă avertisment;
# prefixat cu ! (de exemplu '!costs.sqlite') devine OBLIGATORIU: dacă lipsește pe o ramură existentă, jobul se oprește
# (altfel registrul de buget ar reporni de la zero și plafoanele s-ar reseta).
set -euo pipefail

# Dacă GH_TOKEN e dat doar acestui pas, îl folosim pentru rețea fără să-l lăsăm în .git/config.
git_net() {
  # Dacă checkout-ul a păstrat deja credențiale (antet extra), nu adăugăm un al doilea: GitHub respinge antetele duble.
  if [ -n "${GH_TOKEN:-}" ] && ! git config --get-regexp 'http\..*extraheader' >/dev/null 2>&1; then
    git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $(printf 'x-access-token:%s' "$GH_TOKEN" | base64 -w0)" "$@"
  else
    git "$@"
  fi
}
branch="$1"; dest="$2"; shift 2
mkdir -p "$dest"
rc=0
git_net ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1 || rc=$?
if [ "$rc" = 2 ]; then
  echo "Ramura $branch nu există încă (prima rulare)."
  exit 0
elif [ "$rc" != 0 ]; then
  echo "::error::Nu pot verifica ramura $branch (ls-remote cod $rc); mă opresc ca să nu pierd istoricul."
  exit 1
fi
fetched=0
for attempt in 1 2 3; do
  if git_net fetch -q --depth=1 origin "$branch"; then fetched=1; break; fi
  sleep $((attempt * 3))
done
if [ "$fetched" != 1 ]; then
  echo "::error::Nu pot descărca ramura $branch; mă opresc ca să nu pierd istoricul."
  exit 1
fi
if [ "$#" = 0 ]; then
  git archive FETCH_HEAD | tar -x -C "$dest"
else
  for spec in "$@"; do
    f="${spec#!}"
    if git cat-file -e "FETCH_HEAD:$f" 2>/dev/null; then
      git show "FETCH_HEAD:$f" > "$dest/$(basename "$f")"
    elif [ "$spec" != "$f" ]; then
      echo "::error::$f lipsește pe ramura $branch, deși e obligatoriu; mă opresc ca să nu repornesc de la zero."
      exit 1
    else
      echo "::warning::$f lipsește pe ramura $branch."
    fi
  done
fi
