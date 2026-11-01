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
- Dependențe: `python3` ≥ 3.11 și `git` (modulele BND folosesc doar biblioteca standard; `requirements.txt` e doar pentru teste).
- Fără Docker obligatoriu. Dacă totuși îl folosești într-un LXC neprivilegiat: activează `nesting=1,keyctl=1` pe container; volumele montate sunt „mapate” (uid-ul din container = 100000 + uid) și trebuie să aparțină utilizatorului `bnd` (uid 10001 în imagine). `docker build -f deploy/Dockerfile.observer -t bnd-observer .` și `-v /srv/bnd-observer:/data`.
- Rețea: doar ieșire HTTPS către github.com. Fără port expus public. `bnd-observer-http.service` ascultă pe 127.0.0.1:8765 și servește doar `status.json`; expune-l către Home Assistant prin LAN/VPN (WireGuard/Tailscale) sau un proxy, cu regulă de firewall care permite doar IP-ul HA.
- Token (doar dacă repo-ul rămâne privat): fine-grained, **Contents: Read** pe acest repo, în `/etc/bnd-observer/github-read-token` (root, chmod 600). Nu pune tokenuri în issue/chat. Nu cere și nu stoca chei de broker.

## Instalare (o faci tu, ca root în LXC; nimic nu rulează automat)
```bash
apt update && apt install -y python3 git
git clone https://github.com/Leontim696/BND-Global-Trading-Intelligence.git /root/bnd && cd /root/bnd
bash deploy/observer/install.sh --dry-run     # arată pașii, nu modifică nimic
bash deploy/observer/install.sh               # idempotent; activează DOAR bnd-observer.timer
```
Verificare:
```bash
systemctl list-timers bnd-observer.timer
journalctl -u bnd-observer -n 30
bash /opt/bnd-observer/deploy/observer/healthcheck.sh && cat /var/lib/bnd-observer/public/status.json
```

## Health checks
`healthcheck.sh` cere `status.json` mai nou de 2 ore, `ok=true`, `verdict=ok`, `observer_only=true`. Verdicte: `ok` · `stale` (ultima rulare zilnică > 36 h — GitHub nu a publicat) · `integrity` (SQLite/audit stricat) · `missing`. Pentru Home Assistant: senzor REST pe `http://<lxc>:8765/status.json` (câmpuri: `verdict`, `last_run.equity`, `last_run.age_hours`, `kill_switch`, `open_positions`). Imaginea Docker are `HEALTHCHECK` echivalent. Repornirea după o întrerupere: `Persistent=true` și `OnBootSec=2min` refac oglinda la pornire.

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
