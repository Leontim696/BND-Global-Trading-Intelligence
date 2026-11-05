# Registrul de experimente (AI Research Memory)

Un singur loc pentru fiecare ipoteză testată, inclusiv eșecurile. Fișier: `experimente/registru.jsonl`
(jurnal cu lanț de hash-uri, ca `audit_log`: o modificare ulterioară se vede la `verifica`).

## Ciclul
1. **Propune** înainte de rulare: titlu, ipoteză, familie, tip, parametri, date (cu hash), perioade, **criteriul de acceptare**.
2. Rulezi experimentul (backtest, analiză, consiliu în umbră).
3. **Rezultat**: verdict `acceptat` / `respins` / `neconcludent`, concluzie obligatorie, metrici, cost.

```bash
python -m src.bnd.experiments propune --titlu "..." --ipoteza "..." --familie capital --tip backtest \
    --criteriu "Sharpe mai mare după costuri, p<0.05 corectat" \
    --antrenare 2015-01-01:2019-12-31 --test 2020-01-01:2024-12-31 --info-pana-la 2026-10-31
python -m src.bnd.experiments rezultat E-001 --verdict respins --concluzie "..." --p 0.2
python -m src.bnd.experiments cauta volatilitate
python -m src.bnd.experiments raport
python -m src.bnd.experiments verifica
```

## Reguli aplicate de cod
- **Fără informație din viitor:** testul începe după antrenare; testul nu depășește `--info-pana-la`.
- **Fără duplicate:** aceeași amprentă (tip, ipoteză, parametri, date, perioade) cere `--justificare-duplicat`.
- **Fără câștigători întâmplători:** un „acceptat” cu valoare p e refuzat dacă p > 0,05 / numărul de experimente din familie (Bonferroni).
- **Fără rescriere:** un experiment încheiat nu se mai modifică; repetarea e un experiment nou.
- **Criteriul se scrie înainte** de rezultat; concluzia e obligatorie și pentru eșecuri.

Nu apelează AI și nu costă nimic. Doar experimentele marcate ca trecute prin acest registru pot fundamenta o promovare în conturi.

## Experimentele rulate (1.11.2026)
Date: arhiva `date-piete`, 10 piețe, 1.11.2023–30.10.2026 (≈666 de zile comune, test = ultimele 267). Cod: `src/bnd/research_lab.py`. Zero cost, fără AI.

| ID | Întrebare | Verdict | Pe scurt |
|---|---|---|---|
| E-001 | Kelly fracționat bate volatilitatea-țintă? | **neconcludent** | În test da (Sharpe 1,76 față de 0,76, p=0,006), în antrenare invers (0,88 față de 1,45). Instabil, cu volatilitate mai mare (24% față de 15%). |
| E-002 | Strategie aleasă pe piață × regim bate strategiile fixe? | **respins** | Sharpe 0,79 față de 1,50 (combo) și 1,48 (fixă aleasă în antrenare); p=0,96. Confirmă cercetarea anterioară. |
| E-003 | Procedura de descoperire dă câștigători falși pe zgomot? | acceptat (slab) | 0 din 12 universuri; eșantion prea mic, vezi E-004. |
| E-004 | Idem, 80 de universuri | **acceptat** | 0 din 80 (limita superioară 4,6%); rata naivă doar 1,25%. Nulul sintetic e prudent: nu dovedește nimic despre piețe reale. |
| E-005 | E-001 repetat pe 12 ani (9 piețe, 2014–2026) | **neconcludent** | Kelly bate volatilitatea-țintă în ambele perioade (Sharpe 1,45/1,39 față de 1,18/1,12), dar p=0,071 > 0,025; cu risc mai mare. |
| E-006 | E-002 repetat pe 12 ani | **respins** | Meta 1,20 față de combo 1,38; p=0,51. Aceeași concluzie ca pe 3 ani. |

(E-003/E-004 sunt pe date sintetice, deci nu depind de istoric. Datele de 12 ani: ramura `date-12-ani`, fără ETHEREUM, care nu există din 2014.)

**Ce NU s-a întâmplat:** nimic nu s-a promovat în conturi. E-001 a fost privit informal o dată înainte de înregistrare; criteriul scris cere de aceea consistență pe ambele perioade (transparent în registru). Cu 3 ani și 10 piețe, orice concluzie rămâne limitată; următorul pas e repetarea pe 12 ani de istoric, ca experimente noi.

```bash
python -m src.bnd.research_lab capital --id E-005 --data-dir date --markets SP500,GOLD,BITCOIN
python -m src.bnd.experiments nota E-001 "interpretare ulterioară"   # nu schimbă verdictul
```

## Corectat după auditul din 1.11.2026
Auditul a găsit în laborator: semnalul se executa la închiderea care îl producea (nu la deschiderea următoare), costul era 5 bps și nu se plătea deriva ponderilor, `p` din bootstrap avea rezoluție 1/300 (sub pragul Bonferroni), iar planul înregistrat nu era verificat. Toate sunt reparate în cod (rezultatele vechi au rămas în registru, marcate DEPĂȘIT/INVALID prin note).

| ID | Înlocuiește | Verdict | Pe scurt |
|---|---|---|---|
| E-007 | E-001 (3 ani) | neconcludent | Kelly bate volatilitatea-țintă în test (p=0,003), dar pierde în antrenare; volatilitatea-țintă are rotație 30–36/an și costurile reale o strică. |
| E-008 | E-002 (3 ani) | respins | Meta 0,54 față de 1,37 (combo). |
| E-009 | E-005 (12 ani) | neconcludent | Kelly bate volatilitatea-țintă în ambele perioade, p=0,047 > 0,0125; risc dublu față de ponderea egală. |
| E-010 | E-006 (12 ani) | respins | Meta 1,00 față de 1,19 (combo). |
| E-011 | E-003/E-004 | acceptat (depășit de E-012) | Fals pozitive ≤ 4,6% (limită superioară), putere 97,5% la regularitate puternică; rata naivă 16%. |

Regula nouă: o rulare care diferă de planul înregistrat (parametri, perioade) e refuzată sau cere `--accept-deviation` cu motivul; „acceptat” cere valoarea p sau o justificare.

| E-012 | E-011 | **neconcludent** | Decis pe avantaj realist (0,1%/zi ≈ 25%/an): fals pozitive 0/80 (limită 4,6%), dar puterea e 0% la 25%/an, 20% la 63%/an, 87,5% la 126%/an. Procedura nu vede decât avantaje enorme. |

## Reproductibilitate (audit 01.11)
Un experiment se poate repeta doar dacă sunt fixate: **codul**, **datele**, **costurile**, **criteriile de acceptare** și **seed-urile**.
- Codul: la propunere se salvează commit-ul scurt (`cod`); de acum, la rezultat se salvează și commit-ul complet împreună cu starea „modificat” (`cod_la_rezultat`). Un rezultat dintr-un cod cu modificări necomise sau cu alt commit decât la propunere e marcat.
- Datele: la rezultat, `research_lab` salvează în metrici `reproducere.date` (SHA-256, număr de rânduri, prima și ultima zi pentru fiecare CSV, plus un hash comun). `python -m src.bnd.experiments verifica-date E-0xx FOLDER` compară datele de acum cu cele din rezultat.
- Costurile vin din cod (`CLASS_COSTS`/`market_costs()`), deci sunt fixate doar prin commit; parametrii înregistrați conțin costul unde a fost dat explicit.
- Criteriul se scrie înainte de rulare și rămâne în registrul cu lanț de hash-uri; `plan_deviations` blochează rularea care se abate de la plan.
- Seed-urile: bootstrap 7; universurile sintetice `random.Random(1000 + u)`. Se salvează acum în `reproducere.seeds`.

Raport: `python -m src.bnd.experiments reproducere` (cod de ieșire 1 dacă un experiment nu poate fi repetat complet).

**Verdict onest pentru E-001..E-012 (făcute înainte de această schimbare):** NU sunt reproductibile complet. Codul de la propunere există (commit-uri valide), seed-urile sunt deterministe în cod, dar datele sunt doar etichetate (`date-piete/zilnic ...`, `date-12-ani ...`), fără hash, iar codul de la rezultat nu a fost salvat. O repetare cu datele de azi poate da alte numere dacă arhiva sau prețurile ajustate s-au schimbat. Registrul nu se rescrie; experimentele noi (E-013 și următoarele) pornesc cu aceste câmpuri.

## Strategii noi, 4.11.2026 (E-013 … E-016)
Cerute de proprietar („dezvoltă câteva strategii ce merită încercate”). Cod: `src/bnd/strategii_noi.py`. Parametri fixați din
literatură, criteriu scris înainte (bate „cumperi tot în părți egale” adus la aceeași volatilitate, p < 0,0125 și Sharpe mai
bun în ambele părți 60/40). Zero cost, fără AI. Doar long, fără leverage, costuri reale.

| ID | Strategie | Verdict | Pe scurt |
|---|---|---|---|
| E-013 | Momentum crypto 14 zile + filtru Bitcoin > media 50 | respins | Sharpe 0,04 față de −0,27; mai bun în ambele părți, +11,9 puncte/an, dar p = 0,28. Ferește de prăbușirea altcoin-urilor (ținut 1x: −37,5%/an, −84% maxim), însă tot −5,7%/an. Doar 2,7 ani, 39 de monede (supraviețuitori). |
| E-014 | Rotație săptămânală top 10 pe 28 de zile | respins | Sharpe −0,05, −18,6%/an, −66% maxim; p = 0,30. |
| E-015 | Final de lună pe S&P 500 + Nasdaq 100 (2014–2026) | respins | Sharpe 0,32 față de 0,89; mai slab în ambele părți; p = 0,97. |
| E-016 | RSI(2) revenire pe indici (2015–2026) | respins | Sharpe 0,77 față de 0,87; stă în piață 17% din timp, −17% maxim; mai bun doar în a doua parte; p = 0,64. |

Concluzie: niciuna nu bate „cumperi și ții” la același risc, în mod dovedit. Singurul indiciu interesant e filtrul Bitcoin
din E-013 (reduce mult pierderile pe altcoin-uri), dar pe prea puțini ani ca să conteze. Nimic nu se promovează în conturi.

## Intraday crypto, 5.11.2026 (E-017, E-018)
Cerute de proprietar (execuție la 10 minute). Cod: `src/bnd/intraday_live.py`. Reguli și criteriu scrise înainte de test
(registru): net după costuri > 0 pe portofoliul egal ponderat al monedelor și Sharpe anual > 1, pe 30 de zile de lumânări
de 5 minute de la Binance. Testul rulează pe GitHub (`intraday-10min.yml`, mode=backtest). Conturile P27/P28 rulează oricum
în paralel ca observație; rezultatul nu mută nimic în contul oficial.

| ID | Strategie | Verdict | Pe scurt |
|---|---|---|---|
| E-017 (v1 simplificat) | Trend crypto 15 minute (P27) | respins | 30 de zile, 49 de monede: −2,1% înainte de costuri, **−48,3% după costuri** (18.415 schimbări de poziție, ~12/zi pe monedă). 13% din zile pe plus. |
| E-018 (v1 simplificat) | Revenire la medie crypto 5 minute (P28) | respins | −8,8% înainte de costuri, **−43,9% după costuri** (14.018 schimbări de poziție). |

Concluzie: pe lumânări de 5–15 minute, costurile (0,15–0,25% la fiecare intrare/ieșire) sunt mai mari decât orice
avantaj al acestor reguli; niciuna nu câștigă nici înainte de costuri. Ce poate aduce frecvența mare e verificat separat
de P26 (aceleași semnale zilnice ca P24, doar TP/stop verificate la 10 minute), unde numărul de tranzacții rămâne mic.

Varianta v1 de mai sus e simplificată (toate monedele egal, fără stop, fără selecția celor 10). După auditul din 5.11
testul s-a refăcut cu ACELAȘI motor și aceleași funcții ca P27/P28 (v2 „motor”, `backtest_engine`); pe aceleași
lumânări face exact aceleași tranzacții ca execuția contului (test automat). Rezultatele v2 sunt adăugate ca notă în
registru, lângă cele v1; vezi și `docs/VERSIUNI_EXPERIMENTE.md`.
