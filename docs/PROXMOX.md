# Mutare pe Proxmox (opțional)

Acum botul rulează gratuit pe GitHub Actions (starea e pe ramura `paper-trading`). Mutarea pe un server propriu nu e necesară; fișierele din `deploy/` o fac posibilă.

1. Container LXC Debian (1 CPU, 512 MB), `apt install python3 sqlite3 git`.
2. `useradd -r bnd`, clonează repo-ul în `/opt/bnd`.
3. Copiază contul curent: `git show origin/paper-trading:paper.sqlite > /var/lib/bnd/paper.sqlite` (la fel `audit.jsonl`), proprietar `bnd`. **Nu rula în paralel cu GitHub** (dezactivează întâi workflow-ul „Bot virtual zilnic”), altfel contul se dublează.
4. `cp deploy/bnd-paper.* /etc/systemd/system/ && systemctl enable --now bnd-paper.timer`.
5. Backup: cron zilnic `deploy/backup.sh` (păstrează 30 de copii; copiază periodic și în afara serverului).
6. Verificare: `systemctl list-timers`, `journalctl -u bnd-paper`, `/var/lib/bnd/REPORT.md`.
7. Alternativ Docker: `docker build -f deploy/Dockerfile -t bnd .` și `-v /srv/bnd:/data`.

Mereu doar PAPER: `safety.py` refuză LIVE. Repornire: timerul are `Persistent=true`, deci o zi ratată se recuperează la pornire (runnerul procesează zilele lipsă în ordine). Consiliul AI plătit rămâne pe GitHub (cheia nu se mută pe server fără decizia ta).
