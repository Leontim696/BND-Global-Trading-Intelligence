# Operare: monitorizare, alerte, backup, recuperare

## Monitorizare
- **Aplicația de pe telefon** (artifact privat, reîmprospătat din oră în oră): conturi, poziții, comenzi, drawdown, costuri, starea celor cinci agenți, alerte.
- **`status.json`** pe ramura `status` (workflow `status.yml`, la :35 în fiecare oră): același conținut, plat, pentru senzori. Home Assistant (depozitul e privat, deci cu un token GitHub cu drept de citire pe conținut):
  ```yaml
  rest:
    - resource: https://api.github.com/repos/Leontim696/BND-Global-Trading-Intelligence/contents/status.json?ref=status
      headers:
        Authorization: "Bearer <TOKEN_DE_CITIRE>"
        Accept: application/vnd.github.raw+json
      scan_interval: 1800
      sensor:
        - name: BND AI unificat
          value_template: "{{ value_json.accounts.ai.equity }}"
          unit_of_measurement: "USD"
          json_attributes_path: "$.accounts.ai"
          json_attributes: [return_pct, drawdown_pct, positions, orders, kill_switch, reconciled]
        - name: BND alerte
          value_template: "{{ value_json.alerts | length }}"
        - name: BND sold cheie AI
          value_template: "{{ value_json.ai_balance_usd }}"
          unit_of_measurement: "USD"
  ```
  Tokenul trebuie tratat ca o parolă (doar citire, un singur depozit). Aplicația e doar vizualizare.
- **Ce se verifică automat:** oprire de siguranță, rulare mai veche de 36 h, discrepanță contabilă (reconciliere independentă), prețuri mai vechi de 6 h, agent AI eșuat în ultima rundă, rulare programată eșuată, sold al cheii AI sub 2 $.

## Alerte
`alerting.py` trimite pe telefon (ntfy) doar alertele noi; aceeași alertă nu se repetă 12 ore, una rezolvată poate reapărea. Fără secretul `NTFY_TOPIC` nu se trimite nimic.

## Costuri și limite
Limitele din cod (plafon pe rundă, zilnic, lunar, buget pe scop) și limita cheii OpenRouter sunt **mecanisme de control**, nu garanții de facturare: furnizorul rămâne sursa de adevăr pentru ce se plătește. Registrul intern folosește costul facturat de furnizor, când e raportat.

## Backup și recuperare
1. Backup zilnic: `deploy/backup.sh` (copie consistentă SQLite + jurnalul de audit, 30 de copii).
2. Verificarea unei copii: `python -m src.bnd.restore_check --backup-dir /var/backups/bnd` (integritate SQLite, reconciliere, lanț de audit); cod 0 = restaurabil. De rulat săptămânal.
3. Restaurare: copiezi `paper_<marcaj>.sqlite` ca `paper.sqlite` în folderul de stare, apoi `python -m src.bnd.reconcile --state paper.sqlite`. Zilele ratate se recuperează automat la următoarea rulare (runnerul procesează lumânările lipsă, în ordine).
4. Pe GitHub, starea fiecărui cont e și istoric de commit-uri pe ramura lui (`paper-trading`, `crypto-trading`, `ai-unificat`): se poate reveni la orice stare anterioară.
5. Configurația: setările contului sunt înghețate în jurnalul lui (`runner_settings`), iar workflow-urile și codul sunt versionate în git. Detalii pentru Proxmox în `docs/PROXMOX.md`.

## Rezumat de dimineață
`dimineata.yml` trimite în fiecare zi la 05:05 ora Germaniei (04:05 UTC iarna) o notificare cu: cursul EUR/USD, valoarea fiecărui cont (și echivalentul în euro), ce s-a executat peste noapte, ce a votat consiliul, agenții cu eșecuri, alertele, costul AI și soldul cheii, apoi planurile zilei (rulările programate în ora Germaniei și evenimentele importante, de exemplu comparația din 6.11). Se oprește singur după 17.11.2026. Test manual: Actions → „Rezumat de dimineață” → Run workflow.

## Arhiva de date
`arhiva-date.yml` păstrează în fiecare seară (23:45 UTC), pe ramura `date-piete`, prețurile zilnice ale celor 13 piețe ale consiliului (CSV în `zilnic/`) și ultimele cursuri (`ultimele-cursuri.json`, inclusiv EUR/USD și EUR/RON). Scop: să rămână datele cu care au decis conturile, pentru analiza de după test. Nu include încă rata de finanțare (funding), indicele Fear & Greed sau date on-chain: se pot adăuga separat.
