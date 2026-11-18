# Secțiunile suplimentare ale raportului (17.11 și 1.12)

Doar citire, gratuit, fără apeluri AI. Folosite pentru raportul preliminar din 17.11; se refolosesc pe 1.12 cu `BND_END=2026-11-30`.

1. Date în `W/`: `unic.sqlite` (cont-unic), `control.sqlite` (cont-control), `registry.sqlite` (consiliu-umbra),
   `f/<formație>/paper.sqlite` (git archive origin/formatii-ai), `dp/zilnic/*.csv` (date-piete).
2. `python3 scripts/raport/levsim.py W/dp/zilnic > W/levsim.json` — simularea pe istoric (prudent/acum/agresiv, 5x/10x long/short).
3. `BND_END=… python3 scripts/raport/formsec.py W` — clasamentul formațiilor și leverage-ul ales de fiecare.
4. `BND_END=… python3 scripts/raport/extra_md.py W` — scrie `W/extra.md` (long/short, simularea, formațiile, leverage),
   de inserat în raportul generat de `python -m src.bnd.final_report` înainte de secțiunea „Limite”.
