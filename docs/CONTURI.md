# Conturile virtuale

Trei portofolii separate, fără capital comun (detalii în `docs/AUDIT_P0.md`, secțiunea A3). Se compară prin randament în procente, nu prin valoare absolută: toate trei sunt acum etichetate USD, iar prețurile sunt în USD, fără conversie. Contul „Reguli” are 10.000 USD (a fost etichetat EUR până pe 31.10.2026, schimbare de etichetă auditată, fără conversie), celelalte două 11.183 USD (10.000 € la 1,1183 la creare).

Verificarea contabilă independentă: `python -m src.bnd.reconcile --state paper.sqlite` (cod de ieșire 0 = corect).

## Long, short și leverage pe cont (31.10.2026)
| Cont | Direcții | Leverage permis | Finanțare |
|---|---|---|---|
| Reguli (`paper-trading`) | doar long (`--no-shorts`) | 1x | 0% |
| Reguli long/short (`reguli-ls`, nou, nepornit) | long și short | până la 3x | 5%/an |
| Cripto AI | long și short | până la 2x | 5%/an |
| AI unificat | long și short | până la 2x | 5%/an |

În conturile AI, „vinde" = poziție short (câștigi dacă prețul scade), iar „cumpără" = long. Leverage-ul e un plafon, nu o țintă: expunerea reală vine din dimensionarea după volatilitate și din semnale (de exemplu AI unificat plănuia pe 1.11 long 12% și short 127%, adică expunere brută de 1,39x). Contul „Reguli" e conservator din setările de creare și nu poate fi schimbat fără cont nou; `reguli-ls.yml` pornește un cont-frate cu aceeași strategie de reguli, dar cu short și leverage.

## Cont unic (din 1.11.2026)
Cele patru conturi (Reguli, Reguli long/short, Cripto AI, AI unificat) au fost înlocuite de **un singur cont**, `cont-unic` (workflow „Cont unic (virtual)”, 22:25 UTC, după consiliu). Cele patru vechi au fost oprite după primele rulări, fără nicio tranzacție executată, și rămân ca arhivă (starea lor nu mai e actualizată).

Cum decide contul unic, pe fiecare dintre cele 71 de piețe (ETF/forex, SOL/BNB/XRP și 44 de monede din top 50 cripto):
- semnal final = ½ × semnalul regulilor (`regime_switch`) + ½ × semnalul consiliului AI (net BUY−SELL, 1 vot net = 0,5, 2+ = 1);
- acord între reguli și AI: poziție întreagă; dezacord: se anulează; fără vot AI azi (piețe pe care consiliul nu votează): decid doar regulile;
- poate face long și short; leverage maxim 2x; maxim 25% într-o piață și 60% într-o clasă (memecoin-urile au clasă proprie și alunecare de 3x mai mare); țintă de volatilitate 15%; stop 3×ATR; finanțare 5%/an.
Capital: 11.183 USD (10.000 € la 1,1183, ca la celelalte). Pornire manuală, o singură dată: Actions → „Cont unic (virtual)” → Run workflow, capital `11183`, reset gol. Pentru alt leverage se poate da la creare setarea `--max-leverage 3` (setările se îngheață la creare).

## Cont de control: doar reguli (din 4.11.2026)
Cerut de proprietar pe 3.11.2026. Ramura `cont-control`, workflow „Cont de control (doar reguli, virtual)” (22:35 UTC).
Identic cu contul unic (aceleași 101 piețe, aceleași limite și același capital de 11.183 USD), dar cu strategia
`regime_switch` singură, fără consiliul AI. Diferența de randament dintre cele două conturi, pe aceeași
fereastră, arată ce aduce consiliul. Fără apeluri AI; contul unic nu e atins. Apare în raportul preliminar și
în cel final (`final_report --control`) și în aplicație („Doar reguli (control)”).

## Acțiuni și apărare/armament (din 1.11.2026)
Contul unic are acum 101 de piețe: cele 71 de până atunci (ETF, forex, obligațiuni, mărfuri, crypto) plus **16 acțiuni americane mari** (Apple, Microsoft, Nvidia, Alphabet, Amazon etc., pe sectoare) și **14 titluri din industria de apărare și armament**: Rheinmetall, Hensoldt, Renk, BAE Systems, Thales, Leonardo, Saab, Kongsberg, Lockheed Martin, Northrop Grumman, RTX, General Dynamics, L3Harris și ETF-ul ITA. Apărarea are sector propriu (`armament`, limită de 60% din cont).
- **Apărarea intră și în consiliul AI** (14 piețe în plus, ~0,38 $/zi; consiliul ajunge la 72 de piețe, ~2,0 $/zi). Acțiunile americane mari decid doar regulile, fără consiliu (ar fi costat ~0,43 $/zi în plus).
- **Monede locale:** acțiunile europene sunt în moneda lor (EUR, GBP/pence, SEK, NOK), fără conversie în dolari. Procentele sunt corecte; valorile absolute ale acestor poziții nu sunt convertite (aceeași limitare ca F-08/F-11 din `docs/AUDIT_P0.md`).
- Datele vin de la Yahoo; un titlu care nu se descarcă într-o zi e sărit și notat în raport.

Actualizare: cele 16 acțiuni americane intră acum și în consiliul AI (88 de piețe în total, ~2,4 $/zi); apărarea era deja acolo.

## Formații AI (31 de conturi-umbră, din 4.11.2026)

Cerute de proprietar pe 4.11.2026, ca să vedem după 30.11 ce AI sau ce grupă de AI merită păstrată
(și eventual să reducem costurile). Ramura `formatii-ai`, workflow `formatii-ai.yml` (22:50 UTC, după contul unic),
cod în `src/bnd/formations.py`. **Fără niciun apel AI în plus**: refolosesc voturile pe care consiliul zilnic
le dă oricum, salvate pe fiecare agent în `registry.sqlite`.

| Punct | Formație | Reguli | Conturi |
|---|---|---|---:|
| 1 | GPT + Grok | cu reguli (50% regime_switch + 50% formația) | 1 |
| 2 | GPT + Grok | fără reguli (100% formația) | 1 |
| 3 | fiecare AI singur | cu reguli | 5 |
| 4 | fiecare AI singur | fără reguli | 5 |
| 5 | GPT + Claude + Grok | cu reguli | 1 |
| 6 | GPT + Claude + Grok | fără reguli | 1 |
| 7 | toți 5, ponderați după rezultate (avantajul peste 50% pe deciziile încheiate; egale până la ≥20 decizii încheiate per AI) | cu reguli | 1 |
| 8 | toți 5, dar consiliul contează doar la consens ≥4 din 5; altfel doar regula | cu reguli | 1 |
| 9 | toți 5, doar la crypto și memecoin; la restul piețelor doar regula | cu reguli | 1 |
| 10 | „Miză după convingere”: puternic (≥4/5 AI și regula în aceeași direcție) = miză întreagă (până la 25%/piață), mediu (2–3 AI net cu regula, sau ≥4/5 cu regula neutră) = jumătate, slab sau contradictoriu = nimic; aceeași limită de 2x | cu reguli | 1 |
| 11 | ca 10, dar AGRESIV: până la 3x (plafonul motorului), 50% pe piață, 100% pe clasă, volatilitate-țintă 30%; marjele ESMA (crypto 50%, acțiuni 20%) limitează oricum leverage-ul pe piață; opririle de siguranță (−5%/zi, −25% de la vârf) rămân | cu reguli | 1 |
| 12 | ca contul oficial (toți 5 AI + regula), dar fiecare poziție nouă are take profit +5% și stop fix −1% (cerut pe 4.11, ideea proprietarului) | cu reguli | 1 |
| 13 | ca contul oficial, cu take profit +5%, dar stopul normal (3×ATR) | cu reguli | 1 |
| 14 | Reciclare, varianta OBIȘNUITĂ: take profit +5%, stop normal; după un TP/stop piața stă 5 zile în pauză pe aceeași direcție și capitalul eliberat rămâne lichid | cu reguli | 1 |
| 15 | Reciclare, varianta „Adaptive Position Recycling” (`src/bnd/recycling.py`): ca 14, dar capitalul eliberat se mută la rularea zilnică pe următoarele cele mai bune semnale (semnal/volatilitate), cu: expunere ≤ 2x, ≤ 25% pe piață, grup corelat (>0,7 pe 60 de zile, aceeași direcție) ≤ 50% din cont, nimic nou după o zi cu ≥ −2%, reciclare oprită dacă pe 10 rulări contul a pierdut ≥ 3% sau e ≥ 8% sub vârf, cel mult 10 poziții reciclate pe zi | cu reguli | 1 |

14 și 15 au aceleași semnale și aceleași limite de risc; singura diferență e ce se face cu capitalul eliberat. Comparația de la 30.11: profit brut și net (după comisioane, alunecare, finanțare), pierdere maximă, eficiența capitalului (profit pe 1 $ expus în medie, rotație, comisioane plătite) și numărul de tranzacții. Fiecare rulare salvează în `runs/<zi>.json` blocul `recycling` (ce s-a eliberat, ce s-a reciclat, ce s-a blocat și de ce).

La 12 și 13: după un take profit sau un stop, poziția se poate redeschide a doua zi dacă semnalul rămâne (tranzacție nouă, cu take profit și stop noi). Dacă în aceeași zi se ating și stopul și take profit-ul, motorul socotește stopul (prudent). Take profit-ul și stopul se calculează față de ultima închidere, iar ordinul se execută la deschiderea următoare.

Punctele 7–9 au fost propuse de Claude și aprobate de proprietar pe 4.11. Pornite cu voturile din 3.11 (ziua
de dinainte), apoi zilnic cu voturile zilei. În aplicație apare și un „scor din voturi” provizoriu, din date reale de
la 31.10: fiecare semnal al formației comparat cu prețul de acum (fără leverage, fără reguli).

Toate au aceleași setări ca contul unic (101 piețe, 11.183 USD, leverage 2x, 25%/piață, 60%/clasă, volatilitate 15%).
Semnal: net = BUY − SELL ale membrilor; prag = max(1, round(0,4 × membri)); semnal = semn(net) × min(1, |net|/prag)
(cu toți 5 membri e exact formula contului unic). Agenții văd ca informație indicatorii și ce spune regula, dar nu sunt
obligați s-o urmeze, deci „fără reguli” înseamnă că votul lor nu e amestecat cu regula, nu că nu au văzut-o.

Criteriu fixat dinainte (4.11): câștigă formația cu randamentul cel mai mare de la pornire până la 30.11, DOAR dacă
drawdown-ul maxim e cel mult cât al contului oficial și a câștigat și în zilele de creștere ale pieței, nu doar în cele
de scădere. Cu 16 conturi comparate, una iese prima și din noroc: rezultatul e un indiciu, nu o dovadă.

### Ideile din 4.11 (P16–P19), propuse de Claude și aprobate de proprietar
Toate pornesc de la semnalele contului oficial (toți 5 AI + regula) și adaugă O singură regulă, ca să se vadă exact ce aduce:

| # | Regula | Detalii |
|---|---|---|
| 16 | Frână la pierderi | când contul e cu ≥ 3% sub vârf, expunerea se înjumătățește; revine doar la un vârf nou (`--dd-brake-pct 3`) |
| 17 | Contra mulțimii pe crypto | media ultimelor 3 rate de finanțare (date-piete/funding: BTC, ETH, SOL, BNB, XRP): ≥ 0,03%/8h = toată lumea pe long → niciun long nou; < 0 = toată lumea pe short → niciun short nou; restul piețelor ca oficial |
| 18 | Prudență la anunțuri | în ziua dinaintea unui anunț „High” din SUA (calendarul de pe date-piete) expunerea × 0,5 (`--event-cut 0.5`) |
| 19 | Meta-formație | în fiecare zi, media semnalelor AI ale celor mai bune 3 formații (din P1, P3, P5, P7–P9) după randamentul pe ultimele 7 zile; fără clasament încă = tot consiliul |
| 20 | **Idee nebună** (cerută pe 4.11) | toate deodată: semnalele cu filtrul de funding (17) + frâna (16) + prudența la anunțuri (18) + take profit +5% cu stop normal (13) + reciclarea capitalului (15). Dacă iese bine, conturile separate arată ce ingredient a ajutat; din ele se construiește „Idee nebună v2” |

Limite: funding există doar pentru 5 monede și ~1 lună de istoric; calendarul se descarcă pe săptămâna curentă (săptămâna următoare uneori lipsește), deci un anunț poate fi ratat; P19 are clasament abia după câteva rulări.

### Din lista „BND 2.0” (GPT, 4.11): R02, R08, R09 — gratuite, implementate pe 4.11
- **R02 — cât de independente sunt cele 5 AI** (`src/bnd/ortogonalitate.py`, rulat zilnic, în aplicație sub „Formații AI”):
  acord și kappa pe perechi, corelația voturilor, „numărul efectiv de AI independente” (N²/(N + 2·Σρ)) și cât se schimbă
  votul consiliului fără fiecare AI. Pe 4.11: 274 de decizii, ~2,1 AI independente efectiv; fără Claude direcția nu se
  schimbă niciodată (95% HOLD), fără DeepSeek se schimbă în ~20% din cazuri.
- **R09 — alfa negativ:** un AI e „candidat pentru inversare” doar dacă a greșit în medie în AMBELE jumătăți ale perioadei,
  cu ≥ 30 de voturi pe jumătate și DOAR pe decizii încheiate la 5 zile (cu prețul de acum, o singură zi de revenire ar
  face orice AI „greșit constant” — exact ce s-a văzut pe 4.11 seara). Doar candidat; inversarea se testează separat.
- **R08 — gemenii oficialului** (aceleași semnale și limite, doar execuția e mai proastă): P21 comisioane și alunecare × 2,
  P22 20% din ordinele de deschidere ratate (alegere deterministă), P23 voturile executate cu o zi întârziere.
  Arată cât din profit ar rezista unei execuții reale.

### P24–P25: take profit mare, stop strâns, reciclare cu redeschidere (cerute pe 5.11.2026)
Aceleași semnale și limite ca oficialul (toți 5 AI + regula, STANDARD 2x), bani virtuali, fără apeluri AI în plus.
- **P24:** închide la **+7%** (chiar dacă poziția ar mai urca) sau la **−2%**.
- **P25:** închide la **+10%** sau la **−3%**.
- Capitalul eliberat se mută la aceeași rulare pe următoarele cele mai bune semnale (reciclarea din P15, cu toate
  protecțiile ei), iar piața închisă stă în pauză **o singură zi** (`--recycle-cooldown 1`, față de 5 la P15): de la
  rularea următoare aceeași poziție se poate redeschide dacă semnalul e tot acolo.
- Verificarea TP/stop se face pe lumânarea zilnică (maxim/minim al zilei), la rularea de noapte.

### Intraday la 10 minute: P26–P28 (cerute pe 5.11.2026)
Cod: `src/bnd/intraday_live.py`, workflow `intraday-10min.yml` (buclă de ~6 ore care se repornește singură), stare pe ramura
`intraday` (publicată o dată pe oră, un singur commit). Bani virtuali, fără apeluri AI, contul oficial neatins.
- **P26 — geamănul lui P24 la 10 minute:** aceleași ponderi țintă ca P24 (`weights_base` din raportul zilnic al lui P24,
  adică înainte de reciclare), aceleași limite și setări (TP +7%, stop −2%, reciclare, pauză 1 zi). Diferă doar frecvența:
  umplerile, TP și stopul se verifică pe lumânări de 5 minute la fiecare 10 minute. Piețele fără lumânare recentă (bursa
  închisă) nu primesc ordine noi; ordinul rămas se execută la prima lumânare de după deschidere.
- **P27 — trend crypto pe 15 minute:** long dacă prețul și EMA 20 sunt peste EMA 80 și impulsul pe 4 ore e pozitiv (short
  invers); cele mai puternice 10 semnale (impuls/volatilitate), câte 10% din cont, stop −3%. Experimentul E-017.
- **P28 — revenire la medie crypto pe 5 minute:** intră contra unei abateri ≥ 2,5σ față de media pe 3 ore, iese când prețul
  revine (|z| < 0,3) sau după 2 ore; cele mai puternice 10, câte 10%, stop −2%. Experimentul E-018.
- Date: crypto din API-ul public Binance, restul din Yahoo la 5 minute (doar cât e bursa deschisă).
- Limita de volatilitate a portofoliului din motor e oprită la aceste conturi: e calculată pe randamente zilnice și pe
  lumânări de 5 minute ar subestima riscul. Celelalte limite (pierdere zilnică, drawdown, risc pe tranzacție) rămân.

### Leverage în simulări: fiecare formație „decide” singură (cerut pe 4.11.2026)

Doar în SIMULĂRI (rapoartele din 17.11 și 1.12), nu în conturi. Pentru fiecare formație se simulează propriile semnale
zilnice (de la 31.10, pe lumânările zilnice reale) la 2x, 5x și 10x, separat doar long, doar short și long+short, cu
lichidare la ~−18% (5x) / ~−9% (10x) mișcare adversă și finanțare ~5%/an pe suma împrumutată.

Decizia nu se cere AI-urilor (ar însemna apeluri plătite); o ia o regulă fixată de acum, din rezultatele formației.
O formație „alege” leverage-ul L > 2 (pe long, pe short sau pe ambele) DOAR dacă îndeplinește toate:
1. are ≥ 20 de decizii încheiate pe direcția respectivă, cu rata de reușită > 55% și test de semn p < 0,05;
2. în simularea la L nu ar fi fost lichidată niciodată și pierderea maximă ar fi fost ≤ 25%;
3. la L câștigă după costuri mai mult decât la 2x.
Altfel rămâne la 2x. Dacă mai multe niveluri trec, se alege cel mai mic care trece (prudență). Rezultatul e o
recomandare pentru proprietar, nu o schimbare automată: limitele conturilor (2x, plafon tehnic 3x) nu se ating
fără decizia lui.
