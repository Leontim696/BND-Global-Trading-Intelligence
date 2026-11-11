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

## C. Bot autonom: mandat, portofoliu, broker (primită pe 11.11.2026)

Obiectiv: un bot care analizează oportunitățile, alocă bugetul și gestionează tranzacțiile autonom, **în limitele stabilite
de proprietar**. Implementarea începe după 1.12.2026. Trecerea la bani reali se face **după validarea componentelor**, nu la
o dată fixă; brokerul/exchange-ul și capitalul real nu sunt stabilite — nu se presupun valori și nu se activează nimic real
fără mandat explicit.

1. **Audit al componentelor** (implementat / parțial / absent; existența unui modul nu dovedește că e legat în flux):
   `strategies.py`, `intraday_live.py`, `universe.py`, `council_context.py`, `signal_pipeline.py`, `trade_coordinator.py`,
   `portfolio.py`, `exposure.py`, `risk_engine.py`, `backtester.py`, `robustness.py`, `scenarios.py`, `paper_engine.py`,
   `reconcile.py`, `audit_log.py`, `safety.py` (azi permite doar MOCK/PAPER). Toate există pe 11.11.2026.
2. **Mandat explicit, versionat**: conturi și capital, piețe/instrumente/tipuri de ordine permise, long/short/leverage,
   limite pe tranzacție, instrument, sector, clasă și portofoliu, pierdere zilnică și drawdown maxim, rezervă de lichiditate,
   condiții de oprire și reluare. În interiorul mandatului botul decide singur; majorarea limitelor, capitalul suplimentar și
   activarea modului real sunt decizii ale proprietarului; AI-ul nu își poate modifica mandatul.
3. **Chart Screener** (ref. `trader-scanner/scan.py`) — ca la B.2.
4. **News Agent** (ref. `trader-news/news.py`) — ca la B.3, plus marcarea informațiilor lipsă, contradictorii sau expirate.
5. **Time Machine** (ref. `trader-timemachine/timemachine.py`) — ca la B.4.
6. **Administrator de portofoliu**: compară oportunitățile cu pozițiile existente; decide ce e eligibil, ce se păstrează,
   reduce sau închide, unde merge capitalul nou, cât numerar rămâne și dacă realocarea merită costurile; „nu tranzacționez”
   e o decizie validă; praguri de realocare și intervale de reevaluare fixate dinainte (fără tranzacționare excesivă).
7. **Alocator și dimensionare**: AI-ul propune ponderi și priorități; motorul determinist calculează cantitățile și aplică
   limitele, ținând cont de avantajul net și incertitudinea lui, distanța la stop și riscul de execuție peste stop,
   volatilitate, lichiditate, spread, corelații, marjă, finanțare, pierderi recente și bugetul de risc rămas.
   Încrederea declarată de AI nu mărește singură poziția — doar calibrarea validată independent.
8. **Contract unic de decizie**: ID, versiunea mandatului, instrument, direcție, acțiune, orizont, alocare și cantitate finală,
   intrare/stop/țintă/invalidare, expirarea deciziei, sursele și momentul datelor, costuri estimate, motive, opinii divergente,
   rezultatul verificării de risc. Ordinul final legat de planul verificat; orice schimbare materială → reverificare.
9. **Risc la nivel de portofoliu**: expuneri corelate și factori comuni, riscul pozițiilor + ordinelor în așteptare,
   rezervare atomică a capitalului, stres pe portofoliul rezultat, verificare imediat înainte de trimitere. Riscul poate
   reduce sau respinge propunerea AI; consensul modelelor nu poate depăși limitele.
10. **Adaptor broker/exchange**, separat de motorul paper: solduri, poziții, ordine, execuții, comisioane, reguli de cantitate,
    pas de preț, valoare minimă, program, conversii valutare; chei API minime, **fără retrageri**; credențiale de test separate
    strict de cele reale. Blocarea LIVE nu se șterge — se adaugă un mecanism explicit și verificabil de activare.
11. **Ciclul ordinului**: creat → verificat → trimis → confirmat → executat parțial/total, anulat sau respins; ID-uri stabile,
    fără duplicate; după timeout se verifică ordinul existent înainte de retrimitere; anulare și execuție aproape simultane;
    protecții actualizate după cantitatea executată; ordine de protecție la broker unde există; reevaluare la expirarea
    orizontului sau invalidarea motivului. Stopul nu se lărgește ca să amâne o pierdere.
12. **Reconciliere și recuperare**: numerar, marjă, poziții, ordine, costuri comparate cu brokerul; pornire numai după
    recuperarea stării; diferențele neexplicate blochează intrările noi; un singur executor activ pe cont; copii de siguranță.
13. **Supraveghere**: vechimea datelor, disponibilitatea surselor, latență, erori și costuri AI, ordine fără protecție,
    neconcordanțe, limite atinse. Oprirea intrărilor, anularea ordinelor și închiderea pozițiilor sunt trei acțiuni distincte.
    Dashboard: modul PAPER/LIVE, capital, expunere, profit net, costuri, decizii și motivul unei opriri.
14. **Idei în plus**: valabilitatea oportunității (reevaluare dacă analiza durează sau prețul a fugit); atribuirea rezultatului
    (semnal, știri, alocare, execuție); evaluarea execuției (preț estimat vs. realizat); mod degradat (fără știri sau fără un AI,
    protecțiile merg în continuare); AI-ul nu își schimbă singur codul, modelele sau limitele; teste de incidente
    (deconectări, execuții parțiale, date greșite, rate limits, restart, ordine cu stare necunoscută).
15. **Ordinea de lansare**: audit și mandat → portofoliu, alocator, risc comun → știri, scanner, Time Machine → adaptor broker
    și ciclul ordinelor → teste de integrare/recuperare/reconciliere → paper trading cu aceeași logică de ordine ca la real →
    rulare în paralel cu piața reală, fără ordine → activare explicită cu capital real limitat, după criterii stabilite
    dinainte. Livrabile: inventarul diferențelor, arhitectură, cod, teste, configurația mandatului, proceduri de operare și
    recuperare, raport de validare, criterii concrete pentru activarea modului real. La cod extern: licență și atribuire.

## D. Selecție, ieșiri și pierderi (primită pe 11.11.2026)

Obiectiv: profit net mai mare, pierderi mai rare și mai mici, prin selecție, dimensionare și ieșiri validate. Nu se
optimizează doar rata de câștig și nu se presupune că pierderile pot fi eliminate. Prioritate: **filtrul de selecție →
colectarea MAE/MFE → compararea politicilor de ieșire → calibrare și degradare**.

Ce există deja (verificat pe 11.11.2026): componenta „Trade Selectivity” nu există încă sub acest nume (se construiește peste
Time Machine din B.4); scorul Brier pe agenți există în `decision_registry.py` (folosit de raportul consiliului);
MAE/MFE nu se înregistrează încă.

1. **Filtru de avantaj insuficient** (Trade Selectivity): rezultat așteptat după comisioane, spread, slippage, finanțare;
   incertitudinea și scenariile nefavorabile; respinge avantajul insuficient sau datele insuficiente; „nu tranzacționez”
   fără cote de activitate; praguri alese pe datele de dezvoltare și verificate pe date separate. Încrederea declarată
   de AI nu e o probabilitate validă fără calibrare.
2. **Detector de condiții nefavorabile**: spread/costuri neobișnuite, lichiditate slabă, volatilitate extremă sau schimbare
   de regim, evenimente, date întârziate, condiții diferite de cele de validare. Condițiile de suspendare și reluare
   sunt fixate dinainte; regulile nu se schimbă după fiecare pierdere.
3. **Invalidarea explicită a tranzacției**: motivul intrării, orizontul, condițiile observabile de invalidare, stopul,
   expirarea semnalului și durata maximă. Ieșire anticipată la invalidare — păstrată doar dacă bate ieșirea standard.
4. **Optimizator de ieșire**: compară stop/țintă fixe, pe volatilitate, trailing, închidere parțială, stop la pragul de
   rentabilitate (cu costuri), ieșire după timp, ieșire la invalidare. Alegere pe strategie și regim, cu suport statistic;
   nu se combină totul automat; politica e fixată înainte de tranzacție, cu adaptările permise definite explicit.
   (Conturile paralele P12–P15, P24–P26 testează deja câteva variante de take profit/stop și reciclare.)
5. **MAE/MFE** pentru fiecare tranzacție: mișcarea maximă contra și pentru poziție, timpul până la ele, profitul net final
   și diferența față de MFE, motivul și costul ieșirii. Doar pentru analiză retrospectivă, niciodată ca date la decizie.
6. **Calibrare** (AI și Time Machine): probabilități estimate vs. frecvențe realizate, pe strategie, orizont și regim unde
   există eșantion; mărimea eșantionului și incertitudinea; Brier și diagrame de fiabilitate; miza nu crește automat pe
   rezultate recente insuficiente. Se refolosește infrastructura existentă a consiliului.
7. **Detector de degradare**: rezultat net mediu pe tranzacție, costuri și slippage, drawdown și pierderi extreme,
   calibrare, schimbarea pieței; praguri, eșantion minim, reguli de reluare. Reducerea riscului poate fi automată
   (în mandat); schimbarea strategiei trece printr-o nouă validare.
8. **Registrul oportunităților respinse**: motivul, datele de atunci, planul ipotetic și ieșirea, rezultatul simulat
   cu costuri realiste (fără presupunerea execuției integrale la prețul dorit); pierderi evitate vs. profit ratat.
9. **Împotriva rezultatelor înșelătoare**: pierderile nerealizate și costurile intră în evaluare; pierderile nu se amână
   ca să protejeze rata de câștig; fără lărgirea stopurilor și fără martingale; statisticile nu se resetează după
   perioade slabe; intrările și ieșirile parțiale se evaluează împreună (fără „câștiguri” umflate artificial).
10. **„Sub 5%” definit corect** (în configurație și rapoarte, separat): proporția tranzacțiilor pe pierdere, pierderea
    procentuală a poziției, pierderea raportată la capital, drawdown-ul portofoliului. **Nu** se introduce un obiectiv
    obligatoriu de 95% tranzacții câștigătoare. Pierderea planificată la stop nu garantează pierderea maximă reală.
11. **Validare**: ipoteze, variante și criterii scrise înainte; fiecare componentă comparată separat cu aceeași bază;
    testare cronologică în afara datelor de dezvoltare și walk-forward; corecție pentru numărul variantelor încercate;
    scenarii cu costuri mari, gap-uri, lichiditate slabă; confirmare prin forward paper trading. Metrici principale:
    profit net mediu pe tranzacție, profit factor, drawdown, pierderi extreme, expunere, costuri, stabilitate; rata de
    câștig e secundară. Livrabile: inventarul componentelor refolosite, implementare modulară, teste, raport comparativ,
    limitări, dezactivare separată a fiecărei funcții. Modul real urmează criteriile de lansare din C.15.
