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

**Ce NU s-a întâmplat:** nimic nu s-a promovat în conturi. E-001 a fost privit informal o dată înainte de înregistrare; criteriul scris cere de aceea consistență pe ambele perioade (transparent în registru). Cu 3 ani și 10 piețe, orice concluzie rămâne limitată; următorul pas e repetarea pe 12 ani de istoric, ca experimente noi.

```bash
python -m src.bnd.research_lab capital --id E-005 --data-dir date --markets SP500,GOLD,BITCOIN
python -m src.bnd.experiments nota E-001 "interpretare ulterioară"   # nu schimbă verdictul
```
