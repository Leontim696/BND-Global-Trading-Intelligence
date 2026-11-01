# Dezbatere în umbră (Fusion Council 2.0)

Runda a doua a consiliului, doar pe piețele cu obiecții reale, într-un registru separat. **Nu tranzacționează nimic și nu atinge contul unic, consiliul principal sau testul de 16 zile.** Planificată pentru după 17.11.2026; până atunci rămâne oprită (doar manual).

## Cum funcționează
1. Consiliul principal rămâne la o singură rundă, cinci agenți independenți. Raportul zilei (cu motivele) se salvează acum și ca `consiliu/LATEST.json` pe ramura `consiliu-umbra`.
2. `council_debate` citește raportul și alege piețele cu **declanșator**: *opoziție directă* (și BUY, și SELL) sau *vot izolat puternic* (un BUY/SELL cu încredere ≥ 0,70 când restul votează HOLD). Nu orice dezacord: 81% dintre piețe au măcar un vot diferit, deci ar declanșa aproape peste tot. Se iau cele mai puternice cel mult 12.
3. Fiecare agent primește aceeași întrebare plus părerile celorlalți și poate **revizui votul doar dacă un argument concret îl convinge**. Voturile inițiale și cele revizuite se păstrează ambele (`debate-registry.sqlite`).
4. Candelele sunt tăiate la ziua rundei 1: dezbaterea nu vede nimic mai nou.
5. După 5 zile: `council_analytics.before_after` compară, pe aceleași piețe, înclinația inițială cu cea finală (câte au schimbat direcția, câte au ajutat, câte au stricat).

## Rulare (manual: workflow „Dezbatere în umbră”)
| Mod | Cost | Ce face |
|---|---|---|
| `settle` | 0 | închide deciziile scadente |
| `mock` | 0 | agenți simulați, registru aruncat |
| `live` | ~0,03–0,05 $/piață (≈0,5 $ la 12 piețe) | agenți reali; cere exact `RUN-PAID-TEST`; respectă plafoanele zilnic/lunar ale consiliului |

## Criteriul de acceptare
Votul final trebuie să reușească mai des decât cel inițial **la 5 zile, pe multe decizii**. Cu <20 de decizii închise sau cu `neconcludent` nu se trage nicio concluzie. Un rezultat se trece în registrul de experimente (`docs/EXPERIMENTE.md`) cu verdict. Dezbaterea nu intră în conturi decât cu aprobarea ta, după dovezi.
