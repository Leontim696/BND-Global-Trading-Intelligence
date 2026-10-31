# Audit P0 (31.10.2026) — constatări, severitate, dovezi

Stare: în lucru. Fiecare constatare are un identificator (F-nn), severitate (CRITIC / RIDICAT / MEDIU / SCĂZUT / INFO), dovada și starea. „Reparat” înseamnă reparat și testat; „Deschis” înseamnă necesită decizie sau lucru ulterior. Evaluarea activă de 16 zile nu a fost modificată: nicio strategie, parametru, alocare sau regulă de decizie.

## A1. Arhitectură

Matricea completă e în `docs/MATRICE_INTEGRARE.md` (generată din cod de `scripts/arch_audit.py`).

| ID | Sev. | Constatare | Dovadă | Stare |
|---|---|---|---|---|
| F-01 | MEDIU | 14 din 65 de module nu sunt apelate de nimic în producție (doar teste): `funding`, `instruments`, `intraday`, `rolls`, `compare_wfo`, `cost_report`, `paper_demo` sunt utilitare manuale de cercetare; `council_round`, `live_council_bridge`, `ai_smoke_test`, `code_review_loop`, `review_budget` sunt trasee vechi de audit/AI; `orchestrator` și `local_ai` sunt construite, dar neconectate la consiliu. | `docs/MATRICE_INTEGRARE.md` | Deschis (nu se șterge nimic în timpul testului; decizie după 17.11) |
| F-02 | RIDICAT | Protecția motorului împotriva LIVE (`PaperEngine.require_mode`) nu era apelată din niciun loc: singura barieră reală era `trading_mode()` din `paper_runner`. Orice alt punct de intrare care ar fi deschis un cont virtual nu verifica modul. | `grep require_mode` → doar definiția | **Reparat**: constructorul `PaperEngine` apelează acum `trading_mode()`; testat cu 12 valori greșite |
| F-03 | MEDIU | Mai multe module pentru aceeași idee de „rundă de consiliu”: `council_round` (vechi), `council_runner` (folosit), `council_orchestrator`, `live_council_bridge`. Risc de confuzie la întreținere. | matrice | Deschis |
| F-04 | MEDIU | O singură sursă de prețuri pentru ETF/forex/crypto (Yahoo, fără cheie). Dacă își schimbă formatul sau ne blochează, toate conturile rămân fără date. Datele lipsă sunt detectate (`missing_data`, alertă de 36 h), dar nu există sursă de rezervă. | `market_data.py`, `report_card.py` | Deschis (limitare cunoscută) |
| F-05 | MEDIU | Aplicația de pe telefon și rapoartele din Drive depind de o rutină care rulează în sesiunea de lucru, nu de un serviciu independent. Dacă sesiunea cade, aplicația nu se mai reîmprospătează (conturile și consiliul continuă pe GitHub). | rutinele programate | Deschis (se atenuează prin banner de date vechi: există, 36 h) |

## A2. Izolare paper-only

Testele negative sunt în `tests/test_paper_only.py` (34 de teste): valori greșite pentru `BND_TRADING_MODE` (inclusiv litere mici, spații, `PAPER;LIVE`), refuzul motorului și al runnerului fără să creeze cont, absența oricărui client de broker/exchange, absența oricărui endpoint de ordine sau retragere, lista de gazde de rețea permise, workflow-urile care nu pot seta un mod LIVE și `BND_ALLOW_LIVE_AI=false` în workflow-urile de tranzacționare.

| ID | Sev. | Constatare | Stare |
|---|---|---|---|
| F-06 | INFO | Nicio cale din cod nu poate trimite ordine reale: nu există client de broker, endpoint de ordine sau de retragere; singurele gazde externe sunt date (Yahoo, Binance public), AI (OpenRouter), notificări (ntfy) și GitHub. | Verificat prin test |
| F-07 | INFO | Cuvântul „live” apare și în „consiliu AI live” (apeluri AI plătite). E altă axă decât tranzacționarea: nu atinge `BND_TRADING_MODE`. Confuzia de nume rămâne un risc de citire. | Documentat |

## A3. Reconcilierea conturilor virtuale

Există **trei portofolii virtuale separate**, fără capital comun. Nu sunt trei reprezentări ale aceluiași capital și nu se adună între ele.

| Cont | Ramură | Capital inițial | Monedă din cont | Decide | Rulează |
|---|---|---|---|---|---|
| Reguli matematice | `paper-trading` | 10.000 | USD (era EUR până pe 31.10, vezi F-08) | strategia `regime_switch` | 23:23 ora Germaniei |
| Cripto AI | `crypto-trading` | 11.183 | USD | voturile consiliului, 5 monede | 23:10 |
| AI unificat | `ai-unificat` | 11.183 | USD | voturile consiliului, 13 piețe | 23:15 |

Cele 11.183 $ reprezintă 10.000 € la cursul EUR/USD 1,1183 din 30.10.2026 (valoare folosită o singură dată, la creare).

| ID | Sev. | Constatare | Dovadă | Stare |
|---|---|---|---|---|
| F-08 | RIDICAT (rezolvat prin decizia proprietarului) | Contul „Reguli matematice” e etichetat EUR, dar toate prețurile sunt în USD și motorul **nu convertește nimic**: 10.000 „EUR” sunt de fapt 10.000 de unități evaluate cu prețuri în dolari. Procentele sunt corecte; valoarea absolută nu e în euro, iar efectul cursului EUR/USD asupra proprietarului nu e în rezultat. Același lucru e declarat în fiecare raport, dar rămâne o sursă de confuzie. Proprietarul a decis să treacă eticheta în USD. | `account.currency = EUR`, `PaperEngine` fără conversii; `docs/CONTURI.md` | **Reparat pe 31.10, cont gol:** eticheta EUR → USD cu înregistrare auditată `currency_relabel` (`scripts/relabel_currency.py`); capitalul rămâne 10.000, fără conversie, deci procentele și comportamentul de dimensionare nu se schimbă. Efect asupra limitei pe monedă: vezi F-09. |
| F-09 | MEDIU (efect al F-08) | Limita de expunere pe monedă ignoră moneda contului. La contul etichetat EUR se limitează expunerea la USD, la conturile în USD se limitează EUR: același risc economic, reguli oglindite. | `paper_engine.py`, `_pre_trade_check` | Acum contul „Reguli” se comportă ca celelalte două (limită pe EUR, JPY, CHF, CAD, nu pe USD). Pe 31.10 contul era gol, deci nicio poziție existentă nu a fost afectată; limita poate fi puțin mai largă decât cea pe USD pentru perechile USDxxx. Schimbare cerută de proprietar. |
| F-10 | INFO | Dublă contabilizare: aplicația și rapoartele arată fiecare cont separat, niciun total agregat. Cele trei conturi trec reconcilierea independentă (`src/bnd/reconcile.py`) cu 0 diferențe la 31.10. | `python -m src.bnd.reconcile` pe cele 3 conturi | Verificat |

## A4. Contabilitate financiară

Verificat cu rezultate calculate de mână (`tests/test_accounting.py`): rundă completă long cu comision și slippage pe ambele părți, short, carry pe fracțiune de an, finanțare doar pe partea împrumutată pe zile calendaristice, plus reconcilierea independentă (numerar = capital + tranzacții − comisioane − carry − finanțare; poziții = suma tranzacțiilor; ordine fără umpleri peste cantitate; o singură înregistrare de creare). Reconcilierea detectează un sold modificat și o poziție fără tranzacții.

| ID | Sev. | Constatare | Stare |
|---|---|---|---|
| F-11 | MEDIU | Nu există conversie valutară (vezi F-08): P&L în valuta contului nu include efectul EUR/USD. | Deschis |
| F-12 | SCĂZUT | Spread-ul și slippage-ul sunt un singur parametru (`slippage_pct`), deci spread-ul nu e modelat separat. Costurile reale pot fi mai mari la piețe subțiri sau în afara programului. | Limitare cunoscută |
| F-13 | SCĂZUT | Slippage-ul nu se vede separat în tranzacții (prețul salvat îl include), așa că „P&L brut înainte de costuri” din reconciliere conține slippage-ul ca parte din preț. Comisioanele, carry-ul și finanțarea sunt separate. | Limitare cunoscută |

## A5. Persistență și recuperare

Teste noi în `tests/test_persistence.py`: scrieri simultane în jurnalul de audit (4 procese, 40 de rânduri, lanț valid), rând rupt de o oprire bruscă, modificare retroactivă detectată, proces ucis cu `SIGKILL` în mijlocul unei tranzacții (contul rămâne neschimbat și reconciliat) și fișierul contului publicabil ca un singur fișier. Deja existau teste pentru: repornire zilnică = sesiune continuă, rulare dublă fără efect, zile ratate recuperate în ordine, ordin trimis simultan creat o singură dată, bară procesată o singură dată, eroare în bară cu oprire sigură.

| ID | Sev. | Constatare | Dovadă | Stare |
|---|---|---|---|---|
| F-14 | RIDICAT | Jurnalul de audit (`audit_log.append`) nu avea blocare: două rulări simultane puteau bifurca lanțul, iar un rând rupt de o oprire bruscă făcea ca orice adăugare următoare să arunce excepție (iar rularea zilnică, care adaugă în jurnal la sfârșit, ar fi eșuat după ce contul era deja salvat local, dar înainte de raport). | analiza codului + testele noi | **Reparat**: blocare pe fișier, continuare de la ultimul rând valid, flush + fsync; rândul rupt rămâne vizibil la `verify` |
| F-15 | MEDIU | Jurnalul de audit e un fișier text în ramură, nu în baza de date: două ramuri sau două conturi folosesc fișiere separate. Nu există un jurnal comun al sistemului. | structura workflow-urilor | Deschis (acceptabil: fiecare cont își are lanțul) |
| F-16 | INFO | Contul SQLite e publicat ca fișier singur după `close()`; la oprire bruscă tranzacțiile neterminate se anulează (SQLite). Verificat cu `SIGKILL`. | `test_killed_process…` | Verificat |

## A6. Securitate

Verificat prin `tests/test_workflow_security.py` (inclusiv un test negativ făcut pe loc: o permisiune de scriere dată jobului cu secret a picat testul): permisiuni declarate la nivel de workflow, scriere doar în joburi separate fără secrete, secretele doar în workflow-urile așteptate (`OPENROUTER_API_KEY` în cele 6 de AI, `NTFY_TOPIC` în verificarea zilnică), fără `pull_request_target` sau `workflow_run`, nicio expresie din intrări/evenimente în comenzi shell, doar acțiuni oficiale `actions/*`, dependențe de rulare zero (doar biblioteca standard), Dependabot activ, pagina aplicației cu toate șirurile din date trecute prin `esc()`.

| ID | Sev. | Constatare | Stare |
|---|---|---|---|
| F-17 | MEDIU | Acțiunile sunt fixate pe etichete (`@v4`, `@v7`), nu pe hash de commit. Etichetele pot fi mutate de autorul acțiunii. Atenuare: doar acțiuni oficiale `actions/*` și Dependabot. | Deschis: nu se poate rezolva din această sesiune (nu pot citi hash-urile acțiunilor de la GitHub și nu inventez hash-uri). Se face cu un workflow dedicat sau de proprietar. |
| F-18 | MEDIU | `branch-cleanup.yml` are `contents: write` pe tot workflow-ul și rulează o comandă de ștergere de ramuri, la pornire manuală. Fără secrete, dar cu putere de ștergere; protejează ramurile de stare (`paper-trading` etc.). | **Reparat** (scriere doar în job; plus: lista de protecție nu includea ramurile `crypto-trading`, `ai-unificat`, `consiliu-umbra`, `status`; acum le include, cu test). Ramurile de stare sunt orfane, deci nu ar fi fost șterse oricum, dar protecția e acum explicită. |
| F-19 | MEDIU | Intrarea `settings` din `paper-trading.yml` se desparte în argumente (intenționat) și poate transmite orice opțiune runnerului. Doar cine poate porni manual workflow-ul (colaboratori cu scriere) o poate folosi; opțiunile se validează în `paper_runner`. | Risc acceptat |
| F-20 | SCĂZUT | Pagina aplicației punea valoarea unui vot direct într-un atribut `class` fără `esc()`. Date din registrul propriu, deci risc scăzut, dar nu apărare în profunzime. | **Reparat** (+ test care cere `esc()` pe orice câmp-șir) |
| F-21 | INFO | Aplicația de pe telefon e statică, privată (vizibilă doar contului proprietarului), fără formulare, fără apeluri de rețea și fără chei; nu are endpointuri de atacat. Datele din ea sunt cele din ramurile depozitului, la ora ultimei reîmprospătări. | Verificat |
| F-22 | INFO | `pip-audit` nu e rulat: runtime-ul are zero dependențe externe, iar singura dependență de dezvoltare (`pytest`) e actualizată de Dependabot. | Documentat |

## B. Consiliul celor cinci AI (P1, punctele 7–12)

| Punct | Stare | Ce există acum |
|---|---|---|
| 7 Registru de modele | IMPLEMENTAT, TESTAT UNITAR | `src/bnd/model_registry.py`: model exact, furnizor, configurație, cost (din registrul de costuri), latență și disponibilitate (din urma fiecărei analize, începând cu analizele de după această modificare). |
| 8 Contract de răspuns | IMPLEMENTAT, TESTAT UNITAR, **dezactivat** | `src/bnd/response_contract.py`: vot, încredere, argumente, dovezi, riscuri, motiv de abținere; răspunsurile incomplete sau invalide sunt marcate explicit. Nu e legat de consiliul activ: promptul lui rămâne neschimbat ca să nu influențeze evaluarea de 16 zile. |
| 9 Fusion Council | NECONFIRMAT | Mecanismul de revizuire există (`FusionCouncil.revise`, voturile inițiale și cele revizuite se păstrează), dar consiliul activ face o singură rundă fără dezbatere. Dezbaterea cu reevaluare declanșată de un argument minoritar (`debate_engine`) nu e folosită în producție și nu e validată; se evaluează separat după 17.11. |
| 10 Erori AI | IMPLEMENTAT, TESTAT UNITAR | **F-23 (RIDICAT, reparat):** o excepție neașteptată dintr-un adaptor (timeout, conexiune întreruptă, JSON/câmp lipsă) oprea toată runda consiliului, deoarece doar erorile de gateway erau prinse. Acum agentul respectiv e marcat „failed", fără vot inventat, iar runda continuă (testat cu 5 tipuri de eroare). Rundele incomplete rămân „NU TRANZACȚIONA". |
| 11 Trasabilitate | IMPLEMENTAT, TESTAT UNITAR | Fiecare decizie nouă păstrează: ora, versiunea datelor (ultima lumânare), hash-ul întrebării, per agent modelul, furnizorul, latența, costul, tokenii, încercările și hash-ul cererii, plus toate voturile inițiale și revizuite (inclusiv minoritare). Doar metadate: nu intră în nicio decizie. Vetourile de risc nu apar încă (consiliul nu tranzacționează). |
| 12 Instrumente de evaluare | IMPLEMENTAT, TESTAT UNITAR | `src/bnd/council_analytics.py` (doar citire): scorboard per agent (rată, profit virtual, calibrare, HOLD corect, contribuții minoritare, pe piață și clasă), dezacord vs mișcare, botul pe reguli vs consiliu vs înclinație vs hibrid. Sub 20 de decizii încheiate raportează „orientativ". Nu modifică evaluarea activă. |

## C. Monitorizare și operare (P1, punctele 13–17)

| Punct | Stare | Ce există |
|---|---|---|
| 13 Dashboard unificat read-only | IMPLEMENTAT, TESTAT UNITAR | Aplicația de pe telefon (rezumat, conturi, drawdown, costuri, agenți, alerte) și `status.json` pentru Home Assistant (`docs/OPERARE.md`). Integrarea efectivă cu Home Assistant: NECONFIRMAT (nu am instanța). „BND Command Center Dashboard” (al GPT-6) nu a fost atins. |
| 14 Health monitoring | IMPLEMENTAT, TESTAT UNITAR | Alertă la: cont oprit, rulare veche (36 h), discrepanță contabilă, prețuri vechi (6 h), agent eșuat, rulare programată eșuată, sold AI mic. Date lipsă pe piață: `missing_data` din raportul zilnic, nu și alertă separată. Blocaje de sincronizare între ramuri: NECONFIRMAT. |
| 15 Alerte inteligente | IMPLEMENTAT, TESTAT UNITAR | `alerting.py`: fără repetiții (12 h), reapariție după rezolvare, reîncercare dacă trimiterea eșuează, nimic fără `NTFY_TOPIC`. Livrarea reală pe telefon: NECONFIRMAT până când secretul e setat și primește prima alertă. |
| 16 Backup/DR | IMPLEMENTAT, TESTAT UNITAR | `deploy/backup.sh` + `restore_check.py` (integritate, reconciliere, audit) + procedură în `docs/OPERARE.md`. Restaurarea pe un Proxmox real: NECONFIRMAT. |
| 17 Observabilitate | PARȚIAL | Latență, erori, tokeni, cost per model și cumulat: în registrul de modele și în aplicație, din analizele de după introducerea urmei. Nu există serie de timp a metricilor. Limitele de cost sunt mecanisme de control, nu garanții de facturare. |
