# Raportul final al testului oficial (17.11.2026)

Plan fixat pe **2.11.2026**, înainte de rezultate. Structura, comparațiile și criteriile verdictului de mai jos
nu se schimbă după ce apar cifrele (pre-înregistrare: altfel s-ar putea alege, conștient sau nu, criteriile care
ies bine).

## Ce se măsoară

| Secțiune | Sursa | Ce arată |
|---|---|---|
| Rezumat | `paper.sqlite` (cont-unic) | capital inițial și final, randament, scădere maximă, zile cu rulare, cea mai bună și cea mai slabă zi, execuții, comisioane, oprirea de urgență |
| Comparație | `zilnic/SP500.csv` (date-piete) | „cumperi și ții” S&P 500: ultima închidere înainte de 31.10 → ultima închidere până la 16.11 |
| Curba de capital | jurnalul `daily_run` | capitalul la ultima rulare a fiecărei zile (UTC) |
| Consiliul AI | `registry.sqlite` (consiliu-umbra), `council_analytics` | decizii încheiate la 5 zile: doar reguli, consiliul, înclinația, hibridul; pe agent: rată de reușită, supra-încredere, HOLD corect |
| Cost | `costs.sqlite` | costul AI total |
| Poziții | `paper.sqlite` | ce rămâne deschis la final |
| Limite | text fix | de ce rezultatul nu e o dovadă |

## Criteriile verdictului

Verdictul „indiciu de avantaj” apare **doar dacă toate** sunt îndeplinite:

1. Contul unic bate S&P 500 „cumperi și ții” pe aceeași fereastră.
2. Cel puțin 20 de decizii hibride încheiate.
3. Rata de reușită a hibridului peste 50%.
4. Testul semnului pe deciziile hibride: p < 0,05.

Un criteriu fără date contează ca neîndeplinit. Chiar dacă toate trec, textul spune „indiciu, NU dovadă”: 16 zile și
decizii corelate între piețe nu ajung pentru o concluzie. Altfel verdictul e „fără dovezi de avantaj”.

## Cum se generează

Doar citire; nu tranzacționează și nu schimbă nimic din test.

```
python -m src.bnd.final_report --unic paper.sqlite --registry registry.sqlite \
    --costs costs.sqlite --benchmark SP500.csv --out raport-final
```

Scrie `raport-final.md` și `raport-final.html` (pentru Drive). Pe 17.11.2026 dimineața raportul se generează din
datele ramurilor `cont-unic`, `consiliu-umbra` și `date-piete` și se pune în Drive.
