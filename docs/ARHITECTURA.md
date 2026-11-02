# Arhitectura BND (stare 31.10.2026)

Doar bani virtuali. Matricea completă modul cu modul: `docs/MATRICE_INTEGRARE.md`. Constatări de audit: `docs/AUDIT_P0.md`. Operare: `docs/OPERARE.md`. Maturitate: `docs/MATURITATE.md`.

## Fluxul de date

```
Yahoo (zilnic, public)  ──►  CSV de lumânări (cache în Actions)
        │                          │
        │                          ├─►  consiliul AI (5 agenți, OpenRouter, plătit, în umbră)  ─►  registry.sqlite + costs.sqlite  (ramura consiliu-umbra)
        │                          │                                   │ voturi
        │                          │                                   ▼
        │                          │                         crypto_signals (voturi → semnale)
        │                          ▼                                   │
        │                paper_runner (strategie sau semnale)  ◄───────┘
        │                          │  ordine virtuale la deschiderea următoare
        │                          ▼
        │                   PaperEngine (SQLite): risc, stop, marjă, finanțare, kill switch
        │                          │
        └─ prețuri de acum ─►  rapoarte orare / status.json / aplicația de pe telefon / alerte
```

## Conturi (un singur cont activ din 1.11.2026: `cont-unic`; cele patru vechi sunt arhivă, vezi `docs/CONTURI.md`)
| Cont | Ramură | Decide | Workflow | Ora (UTC) |
|---|---|---|---|---|
| **Cont unic** (activ) | `cont-unic` | jumătate `regime_switch`, jumătate voturile consiliului (hibrid), long și short | `cont-unic.yml` | 22:25 |
| Reguli (arhivă, oprit) | `paper-trading` | strategia `regime_switch` | `paper-trading.yml` | – |
| Cripto AI (arhivă, oprit) | `crypto-trading` | voturile consiliului, 5 monede | `cripto-ai.yml` | – |
| AI unificat (arhivă, oprit) | `ai-unificat` | voturile consiliului, 13 piețe | `bot-ai-unificat.yml` | – |
| Reguli long/short (arhivă, oprit) | `reguli-ls` | reguli cu short și leverage | `reguli-ls.yml` | – |

Publicarea contului unic trece de un punct de control (`state_check.py`): SQLite valid, lanț de audit continuat, istoric care nu se micșorează, capital neschimbat; `VALID.json` cu hash-uri se verifică în jobul de publicare (fără cod de proiect). Ultima stare validă rămâne în istoricul ramurii.
Consiliul: `consiliu-umbra.yml`, 21:40 UTC (plătit, plafoane implicite în workflow: 0,60 $ pe rundă, 3,00 $ pe zi, 38 $ pe lună, ajustabile din variabilele `BND_COUNCIL_DAILY_CAP` / `BND_COUNCIL_MONTHLY_CAP`; soldul real al cheii se citește de la OpenRouter).

## Straturi și reguli de siguranță
1. **Mod:** `safety.trading_mode()` acceptă doar MOCK/PAPER; motorul îl verifică la fiecare deschidere de cont. Nu există cod de broker.
2. **Risc (în motor):** limită pe poziție, sector, monedă, volatilitatea portofoliului, leverage brut, risc pe tranzacție, pierdere zilnică și drawdown cu oprire de siguranță (kill switch), marjă ESMA cu lichidare la 50%, date vechi sau gap mare = fără risc nou.
3. **Idempotență:** id de ordin = `<dată>:<piață>`; tranzacții SQLite `BEGIN IMMEDIATE`; jurnal de audit cu lanț de hash și blocare pe fișier.
4. **Joburi de publicare separate:** jetonul cu drept de scriere nu rulează cod de proiect.
5. **Costuri AI:** poartă de confirmare (`RUN-PAID-TEST`), comutator `BND_COUNCIL_DAILY`, dată de final 16.11.2026, buget pe scop, plafoane în cod.

## Configurații
Setările unui cont sunt înghețate la creare (jurnalul `runner_settings`); nu se pot schimba fără cont nou. Variabile: `BND_TRADING_MODE` (PAPER), `BND_ALLOW_LIVE_AI` (true doar în consiliu), `BND_MODEL_*` (modele), `BND_COUNCIL_DAILY` (on), secretele `OPENROUTER_API_KEY` și `NTFY_TOPIC`.

## Instalare locală / depanare
- Teste: `python -m pytest -q` (doar `pytest`; restul e bibliotecă standard).
- Un pas: `python -m src.bnd.paper_runner --state paper.sqlite --data-dir data ...` (vezi `--help`).
- Reconciliere: `python -m src.bnd.reconcile --state paper.sqlite`; jurnal: `python -m src.bnd.audit_log verify audit.jsonl`.
- Cont oprit (kill switch): cauza e în raport; repornire doar manual cu `RESET-KILL-SWITCH`.
- Rulare ratată: următoarea rulare procesează zilele lipsă în ordine.
- Date lipsă pe o piață: apare în `missing_data`; piața nu primește ordine noi.
- Recuperare și backup: `docs/OPERARE.md`, `docs/PROXMOX.md`.

## Performanță (măsurat pe date sintetice, un nucleu)
Pas zilnic al unui cont: 23 de piețe × 1100 de zile cu `regime_switch` = 0,3–0,4 s și ~45 MB RAM; cont AI cu semnale externe, 13 piețe: 0,1–0,2 s; fișierul contului < 1 MB. Blocajele reale: descărcarea prețurilor de la Yahoo (zeci de secunde), latența agenților AI (zeci de secunde per piață; runda de 10 piețe a durat ~2 minute) și coada GitHub Actions. CPU, RAM și stocarea nu sunt blocaje: un LXC cu 1 CPU și 512 MB ajunge. Nu s-au făcut optimizări.

## Limite cunoscute
Vezi `docs/AUDIT_P0.md` (F-04 o singură sursă de prețuri, F-08 cont etichetat EUR fără conversie, F-12 spread și slippage unite, F-05 aplicația depinde de o rutină). Niciun avantaj de tranzacționare nu e dovedit; testul de 16 zile abia a început.
