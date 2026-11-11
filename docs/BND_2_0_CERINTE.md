# BND 2.0 — cerințele primite (doar documentație până pe 30.11.2026)

Implementarea începe **după 1.12.2026**, după raportul final al testului oficial (31.10–30.11).
Până atunci: nu se schimbă codul, strategiile, limitele de risc sau testul în desfășurare.

## A. Specificația „Master Technical Brief – BND 2.0” (primită pe 9.11.2026)

Rezumat:
- Obiectiv: sistem autonom în PAPER/MOCK (fără confirmare pentru fiecare tranzacție virtuală), profit net după costuri,
  randament ajustat la risc, drawdown mic. Capital real: în afara proiectului, cere autorizare separată.
- Referință externă: Day Trader Skill (Jake Schincariol) — Time Machine, Risk Manager, Entry Timer, Scanner,
  News Monitor, Earnings Analyst, Order Integrity. Se citește, nu se instalează; se verifică licența, dependențele, securitatea.
- P1: Trade Probability Engine (Monte Carlo/bootstrap pe blocuri, LONG și SHORT, toate clasele, costuri incluse,
  calibrare, fără leakage), întâi **doar în modul umbră**.
- P1: Order Integrity & Risk Gate (fingerprint pe ordin, duplicate, date proaspete, expunere după execuție,
  jurnal PASS/BLOCK) — **fără** aprobare manuală per ordin; niciun AI nu ocolește veto-ul Risk Engine.
- P2: Entry Precision (confirmare după închiderea lumânării, volum, expirarea semnalelor, 1/5/15 minute, crypto 24/7).
- P2: Scanner și Event Filter (breakout, volum neobișnuit, macro, rezultate, splituri, lichiditate).
- Consiliul de 5 AI: analiză independentă, dezbatere, opinii minoritare păstrate, fără consens forțat.
- Plan de test după 30.11: variantele A Baseline, B Probability, C Entry, D Combined, E Risk Integrity, pe aceleași date;
  walk-forward, out-of-sample, stres de costuri și regim, teste de leakage, crash/recuperare, ordine duplicate.
- Faze: 1 audit și baseline → 2 Probability Engine (umbră) → 3 Risk & Order Integrity → 4 Entry Precision →
  5 integrare → 6 paper trading extins.
- Livrabile până pe 30.11: audit Day Trader Skill, matrice de comparație, componente reutilizabile/riscante,
  arhitectura BND 2.0, specificații (Probability Engine, Entry Precision, Order Integrity), plan de implementare,
  plan de teste și criterii de acceptare, costuri și dependențe, riscuri tehnice și statistice.

## B. Cele trei funcții (primite pe 11.11.2026)

Ordinea recomandată: **News Agent → Time Machine → extinderea Chart Screener**.
Flux țintă: scanner → știri → consiliu → plan de tranzacție → Time Machine → dimensionare și verificarea finală a riscului
→ execuție paper. Orice schimbare de mărime sau plan după simulare cere reverificare; limitele deterministe au veto;
date expirate sau invalide nu pot autoriza o tranzacție. Fiecare funcție se poate dezactiva separat.

1. **Verificare înainte de module noi**: `strategies.py`, `intraday_live.py`, `universe.py`, `council_context.py`
   (azi primește prețuri, fără știri), `backtester.py`, `robustness.py`, `scenarios.py`, `signal_pipeline.py`,
   `risk_engine.py`, `paper_engine.py` (toate există pe 11.11.2026). Un singur calcul pentru costuri și risc.
2. **Chart Screener** (ref. `trader-scanner/scan.py`): breakout, trend, revenire la medie pe lumânări închise; volum,
   volatilitate, lichiditate, spread (datele lipsă marcate explicit); pentru fiecare candidat: instrument, configurație,
   direcție, interval, momentul semnalului, condiția de invalidare, scor, motive; reguli separate pe clase
   (opening-range doar pe sesiunea bursieră, crypto 24/7); spre consiliu doar o listă limitată, cu buget AI controlat.
3. **News Agent** (ref. `trader-news/news.py`; legat de punctul 3e din `DUPA_30_11.md`): SEC și comunicate pentru acțiuni,
   apoi surse pentru crypto, forex, mărfuri; sursă, URL, ora publicării și a colectării; fără duplicate; asociere corectă
   cu instrumentele; clasificare (rezultate, estimări, achiziții, investigații, incidente, suspendări, macro); faptele
   separate de interpretarea AI; conținutul extern e **date, nu instrucțiuni**; rezumat scurt cu surse și vechime;
   la surse indisponibile se raportează lipsa, nu „nimic nou”. Teste istorice doar cu ce era disponibil la decizie;
   fără arhivă → validare prin forward paper trading.
4. **Time Machine** (ref. `trader-timemachine/timemachine.py`; e același lucru cu Trade Probability Engine din A):
   bootstrap pe secvențe consecutive + configurații istorice comparabile, condiționate de volatilitate, regim, sesiune;
   costuri, spread, slippage, finanțare, gap-uri prin stop; probabilitățile țintă/stop/expirare, rezultat mediu net,
   coada pierderilor; numărul simulărilor separat de numărul observațiilor distincte; „date insuficiente” când e cazul;
   configurația, versiunea datelor și seed-ul salvate; calibrare în afara datelor de construire. Nu se copiază ipotezele
   originale (sesiunea SUA, istoric scurt, pierdere exact la stop). Coordonat cu Synthetic Twin și Adversarial Simulator.
5. **Validare**: ipoteze, praguri și criterii de succes scrise înainte de test; baza comparată cu fiecare funcție separat,
   apoi cu combinația; profit net, drawdown, risc, costuri, latență, consum AI, oportunități respinse; teste de
   look-ahead, întreruperi de surse, gap-uri, reproductibilitate. O funcție se promovează doar cu câștig susținut
   în afara datelor de dezvoltare. La cod extern: licența versiunii preluate și atribuirea.
