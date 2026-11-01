import json

from src.bnd import drive_pack as dp

REPORT = """# Consiliul AI în umbră, 2026-11-01 05:46 UTC

## SP500: **NU TRANZACȚIONA** (fără înclinație)
Preț 755.7200 (închidere 2026-10-30); regula simplă a botului: cumpără; cost 0.026 $.

| Agent | Vot | Încredere | Motiv |
|---|---|---:|---|
| gpt | HOLD | 0.80 | Semnale mixte \\| nu e clar. |
| claude | BUY | 0.55 | RSI mic, posibil rebound. |

## BITCOIN: **VINDE** (înclină spre vânzare)
Preț 60000.0000 (închidere 2026-10-30); regula simplă a botului: vinde; cost 0.027 $.

| Agent | Vot | Încredere | Motiv |
|---|---|---:|---|
| gpt | SELL | 0.70 | Sub SMA50. |
"""


def test_parse_council_reads_decisions_prices_and_every_agents_reason():
    markets = dp.parse_council(REPORT)
    assert [m["market"] for m in markets] == ["SP500", "BITCOIN"]
    sp = markets[0]
    assert sp["decision"] == "NU TRANZACȚIONA" and sp["price"] == "755.7200" and sp["bot"] == "cumpără"
    assert [v["agent"] for v in sp["votes"]] == ["gpt", "claude"] and sp["votes"][0]["reason"] == "Semnale mixte | nu e clar."
    assert markets[1]["lean"] == "înclină spre vânzare"


def test_council_docs_group_by_category_and_keep_every_reason():
    docs = dp.council_docs(dp.parse_council(REPORT), "2026-11-01")
    titles = [t for t, _ in docs]
    assert titles == ["02 Consiliu 2026-11-01 - Indici bursieri", "03 Consiliu 2026-11-01 - Crypto"]
    assert "Semnale mixte | nu e clar." in docs[0][1] and "RSI mic" in docs[0][1] and "/" not in titles[0]
    assert "Sub SMA50." in docs[1][1] and docs[1][1].count("<h3>") == 1


def test_big_groups_are_split_into_documents_under_the_size_limit(monkeypatch):
    monkeypatch.setattr(dp, "MAX_DOC_CHARS", 3000)
    many = "\n".join(f"## {n}: **NU TRANZACȚIONA**\n\n| Agent | Vot | Încredere | Motiv |\n|---|---|---:|---|\n| gpt | HOLD | 0.5 | {'x' * 800} |\n"
                     for n in ("BNB", "XRP", "DOGE_", "ADA", "LINK"))
    docs = dp.council_docs(dp.parse_council(many.replace("DOGE_", "TRX")), "2026-11-01")
    assert len(docs) >= 2 and all("partea" in t for t, _ in docs)


def test_investments_explain_each_order_with_rule_council_and_combined_signal():
    run = {"equity": 11183.0, "cash": 11183.0, "currency": "USD", "gross_leverage": 0.0, "strategy": "hibrid",
           "settings": {"max_leverage": 2.0, "max_weight": 0.25, "max_sector": 60.0, "portfolio_vol": 15.0},
           "signals": {"GOLD": 0.5, "EURUSD": -1.0}, "weights": {},
           "orders": [{"market": "GOLD", "weight_from": 0.0, "weight_to": 0.0256, "side": "BUY", "quantity": 0.8, "price": 355.78,
                       "stop_loss": 337.1, "status": "PENDING", "risk_capped": False},
                      {"market": "EURUSD", "weight_from": 0.0, "weight_to": -0.07, "side": "SELL", "quantity": 1333.0,
                       "price": 1.16, "stop_loss": None, "status": "PENDING", "risk_capped": True}]}
    page = dp.investments_html("2026-11-01", run, {"GOLD": 0.0, "EURUSD": -1.0}, {"GOLD": 0, "EURUSD": -2})
    assert "regulile (tendință/regim) dau semnal +1.00" in page            # 2*0.5 - 0.0
    assert "consiliul dă semnal -1.00 (voturi nete -2)" in page
    assert "semnalul combinat (50% reguli + 50% consiliu) e -1.00" in page
    assert "limitată de plafonul de risc" in page and "vinde (short)" in page


def test_merge_reports_keeps_the_first_decision_per_market():
    second = REPORT.replace("VINDE", "CUMPĂRĂ").replace("SELL", "BUY") + \
        "\n## ETHEREUM: **VINDE**\nPreț 1.0 (x); regula simplă a botului: vinde; cost 0.0 $.\n\n| Agent | Vot | Încredere | Motiv |\n|---|---|---:|---|\n| gpt | SELL | 0.6 | m |\n"
    merged = dp.parse_council(dp.merge_reports([REPORT, second]))
    assert [m["market"] for m in merged] == ["SP500", "BITCOIN", "ETHEREUM"]
    assert merged[1]["decision"] == "VINDE"


def test_build_day_writes_files(tmp_path):
    names, state = dp.build_day("2026-11-01", REPORT, None, {}, tmp_path / "o")
    assert names[0] == "00 Rezumat 2026-11-01" and all((tmp_path / "o" / f"{n}.html").exists() for n in names)
    assert state["markets"] == ["BITCOIN", "SP500"]


def test_second_run_of_the_same_day_only_adds_new_markets_and_a_changed_account(tmp_path):
    more = REPORT + "\n## ETHEREUM: **VINDE**\nPreț 1.0 (x); regula simplă a botului: vinde; cost 0.0 $.\n\n| Agent | Vot | Încredere | Motiv |\n|---|---|---:|---|\n| gpt | SELL | 0.6 | m |\n"
    run = {"equity": 100.0, "orders": [], "weights": {}, "signals": {}, "currency": "USD", "settings": {}}
    first, state = dp.build_day("2026-11-01", REPORT, run, {}, tmp_path / "a")
    assert any(n.startswith("01 Investiții") for n in first)
    second, state2 = dp.build_day("2026-11-01", more, run, {}, tmp_path / "b", state=state, suffix=" (seara)")
    assert not any(n.startswith(("00 Rezumat", "01 Investiții")) for n in second)       # cont neschimbat, fără rezumat nou
    assert second == ["12 Consiliu 2026-11-01 (seara) - Crypto"] and state2["markets"] == ["BITCOIN", "ETHEREUM", "SP500"]
    changed = dict(run, equity=105.0)
    third, _ = dp.build_day("2026-11-01", more, changed, {}, tmp_path / "c", state=state2, suffix=" (actualizat)")
    assert third == ["01 Investiții 2026-11-01 (actualizat)"]


def test_cli_state_file_roundtrip(tmp_path):
    council, state = tmp_path / "c.md", tmp_path / "s.json"
    council.write_text(REPORT)
    args = ["--day", "2026-11-01", "--council", str(council), "--out", str(tmp_path / "o"), "--state", str(state)]
    assert dp.main(args) == 0 and not state.exists()                    # fără --mark-uploaded nu se scrie nimic
    assert dp.main(args + ["--mark-uploaded"]) == 0
    assert json.loads(state.read_text())["2026-11-01"]["markets"] == ["BITCOIN", "SP500"]
    again = ["--day", "2026-11-01", "--council", str(council), "--out", str(tmp_path / "o2"), "--state", str(state)]
    assert dp.main(again) == 0 and list((tmp_path / "o2").glob("*.html")) == []          # nimic nou de urcat
