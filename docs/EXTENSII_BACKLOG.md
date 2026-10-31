# Extension backlog: verificare față de cod (31.10.2026)

Principiu: mai multă complexitate nu înseamnă mai mult profit; nimic din aici nu a fost adăugat testului activ. DONE = există și e testat; PARTIAL = există în parte; MISSING = nu există; NOT JUSTIFIED = nu merită acum, cu motiv.

| # | Propunere | Stare | Ce există / de ce |
|---|---|---|---|
| 1 | AI Performance Scoreboard | PARTIAL | `council_analytics` (rată, profit virtual, calibrare, HOLD corect, minoritare, pe piață/clasă) și `decision_registry.performance()`; ponderi din scor în regula WEIGHTED (calculate, nefolosite la decizie). Lipsește împărțirea pe regim și ajustarea out-of-sample (cere date). |
| 2 | Devil's Advocate | NOT JUSTIFIED acum | Consiliul nu decide tranzacții (umbră); un apel plătit în plus fără ceva de protejat. De reevaluat dacă consiliul ajunge să decidă. |
| 3 | Confidence Calibration Engine | PARTIAL | Tabelul de calibrare și diferența declarat vs observat sunt calculate; recalibrarea efectivă nu e aplicată (cere zeci de decizii). |
| 4 | Counterfactual Decision Analysis | PARTIAL | `comparison()` compară consiliu, înclinație, bot și „doar cumpără" cu informații doar de la momentul deciziei; cele trei conturi rulează în paralel. Lipsesc „expunere mai mică" și „altă strategie" pe același cont. |
| 5 | AI Disagreement Intelligence | PARTIAL | `council_analytics.disagreement`: dezacord scăzut/mediu/ridicat vs mișcarea reală; ipoteza se testează când există decizii. |
| 6 | Market Microstructure Engine | NOT JUSTIFIED | Botul folosește lumânări zilnice; nu există sursă gratuită de order book; scalpingul nu e în test. |
| 7 | Event & News Intelligence | MISSING (NOT JUSTIFIED în timpul testului) | Ar schimba informația văzută de consiliu și deci evaluarea. De făcut separat, începând cu un calendar de evenimente doar ca filtru de risc. |
| 8 | Cross-Market Intelligence | PARTIAL | Contextul consiliului include mișcarea pe 20 de zile a celorlalte piețe; strategii cross-sectional (`cross_sectional.py`). Nu există test de putere predictivă pe relații concrete. |
| 9 | Adaptive Trade Execution Simulator | NOT JUSTIFIED | Motorul are ordine MARKET/LIMIT, stop, slippage și comision; fragmentarea și latența nu contează pentru un bot zilnic. |
| 10 | Strategy Retirement & Revival | MISSING | Există rotație după scor (`selector`, `score_weighted`), dar nu reguli de suspendare/reactivare. Util doar cu luni de date. |
| 11 | Portfolio Stress Laboratory | PARTIAL | `scenarios.py` (șocuri pe poziții curente) și teste extreme (gap peste stop, date vechi, prăbușire). Lipsesc corelații în creștere, spread extrem și întreruperi de furnizor ca scenarii. |
| 12 | Model & Data Drift Detection | MISSING | Doar alertele de date vechi; `regimes.py` e cercetare offline. |
| 13 | Shadow Portfolio | PARTIAL | Trei conturi paralele (reguli = „fără AI", AI cripto, AI unificat) cu aceleași date. Lipsesc variantele „profit maxim", „randament/risc maxim" și „consens unanim" (se pot adăuga ca conturi AI fără cost de apeluri). |
| 14 | Independent Risk Watchdog | PARTIAL | Kill switch-ul e în motor, independent de consiliu; `status.yml` supraveghează separat (reconciliere, date, rulări). Nu poate opri singur o simulare, doar alertează. |
| 15 | Failure Injection & Recovery | DONE (la nivel de test) | API indisponibil, răspuns AI invalid, date lipsă/invalide, restart, scriere întreruptă (SIGKILL), execuții concurente: `test_council_quality`, `test_persistence`, `test_end_to_end`. Nu s-au injectat erori în producție. |
| 16 | AI Cost-to-Value Analysis | PARTIAL | `council_analytics.cost_to_value` compară 5, primii 3 și câte 1 agent din voturile salvate, cu costul pe decizie. Concluziile vin după zeci de decizii. |
| 17 | Intelligent Analysis Scheduling | NOT JUSTIFIED | O analiză pe zi pe 13 piețe costă ~0,35 $; economia ar fi mică față de complexitate. |
| 18 | Research Reproducibility Registry | PARTIAL | Setări înghețate în cont, jurnal de audit, urma deciziilor, rezultate pe ramura `backtest-results`, versiuni în git. Nu există un registru unic de experimente cu hash de date. |
| 19 | Automated Strategy Tournament | PARTIAL | `compare_wfo` (test de semn), walk-forward pe portofoliu, bootstrap. Fără competiție periodică automată; nu se promovează nimic automat. |
| 20 | Capital Allocation Research Engine | PARTIAL | Dimensionare după volatilitate cu corelații, limite pe grup, `selector`/`score_weighted`. Fără cercetare dedicată pe capacitate de piață și incertitudine statistică. |

**Ce am implementat din listă acum:** doar ce e doar citire sau analiză și ajută evaluarea de după test (1, 3, 5 parțial; 16 parțial; 15 la nivel de test). Restul rămâne pentru după 17.11, ca să nu întârziem sau altereze testul.
