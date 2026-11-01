#!/usr/bin/env bash
# Restaurează un cont virtual de pe ramura lui. Scrie account=existing|new|none în $GITHUB_OUTPUT.
#   restore_account.sh RAMURĂ "mesaj când nu există" [DIRECTOR_STARE=state]
# Un cont NOU se creează doar dacă ramura nu există deloc ȘI s-a dat CAPITAL. Dacă ramura există dar
# descărcarea eșuează sau lipsește paper.sqlite, jobul se oprește (nu se scrie niciun cont peste cel real).
set -euo pipefail

# Dacă GH_TOKEN e dat doar acestui pas, îl folosim pentru rețea fără să-l lăsăm în .git/config.
git_net() {
  if [ -n "${GH_TOKEN:-}" ]; then
    git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $(printf 'x-access-token:%s' "$GH_TOKEN" | base64 -w0)" "$@"
  else
    git "$@"
  fi
}
branch="$1"; none_msg="${2:-Încă nu există contul.}"; state="${3:-state}"
mkdir -p "$state" data
out="${GITHUB_OUTPUT:-/dev/stdout}"
summary="${GITHUB_STEP_SUMMARY:-/dev/null}"
rc=0
git_net ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1 || rc=$?
if [ "$rc" = 0 ]; then
  fetched=0
  for attempt in 1 2 3; do
    if git_net fetch -q --depth=1 origin "$branch"; then fetched=1; break; fi
    sleep $((attempt * 3))
  done
  if [ "$fetched" != 1 ]; then
    echo "::error::Nu pot descărca contul de pe $branch; nu creez un cont nou."
    exit 1
  fi
  if ! git cat-file -e FETCH_HEAD:paper.sqlite 2>/dev/null; then
    echo "::error::Ramura $branch există, dar fără paper.sqlite; refuz să pornesc un cont nou peste ea."
    exit 1
  fi
  git show FETCH_HEAD:paper.sqlite > "$state/paper.sqlite"
  if git cat-file -e FETCH_HEAD:audit.jsonl 2>/dev/null; then
    git show FETCH_HEAD:audit.jsonl > "$state/audit.jsonl"
  elif [ "${REQUIRE_AUDIT:-0}" = 1 ]; then
    echo "::error::audit.jsonl lipsește pe $branch, deși e obligatoriu; nu repornesc lanțul de la GENESIS."
    exit 1
  else
    echo "::warning::audit.jsonl lipsește pe $branch: jurnalul de audit începe un lanț nou."
  fi
  echo "account=existing" >> "$out"
elif [ "$rc" = 2 ]; then
  if [ -n "${CAPITAL:-}" ]; then
    echo "account=new" >> "$out"
  else
    echo "account=none" >> "$out"
    echo "$none_msg" >> "$summary"
  fi
else
  echo "::error::Nu pot verifica ramura $branch (ls-remote cod $rc); nu creez un cont nou."
  exit 1
fi
