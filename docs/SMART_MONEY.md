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
