# Planul pentru versiunea următoare (după 1.12.2026)

Pagina unică cu tot ce e de implementat sau de decis după testul oficial (31.10–30.11.2026). Detaliile stau în
documentele indicate; aici e doar lista completă și ordinea. Până pe 30.11 nu se schimbă nimic în test.
Regulile rămân: doar bani virtuali până la mandatul explicit al proprietarului, un branch și un PR pe schimbare,
merge doar cu CI verde, totul întâi în umbră sau într-un cont paralel.

## 1. Deciziile proprietarului (pe 1.12, din raportul final)

Sursa: [`DUPA_30_11.md`](DUPA_30_11.md) și raportul final din 1.12.

- Contul condus de consiliu sau „Reguli matematice” (1); formația câștigătoare și ce AI rămân (3g, 3l).
- Leverage pe long / short (recomandare din raport; limitele nu se schimbă automat).
- Long față de short (P35, P36, P37): variantă doar-short / short mai mare sau nu.
- Take profit și reciclarea (P12–P15, P24–P25).
- Piețe: înlocuitorul TON (2), indici noi (3), curățarea piețelor slabe (3b), Germania (3i).
- Consiliul: două runde pe zi sau variantele A/B pentru crypto (3j), decizii la câteva ore (3f), indicatori noi (3c).
- Agentul de știri și sursele noi de date (3e, 3h).

## 2. Ce se îmbină sau rulează automat

- 2.12: reparațiile #244 (prețul memecoin-urilor) și #245 (volatilitatea); auditul de securitate.
- 1.12: Smart-Money revine (limita Solana Tracker se resetează); căutarea se reduce la ~80 de cereri pe zi ca să ajungă
  cheia gratuită toată luna (2.500 / lună).

## 3. De implementat, în ordine

1. **Reparațiile rămase din test**: semnalul regulii trimis consiliului (regime_switch în loc de SMA 20/50, 3d);
   notificările de pe telefon — mesajul despre consiliu trimis de două ori (a doua oară cu 0,00 $) și rubrica veche
   „Planuri azi” din rezumatul de dimineață.
2. **Calitatea și vechimea datelor** (§4 din [`ANALIZA_DAILY_STOCK_ANALYSIS.md`](ANALIZA_DAILY_STOCK_ANALYSIS.md)).
3. **Risc long/short cu acțiuni explicite** (§6 de acolo; E.5 din [`BND_2_0_CERINTE.md`](BND_2_0_CERINTE.md)).
4. **Evaluarea fiecărei opinii AI și istoricul deciziilor** (§2, §3, §5 de acolo; D.5–D.8 din BND 2.0: MAE/MFE,
   calibrare, degradare, registrul oportunităților respinse).
5. **Filtrul de selecție și ieșirile** (D.1–D.4, D.9–D.11 din BND 2.0); numerarul ca alocare validă (E.1).
6. **Funcțiile noi**: Chart Screener, News Agent, Time Machine (B din BND 2.0), cu limita pe grupuri corelate (3k).
7. **Conturi paralele noi**: copierea walleturilor Smart-Money (3m); studiul pe lumânări de 1/3/5 minute (cere acces
   de citire la data-api.binance.vision).
8. **Botul autonom** (C din BND 2.0): mandat, portofoliu, alocator, contract de decizie, adaptor broker fără retrageri,
   ciclul ordinului, reconciliere, supraveghere; contabilitate, control de pe telefon, explicația alocării (E.2–E.6).
9. **Prima versiune reală**: doar cerințele din E.7 („obligatoriu înainte de LIVE”), raportul din E.8 și activarea
   explicită de către proprietar. Mutarea pe Proxmox (7 din DUPA_30_11) e o decizie separată.

## 4. Cum se validează fiecare pas

Teste pentru cazurile cerute, apoi rulare în umbră sau în cont paralel pe aceleași date și costuri ca versiunea de
acum; raport cu profit net, pierdere maximă, expunere, costuri AI și incertitudinea rezultatelor. Fără obiectiv de
95% tranzacții câștigătoare (D.10). PR-urile externe: doar notate în [`PR_EXTERNE.md`](PR_EXTERNE.md).
