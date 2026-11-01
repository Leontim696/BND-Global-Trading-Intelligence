# Smart-Money Graph, pasul 1 (colector, Solana)

Colector read-only pentru walleturi de meme-coinuri. **Nu ia decizii, nu atinge conturile, nu intră în consiliu.** Rulează zilnic (06:50 UTC = 07:50 ora ta) și salvează istoricul pe ramura `smart-money` (`wallete.csv`, `status.json`).

## Ce intră în listă
1. **Automat:** clasamentul Solana Tracker, dacă există secretul `SOLANATRACKER_API_KEY`.
2. **Manual:** adresele tale din `smart_money/wallete.json` (le adaugi oricând; adresele invalide se ignoră).

## Filtre (în `src/bnd/smart_money.py`)
Cel puțin 8 monede, 50 de tranzacții, rată de succes 40%, cumpărătură medie ≤ 2.000 $, profit realizat ≥ 20.000 $, ROI ≥ 200%, ținere ≥ 5 minute (nu bot), vechime ≥ 90 de zile. Un câmp lipsă nu penalizează, dar rândul nu trece fără datele de bază.

## Eticheta `tipar_insider`
Cel puțin jumătate dintre cumpărături în primele minute de la lansare, pe cel puțin 5 monede. Este un **tipar de comportament**, nu o dovadă de informații interne (poate fi și sniper sau bot). Se urmărește pentru că intrările timpurii repetate anunță mișcări.

## Limite
- Sursa și numele câmpurilor n-au putut fi verificate din sandbox: prima rulare cu cheie arată în `status.json` ce a răspuns API-ul; ajustez după asta.
- Câștigători în urmă ≠ câștigători în viitor (supraviețuire, boturi, norocoși). Nu se promovează nimic într-un cont fără dovadă înainte în timp, în registrul de experimente.
- Pașii următori (după 17.11): legarea tranzacțiilor walleturilor de mișcările monedelor, ca experiment înregistrat.

## Ce ai de făcut tu, când vrei
- Cheie gratuită Solana Tracker → secret `SOLANATRACKER_API_KEY` în depozit; și/sau adrese în `smart_money/wallete.json`.


## Validat, candidat, date insuficiente (audit 01.11)
Descoperirea (`smart_money_discovery.py`) pornește de la un singur câștig mare pe o monedă în trend; asta **nu** dovedește nimic. Fiecare wallet din `descoperite.csv` are coloana `status`:
- **validat**: istoricul complet (`/pnl`) trece TOATE filtrele (monede, tranzacții, rată de succes, profit realizat, ROI, ținere, vârstă unde sunt cunoscute).
- **candidat**: a câștigat mult pe o monedă, dar istoricul complet nu trece filtrele. Se urmărește doar înainte în timp (cele 4 walleturi din `smart_money/wallete.json` sunt candidate, nu validate: au 1–17 monede și 1–16 tranzacții, sub minimul de 8 monede și 50 de tranzacții).
- **date_insuficiente**: istoricul nu s-a putut citi sau lipsesc câmpuri esențiale; nu se judecă și nu se numește validat.
Rândurile mai vechi (fără coloană) au statusul gol = necunoscut.

**Nu se atribuie „insider” din descoperire.** `first-buyers` nu spune cât de devreme față de lansare a cumpărat walletul. Din ≥3 monede câștigate ca prim cumpărător iese doar `indiciu_intrare_timpurie`. Eticheta `tipar_insider` apare numai în colectorul zilnic, când datele din API arată că cel puțin jumătate din cumpărături sunt în primele minute pe cel puțin 3 monede; și atunci e un tipar statistic, nu o dovadă.

**Limite API:** 429 așteaptă `Retry-After` (maximum 30 s) cu 3 încercări; după 5 erori consecutive rularea se oprește ca să nu epuizeze limita. Rezultatul rulării: `ok`, `partial` (cod 0, cu avertisment), `failed` (cod 2, workflow roșu) sau cheie lipsă (cod 3). Workflow-ul salvează oricum `descoperire.json`, iar verdictul final reflectă rezultatul colectării, separat de publicare.
