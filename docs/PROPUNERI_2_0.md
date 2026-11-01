# Analiza tehnică a propunerilor „BND 2.0” (1.11.2026)

Livrabil cerut: starea actuală, componentele reutilizabile, dependențele, costurile API, beneficiul măsurabil și ordinea recomandată pentru cele zece propuneri. **Nu s-a implementat nimic** din ele; implementarea urmează după aprobarea priorităților. Totul rămâne în modul PAPER și nu atinge testul activ de 16 zile. „BND Command Center Dashboard” nu e atins; la nevoie se oferă doar contracte de date (exemplu: `status.json`).

Stări: **DONE**, **PARTIAL**, **MISSING**, **NOT JUSTIFIED** (acum). Complexitate: S (zile de lucru puține), M, L. Costuri API pentru consiliu: ~0,027 $ pe piață și pe rundă de 5 agenți (măsurat), consiliul actual: 88 de piețe, ~2,4 $/zi.

## Trei constatări care schimbă ordinea

1. **Un consiliu AI nu se poate valida pe istoric.** Modelele cunosc deja istoria, deci un backtest al votului lor ar scurge viitorul în decizie (look-ahead). Singura evaluare validă a propunerilor 1, 4 și 6 este **înainte în timp**, cu decizii închise la 5 zile. Cele 88 de decizii zilnice dau multe puncte, dar corelate între piețe: 15 zile nu dovedesc nimic statistic, cum scrie și `council_analytics` („sub 20 de decizii: orientativ").
2. **Cercetarea proprie a fost deja negativă la selecția dinamică de strategii.** `docs/REZULTATE_CERCETARE.md`: „alegere automată a strategiei: +27% față de +48,8%; strategia care a câștigat anul trecut nu continuă să câștige”; nicio strategie nu bate „cumperi tot și ții” în mod dovedit; `regime_switch` (+63% în 12 ani față de +155%) a fost printre cele mai slabe. Contul unic folosește `regime_switch` pe jumătatea de reguli: e o alegere fără dovadă statistică, de urmărit.
3. **Cea mai bună investiție acum nu e o funcție nouă, ci instrumentarea**: registrul de experimente (propunerea 10) și evaluarea agenților (propunerea 4) fac toate celelalte verificabile. Fără ele, orice îmbunătățire ar fi o afirmație.

## Tabel de ansamblu

| # | Propunere | Stare | Complexitate | Cost API | Impact asupra testului | Recomandare |
|---|---|---|---|---|---|---|
| 1 | Fusion Council 2.0 | **PARTIAL** | M | mare dacă se rulează pe toate piețele | niciunul în umbră | după 17.11, în umbră, pe un subset |
| 2 | Meta-Strategy Engine | **PARTIAL** (dovadă negativă) | L | 0 | ar schimba conturile | retestat onest, prioritate scăzută |
| 3 | Portfolio Brain | **PARTIAL** | M | 0 | doar raportare acum | **începe cu raport de expuneri corelate** |
| 4 | AI Learning & Calibration | **PARTIAL** | S–M | 0 | niciunul (doar citire) | **continuă acum, gratuit** |
| 5 | Execution Intelligence | **NOT JUSTIFIED** (acum) | M | 0 | – | amânat: bot zilnic, ordine la deschidere |
| 6 | Market Intelligence Layer | **PARTIAL** | M | 0–mic | niciunul dacă rămâne în arhivă | calendar economic + context, după test |
| 7 | Strategy Discovery Lab | **MISSING** (părți existente) | L | mediu | niciunul | după registrul de experimente |
| 8 | Crypto Smart-Money Graph | **MISSING** | L | 0–mic + chei de date | – | **NOT JUSTIFIED acum**; blocat de date și juridic |
| 9 | Capital Efficiency Engine | **PARTIAL** | M | 0 | ar schimba dimensionarea | cercetare offline, după test |
| 10 | AI Research Memory | **PARTIAL** | S–M | 0 | niciunul | **primul, gratuit** |

## 1. Fusion Council 2.0 — PARTIAL

**Există (testat unitar, nefolosit în producție):**
- `fusion_council.py`: voturi inițiale păstrate separat de revizuiri (`revise`), istoric de audit complet.
- `debate_engine.py` (236 de linii): dezbatere cu porți de participare, argumente cu dovezi obligatorii, revizuire de vot doar cu argument, închidere blocată dacă lipsesc argumente.
- `decision_rules.py`: majoritate, consens ponderat, unanimitate; implicit HOLD când dovezile sunt slabe; `AgentScorebook` cu netezire pentru eșantioane mici.
- **Criteriul de acceptare e deja demonstrat în teste:** `test_minority_can_change_majority` (în trei fișiere de test), `test_minority_remains_recorded`, `test_minority_objection_forces_reconsideration_and_keeps_history`.
- `signal_pipeline.py` și `trade_coordinator.py`: lanțul decizie → semnal → ordin dimensionat → motor, cu veto de risc și jurnal; offline, doar ordine virtuale.
- Veto de risc independent: `risk_engine.py` + limitele motorului + oprirea de siguranță, neinfluențate de vot.
- Producție azi: **o singură rundă**, 5 agenți independenți (`council_runner`, `council_daily`), cu urmă de audit (model, hash, latență, cost) per decizie, voturi inițiale și finale salvate.

**Lipsește:** fazele 2–4 pe date reale (publicare, dezbatere, revizuire) în producție, un prompt de contestare, regulă de declanșare a dezbaterii doar la dezacord, măsurarea valorii revizuirii (voturile „înainte/după” față de rezultat).

**Dependențe/cost:** apeluri AI în plus: o rundă de dezbatere are ~5 apeluri cu prompturi mai lungi, aproximativ 0,03–0,05 $ pe piață. Pe toate cele 88 de piețe ar fi ~3–4 $/zi, inacceptabil la bugetul actual. Soluția: dezbatere doar când votul e împărțit (în ziua de azi ~40% dintre piețe au măcar un vot neunanim) și pe un subset limitat, ~10–15 piețe, aproximativ 0,5 $/zi.

**Recomandare:** în umbră, după 17.11, cu măsurătoare dublă (înainte/după dezbatere) pe aceleași piețe; nu se adaugă în evaluarea activă. Beneficiu măsurabil: rata de reușită a votului final față de cel inițial, la 5 zile, după multe decizii.

## 2. Meta-Strategy Engine — PARTIAL (cu dovadă negativă)

**Există:** `regimes.py` (regimuri de tendință și volatilitate fără informații din viitor), `regime_switch` și alte 12 strategii în `strategies.py`, `combo`, `selector` și `score_weighted` (alocare după scorul recent), `walk_forward.py`, `portfolio_walk_forward.py`, `robustness.py`, `significance.py`, `compare_wfo.py` (test de semn), costuri incluse în `backtester.py`.

**Lipsește:** selecția pe piață × regim cu ponderi dinamice, suspendarea/reactivarea cu criterii, condiții de stres ca regim propriu.

**Dovadă existentă:** selecția automată a pierdut față de varianta simplă (vezi mai sus). Un motor mai complex n-are motiv să meargă mai bine decât `selector`; testul trebuie făcut onest (walk-forward, penalizare pentru teste multiple, comparat cu „cumperi tot și ții” și cu o strategie fixă).

**Cost:** zero API, dar complexitate mare și risc de supraoptimizare. **Recomandare:** prioritate mai mică decât cea cerută (P1, nu P0), doar ca experiment în registrul de cercetare; nu se promovează în conturi fără dovadă out-of-sample.

## 3. Portfolio Brain — PARTIAL

**Există:** dimensionare după volatilitate cu corelații măsurate (`portfolio.target_weights`), limită pe grup/sector/clasă, pe monedă (forex), volatilitate de portofoliu, leverage brut, risc pe tranzacție, marjă și lichidare, financiarea împrumutului (`paper_engine`), scenarii de șoc (`scenarios.py`), `fit_limits` în `paper_runner`.

**Lipsește:** raport explicit de **expuneri suprapuse** (de exemplu BTC, ETH, Nasdaq și acțiuni tehnologice ca același risc), grupare după corelație măsurată (nu doar după clasă), comparația alocare profit maxim față de randament/risc maxim, ajustare după lichiditate.

**Valoare mare, cost mic:** primul pas, doar citire, calculează matricea de corelații pe 60 de zile pentru pozițiile deschise ale contului unic, riscul pe cluster și avertizează când un cluster depășește un prag. Se arată în aplicație. Nu schimbă nicio poziție. Criteriul de acceptare (teste în scenarii extreme) se acoperă cu `scenarios.py` + cazuri sintetice de corelație 1.

## 4. AI Learning & Calibration — PARTIAL

**Există:** `council_analytics.py` (rată de reușită, profit virtual, calibrare pe intervale de încredere, HOLD corect, contribuții minoritare, pe piață și pe clasă, dezacord față de mișcare, cost-valoare pe 5/3/1 agenți), `decision_registry.performance()`, `AgentScorebook` cu netezire spre 0,5 (`prior_outcomes=20`) și pondere minimă 0,25, regula WEIGHTED, registru cu urmă completă.

**Lipsește:** scoruri pe regim și pe orizont, comparația „înainte/după revizuire” (cere propunerea 1), testul că ponderarea egalează sau bate votul egal pe date nevăzute, penalizarea explicită a supraîncrederii (calibrarea e doar măsurată).

**Cost:** zero. **Recomandare:** continuă acum, e doar citire. Primul rezultat real vine după închiderea deciziilor din 1–2.11 (la 5 zile), cu avertisment de eșantion mic. Concluzii pe ponderi abia după ~100 de decizii independente pe agent și piață.

## 5. Execution Intelligence — NOT JUSTIFIED (acum)

**Există:** ordine MARKET și LIMIT (limita nu e umplută niciodată mai rău, inclusiv cu alunecare), stop-uri, take-profit, trailing, ordine parțiale (`PARTIAL`), expirarea ordinelor, comision, alunecare per clasă, carry, finanțare, ID-uri idempotente.

**De ce nu acum:** botul decide o dată pe zi și execută la deschiderea următoare, pe lumânări zilnice. Fragmentarea, latența și impactul pe order book nu pot fi modelate onest fără date de order book (nu există sursă gratuită) și n-ar schimba un bot zilnic. Singura lacună reală e spread-ul modelat separat de alunecare (F-12). **Recomandare:** nu se construiește; spread separat doar dacă trecem la intraday.

## 6. Market Intelligence Layer — PARTIAL

**Există:** funding și Fear & Greed arhivate zilnic (`context_data.py`), prețuri pe 88 de piețe în arhivă, program burse (`calendars.py`), lumânări intraday (`intraday.py`), contextul consiliului include mișcarea pe 20 de zile a piețelor de bază (relații între piețe), cursuri EUR/USD și EUR/RON.

**Lipsește:** calendar economic (dobânzi, inflație, ocupare), calendar de raportări pentru acțiuni, open interest, filtru de risc înaintea evenimentelor, separarea informației confirmate de interpretarea AI, testul cu/fără sursă.

**Dependențe:** surse gratuite de calendar economic (verificare de acces din GitHub). **Cost API:** zero pentru colectare; mic dacă se pune în context. **Recomandare:** colectare în arhivă acum sau după test; **nu se dă consiliului în timpul testului** (ar schimba întrebarea); evaluarea cu/fără sursă se face pe un al doilea consiliu în umbră, după 17.11.

## 7. Strategy Discovery Lab — MISSING (cu piese)

**Există:** backtester cu costuri, walk-forward pe strategie și portofoliu, grile de parametri și teste de robustețe, semnificație statistică (corecție Holm), comparații an cu an, rezultate publicate (`docs/REZULTATE_CERCETARE.md`, ramura `backtest-results`).

**Lipsește:** generarea de ipoteze de către agenți AI, transformarea lor în reguli deterministe, registrul de experimente (inclusiv eșecurile), promovare cu aprobare.

**Risc principal:** cercetarea automată fără disciplină produce supraoptimizare (mulți experimenți, un câștigător întâmplător). De aceea depinde de propunerea 10 și de corecția pentru teste multiple deja existentă. **Cost:** mediu (apeluri AI pentru ipoteze, ieftine; backtesturile sunt gratuite). **Recomandare:** după registrul de experimente.

## 8. Crypto Smart-Money Graph — MISSING, NOT JUSTIFIED acum

**Nu există nimic** pentru on-chain în cod. **Dependențe:** furnizori de date (explorere de blockchain pentru Ethereum, Solana, Base, BNB Chain, cu chei API, limite gratuite mici), lista de walleturi urmărite aleasă de tine, filtre anti-scam. **Riscuri:** acuzații nejustificate la categoria „posibil suspect”, date incomplete la clusterizarea walleturilor, lag față de evenimente (informația pe care o vedem e deja prinsă de piață). **Criteriul de acceptare** (reproducerea unor tipare istorice fără informații ulterioare) cere date istorice on-chain pe care nu le avem.

**Recomandare:** nu se începe în timpul testului. Dacă o vrei, primul pas e mic: un singur lanț (de exemplu Ethereum), 6 walleturi alese de tine, colectare în arhivă, fără decizii și fără categoria de „insider”. Decizia de a o porni, și furnizorul, sunt ale tale.

## 9. Capital Efficiency Engine — PARTIAL

**Există:** dimensionare după volatilitate (țintă de volatilitate de portofoliu), plafoane de leverage, finanțare cu 5% pe an, limite pe poziție și clasă, scenarii de stres, comparații cu și fără dobândă în cercetare (levierul pe ETF-uri își mănâncă avantajul la 5% pe an, după rezultate).

**Lipsește:** dimensionare după randament așteptat și incertitudine (de exemplu o fracțiune Kelly cu plafon), estimarea capacității pe piață, compararea sistematică a metodelor de alocare în scenarii nefavorabile.

**Notă:** „leverage maxim nu e obiectiv” e deja principiul cercetării proprii. **Recomandare:** cercetare offline după test, comparând volatilitate-țintă fixă, risc egal și Kelly fracționat pe date istorice, după costuri; fără schimbarea conturilor.

## 10. AI Research Memory — PARTIAL

**Există:** setările conturilor înghețate în jurnal (`runner_settings`), jurnal de audit cu lanț de hash, registru de decizii cu urmă (model, hash de context, versiunea datelor), costuri, arhiva de date pe `date-piete`, rezultate de backtest pe `backtest-results`, versiuni în git.

**Lipsește:** un **registru unic de experimente** (ipoteză, cod și date cu hash, perioade de antrenare/test, parametri, costuri, rezultat, motiv de acceptare/respingere), detectarea experimentelor duplicate, căutare în concluzii, regula care separă informația disponibilă la momentul deciziei de rezultatul de după.

**Cost:** zero API, complexitate mică–medie (un tabel SQLite + o comandă care înregistrează fiecare rulare de backtest). **Recomandare:** primul, pentru că face verificabile toate celelalte.

## Ordinea recomandată (după valoare)

1. **AI Research Memory (10)**: registru de experimente. Gratuit, fără risc pentru test, condiție pentru 2, 7, 9.
2. **AI Learning & Calibration (4)**: continuă analiza deja construită pe voturile care se închid din 6.11. Gratuit.
3. **Portfolio Brain (3), pasul 1**: raport de expuneri corelate în aplicație, doar citire.
4. După 17.11: **Fusion Council 2.0 (1)** în umbră, pe subset, cu măsurare înainte/după; **Market Intelligence (6)**: calendar economic în arhivă.
5. **Capital Efficiency (9)** și **Meta-Strategy (2)** ca experimente în registru, cu comparație walk-forward onestă; **Strategy Discovery Lab (7)** abia când registrul și corecția pentru teste multiple sunt folosite.
6. **Execution Intelligence (5)**: respinsă pentru un bot zilnic (motiv în secțiunea 5).
7. **Smart-Money Graph (8)**: amânată; cere decizia și datele tale.

## Limite și riscuri comune
- Orice propunere cu AI se evaluează doar înainte în timp (constatarea 1).
- Mai multă complexitate nu garantează randament mai bun: cercetarea proprie arată contrariul pentru selecția de strategii.
- Costul consiliului e deja ~2,4 $/zi; orice apel AI nou se plătește din același sold.
- Deciziile de a promova ceva în conturi rămân la tine, după dovezi.
