# Conturile virtuale

Trei portofolii separate, fără capital comun (detalii în `docs/AUDIT_P0.md`, secțiunea A3). Se compară prin randament în procente, nu prin valoare absolută: toate trei sunt acum etichetate USD, iar prețurile sunt în USD, fără conversie. Contul „Reguli” are 10.000 USD (a fost etichetat EUR până pe 31.10.2026, schimbare de etichetă auditată, fără conversie), celelalte două 11.183 USD (10.000 € la 1,1183 la creare).

Verificarea contabilă independentă: `python -m src.bnd.reconcile --state paper.sqlite` (cod de ieșire 0 = corect).

## Long, short și leverage pe cont (31.10.2026)
| Cont | Direcții | Leverage permis | Finanțare |
|---|---|---|---|
| Reguli (`paper-trading`) | doar long (`--no-shorts`) | 1x | 0% |
| Reguli long/short (`reguli-ls`, nou, nepornit) | long și short | până la 3x | 5%/an |
| Cripto AI | long și short | până la 2x | 5%/an |
| AI unificat | long și short | până la 2x | 5%/an |

În conturile AI, „vinde" = poziție short (câștigi dacă prețul scade), iar „cumpără" = long. Leverage-ul e un plafon, nu o țintă: expunerea reală vine din dimensionarea după volatilitate și din semnale (de exemplu AI unificat plănuia pe 1.11 long 12% și short 127%, adică expunere brută de 1,39x). Contul „Reguli" e conservator din setările de creare și nu poate fi schimbat fără cont nou; `reguli-ls.yml` pornește un cont-frate cu aceeași strategie de reguli, dar cu short și leverage.

## Cont unic (din 1.11.2026)
Cele patru conturi (Reguli, Reguli long/short, Cripto AI, AI unificat) au fost înlocuite de **un singur cont**, `cont-unic` (workflow „Cont unic (virtual)”, 22:25 UTC, după consiliu). Cele patru vechi au fost oprite după primele rulări, fără nicio tranzacție executată, și rămân ca arhivă (starea lor nu mai e actualizată).

Cum decide contul unic, pe fiecare dintre cele 71 de piețe (ETF/forex, SOL/BNB/XRP și 45 de monede din top 50 cripto):
- semnal final = ½ × semnalul regulilor (`regime_switch`) + ½ × semnalul consiliului AI (net BUY−SELL, 1 vot net = 0,5, 2+ = 1);
- acord între reguli și AI: poziție întreagă; dezacord: se anulează; fără vot AI azi (piețe pe care consiliul nu votează): decid doar regulile;
- poate face long și short; leverage maxim 2x; maxim 25% într-o piață și 60% într-o clasă (memecoin-urile au clasă proprie și alunecare de 3x mai mare); țintă de volatilitate 15%; stop 3×ATR; finanțare 5%/an.
Capital: 11.183 USD (10.000 € la 1,1183, ca la celelalte). Pornire manuală, o singură dată: Actions → „Cont unic (virtual)” → Run workflow, capital `11183`, reset gol. Pentru alt leverage se poate da la creare setarea `--max-leverage 3` (setările se îngheață la creare).
