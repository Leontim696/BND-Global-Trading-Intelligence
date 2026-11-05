"""P29–P33 (5.11): semnalele de bază ale lui P17 filtrate cu sursele noi (poziționare, DVOL, COT, stablecoin-uri)."""

import csv

from src.bnd import formations as fm


def _write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _surse(tmp_path, ls_last=3.0, dvol_last=60.0, gold_net=900.0, jpy_net=900.0, stable_last=90.0):
    days = [f"2026-{(i // 28) + 7:02d}-{(i % 28) + 1:02d}" for i in range(100)]
    _write(tmp_path / "pozitionare" / "BITCOIN.csv", ["date", "open_interest_usd", "volum_usd", "long_short_conturi",
                                                       "taker_cumparare", "taker_vanzare"],
           [(d, 1, 1, 1.0 + (i % 10) / 10, 1, 1) for i, d in enumerate(days[:-1])] + [(days[-1], 1, 1, ls_last, 1, 1)])
    _write(tmp_path / "deribit" / "dvol_BTC.csv", ["date", "dvol"],
           [(d, 40.0) for d in days[:-1]] + [(days[-1], dvol_last)])
    for name, last in (("GOLD", gold_net), ("USDJPY", jpy_net)):
        _write(tmp_path / "cot" / f"{name}.csv", ["date", "open_interest", "spec_long", "spec_short", "spec_net",
                                                 "comerciali_long", "comerciali_short"],
               [(d, 1, 1, 1, float(i), 1, 1) for i, d in enumerate(days[:-1])] + [(days[-1], 1, 1, 1, last, 1, 1)])
    _write(tmp_path / "defi" / "stablecoins.csv", ["date", "total_usd"],
           [(d, 100.0) for d in days[:-1]] + [(days[-1], stable_last)])
    return fm.load_surse(tmp_path)


def test_formatiile_noi():
    by = {f["key"]: f for f in fm.FORMATIONS}
    assert [by[k]["filter"] for k in ("p29-pozitionare-futures", "p30-volatilitate-optiuni", "p31-cot-speculatori",
                                     "p32-stablecoins", "p33-toate-sursele")] == \
        ["pozitionare", "dvol", "cot", "stablecoins", "toate"]
    assert all(by[k]["strategy"] == "ai_council" and "settings" not in by[k] for k in by if by[k]["kind"] == "surse")


def test_incarcarea_indicatorilor(tmp_path):
    s = _surse(tmp_path)
    assert s["pozitionare"]["BITCOIN"] == 1.0                     # 3,0 e cel mai mare raport din istoric
    assert abs(s["dvol_ratio"] - 1.5) < 1e-9
    assert s["cot"]["GOLD"] == 1.0 and s["cot"]["USDJPY"] == 0.0  # perechea cu dolarul în față e inversată
    assert abs(s["stable_change"] + 0.1) < 1e-9
    assert fm.load_surse(tmp_path / "lipsa") == {}


def test_filtrele(tmp_path):
    s = _surse(tmp_path)
    assert fm.surse_filter("BITCOIN", 1.0, "pozitionare", s) == 0.0       # mulțimea pe long: fără long nou
    assert fm.surse_filter("BITCOIN", -1.0, "pozitionare", s) == -1.0
    assert fm.surse_filter("ETHEREUM", 0.8, "dvol", s) == 0.4              # DVOL sare: crypto × 0,5
    assert fm.surse_filter("GOLD", 0.8, "dvol", s) == 0.8                  # nu atinge ce nu e crypto
    assert fm.surse_filter("GOLD", 1.0, "cot", s) == 0.0
    assert fm.surse_filter("USDJPY", -1.0, "cot", s) == 0.0                # speculatori long JPY = USDJPY short aglomerat
    assert fm.surse_filter("SOLANA", 1.0, "stablecoins", s) == 0.0 and fm.surse_filter("SOLANA", -1.0, "stablecoins", s) == -1.0
    assert fm.surse_filter("BITCOIN", -1.0, "toate", s) == -0.5
    calm = _surse(tmp_path / "calm", ls_last=1.45, dvol_last=40.0, gold_net=50.0, jpy_net=50.0, stable_last=110.0)
    assert all(fm.surse_filter(m, 0.7, "toate", calm) == 0.7 for m in ("BITCOIN", "GOLD", "USDJPY", "SOLANA"))


def test_semnalele_din_voturi(tmp_path):
    s = _surse(tmp_path)
    f = {"kind": "surse", "filter": "pozitionare"}
    votes = {"BITCOIN": {a: "BUY" for a in fm.AGENTS}}
    out = fm.signals_for(f, votes, {}, {"BITCOIN": 1.0, "GOLD": -1.0}, surse=s)
    assert out == {"BITCOIN": 0.0, "GOLD": -1.0}
    assert fm.signals_for(f, votes, {}, {"BITCOIN": 1.0}, surse={}) == {"BITCOIN": 1.0}


def test_percentila_egalitati_v2():
    p = fm._percentile
    assert p([1.0] * 90) is None                                   # istoric constant: neinformativ, fără filtru
    assert fm._crowd_clip(1.0, p([1.0] * 90)) == 1.0               # v1 dădea 1,0 și bloca longul
    assert p([1.0] * 89 + [2.0]) == 1.0 and p([1.0] * 89 + [0.5]) == 0.0   # salt după istoric constant = extremă reală
    assert abs(p([1.0] * 45 + [2.0] * 45) - (45 + 0.5 * 44) / 89) < 1e-12 # multe egalități: rang mediu
    assert 0.1 < p([1.0, 2.0] * 45) < 0.9                          # egalități alternante: nu e extremă
    assert p(list(range(90))) == 1.0 and p(list(range(89)) + [-5]) == 0.0  # extreme reale
    assert p([1.0] * 19) is None                                   # istoric insuficient
