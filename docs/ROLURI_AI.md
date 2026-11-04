# Specializarea fiecărui AI și rolul propus după 1.12 (cerut de proprietar pe 4.11.2026)

Bani virtuali. Profil construit din voturile reale ale consiliului 31.10–3.11 (274 de decizii complete), din analiza
R02 (`src/bnd/ortogonalitate.py`) și din costurile reale (`costs.sqlite`). **Provizoriu:** nicio decizie nu era încă
încheiată la 5 zile, iar rezultatele pe clase se schimbă mult cu direcția pieței (dimineața GPT avea +3,3%/semnal, seara
−1,6%, după revenirea crypto). Tabelul se actualizează pe 1.12 cu deciziile încheiate; atunci se aleg rolurile.

| AI (model) | Cost 31.10–4.11 | Stil de vot | Unde a mers (provizoriu, 4.11 seara) | Independență (R02) | Rol propus după 1.12 |
|---|---:|---|---|---|---|
| **GPT** (gpt-6.1-sol) | 2,92 $ (39%) — cel mai scump | 103 SELL, 0 BUY, 62% HOLD; încredere declarată mare (0,72) | crypto pe scădere a mers dimineața, seara pe minus; memecoin ușor plus | 77% acord cu Grok — cel mai redundant cuplu | **la vot doar dacă rezultatele încheiate o justifică**; altfel înlocuit de Grok/DeepSeek (economie ~40%). Candidat: „specialist crypto” |
| **Grok** (grok-4.7) | 1,37 $ (18%) | 90 SELL, 1 BUY, 67% HOLD; încredere mică (0,48) | armament 8/8 corecte; crypto ca GPT | aproape aceleași voturi ca GPT | **agentul de știri / postări X** (punctul 3e): are acces natural la X; la vot doar unul dintre GPT și Grok |
| **Claude** (claude-opus-5.5) | 1,88 $ (25%) | 95% HOLD (13 voturi în 274 de decizii); încredere mică (0,46) | puținele voturi, pe plus (+0,75%) | scoaterea lui nu schimbă niciodată direcția consiliului | **avocatul diavolului** (motive împotriva pozițiilor mari, fără vot) și **rezumatul zilnic pentru proprietar** |
| **Gemini** (gemini-4-argon) | 0,68 $ (9%) | echilibrat: 79 SELL, 8 BUY, 68% HOLD; încredere 0,62 | cel mai bun acum: +0,12%/semnal, 45% corecte; armament 17/19, indici, acțiuni | moderat independent | **rămâne la vot** — acțiuni, armament, indici |
| **DeepSeek** (deepseek-v4-pro) | 0,59 $ (8%) — cel mai ieftin | cel mai activ: 165 SELL, 28 BUY, doar 30% HOLD | armament 23/28, indici, memecoin; slab pe crypto mari | cel mai independent: fără el direcția se schimbă în ~20% din cazuri | **rămâne la vot** (aduce diversitate ieftin); poate și **verificatorul de date** |

Pe scurt: Gemini și DeepSeek sunt ieftini și aduc ceva propriu; GPT și Grok spun aproape același lucru (păstrăm unul la
vot); Claude e prea prudent ca votant, dar potrivit pentru roluri de control. Toate rolurile noi costă apeluri AI, deci
primesc buget separat și rămân doar dacă dovedesc un folos. Decizia finală: proprietarul, pe 1.12.
