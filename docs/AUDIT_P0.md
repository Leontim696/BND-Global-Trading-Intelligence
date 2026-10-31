# Audit P0 (31.10.2026) — constatări, severitate, dovezi

Stare: în lucru. Fiecare constatare are un identificator (F-nn), severitate (CRITIC / RIDICAT / MEDIU / SCĂZUT / INFO), dovada și starea. „Reparat” înseamnă reparat și testat; „Deschis” înseamnă necesită decizie sau lucru ulterior. Evaluarea activă de 16 zile nu a fost modificată: nicio strategie, parametru, alocare sau regulă de decizie.

## A1. Arhitectură

Matricea completă e în `docs/MATRICE_INTEGRARE.md` (generată din cod de `scripts/arch_audit.py`).

| ID | Sev. | Constatare | Dovadă | Stare |
|---|---|---|---|---|
| F-01 | MEDIU | 14 din 65 de module nu sunt apelate de nimic în producție (doar teste): `funding`, `instruments`, `intraday`, `rolls`, `compare_wfo`, `cost_report`, `paper_demo` sunt utilitare manuale de cercetare; `council_round`, `live_council_bridge`, `ai_smoke_test`, `code_review_loop`, `review_budget` sunt trasee vechi de audit/AI; `orchestrator` și `local_ai` sunt construite, dar neconectate la consiliu. | `docs/MATRICE_INTEGRARE.md` | Deschis (nu se șterge nimic în timpul testului; decizie după 17.11) |
| F-02 | RIDICAT | Protecția motorului împotriva LIVE (`PaperEngine.require_mode`) nu era apelată din niciun loc: singura barieră reală era `trading_mode()` din `paper_runner`. Orice alt punct de intrare care ar fi deschis un cont virtual nu verifica modul. | `grep require_mode` → doar definiția | **Reparat**: constructorul `PaperEngine` apelează acum `trading_mode()`; testat cu 12 valori greșite |
| F-03 | MEDIU | Mai multe module pentru aceeași idee de „rundă de consiliu”: `council_round` (vechi), `council_runner` (folosit), `council_orchestrator`, `live_council_bridge`. Risc de confuzie la întreținere. | matrice | Deschis |
| F-04 | MEDIU | O singură sursă de prețuri pentru ETF/forex/crypto (Yahoo, fără cheie). Dacă își schimbă formatul sau ne blochează, toate conturile rămân fără date. Datele lipsă sunt detectate (`missing_data`, alertă de 36 h), dar nu există sursă de rezervă. | `market_data.py`, `report_card.py` | Deschis (limitare cunoscută) |
| F-05 | MEDIU | Aplicația de pe telefon și rapoartele din Drive depind de o rutină care rulează în sesiunea de lucru, nu de un serviciu independent. Dacă sesiunea cade, aplicația nu se mai reîmprospătează (conturile și consiliul continuă pe GitHub). | rutinele programate | Deschis (se atenuează prin banner de date vechi: există, 36 h) |

## A2. Izolare paper-only

Testele negative sunt în `tests/test_paper_only.py` (34 de teste): valori greșite pentru `BND_TRADING_MODE` (inclusiv litere mici, spații, `PAPER;LIVE`), refuzul motorului și al runnerului fără să creeze cont, absența oricărui client de broker/exchange, absența oricărui endpoint de ordine sau retragere, lista de gazde de rețea permise, workflow-urile care nu pot seta un mod LIVE și `BND_ALLOW_LIVE_AI=false` în workflow-urile de tranzacționare.

| ID | Sev. | Constatare | Stare |
|---|---|---|---|
| F-06 | INFO | Nicio cale din cod nu poate trimite ordine reale: nu există client de broker, endpoint de ordine sau de retragere; singurele gazde externe sunt date (Yahoo, Binance public), AI (OpenRouter), notificări (ntfy) și GitHub. | Verificat prin test |
| F-07 | INFO | Cuvântul „live” apare și în „consiliu AI live” (apeluri AI plătite). E altă axă decât tranzacționarea: nu atinge `BND_TRADING_MODE`. Confuzia de nume rămâne un risc de citire. | Documentat |
