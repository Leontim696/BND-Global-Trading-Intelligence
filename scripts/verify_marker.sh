#!/usr/bin/env bash
# Verifică VALID.json față de fișierele descărcate. Rulat în jobul de publicare: fără cod de proiect.
#   verify_marker.sh DIRECTOR   -> exit 0 doar dacă toate hash-urile coincid
set -euo pipefail
dir="${1:-state}"
marker="$dir/VALID.json"
[ -f "$marker" ] || { echo "::error::Lipsește VALID.json: starea nu a trecut de punctul de control."; exit 1; }
for name in paper.sqlite audit.jsonl last_run.json; do
  want="$(sed -n "s/.*\"$name\": \"\([0-9a-f]\{64\}\)\".*/\1/p" "$marker" | head -n1)"
  [ -n "$want" ] || { echo "::error::VALID.json nu conține hash pentru $name."; exit 1; }
  [ -f "$dir/$name" ] || { echo "::error::Lipsește $name."; exit 1; }
  have="$(sha256sum "$dir/$name" | cut -d' ' -f1)"
  [ "$want" = "$have" ] || { echo "::error::$name nu corespunde punctului de control (hash diferit)."; exit 1; }
done
echo "Punct de control verificat."
