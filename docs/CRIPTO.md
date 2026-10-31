# Bot cripto virtual condus de consiliul AI

**Doar bani virtuali.** Date gratuite și publice (prețuri zilnice Yahoo), fără furnizor plătit.

- Monede: BITCOIN, ETHEREUM, SOLANA, BNB, XRP.
- Decizia: consiliul AI zilnic (5 agenți) votează pe fiecare monedă. Semnal = semn(BUY−SELL) × min(1, |BUY−SELL|/2): 1 vot net = jumătate de poziție, 2 sau mai multe = poziție întreagă; egalitate sau doar HOLD = fără poziție. Poate merge și short.
- Execuția: aceeași mașinărie ca botul principal (`paper_runner`, strategia `ai_council`): dimensionare după volatilitate, stop la 3×ATR, limite de risc, oprire de siguranță, marjă 50% pe crypto, finanțare 5%/an. Leverage maxim 2x, maxim 60% dintr-o singură monedă.
- O monedă fără decizie în ziua respectivă își păstrează poziția (nu se închide din greșeală).
- Nu face apeluri AI proprii: citește deciziile consiliului (`crypto_signals.py`). Costul suplimentar e doar al celor 3 monede noi în consiliu (~0,08 $/zi).
- Cont separat pe ramura `crypto-trading`, rulează zilnic la 22:10 UTC, după consiliu (21:40 UTC). Consiliul rulează automat doar până pe 16.11.2026; după aceea contul își păstrează pozițiile.
- Pornire (o singură dată, manual): Actions → „Bot cripto virtual (AI)” → capital în dolari (10.000 € la cursul EUR/USD 1,1183 din 30.10 ≈ 11183).
- Mai târziu, dacă e cazul: funding/date on-chain (`funding.py` există, dar Binance poate fi blocat din SUA).

Un rezultat bun în 16 zile nu dovedește un avantaj: cu puține decizii diferențele pot fi noroc.

## Cont unic AI pe toate piețele

`bot-ai-unificat.yml` (cont pe ramura `ai-unificat`, 22:15 UTC) face același lucru pe **toate cele 13 piețe** ale consiliului (indici, aur, argint, petrol, forex, obligațiuni, crypto), într-un singur cont: banii se duc unde sunt semnale. Limite: leverage 2x, maxim 40% într-o piață și 60% într-o clasă. Conturile existente (regulile matematice și criptoul) rămân pornite ca termen de comparație până pe 16.11; după aceea se poate păstra doar contul unic.
