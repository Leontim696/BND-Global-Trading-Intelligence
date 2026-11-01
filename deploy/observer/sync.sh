#!/usr/bin/env bash
# Oglindește READ-ONLY contul de pe ramura cont-unic în $BND_DATA_DIR/mirror (legătură simbolică spre releases/<ts>-<commit>).
# - Comutarea e ATOMICĂ (rename peste legătură): oprirea bruscă în orice punct lasă ori vechea oglindă, ori cea nouă, întregi.
# - sync.attempt marchează o tentativă în curs; dacă rămâne după ce procesul a murit, tentativa e raportată ca ÎNTRERUPTĂ,
#   nu ca sincronizare reușită, iar următoarea rulare o înregistrează (interrupted_attempts) și curăță resturile.
# - Dacă `mirror` lipsește (migrare veche sau legătură ruptă) se recuperează cea mai nouă versiune validă din releases/.
# Nu scrie nimic pe GitHub.
#   BND_REMOTE      URL-ul repo-ului (implicit cel oficial) sau o cale locală
#   BND_TOKEN_FILE  fișier cu token fine-grained DOAR contents:read (sau credential systemd `github-token`), dacă repo-ul e privat
set -euo pipefail
DATA="${BND_DATA_DIR:-/var/lib/bnd-observer}"
REMOTE="${BND_REMOTE:-https://github.com/Leontim696/BND-Global-Trading-Intelligence.git}"
BRANCH="${BND_BRANCH:-cont-unic}"
reason="oprit_neasteptat"
marker=0
# Punct de oprire pentru teste (BND_SYNC_PAUSE_AT=<etapă>): marchează etapa atinsă și așteaptă să fie oprit brusc.
checkpoint() {
  if [ "${BND_SYNC_PAUSE_AT:-}" = "$1" ]; then : > "$DATA/.reached.$1"; sleep 120; fi
  return 0
}
finish() {
  local rc=$?
  [ -n "${work:-}" ] && rm -rf "$work"
  [ "$rc" = 4 ] && return 0                      # altă sincronizare rulează: nu e un eșec al acesteia
  if [ "$rc" = 0 ]; then
    python3 -m src.bnd.observer --record-sync ok --data-dir "$DATA" || true
  else
    python3 -m src.bnd.observer --record-sync fail --reason "$reason" --data-dir "$DATA" || true
  fi
  [ "$marker" = 1 ] && rm -f "$DATA/sync.attempt"
  return 0
}
# shellcheck source=deploy/observer/gitauth.sh
source "$(dirname "${BASH_SOURCE[0]}")/gitauth.sh"
verify() {   # verify <folder>: aceeași verificare ca la citire; scrie un status temporar, nu atinge folderul altfel
  BND_OBSERVER_ONLY=true python3 -m src.bnd.observer --mirror "$1" --out "$1.status.tmp" --stale-hours 100000 >/dev/null 2>&1
  local rc=$?; rm -f "$1.status.tmp" "$1/.observer.lock"; return $rc
}
mkdir -p "$DATA/releases"
exec 9>"$DATA/.sync.lock"
flock -n 9 || { echo "Altă sincronizare rulează; ies."; exit 4; }
trap finish EXIT
trap 'reason="intrerupt_semnal"; exit 143' TERM INT HUP
# Lacătul e al nostru: orice marcaj rămas e al unui proces mort = tentativă întreruptă.
if [ -e "$DATA/sync.attempt" ]; then
  echo "Tentativă anterioară întreruptă ($(tr -d '\n' < "$DATA/sync.attempt")); o înregistrez și curăț resturile."
  python3 -m src.bnd.observer --record-sync interrupted --data-dir "$DATA" || true
fi
rm -rf "$DATA"/.work.* "$DATA"/.mirror.tmp "$DATA"/.prev.tmp "$DATA"/releases/.incoming.* "$DATA"/.reached.*
printf '{"pid": %s, "started": "%s"}\n' "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$DATA/sync.attempt.tmp"
mv "$DATA/sync.attempt.tmp" "$DATA/sync.attempt"
marker=1
if [ -d "$DATA/mirror" ] && [ ! -L "$DATA/mirror" ]; then          # oglindă veche (folder real) -> versiune în releases/
  mv "$DATA/mirror" "$DATA/releases/legacy-$(date -u +%Y%m%dT%H%M%SZ)"
fi
if [ ! -e "$DATA/mirror" ]; then                                    # lipsă sau legătură ruptă: recuperăm cea mai nouă versiune validă
  # shellcheck disable=SC2045  # nume generate de noi (marcaj de timp)
  for candidate in $(ls -1t "$DATA/releases" 2>/dev/null); do
    if verify "$DATA/releases/$candidate"; then
      ln -sfn "releases/$candidate" "$DATA/.mirror.tmp"; mv -T "$DATA/.mirror.tmp" "$DATA/mirror"
      echo "Oglinda lipsea; recuperată din releases/$candidate."
      break
    fi
  done
fi
if [ -n "${BND_TOKEN_FILE:-}" ] && [ ! -r "$BND_TOKEN_FILE" ]; then
  reason="token_ilizibil"
  echo "BND_TOKEN_FILE=$BND_TOKEN_FILE nu poate fi citit de acest utilizator ($(id -un)); vezi docs/PROXMOX.md (permisiuni token)."
  exit 1
fi
work="$(mktemp -d "$DATA/.work.XXXXXX")"
git init -q "$work/repo"
git -C "$work/repo" remote add origin "$REMOTE"
checkpoint fetch
ok=0
for attempt in 1 2 3; do
  if git_net -C "$work/repo" fetch -q --depth=1 origin "refs/heads/$BRANCH"; then ok=1; break; fi
  sleep $((attempt * ${BND_RETRY_SLEEP:-3}))
done
[ "$ok" = 1 ] || { reason="remote_indisponibil"; echo "Nu pot descărca $BRANCH; păstrez oglinda veche."; exit 1; }
mkdir "$work/new"
for f in paper.sqlite audit.jsonl; do
  git -C "$work/repo" cat-file -e "FETCH_HEAD:$f" || { reason="lipseste_$f"; echo "Lipsește $f pe $BRANCH; păstrez oglinda veche."; exit 1; }
  git -C "$work/repo" show "FETCH_HEAD:$f" > "$work/new/$f"
done
git -C "$work/repo" rev-parse FETCH_HEAD > "$work/new/COMMIT"
checkpoint before_verify
verify "$work/new" || { reason="oglinda_noua_invalida"; echo "Oglinda nouă nu trece verificarea; păstrez oglinda veche."; exit 1; }
name="$(date -u +%Y%m%dT%H%M%SZ)-$(cut -c1-7 "$work/new/COMMIT")"
mv "$work/new" "$DATA/releases/$name"                                # rename în același sistem de fișiere: atomic
checkpoint after_verify
old="$(readlink "$DATA/mirror" 2>/dev/null || true)"
ln -sfn "releases/$name" "$DATA/.mirror.tmp"
mv -T "$DATA/.mirror.tmp" "$DATA/mirror"                             # comutare atomică
checkpoint after_switch
if [ -n "$old" ] && [ "$old" != "releases/$name" ]; then
  ln -sfn "$old" "$DATA/.prev.tmp"; mv -T "$DATA/.prev.tmp" "$DATA/mirror.prev"
fi
keep_a="$(readlink "$DATA/mirror" || true)"; keep_b="$(readlink "$DATA/mirror.prev" 2>/dev/null || true)"
for dir in "$DATA"/releases/*/; do
  rel="releases/$(basename "$dir")"
  [ "$rel" = "$keep_a" ] || [ "$rel" = "$keep_b" ] || rm -rf "$dir"
done
echo "Oglindă actualizată la $(cat "$DATA/mirror/COMMIT")."
