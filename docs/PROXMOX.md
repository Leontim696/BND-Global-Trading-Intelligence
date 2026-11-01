# Proxmox: instanță observer-only (etapa A) — issue [#196](../../../issues/196)

**Stare:** pregătire. Nu s-a instalat nimic pe Proxmox. Evaluarea oficială de 16 zile rămâne EXCLUSIV pe GitHub Actions.

## Arhitectura actuală (1.11.2026)
- Contul oficial e **un singur cont virtual „hibrid”**, pe ramura `cont-unic` (`paper.sqlite` + `audit.jsonl` + `runs/`), actualizat de workflow-ul `cont-unic.yml` (22:25 UTC). Publicarea se face doar după un punct de control (`src/bnd/state_check.py`).
- Consiliul AI plătit rulează pe GitHub (`consiliu-umbra.yml`); cheile NU se mută pe server.
- Ramurile `paper-trading`, `crypto-trading`, `ai-unificat`, `reguli-ls` sunt conturile vechi, oprite. `deploy/bnd-paper.*` (runnerul clasic) NU face parte din etapa A.

## Ce face instanța observer
Oglindește READ-ONLY ramura `cont-unic` (un commit întreg, nu un fișier scris la mijloc), verifică oglinda (integritate SQLite, lanț de audit) și scrie `public/status.json` pentru Home Assistant. **Nu** are runner de tranzacționare, timer de tranzacționare, chei de broker sau AI, și nu scrie nimic pe GitHub.

Garanții (testate în `tests/test_observer.py`):
- `BND_OBSERVER_ONLY=true` face ca `PaperEngine` și `paper_runner` să refuze (cod 2, fără fișiere create); `observer.py` refuză să pornească fără acest flag.
- SQLite se deschide `mode=ro`; `status.json` nu conține SQLite și se scrie atomic.
- Lacăt pe oglindă: a doua instanță e refuzată. `install.sh` refuză dacă `bnd-paper.timer` e activ; `bnd-observer.service` are `Conflicts=` cu el.
- O oglindă nouă stricată sau un remote căzut NU înlocuiesc oglinda bună; cea veche rămâne ca `mirror.prev` (rollback).

## Resurse și LXC neprivilegiat
- Debian 12/13, **neprivilegiat** (implicit în Proxmox), 1–2 vCPU, 512 MB–1 GB RAM, 5–10 GB disc (oglinda e de ordinul MB). Valorile se rafinează după măsurători; serviciul are `MemoryMax=512M`.
- Dependențe: `python3` ≥ 3.11 și `git` ≥ 2.31 (autentificarea trece prin variabile de mediu `GIT_CONFIG_*`); modulele BND folosesc doar biblioteca standard.
- Fără Docker obligatoriu. Dacă totuși îl folosești într-un LXC neprivilegiat: `nesting=1,keyctl=1`; volumele sunt „mapate” (uid din container = 100000 + uid) și trebuie să aparțină utilizatorului `bnd` (uid 10001). `docker build -f deploy/Dockerfile.observer -t bnd-observer .` și `-v /srv/bnd-observer:/data`.
- Rețea: doar ieșire HTTPS către github.com. Niciun port expus public.

## Repository privat: bootstrap sigur și token de citire
Regula: **tokenul nu apare niciodată** în URL, în argumentele unei comenzi (se văd cu `ps`), în `~/.gitconfig`, în `.git/config` sau în istoricul shell. Scripturile din `deploy/observer/` respectă asta (`gitauth.sh` îl trimite lui git prin variabile de mediu, doar pentru acel proces).

1. **Creează tokenul** pe GitHub (Settings → Developer settings → Fine-grained tokens): repo selectat = doar acest repo, permisiune **Contents: Read** (nimic altceva), expirare scurtă (30–90 de zile). Nu folosi tokenuri clasice `ghp_...`.
2. **Salvează-l** pe LXC, ca root: `sudo bash deploy/observer/set-token.sh` (te întreabă tokenul fără ecou sau îl citește de pe stdin; nu primește argumente, deci nu intră în istoric). Fișierul `/etc/bnd-observer/github-read-token` devine `root:bnd-observer`, mod `0640`.
   - **Important:** serviciul rulează ca `bnd-observer`. Dacă fișierul ar fi `root:root 0600`, serviciul nu l-ar putea citi; `sync.sh` nu mai continuă pe tăcute fără autentificare, ci eșuează cu `sync_error = token_ilizibil` și mesaj clar.
3. **Clonează repo-ul** fără token în URL: `sudo bash deploy/observer/bootstrap.sh /root/bnd` (după ce ai copiat scriptul sau ai pus doar `deploy/observer/` pe server). Alternativa fără niciun token pe server: pe calculatorul tău `git archive --format=tar.gz -o bnd.tgz HEAD src deploy`, apoi `scp bnd.tgz` și dezarhivare în `/root/bnd`.
4. **Verifică** (nu afișează tokenul): `sudo bash deploy/observer/check-token.sh`. Controlează: permisiunile fișierului (nu e citibil de „alții”), că utilizatorul `bnd-observer` îl poate citi, tipul tokenului (avertizează la token clasic), că citirea ramurii `cont-unic` funcționează (doar `ls-remote`) și că tokenul nu a rămas în `~/.bash_history` (dacă a rămas: șterge linia și **revocă** tokenul).
5. **Activează-l** în `/etc/bnd-observer/env`: decomentează `BND_TOKEN_FILE=/etc/bnd-observer/github-read-token`.
6. **Rotire / revocare:** repetă pasul 2 cu un token nou, rulează `check-token.sh`, revocă-l pe cel vechi pe GitHub.

## Instalare (o faci tu, ca root în LXC; nimic nu rulează automat)
```bash
apt update && apt install -y python3 git
bash deploy/observer/install.sh --dry-run     # arată pașii, nu modifică nimic
bash deploy/observer/install.sh               # idempotent; activează DOAR bnd-observer.timer
```
Verificare:
```bash
systemctl list-timers bnd-observer.timer
journalctl -u bnd-observer -n 30
bash /opt/bnd-observer/deploy/observer/healthcheck.sh && cat /var/lib/bnd-observer/public/status.json
```

## Home Assistant: serviciul HTTP (instalat, dar NEPORNIT implicit)
`bnd-observer-http.service` servește doar `public/status.json` (fără SQLite) și **nu are autentificare**. `install.sh` îl instalează fără să-l pornească; îl activezi explicit cu `bash deploy/observer/install.sh --with-http`. Implicit ascultă pe `127.0.0.1:8765` (`BND_HTTP_BIND` din `/etc/bnd-observer/env`). `http-bind-check.sh` (ExecStartPre) refuză `0.0.0.0`, `::` și valoarea goală în orice situație; o adresă non-loopback cere în plus `BND_HTTP_ALLOW_NON_LOOPBACK=yes`. Metode de acces pentru Home Assistant, în ordinea preferinței:
1. **VPN (WireGuard/Tailscale):** leagă `BND_HTTP_BIND` de adresa interfeței VPN (ex. `10.8.0.2`), setează `BND_HTTP_ALLOW_NON_LOOPBACK=yes` și permite portul 8765 doar de la IP-ul Home Assistant din VPN (firewall). Senzor REST: `http://10.8.0.2:8765/status.json`.
2. **Proxy cu TLS și autentificare:** serviciul rămâne pe 127.0.0.1; `nginx` pe LXC publică doar `/status.json` în LAN, cu `allow <IP-HA>; deny all;` și `auth_basic` (sau mTLS). Exemplu: `location = /status.json { allow 192.168.1.50; deny all; auth_basic "bnd"; auth_basic_user_file /etc/nginx/bnd.htpasswd; proxy_pass http://127.0.0.1:8765; }`.
3. **Tunel SSH** de pe mașina Home Assistant: `ssh -N -L 8765:127.0.0.1:8765 user@lxc` (cheie dedicată, fără shell).
Nu expune portul pe internet. Câmpuri utile pentru senzor: `ok`, `verdict`, `data_ok`, `sync_ok`, `last_successful_sync`, `mirror_commit`, `last_run.equity`, `last_run.age_hours`, `kill_switch`.

## Health checks: date ≠ sincronizare
`status.json` separă două sănătăți:
- **date** (`data_ok`, `verdict` ∈ ok / stale / integrity / missing): oglinda are SQLite valid, lanț de audit corect, ultima rulare zilnică sub 36 h.
- **sincronizare** (`sync_ok`, `last_successful_sync`, `mirror_commit`, `sync_error`, `consecutive_failures`): `sync.sh` scrie `sync.json` la FIECARE încercare, inclusiv la eșec (`remote_indisponibil`, `token_ilizibil`, `lipseste_<fișier>`, `oglinda_noua_invalida`). La eșec păstrează `last_successful_sync` și `mirror_commit` ale ultimei reușite. Dacă ultima reușită e mai veche de 3 ore, `sync_ok` devine false.
Un eșec GitHub dă `verdict = sync_failed`, `ok = false` și cod de ieșire 7 (unitatea systemd apare ca eșuată), chiar dacă datele din oglindă sunt încă valide. `healthcheck.sh` cere `data_ok`, `sync_ok`, `ok` și `status.json` mai nou de 2 ore. Pentru Home Assistant: alertă pe `ok != true` și, separat, pe `sync_ok != true`. Imaginea Docker are `HEALTHCHECK` echivalent. După o întrerupere: `Persistent=true` și `OnBootSec=2min` refac oglinda.

## Backup / restore (etapa A: oglinda se poate reface oricând din GitHub)
- Oglinda e **dispensabilă**: ștergi `/var/lib/bnd-observer/mirror` și rulezi serviciul.
- Pentru copiile consistente SQLite (necesare în etapa C): `deploy/backup.sh` (SQLite `.backup` + audit, 30 de copii) + copie externă periodică. **Test de restaurare:** `bash deploy/observer/verify-backup.sh` restaurează cea mai nouă copie într-un folder temporar și verifică integritatea și lanțul de audit, fără să atingă contul.

## Rollback
1. `systemctl disable --now bnd-observer.timer bnd-observer-http.service`
2. (opțional) `rm -rf /opt/bnd-observer /etc/bnd-observer /var/lib/bnd-observer /etc/systemd/system/bnd-observer*` și `systemctl daemon-reload`.
3. Mergi înapoi la o oglindă veche: `mv mirror mirror.bad && mv mirror.prev mirror`.
Contul oficial nu e afectat în niciun pas, pentru că observerul nu îl scrie.

## Etapa B — instalarea pe Proxmox
Necesită accesul tău la interfața Proxmox/SSH. Nu cer parole sau tokenuri în chat sau issue. Se instalează doar observerul; se validează consumul și monitorizarea.

## Etapa C — mutarea runnerului oficial (NUMAI după o decizie separată, după 17.11)
Condiții: evaluarea încheiată și validă; workflow-urile `cont-unic.yml` și consiliul oprite și verificate oprite; backup consistent + checksum + reconciliere; **exact o instanță** de runner; test de idempotență și rollback; LIVE rămâne dezactivat. Fișierele rămân pregătite dar neactivate: `deploy/bnd-paper.service`, `deploy/bnd-paper.timer`, `deploy/Dockerfile.runner`. Dacă se ajunge aici, pașii vechi (cont copiat de pe ramură, timer) se rescriu pentru `cont-unic`; `Persistent=true` recuperează zilele ratate. Consiliul AI plătit rămâne pe GitHub.
