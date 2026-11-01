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
