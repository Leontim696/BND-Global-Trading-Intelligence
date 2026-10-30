# Rezultatele cercetării BND (bani virtuali)

Actualizat: 30.10.2026. Toate testele sunt pe date istorice publice, cu
costuri de tranzacționare incluse. Un test istoric bun **nu** garantează
profit în viitor.

## Pe scurt

- **Nicio strategie nu bate încă, în mod dovedit, varianta simplă
  „cumperi tot și ții”** pe cele 23 de piețe (ETF-uri, forex, crypto).
- Cea mai promițătoare: **SMA doar pe cumpărare (fără short)**. Iese din
  piață înaintea prăbușirilor mari (2020, 2022), ceea ce contează mult
  când se folosește levier. Avantajul nu este însă dovedit statistic.
- **Levierul pe ETF-uri costă**: dobânda la banii împrumutați de la broker
  mănâncă tot avantajul la 5% pe an. La 3% pe an și levier 2x, SMA ajunge
  aproape de varianta simplă (+146% față de +155%), dar tot n-o bate.

## Testul cel mai cinstit: walk-forward pe tot portofoliul

Botul își alege setările doar din 4 ani trecuți și tranzacționează anul
următor, pe care nu l-a văzut. Se repetă pentru fiecare an, 2014-2026
(12 ani). Fiecare an este comparat cu „cumperi tot și ții” (1x, fără
împrumut) pe aceleași zile.

| Strategie | Levier maxim | Dobândă împrumut | Profit 12 ani | Sharpe mediu | Ani mai buni decât varianta simplă |
|---|---|---|---:|---:|---:|
| Cumperi tot și ții | 1x | – | **+155%** | 0,78 | – |
| SMA (long și short) | 3x | 0% | +126% | 0,61 | 5 din 12 |
| Clasament între piețe | 3x | 0% | +95% | 0,44 | 5 din 12 |
| regime_switch | 3x | 0% | +63% | 0,35 | 6 din 12 |
| SMA doar long | 3x | 0% (nerealist) | +417% | 1,00 | 10 din 12 |
| SMA doar long | 3x | 5% | +114% | 0,51 | – |
| SMA doar long | 2x | 3% (+2% la cash) | +146% | 0,73 | 4 din 12 |
| SMA doar long | 3x | 3% (+2% la cash) | +125% | 0,57 | 6 din 12 |
| SMA doar long | 1x | – (2% la cash) | +80% | 0,86 | 4 din 12 |
| Mereu cumpărat, aceeași împărțire | 3x | 0% | +69% | 0,56 | – |
| Mereu cumpărat, aceeași împărțire | 3x | 5% | −35% | −0,05 | – |
| Mereu cumpărat, aceeași împărțire | 1x | – (2% la cash) | +69% | 0,90 | 4 din 12 |

### Este avantajul SMA real? (comparație an cu an, `compare_wfo`)

SMA doar long față de „mereu cumpărat” cu aceeași împărțire și levier:

- 3x, fără dobândă: SMA mai bun în 7 din 12 ani, +9,3 puncte pe an în
  medie, t = 1,58, p = 0,77: **poate fi noroc**.
- 3x, dobândă 5%: 6 din 12 ani, p = 1,00.
- 1x: 6 din 12 ani, +0,8 puncte pe an, p = 1,00.

## Alte rezultate

- **Bitcoin zilnic, 2018-2026:** SMA +348% și regime_switch +115%, față de
  +549% dacă doar ții Bitcoin.
- **Prima comparație pe 23 de piețe (din 2022):** 13 strategii simple; nicio
  strategie n-a avut un avantaj de sincronizare dovedit după corecția
  pentru teste multiple (Holm).
- **Combinație de 3 strategii:** +50,8% față de +48,8% pentru varianta
  simplă, dar cu Sharpe mai mic (0,71 față de 0,84) și levier 2,7x.
- **Alegere automată a strategiei:** +27% față de +48,8%; strategia care a
  câștigat anul trecut nu continuă să câștige.
- **Momentum** a mers bine în 2022-2026, dar a pierdut 11,6% în 2010-2022:
  a fost noroc.

## Ce ar merita testat în continuare

1. Levier mai ieftin: contracte futures (finanțarea e inclusă în preț),
   dacă găsim date cu rolările ajustate corect.
2. Strategii bazate pe date noi (AI, știri, date on-chain), nu doar pe
   prețuri; aici runda AI plătită este necesară.
3. Testul înainte în timp real (paper trading zilnic), după ce
   proprietarul confirmă suma virtuală de pornire.
