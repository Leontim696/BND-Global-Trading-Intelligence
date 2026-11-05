# Versiunile experimentelor și ale conturilor simulate

Cerut în auditul GPT din 5.11.2026 (punctul 4): orice experiment al cărui comportament se schimbă după pornire primește
o versiune nouă, cu momentul activării, iar rezultatele de dinainte rămân separate. Raportul final (1.12) arată pentru
fiecare cont ce versiune a produs rezultatul. Sursa de adevăr în cod: `VERSIONS` din `src/bnd/formations.py` și
`src/bnd/intraday_live.py`. Contul oficial și contul de control NU au fost atinse.

| Cont / experiment | Versiune | Activă din (UTC) | Ce s-a schimbat | Efect asupra datelor deja strânse |
|---|---|---|---|---|
| P26 geamănul lui P24 la 10 min | v1 | 2026-11-05 05:50 | pornire; istoric zilnic doar din date-piete | 43 din 100 de piețe (acțiuni, apărare, 5 ETF-uri/mărfuri, 4 valute) nu puteau primi ordine |
| P26 | v2 | 2026-11-05, prima rulare a buclei după PR | istoric zilnic pentru toate cele 100 de piețe + diagnostic pe motive (fără istoric / fără lumânări / bursă închisă / date vechi) | rezultatul v1 (≈2 ore, ordine doar pe 57 de piețe) se raportează separat; comparația P26–P24 se face din v2 |
| P27 / P28 (conturile) | v1 | 2026-11-05 05:50 | neschimbate (doar împărțirea codului: aceeași decizie, testată identic) | niciunul |
| E-017 / E-018 (test pe istoric) | v1 „simplificat” | 2026-11-05 05:37 | toate monedele egal ponderate, fără stop, fără selecția celor 10 | rezultatele păstrate în registru (respinse) cu eticheta „simplificat” |
| E-017 / E-018 | v2 „motor” | 2026-11-05 (run 41984069185) | același motor, aceleași funcții, aceleași stopuri, costuri, selecție și oprire de siguranță ca P27/P28; plus o variantă de diagnostic fără oprire | E-017 −6,9% / E-018 −5,1% (oprite la −5% într-o zi); fără oprire −87% / −95%; adăugate ca notă, v1 păstrat |
| P29 / P31 / P33 | v1 | 2026-11-05 06:30 | pornire; percentila număra egalitățile „sub” (istoric constant → 1,0) | pe datele din 5.11 nicio decizie diferită față de v2 (verificat) |
| P29 / P31 / P33 | v2 | 2026-11-05 22:50 (rularea de noapte) | percentilă cu rang mediu; istoric constant = neutru | niciunul |

Optimizare fără efect asupra rezultatelor: `PaperEngine.open_orders()` citește doar ordinele PENDING/PARTIAL în loc să
filtreze tot istoricul (aceleași rânduri, aceeași ordine), ca buclele la 10 minute să nu încetinească pe măsură ce cresc.
