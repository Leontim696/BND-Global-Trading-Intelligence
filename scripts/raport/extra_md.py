import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import longshort as L
W = Path(sys.argv[1])
fs = json.load(open(W / "formsec.json")); ls = json.load(open(W / "levsim.json"))
f2 = lambda x: f"{x:,.2f}"
out = []
out.append("## Long față de short (cerut pe 4.11)\n")
out.append("Câștig/pierdere realizată + nerealizată pe fiecare parte, din execuțiile reale până la sfârșitul zilei de 16.11 "
           "(prețuri de închidere 16.11; fără dobânzi și finanțare, de aceea totalul diferă puțin de capital). "
           "„Câștigătoare/pierzătoare” = poziții (de la deschidere până la închidere sau până azi).\n")
out.append("| Cont | Long net $ | Long câștig./pierz. | Short net $ | Short câștig./pierz. |")
out.append("|---|---:|---:|---:|---:|")
for name, path in (("Contul unic (oficial)", W / "unic.sqlite"), ("Reguli matematice (control)", W / "control.sqlite")):
    a = L.analyse(path)["sides"]
    out.append(f"| {name} | {f2(a['long']['net'])} | {a['long']['win']}/{a['long']['loss']} | {f2(a['short']['net'])} | {a['short']['win']}/{a['short']['loss']} |")
out.append("")
a = L.analyse(W / "unic.sqlite")
out.append("Contul unic pe clase de active (realizat + nerealizat, $):\n")
out.append("| Clasă | Long | Short |"); out.append("|---|---:|---:|")
for c, d in sorted(a["by_class"].items()):
    out.append(f"| {c} | {f2(d['long'])} | {f2(d['short'])} |")
b = L.market_baseline(W / "unic.sqlite")
out.append(f"\n**Comparația cu piața (ca să nu ne păcălim):** pe aceleași {b['markets']} piețe tranzacționate de contul unic, "
           f"„long pe tot” (ponderi egale, 30.10 → 16.11) ar fi adus {b['long_all_pct']:+.2f}%, iar „short pe tot” {b['short_all_pct']:+.2f}%; "
           f"{b['down']} piețe au scăzut și doar {b['up']} au urcat. Cea mai mare parte a câștigului pe short vine deci din faptul că piața a scăzut "
           "în aceste două săptămâni, nu neapărat dintr-o alegere mai bună. Contul de control „Reguli matematice” arată același tipar. "
           "Long-urile contului unic au pierdut puțin pe crypto, indici și mărfuri și au câștigat doar pe acțiuni și forex. "
           "Pe formații, coloanele Long/Short din clasamentul de mai jos arată același lucru.\n")
out.append("## Simulare pe istoric: prudent / ca acum / agresiv și 5x / 10x pe long și pe short (cerută pe 3.11 și 4.11)\n")
out.append(f"Gratuit, fără apeluri AI, fără să atingă vreun cont: semnalele regulii (regime_switch) pe {len(ls['piete'])} piețe din date-piete "
           f"({', '.join(ls['piete'])}), zilnic, {ls['de_la']} → {ls['pana_la']} (~3 ani). Variantele prudent/acum/agresiv = long+short cu "
           "expunere brută 0,6× / 1,2× / 2,4× împărțită egal pe piețe; finanțare 5%/an pe expunerea peste capital. Variantele 5x/10x: "
           "fiecare piață primește 1/13 din cont și deschide doar pe partea cerută, la 5x sau 10x; lichidare la −18% (5x) / −9% (10x) "
           "mișcare adversă într-o zi; **o felie lichidată NU se reface (oprire)**; finanțare 5%/an pe suma împrumutată. Fără funding crypto și "
           "fără chiria titlurilor la short (nu avem date pe 3 ani).\n")
out.append("| Variantă | Câștig mediu / lună | Cea mai bună zi | Cea mai rea zi | Pierdere maximă | Total 3 ani | Lichidări | Finanțare | Cont rămas |")
out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for r in ls["rezultate"]:
    out.append(f"| {r['varianta']} | {r['castig_mediu_luna_pct']:+.2f}% | {r['cea_mai_buna_zi_pct']:+.2f}% | {r['cea_mai_rea_zi_pct']:+.2f}% | "
               f"{r['pierdere_maxima_pct']:.1f}% | {r['total_pct']:+.1f}% | {r.get('lichidari', '–')} | {r['cost_finantare_pct']:.1f}% | "
               f"{(str(round(r['cont_ramas_pct'])) + '%') if 'cont_ramas_pct' in r else '–'} |")
lev = [r for r in ls["rezultate"] if "lichidari" in r]
out.append("\n| Variantă | În lunile cu S&P 500 în creștere | În lunile cu S&P 500 în scădere |"); out.append("|---|---:|---:|")
for r in lev:
    out.append(f"| {r['varianta']} | {r['in_luni_cu_SP500_in_crestere_pct']:+.1f} puncte | {r['in_luni_cu_SP500_in_scadere_pct']:+.1f} puncte |")
out.append("\n**De ce leverage-ul mare golește contul:** câștigul mediu pe lună crește cu leverage-ul (de la +0,4% la +2,9%), dar totalul pe 3 ani "
           "scade sau devine negativ. La 10x, o zi cu −9% împotrivă înseamnă lichidarea feliei (s-a întâmplat de 7 ori pe long și de 7 ori pe short), "
           "iar o zi cu −10% coboară contul cu 100% din miză, după care +10% nu mai recuperează nimic (pierderea e asimetrică: după −50% îți "
           "trebuie +100%). Finanțarea la 5x/10x a costat 26–31% din cont pe long. Câștigurile de 2–10% pe zi nu sunt realiste: cele mai bune zile "
           "de mai sus vin împreună cu zile la fel de rele, iar pierderea maximă la 10x a fost de 85–93%. Pe 3 ani, regula singură n-a câștigat "
           "nici doar pe long, nici doar pe short cu leverage mare; varianta prudentă a avut cel mai bun raport câștig/pierdere maximă.\n")
out.append("## Formații AI: clasament de la pornire (4.11) până la 16.11 (cerut pe 4.11)\n")
o = fs["official"]
out.append(f"Reper: contul oficial {o['return_pct']:+.2f}% de la 31.10, pierdere maximă {o['dd']:.2f}%. Criteriul fixat în docs/CONTURI.md: "
           "câștigă randamentul cel mai mare, DOAR dacă pierderea maximă ≤ cea a contului oficial și formația a câștigat și în zilele de creștere "
           "ale pieței (S&P 500 în urcare). P36/P37 au pornit pe 16.11 și nu intră încă.\n")
out.append("| # | Formație | Randament | Câștig $ | Pierdere max. | Câștig în zilele de creștere $ | Long net $ | Short net $ | Trece criteriul |")
out.append("|---:|---|---:|---:|---:|---:|---:|---:|---|")
i = 0
for r in fs["rank"]:
    if r["days"] < 2:
        continue
    i += 1
    out.append(f"| {i} | {r['key']} ({r['title']}) | {r['return_pct']:+.2f}% | {f2(r['pnl'])} | {r['dd']:.2f}% | {f2(r['up_gain'])} | "
               f"{f2(r['long_net'])} | {f2(r['short_net'])} | {'da' if r['eligible'] else 'nu'} |")
elig = [r for r in fs["rank"] if r["eligible"] and r["days"] >= 2]
out.append(f"\nDupă criteriu ar ieși acum **{elig[0]['key']}** ({elig[0]['return_pct']:+.2f}%, pierdere maximă {elig[0]['dd']:.2f}%), "
           f"singura dintre primele care a câștigat și în zilele de creștere; doar {len(elig)} formații trec ambele condiții. Primele din clasament "
           "(P35 totul pe short ×2, P34 oficialul ×2) au câștigat mult doar pentru că piața a scăzut și au pierdut în zilele de creștere. "
           "Cu 40 de conturi comparate, unul iese primul și din noroc; după ~12 zile e doar un indiciu.\n")
out.append("## Leverage pe formații: ce ar „alege” fiecare (regula fixată în docs/CONTURI.md)\n")
out.append("Din deciziile încheiate ale consiliului (orizont 5 zile, până la 16.11), semnalele fiecărei formații simulate la 2x / 5x / 10x, "
           "100 $ pe semnal, lichidare la −18% / −9%, finanțare 5%/an. Regula: L > 2 doar cu ≥ 20 decizii încheiate pe direcție, reușită > 55%, "
           "p < 0,05, fără lichidare la L, pierdere maximă ≤ 25% și câștig peste 2x; dintre nivelurile care trec, cel mai mic. "
           "**Atenție:** filtrele de funding, sursele noi (P17, P20, P29–P33), take profit/stop și reciclarea nu se pot reface din voturi, așa "
           "că acele formații apar cu semnalele de bază; deciziile de pe zile consecutive cu orizont de 5 zile se suprapun, deci p-urile sunt "
           "prea optimiste. E doar o recomandare: limitele conturilor nu se schimbă.\n")
out.append("| Formație | Long: decizii / reușită / alege | Short: decizii / reușită / alege | Short: lichidări 5x / 10x |")
out.append("|---|---|---|---|")
for r in fs["lev"]:
    if "note" in r:
        out.append(f"| {r['key']} | {r['note']} | | |"); continue
    lo, sh = r["long"], r["short"]
    rr = lambda x: f"{x['n']} / {(round(x['rata']) if x['rata'] is not None else 0)}% / {x['alege']}x"
    out.append(f"| {r['key']} | {rr(lo)} | {rr(sh)} | {sh['lichidari']['5']} / {sh['lichidari']['10']} |")
out.append("\nPe long, nicio formație nu trece pragul (cele mai multe au sub 55% reușită sau sub 20 de decizii): rămân la 2x. Pe short, "
           "aproape toate ar „alege” 5x, dar asta reflectă două săptămâni de piață în scădere, nu o abilitate dovedită: pe 3 ani de istoric, "
           "5x doar short a pierdut 52% (vezi simularea de mai sus). Recomandarea mea: nicio creștere de leverage până nu se vede același "
           "rezultat și într-o piață în creștere.\n")
import os
end = os.environ.get("BND_END", "2026-11-16")
end_ro = f"{int(end[8:10])}.{end[5:7]}"
text = "\n".join(out).replace("pornit pe 16.11", "pornit pe §§").replace("16.11", end_ro).replace("§§", "16.11")
Path(W / "extra.md").write_text(text, encoding="utf-8")
print("ok", len(out))
