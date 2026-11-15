# Analiză: componente din daily_stock_analysis pentru BND (implementare după 1.12.2026)

Cerut de proprietar pe 15.11.2026. **Până pe 30.11: doar analiză și documentație, fără schimbări în codul BND.**

- Proiect de referință: https://github.com/ZhuLinsen/daily_stock_analysis, versiunea
  `82b5eb937d25d4ff033cd74e60536ad7a9b14fd9` (15.11.2026). Licență **MIT** („Copyright (c) 2026 ZhuLinsen”):
  orice cod preluat păstrează notificarea de copyright și textul licenței (în antetul fișierului și în
  `THIRD_PARTY_NOTICES.md`). Preferăm să reimplementăm ideile, ca la TradingAgents (vezi `settlement.py`).
- Codul de referință a fost doar citit, ca date; nu a fost rulat.
- Clasificare: **complet** = există și e legat în flux; **parțial** = există o parte sau nu e legat; **absent**.

## Rezumat

| # | Componentă | În BND azi | Stare | Unde se extinde |
|---|---|---|---|---|
| 2 | Evaluarea individuală a opiniilor AI | `decision_registry.py` (votul și încrederea fiecărui agent, stadiile `initial`/`final`), `settlement.py` (raw / intrare la închiderea următoare / alpha), scor Brier | **parțial** | `decision_registry.py`, `settlement.py` |
| 3 | Istoricul rezultatelor deciziilor finale | `council_analytics.py` (pe agent, regim, orizont, consiliu vs. regulă, ponderare în afara eșantionului) | **parțial** | `council_analytics.py` |
| 4 | Calitatea și vechimea datelor | `council_daily` (sare piața >5 zile fără lumânare), `paper_engine` (date vechi/gap → fără risc nou), `market_data` (validare, gap-uri, timeout) | **parțial** | `market_data.py`, `paper_engine.py`, modul nou subțire `data_quality.py` doar dacă nu încape în `market_data` |
| 5 | Jurnalul dezacordurilor | stadii `initial`/`final` separate, `complete=False` pentru agent lipsă (exclus din statistici, nu HOLD), `council_analytics.disagreement` | **parțial** | `decision_registry.py`, `council_daily.py`, `council_analytics.py` |
| 6 | Risc long/short cu acțiuni explicite | `risk_engine` (APPROVE / APPROVE_REDUCED / REJECT), `paper_engine` (kill switch; ordinele `reduce_only` trec și cu kill switch activ) | **parțial** | `risk_engine.py`, `paper_engine.py` |
| 7 | Proveniența știrilor | nu există agent de știri (punctul 3e din `DUPA_30_11.md`; B.1 din `BND_2_0_CERINTE.md`) | **absent** | se construiește odată cu News Agent |
| 8 | Costul și eficiența agenților | `cost_tracker`, `ai_budgets`, `trace` pe decizie (model, furnizor, latență, încercări, tokeni, cost, hash-ul cererii), `ai_cache` | **parțial** | `council_daily.py`, `cost_report.py` |
| 9 | Motorul de backtest | `backtester.py` (long+short, costuri, finanțare), `robustness.py`, `walk_forward.py` | **nu se preia** | — |

## 2. Evaluarea individuală a opiniilor AI (prioritate mare)

**Referința** (`skill_opinion_outcome_evaluator.py`, `skill_opinion_outcome_service.py`, `skill_opinion_sample_repo.py`):
evaluator pur, determinist; eșantioane imuabile (`on_conflict_do_nothing` pe cheie unică + versiune de schemă);
orizonturi 1/3/5/10 zile; stări `pending` (lipsesc date viitoare), `unable` (semnal invalid, orizont nesuportat,
dată lipsă), `observational` (hold), `evaluated` (hit/miss); preț de start = închiderea zilei analizei.

**BND are deja**: votul și încrederea fiecărui agent, înainte (`initial`) și după dezbatere (`final`), în tabela
`votes`; decontare la orizont cu trei variante (`raw`, `entry_next` – intrare la prima închidere de după decizie,
`alpha` față de SP500/BITCOIN); `trace` cu model, furnizor, `data_through`, hash-ul contextului; excluderea
deciziilor incomplete și a celor pe date vechi.

**Lipsește (diferențe concrete)**:
1. Stările distincte: azi o decizie e doar „nedecontată” sau „decontată”; `outcome_return == 0` e scos din scor.
   Trebuie `pending` / `unable` (cu motiv) / `invalid` / `evaluated`, salvate per agent × orizont.
2. Orizonturi multiple pe aceeași opinie (scalp: ore; day trading: 1 zi; multi-day: 3/5/10 zile). Azi un singur
   `horizon_days` pe decizie. Pentru scalp sunt necesare lumânări intraday (blocate în sesiune; se rulează în CI).
3. Versiunea strategiei/promptului pe opinie (azi doar modelul) și referințele datelor (avem `context_sha256`;
   lipsesc identificatorii lumânărilor și ai surselor).
4. Separarea „direcție corectă” de „tranzacție profitabilă”: randament executabil după comision, spread,
   slippage și funding (azi alpha e brut). Costurile se iau din același model ca `paper_engine`, ca să nu existe
   două calcule.
5. Imuabilitate explicită: eșantionul nu se rescrie; evaluarea se adaugă separat (tabelă nouă `opinion_outcomes`).

**Validare**: test care reface evaluarea dintr-o opinie salvată și lumânările salvate și obține același rezultat;
test că o lumânare de după momentul deciziei nu poate intra în contextul inițial (avem deja regula „doar închideri
finale” în `settlement.py`).

## 3. Istoricul rezultatelor deciziilor finale (prioritate mare)

**Referința** (`decision_signal_outcome_service.py`, `decision_signal_outcome_repo.py`): leagă semnalul final de
evaluare, agregă pe orizont, tratează eșantioane repetate.

**BND are**: `council_analytics` – tabel pe agent, `by_regime`, `by_horizon`, `revision_value` (cât a ajutat
dezbaterea), `council_vs_rule`, `alpha_report`, `out_of_sample_weighting` (ponderi testate în afara eșantionului,
cu test de semn), `cost_to_value`.

**Lipsește**: legătura explicită decizie finală → opinii inițiale → rezultat într-un singur rând de raport;
contribuția fiecărui AI față de decizia echipei **și** față de benchmark în același tabel; numărul de observații și
proporția neevaluabilelor afișate peste tot; tratarea semnalelor suprapuse (aceeași piață, aceeași direcție, zile
consecutive cu orizont care se suprapune — azi fiecare zi contează separat, ceea ce umflă eșantionul): se numără
o dată pe „episod” sau se raportează cu eșantion efectiv redus. Performanța pe strategie lipsește (avem doar
majoritar/ponderat).

**Regulă păstrată**: ponderile **nu** se schimbă automat pe câteva rezultate sau pe rata de succes; orice
adaptare trece prin `out_of_sample_weighting` și o decizie separată.

## 4. Calitatea și vechimea datelor (prioritate mare)

**Referința** (`data_provider/base.py`, `realtime_types.py`): furnizori multipli cu fallback ordonat, cotații în
timp real cu sursa și momentul, tipuri unificate.

**BND are**: validarea seriilor și găsirea gap-urilor (`market_data`), timeout pe cereri, reparare de vârfuri,
pragul de 5 zile în consiliu, blocarea riscului nou la date vechi sau gap mare (`paper_engine`), `STALE_DAYS`
în analiză, verificarea zilnică a stării (`health_check`, `status.yml`).

**Lipsește**: câmpurile furnizor / momentul cotației / momentul recepției / vechime / istoricul fallback-ului pe
fiecare preț; diferența „întârziat” vs. „timestamp necunoscut”; praguri de prospețime pe strategie și piață,
cu programul burselor (`calendars.py` există și se refolosește); circuit breaker pe furnizor (azi doar timeout +
reîncercări în unele locuri); verificarea compatibilității între surse (simbol, monedă, interval, diferență de preț).

**Validare**: teste cu furnizor indisponibil, cotație veche, timestamp absent și prețuri contradictorii →
intrările noi blocate, protecțiile existente funcționale.

## 5. Jurnalul dezacordurilor și independența (prioritate mare)

**Referința** (`disagreement.py`, `protocols.py`, `orchestrator.py`): rezumat structurat al dezacordului
(tabere bullish/bearish/neutral), opiniile invalide numărate separat, nu filtrate tacit; protocol comun de opinie.

**BND are**: opinii `initial` și `final` separate; agent lipsă → `complete=False`, exclus, **nu** HOLD;
`council_analytics.disagreement`; `revision_value`.

**Lipsește**: cine s-a opus, cu ce motiv și cum s-a rezolvat (azi motivele sunt în raportul text, nu în
registru); distincția „consens complet” vs. „acord cu membri lipsă” în raport; motivul deciziei finale
(majoritate / specialist / veto de risc) ca câmp, nu doar textul regulii; opiniile invalide numărate separat de
cele lipsă.

## 6. Risc long/short cu acțiuni explicite (prioritate mare)

**Referința** (`risk_override.py`): veto de risc care transformă **buy → hold**; e gândit pentru long-only.
**Nu se copiază**: în BND „sell” poate deschide un short, deci o coborâre a semnalului nu e o reducere de risc.

**BND are**: `risk_engine` determinist (aprobă / aprobă redus / respinge), kill switch persistent, ordine
`reduce_only` permise și cu oprirea activă, stopuri.

**De făcut**: acțiuni explicite în locul transformării semnalului — `BLOCK_ENTRY`, `REDUCE_EXPOSURE`,
`CLOSE_POSITION`, `REDUCE_ONLY` — aplicate simetric pe long și short; limitele obligatorii rămân în cod
determinist; AI-ul poate adăuga doar evaluări care **restrâng**; dacă verificarea obligatorie eșuează
(excepție, date lipsă) → intrări noi blocate, protecțiile pozițiilor existente rămân active (se leagă de E.5).

## 7. Proveniența știrilor (prioritate medie)

**Referința** (`news_evidence.py`, `search_service.py`): numără știrile **efectiv** primite de agent (nu o
căutare făcută după analiză), ca dezvăluirea „fără știri” să fie corectă.

**BND**: absent (nu avem agent de știri). Se construiește odată cu News Agent (B.1): pentru fiecare știre URL,
sursă, data publicării, data accesării; eliminarea duplicatelor; „nicio știre” separat de „căutare eșuată”;
numărul de rezultate nu e o verificare a veridicității.

## 8. Costul și eficiența agenților (prioritate medie)

**Referința** (`evals/agent_trajectory/metrics.py`, `src/agent/tools/execution.py`): metrici pe traiectoria
agentului (apeluri redundante, erori, latență) și execuția uneltelor cu timeout.

**BND are**: cost pe apel și pe zi (`cost_tracker`, plafoane zilnic/lunar), `trace` pe decizie cu latență,
încercări, tokeni, cost; `ai_cache`; `cost_to_value`.

**Lipsește**: agregarea pe analiză (apeluri redundante, reîncercări, erori, timp total), raportul de
respectare a bugetelor și comportamentul la timeout; regula ca cache-ul să nu servească un răspuns mai vechi
decât pragul de prospețime și să nu împartă opinii între agenți (independență).

## 9. Motorul de backtest — nu se preia

`src/core/backtest_engine.py` e long-only, pe lumânări zilnice și fără modelarea completă a costurilor BND
(funding, short, levier). Poate inspira doar evaluarea semnalelor (stările din §2); `backtester.py`,
`robustness.py` și `walk_forward.py` rămân baza.

## Fișiere BND afectate și ordinea implementării (după 1.12)

1. **§4 date** — `market_data.py`, `paper_engine.py`, `calendars.py` (prospețime, circuit breaker, blocare intrări).
   Primul, pentru că toate evaluările depind de date corecte.
2. **§6 risc** — `risk_engine.py`, `paper_engine.py` (acțiuni explicite, simetrice long/short).
3. **§2 opinii** — `decision_registry.py` (tabelă `opinion_outcomes`, versiunea strategiei, referințe date),
   `settlement.py` (stări, orizonturi multiple, randament după costuri), `council_daily.py` (scrie câmpurile noi).
4. **§5 dezacorduri** — `decision_registry.py`, `council_daily.py` (opozanți, motive, tipul consensului, motivul deciziei).
5. **§3 istoric** — `council_analytics.py` (lanț decizie → opinii → rezultat, episoade suprapuse, observații).
6. **§8 cost** — `council_daily.py`, `cost_report.py`.
7. **§7 știri** — odată cu News Agent.

Fiecare pas: branch + PR, teste unitare pentru cazurile cerute, apoi rulare în umbră/cont paralel.

## Validare după 1.12

- Teste: reproducerea evaluării din opinia salvată; fără informații viitoare; furnizor căzut / cotație veche /
  timestamp lipsă / prețuri contradictorii; long și short simetric la acțiunile de risc; agent lipsă ≠ HOLD.
- Paper trading: versiunea nouă față de cea de referință pe **aceleași date și costuri**, în cont paralel;
  raport cu profit net, drawdown, expunere, costuri AI și incertitudinea rezultatelor (interval, eșantion efectiv).
- Activarea tranzacțiilor reale rămâne o etapă separată (C.15, E.7, E.8).
