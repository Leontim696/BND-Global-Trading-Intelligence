#!/usr/bin/env bash
# Oglindește READ-ONLY contul de pe ramura cont-unic în $BND_DATA_DIR/mirror.
# Nu copiază fișiere în timp ce sunt scrise (ia un commit întreg), verifică înainte de înlocuire
# și păstrează oglinda veche (mirror.prev) pentru rollback. Nu scrie nimic pe GitHub.
#   BND_REMOTE      URL-ul repo-ului (implicit cel oficial) sau o cale locală
#   BND_TOKEN_FILE  fișier (chmod 600) cu un token fine-grained DOAR contents:read, dacă repo-ul e privat
set -euo pipefail
DATA="${BND_DATA_DIR:-/var/lib/bnd-observer}"
REMOTE="${BND_REMOTE:-https://github.com/Leontim696/BND-Global-Trading-Intelligence.git}"
BRANCH="${BND_BRANCH:-cont-unic}"
git_net() {
  if [ -n "${BND_TOKEN_FILE:-}" ] && [ -r "$BND_TOKEN_FILE" ]; then
    git -c "http.extraheader=AUTHORIZATION: basic $(printf 'x-access-token:%s' "$(cat "$BND_TOKEN_FILE")" | base64 -w0)" "$@"
  else
    git "$@"
  fi
}
mkdir -p "$DATA"
exec 9>"$DATA/.sync.lock"
flock -n 9 || { echo "Altă sincronizare rulează; ies."; exit 4; }
work="$(mktemp -d "$DATA/.sync.XXXXXX")"
trap 'rm -rf "$work"' EXIT
git init -q "$work/repo"
git -C "$work/repo" remote add origin "$REMOTE"
ok=0
for attempt in 1 2 3; do
  if GIT_TERMINAL_PROMPT=0 git_net -C "$work/repo" fetch -q --depth=1 origin "refs/heads/$BRANCH"; then ok=1; break; fi
  sleep $((attempt * ${BND_RETRY_SLEEP:-3}))
done
[ "$ok" = 1 ] || { echo "Nu pot descărca $BRANCH; păstrez oglinda veche."; exit 1; }
mkdir "$work/new"
for f in paper.sqlite audit.jsonl; do
  git -C "$work/repo" cat-file -e "FETCH_HEAD:$f" || { echo "Lipsește $f pe $BRANCH; păstrez oglinda veche."; exit 1; }
  git -C "$work/repo" show "FETCH_HEAD:$f" > "$work/new/$f"
done
git -C "$work/repo" rev-parse FETCH_HEAD > "$work/new/COMMIT"
# Verificare înainte de înlocuire (aceeași unealtă ca la citire): oglinda stricată nu înlocuiește una bună.
BND_OBSERVER_ONLY=true python3 -m src.bnd.observer --mirror "$work/new" --out "$work/new.status.json" --stale-hours 100000 \
  || { echo "Oglinda nouă nu trece verificarea; păstrez oglinda veche."; exit 1; }
rm -f "$work/new/.observer.lock"
rm -rf "$DATA/mirror.prev"
[ -d "$DATA/mirror" ] && mv "$DATA/mirror" "$DATA/mirror.prev"
mv "$work/new" "$DATA/mirror"
echo "Oglindă actualizată la $(cat "$DATA/mirror/COMMIT")."
