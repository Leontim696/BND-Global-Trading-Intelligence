# Date macro și context (arhivă), plus regulile „point-in-time”

Idei preluate din TradingAgents v0.7.1 (Apache-2.0; reimplementate, fără dependențe): decontare cu intrare după decizie și alpha, surse gratuite de context, reguli point-in-time, decizii incomplete excluse.

## Decontare (`settlement.py`)
La decontare se adaugă în `meta["settle"]`: randamentul cu intrare la **prima închidere de după data deciziei** (`entry_next_return`), benchmark-ul (SP500, iar pentru cripto BITCOIN) și `alpha_raw` / `alpha_next`. `outcome_return` rămâne neschimbat. `council_analytics.alpha_report` arată rata de reușită brută, cu intrare după decizie și față de piață; dacă rata brută e mare, dar alpha e slabă, consiliul a prins doar direcția pieței. Deciziile cu runda incompletă ies din toate statisticile din analiză.

## Colectare (`macro_data.py`, workflow `date-macro.yml`, ramura `date-macro`)
| Sursă | Cheie | Ce | Când |
|---|---|---|---|
| Polymarket | nu | probabilități implicite pentru evenimente (top 30 după volum) | zilnic |
| FRED | `FRED_API_KEY` (gratuită) | dobândă Fed, randamente 2Y/10Y, inflație, șomaj, VIX, T10Y2Y, cu versiunea (`vintage`) | zilnic, doar cu cheie |
| SEC EDGAR | nu (User-Agent) | Revenues, NetIncome, Assets, Equity, EPS pentru acțiunile americane din univers, CU data depunerii | duminica |

Nu intră în decizii și nu sunt date consiliului în timpul testului. Sursele nu au putut fi verificate din sandbox: `macro/status.json` arată după prima rulare ce a răspuns fiecare. User-Agent-ul EDGAR se poate înlocui cu variabila `EDGAR_USER_AGENT` (SEC cere un contact real).

## Point-in-time (`pit.py`)
`as_of_date` taie o dată cerută la data analizei, `window` refuză ferestre inversate, `in_window` exclude viitorul și elementele fără dată, `filed_as_of` reconstituie ce era public la o dată, cu versiunea (restatarea) care era în vigoare. Se aplică oricărei surse noi înainte să ajungă într-un context.

## Ce nu am luat din TradingAgents
Graful de dezbatere (cost), autentificarea cu planul ChatGPT, screening-ul Jev (plătit), memoria cu reflecții injectate în prompt (ar schimba întrebarea consiliului), normalizarea simbolurilor (fără consumator acum).
