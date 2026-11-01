from src.bnd import smart_money_discovery as sd

MINT = "So11111111111111111111111111111111111111112"


def test_shape_reports_field_names_but_never_values():
    info = sd.shape({"data": [{"token": {"mint": MINT, "secret": "x"}, "pnl": 5}], "page": 1})
    assert info["list_field"] == "data" and "pnl" in info["item_keys"] and "token.mint" in info["item_keys"]
    assert "x" not in str(info) and MINT not in str(info)
    assert sd.shape([{"a": 1}]) == {"type": "list", "length": 1, "keys": ["a"]}
    assert sd.shape("abc")["type"] == "str"


def test_probe_follows_a_mint_from_the_first_working_listing():
    seen = []

    def fetch(path, key):
        seen.append(path)
        if path == "/tokens/trending":
            return 200, [{"token": {"mint": MINT}}]
        if path.startswith("/first-buyers/"):
            return 200, [{"wallet": "w", "total": 1}]
        return 404, "Not found"
    report = sd.probe("k", fetch=fetch, pause=0)
    assert report["/tokens/trending"]["status"] == 200 and report["/tokens/volume"]["status"] == 404
    assert report["/first-buyers/{mint}"]["keys"] == ["total", "wallet"]
    assert any(p == f"/first-buyers/{MINT}" for p in seen)


def test_get_refuses_unknown_hosts(monkeypatch):
    import pytest
    monkeypatch.setattr(sd, "BASE_URL", "https://evil.example")
    with pytest.raises(ValueError):
        sd.get("/x", "k")


W1 = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
W2 = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
M1 = "So11111111111111111111111111111111111111112"
M2 = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def buyer(wallet, invested, realized):
    return {"wallet": wallet, "total_invested": invested, "realized": realized}


def test_tokens_are_picked_by_24h_price_change_and_deduplicated():
    lists = {"a": [{"token": {"mint": M1}, "events": {"24h": {"priceChangePercentage": 40}}},
                   {"token": {"mint": "scurt"}, "events": {}}],
             "b": [{"token": {"mint": M2}, "events": {"24h": {"priceChangePercentage": 900}}},
                   {"token": {"mint": M1}, "events": {"24h": {"priceChangePercentage": 10}}}]}
    assert sd.pick_tokens(lists) == [M2, M1] and sd.pick_tokens(lists, limit=1) == [M2]


def test_winners_need_a_small_investment_and_a_big_gain():
    buyers = [buyer(W1, 200, 3000),           # 15x, 3.000 $: da
              buyer(W2, 20000, 90000),         # sumă mare: nu
              buyer("x", 100, 5000),            # adresă invalidă
              buyer(W1[:-1] + "1", 100, 150),   # câștig mic: nu
              buyer(W2[:-1] + "2", 5, 900)]     # sub suma minimă: nu
    assert set(sd.winners_of(buyers)) == {W1}


def test_discover_ranks_repeated_winners_first_and_filters_by_full_history():
    def fetch(path, key):
        if path.startswith("/tokens/") or path == "/tokens/trending":
            return 200, [{"token": {"mint": M1}, "events": {"24h": {"priceChangePercentage": 5}}},
                         {"token": {"mint": M2}, "events": {"24h": {"priceChangePercentage": 9}}}]
        if path.startswith("/first-buyers/"):
            return 200, [buyer(W1, 100, 2500), buyer(W2, 100, 2500)] if path.endswith(M1) else [buyer(W1, 120, 3000)]
        if path.startswith("/pnl/"):
            return 200, {"summary": {"realized": 50000, "totalInvested": 9000, "totalWins": 20, "totalLosses": 40,
                                     "winPercentage": 45, "averageBuyAmount": 300}, "tokens": {str(i): 1 for i in range(12)}}
        return 404, "x"
    result = sd.discover("k", fetch=fetch, pause=0)
    assert result["tokens_checked"] == 2 and result["candidates"] == 2            # W1 pe 2 monede, W2 pe una
    row = result["rows"][0]                                                       # cel repetat e primul
    assert row[1] == W1 and row[2] == 2 and row[HEADER_INDEX("passes")] == 1
    assert result["rows"][1][1] == W2 and result["rows"][1][2] == 1


def HEADER_INDEX(name):
    return sd.HEADER.index(name)


def test_discover_survives_failing_lists():
    result = sd.discover("k", fetch=lambda p, k: (500, "eroare"), pause=0)
    assert result["rows"] == [] and result["tokens_checked"] == 0 and result["errors"]


# --- audit 01.11, P1 #4: validat ≠ candidat, fără „insider” din indicii slabe, limite API, date incomplete ------------
import json as _json

import pytest

FULL = {"summary": {"realized": 50000, "totalInvested": 9000, "totalWins": 20, "totalLosses": 40,
                    "winPercentage": 45, "averageBuyAmount": 300}, "tokens": {str(i): 1 for i in range(12)}}
THIN = {"summary": {"realized": 18000, "totalInvested": 1000, "totalWins": 1, "totalLosses": 0,
                    "winPercentage": 100, "averageBuyAmount": 1000}, "tokens": {"a": 1}}
LISTING = [{"token": {"mint": M1}, "events": {"24h": {"priceChangePercentage": 5}}},
           {"token": {"mint": M2}, "events": {"24h": {"priceChangePercentage": 9}}}]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(sd, "sleep", lambda s: None)


def make_fetch(pnl, buyers=None, calls=None):
    def fetch(path, key):
        if calls is not None:
            calls.append(path)
        if path.startswith("/tokens/"):
            return 200, LISTING
        if path.startswith("/first-buyers/"):
            return 200, buyers if buyers is not None else [buyer(W1, 100, 2500), buyer(W2, 100, 2500)]
        if path.startswith("/pnl/"):
            return pnl(path) if callable(pnl) else (200, pnl)
        return 404, "x"
    return fetch


def status_by_wallet(result):
    return {r[1]: r[-1] for r in result["rows"]}


def test_validated_candidate_and_insufficient_data_are_separated():
    def pnl(path):
        if W1 in path:
            return 200, FULL            # trece toate filtrele
        return 200, THIN                # un singur câștig: nu trece (1 monedă, 1 tranzacție)
    result = sd.discover("k", fetch=make_fetch(pnl), pause=0)
    assert status_by_wallet(result) == {W1: "validat", W2: "candidat"}
    assert result["validated"] == 1 and result["outcome"] == "ok"


def test_unreadable_or_partial_history_is_insufficient_data_never_validated():
    result = sd.discover("k", fetch=make_fetch(lambda p: (500, "eroare")), pause=0)
    assert set(status_by_wallet(result).values()) == {"date_insuficiente"}
    assert all(r[sd.HEADER.index("passes")] == 0 for r in result["rows"])
    assert all("date insuficiente" in r[sd.HEADER.index("reasons")] for r in result["rows"])
    assert result["outcome"] == "partial" and result["insufficient"] == 2
    partial = {"summary": {"realized": 99999}, "tokens": {}}                # lipsesc rata de succes / tranzacții
    result = sd.discover("k", fetch=make_fetch(partial), pause=0)
    assert set(status_by_wallet(result).values()) == {"date_insuficiente"}


def test_insider_status_is_never_given_from_first_buyer_hints():
    tokens = [M1, M2, "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"]
    listing = [{"token": {"mint": m}, "events": {"24h": {"priceChangePercentage": i}}} for i, m in enumerate(tokens)]

    def fetch(path, key):
        if path.startswith("/tokens/"):
            return 200, listing
        if path.startswith("/first-buyers/"):
            return 200, [buyer(W1, 100, 2500)]
        return 200, FULL
    result = sd.discover("k", fetch=fetch, pause=0)
    row = result["rows"][0]
    assert row[2] == 3                                          # trei câștiguri
    assert row[sd.HEADER.index("tags")] == sd.EARLY_HINT_TAG    # doar indiciu
    assert "insider" not in row[sd.HEADER.index("tags")]
    assert "tipar_insider" not in _json.dumps(result["rows"])


def test_duplicate_buyers_count_once_and_rerun_same_day_does_not_duplicate_rows(tmp_path, monkeypatch):
    buyers = [buyer(W1, 100, 2500), buyer(W1, 100, 2500), {"wallet": W2}, "gunoi", None]   # dublură + rânduri incomplete
    result = sd.discover("k", fetch=make_fetch(FULL, buyers), pause=0)
    assert [r[2] for r in result["rows"]] == [2]                # W1: o dată pe monedă (2 monede), nu 4
    monkeypatch.setenv("SOLANATRACKER_API_KEY", "k")
    monkeypatch.setattr(sd, "get", make_fetch(FULL, buyers))
    monkeypatch.setattr(sd, "PAUSE", 0)
    for _ in range(2):
        assert sd.main(["--discover", "--out", str(tmp_path)]) == 0
    lines = (tmp_path / "smart_money" / "descoperite.csv").read_text().splitlines()
    assert len(lines) == 2                                      # antet + un singur rând (id = wallet|zi)


def test_429_is_retried_with_retry_after_then_gives_up(monkeypatch):
    waits = []
    monkeypatch.setattr(sd, "sleep", waits.append)
    calls = []

    def fetch(path, key):
        calls.append(path)
        return 429, "retry_after=5"
    stats = {}
    assert sd.fetch_retry(fetch, "/x", "k", stats) == (429, "retry_after=5")
    assert len(calls) == sd.RATE_ATTEMPTS and waits == [5.0, 5.0] and stats["rate_limited"] == 3
    waits.clear()
    sd.fetch_retry(lambda p, k: (429, "retry_after=99999"), "/x", "k", {})
    assert max(waits) == sd.MAX_WAIT


def test_run_stops_after_consecutive_errors_to_protect_the_api_limit():
    calls = []

    def fetch(path, key):
        calls.append(path)
        return (200, LISTING) if path.startswith("/tokens/") else (500, "eroare")
    many = [{"token": {"mint": f"{i:0>44}"}, "events": {"24h": {"priceChangePercentage": i}}} for i in range(1, 40)]
    result = sd.discover("k", fetch=lambda p, k: (200, many) if p.startswith("/tokens/") else (calls.append(p) or (500, "x")),
                         pause=0)
    assert result["aborted"] and result["outcome"] == "failed"
    assert len([c for c in calls if c.startswith("/first-buyers/")]) == sd.MAX_CONSECUTIVE_ERRORS


def test_api_down_or_rate_limited_everywhere_is_a_failed_run_with_exit_code(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLANATRACKER_API_KEY", "k")
    monkeypatch.setattr(sd, "get", lambda path, key: (429, "retry_after=0"))
    assert sd.main(["--discover", "--out", str(tmp_path)]) == 2
    status = _json.loads((tmp_path / "smart_money" / "descoperire.json").read_text())
    assert status["outcome"] == "failed" and status["rate_limited"] > 0
    monkeypatch.delenv("SOLANATRACKER_API_KEY")
    assert sd.main(["--discover", "--out", str(tmp_path)]) == 3


def test_old_csv_rows_without_status_column_still_merge(tmp_path):
    from src.bnd.context_data import merge_csv
    path = tmp_path / "d.csv"
    old_header = ["id"] + sd.HEADER[:-1]
    path.write_text(",".join(old_header) + "\nA|2026-11-01," + ",".join(["x"] * (len(old_header) - 1)) + "\n")
    added = merge_csv(path, ["id"] + sd.HEADER, [["B|2026-11-02"] + ["y"] * len(sd.HEADER)])
    assert added == 1 and len(path.read_text().splitlines()) == 3


def test_workflow_separates_discovery_from_publishing():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / ".github/workflows/smart-money-sondaj.yml").read_text()
    assert "rc=$?" in text and "needs.sondeaza.outputs.rc" in text and "Final verdict" in text
