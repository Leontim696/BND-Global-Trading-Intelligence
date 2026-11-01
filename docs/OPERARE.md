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
`arhiva-date.yml` păstrează în fiecare seară (23:45 UTC), pe ramura `date-piete`, prețurile zilnice ale celor 13 piețe ale consiliului (CSV în `zilnic/`) și ultimele cursuri (`ultimele-cursuri.json`, inclusiv EUR/USD și EUR/RON). Scop: să rămână datele cu care au decis conturile, pentru analiza de după test. Include și indicele Fear & Greed (`sentiment/fear_greed.csv`, istoric complet, zilnic) și rata de finanțare pentru cele 5 monede (`funding/<MONEDA>.csv`, la 8 ore; Binance, cu OKX ca rezervă dacă Binance e blocat). Starea fiecărei surse e în `context-status.json`. Datele sunt doar de arhivă și analiză: nu intră în decizia niciunui cont și nu se dau consiliului în timpul testului. Date on-chain: neimplementate.

## Semnale buy/sell în aplicație
Banda de sub file arată, pe orice ecran, direcția curentă a consiliului pe fiecare piață (▲ cumpără, ▼ vinde, – hold, cu numărul net de agenți). Sunt doar recomandări în umbră și poziții virtuale: aplicația nu poate da ordine.

## Top 50 cripto (inclusiv memecoin-uri)
`crypto50.py` arhivează prețurile zilnice (Binance, public) ale unei selecții statice de 50 de monede mari și lichide, 8 dintre ele memecoin-uri (DOGE, SHIB, PEPE, BONK, WIF, FLOKI, TRUMP, PENGU), în `crypto50/` pe ramura `date-piete`. Stablecoin-urile sunt excluse; XMR, KAS și HYPE lipsesc pentru că nu au piață spot publică pe Binance. Lista nu e un clasament live după capitalizare: se poate schimba în `COINS`. Fila „Top 50” din aplicație arată preț, variație pe 24h/7z/30z și semnalul simplu SMA 20/50. **Monedele nu intră în consiliul AI** (50 de piețe ar costa ~1,4 $ pe zi, față de plafonul de 0,80 $ pe zi și soldul rămas) **și nu în conturile virtuale.**

## Consiliul pe 58 de piețe (din 1.11.2026)
Consiliul votează acum pe cele 13 piețe de bază și pe încă 45 de monede din top 50 cripto (inclusiv 8 memecoin-uri). Datele vin din trei surse (Yahoo pentru ETF/forex și SOL/BNB/XRP, Binance pentru restul monedelor); o sursă căzută sau o monedă fără date nu opresc consiliul, piața e doar sărită și trecută în raport. Contextul pus fiecărei piețe vechi a rămas identic (mișcarea pe 20 de zile se arată doar pentru cele 13 piețe de bază). Costul estimat: ~1,6 $ pe zi (~0,027 $ pe piață). Plafoane: 0,60 $ pe piață, 2,50 $ pe zi, 38 $ pe lună; soldul cheii la 1.11.2026: 37,97 $ (ajunge ~20 de zile). Raportul complet cu motive (`consiliu/<zi>.md`) e mare; pentru Drive și comentariul zilnic se folosește varianta scurtă (`consiliu/<zi>-scurt.md`). Conturile virtuale nu au fost schimbate: universul lor rămâne cel de la creare.

## Soldul cheii OpenRouter, citit automat
`status.yml` citește în fiecare oră, direct de la OpenRouter, soldul real (`openrouter_balance.py`: limita cheii și creditul contului, nu consumă credit) și îl salvează în `balance.json` pe ramura `status`. Aplicația și rezumatul de dimineață îl folosesc cât timp citirea are mai puțin de 8 ore; altfel revin la estimarea din registru și o marchează „estimare". Când reîncarci creditul sau ridici plafonul cheii, soldul nou apare singur în cel mult o oră și jumătate. Soldul afișat e minimul dintre ce mai are voie cheia și ce credit mai e în cont.

Plafoanele de cost ale consiliului sunt un control separat: implicit 0,60 $ pe piață, 2,50 $ pe zi și 38 $ pe lună. Se ridică fără cod din variabilele de depozit `BND_COUNCIL_DAILY_CAP` și `BND_COUNCIL_MONTHLY_CAP` (Settings → Secrets and variables → Actions → Variables).
