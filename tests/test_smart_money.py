import csv
import json

from src.bnd import smart_money as sm

W1 = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
W2 = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"


def row(**kw):
    base = {"wallet": W1, "tokens": 20, "trades": 200, "winRate": 55, "realized": 90_000, "totalInvested": 20_000,
            "medianHoldMinutes": 90, "walletAgeDays": 300}
    return {**base, **kw}


def test_address_validation():
    assert sm.valid_address(W1) and not sm.valid_address("abc") and not sm.valid_address("0" * 40) and not sm.valid_address(None)


def test_normalise_accepts_name_variants_and_percentages():
    s = sm.normalise(row())
    assert s["win_rate"] == 0.55 and s["roi"] == 4.5 and s["avg_buy_usd"] == 200.0
    nested = sm.normalise({"wallet": W1, "summary": {"realized": 5000, "totalInvested": 1000, "totalBuys": 10, "totalSells": 10}})
    assert nested["realized_pnl_usd"] == 5000 and nested["trades"] == 20
    assert sm.normalise({"wallet": "x"}) is None


def test_good_wallet_passes_and_each_filter_rejects():
    ok = sm.assess(sm.normalise(row()))
    assert ok["passes"] and not ok["reasons"]
    for change, word in (({"tokens": 3}, "monede"), ({"trades": 10}, "tranzacții"), ({"winRate": 20}, "succes"),
                         ({"realized": 5_000}, "profit"), ({"medianHoldMinutes": 0.1}, "bot"),
                         ({"walletAgeDays": 5}, "zile"), ({"totalInvested": 2_000_000, "realized": 3_000_000}, "cumpărătură")):
        bad = sm.assess(sm.normalise(row(**change)))
        assert not bad["passes"] and any(word in r for r in bad["reasons"]), change


def test_missing_core_fields_never_pass_but_optional_ones_are_noted():
    s = sm.assess({"wallet": W1, "tokens": 20})
    assert not s["passes"]
    r = row()
    r.pop("medianHoldMinutes"); r.pop("walletAgeDays")
    s = sm.assess(sm.normalise(r))
    assert s["passes"] and {"median_hold_min", "age_days"} <= set(s["unknown"])


def test_insider_pattern_tag_needs_many_early_entries_over_several_tokens():
    assert sm.assess(sm.normalise(row(earlyBuyShare=0.7)))["tags"] == ["tipar_insider"]
    assert sm.assess(sm.normalise(row(earlyBuyShare=0.2)))["tags"] == []
    assert sm.assess(sm.normalise(row(earlyBuyShare=0.9, tokens=3)))["tags"] == []


def test_collect_without_key_uses_manual_list_and_reports_it(tmp_path):
    manual = tmp_path / "w.json"
    manual.write_text(json.dumps([{"wallet": W2, "label": "x"}, {"wallet": "invalid"}]))
    status = sm.collect(tmp_path, None, manual)
    assert status["manual"] == 1 and status["written"] == 1 and "cheie" in status["leaderboard"]["error"]
    assert (tmp_path / "smart_money" / "wallete.csv").exists()


def test_collect_with_leaderboard_and_failure_isolated(tmp_path):
    def fetch(url, key):
        assert key == "k"
        if "pnl" in url:
            raise ValueError("HTTP 404")
        return {"data": [row(), row(wallet=W2, earlyBuyShare=0.8), {"wallet": "bad"}]}
    manual = tmp_path / "w.json"
    manual.write_text(json.dumps([{"wallet": "5ZiE3vAkrdXBgyFL7KqG3RoEtnvgrbbV6d1ZtZ1bFp8F"}]))
    status = sm.collect(tmp_path, "k", manual, fetch=fetch)
    assert status["leaderboard"]["ok"] and status["written"] == 3 and status["passing"] == 2
    assert status["insider_pattern"] == 1 and any("HTTP 404" in e for e in status["errors"])
    # a doua rulare adaugă rânduri noi (istoric), nu rescrie
    sm.collect(tmp_path, "k", manual, fetch=fetch)
    lines = (tmp_path / "smart_money" / "wallete.csv").read_text().splitlines()
    assert len(lines) == 1 + 6


def test_leaderboard_failure_does_not_stop(tmp_path):
    def fetch(url, key):
        raise ValueError("nu răspunde")
    assert sm.collect(tmp_path, "k", tmp_path / "lipsa.json", fetch=fetch)["leaderboard"]["ok"] is False
    assert sm.rows_of({"traders": [1]}) == [1]


def test_base_url_is_restricted_to_https_known_host():
    import pytest
    ok = sm.checked_base_url("https://data.solanatracker.io/")
    assert ok == "https://data.solanatracker.io"
    for bad in ("http://data.solanatracker.io", "https://evil.example", "https://user@data.solanatracker.io",
                "https://data.solanatracker.io:8443", "ftp://data.solanatracker.io", ""):
        with pytest.raises(ValueError):
            sm.checked_base_url(bad)


def test_redirects_are_refused_so_the_key_cannot_follow_them():
    from urllib.request import Request
    assert sm._NoRedirect().redirect_request(Request("https://data.solanatracker.io/x"), None, 302, "x", {}, "https://evil.example") is None


def test_paths_cannot_change_the_host():
    import pytest
    assert sm.checked_path("/top-traders/all") == "/top-traders/all"
    assert sm.checked_path("/pnl/{wallet}", ("wallet",)) == "/pnl/{wallet}"
    for bad in ("@evil.example/x", "//evil.example/x", "/../x", "/a?x=1", "/a#b", "evil", "", "/a b", "/pnl/{wallet}"):
        with pytest.raises(ValueError):
            sm.checked_path(bad)
    with pytest.raises(ValueError):
        sm._get("https://data.solanatracker.io@evil.example/x", "k")


def test_env_paths_are_validated_at_import(monkeypatch):
    import importlib
    import pytest
    monkeypatch.setenv("SMART_MONEY_LEADERBOARD_PATH", "@evil.example/x")
    with pytest.raises(ValueError):
        importlib.reload(sm)
    monkeypatch.delenv("SMART_MONEY_LEADERBOARD_PATH")
    importlib.reload(sm)


def test_leaderboard_wallets_are_enriched_with_details_and_field_names_are_reported(tmp_path):
    def fetch(url, key):
        if "pnl" in url:
            return {"summary": {"totalTokens": 25, "totalBuys": 120, "totalSells": 110, "winPercentage": 52,
                                "totalInvested": 9000, "realized": 60000}, "wallet": "ignorat", "secret": "nu-se-raporteaza"}
        return [{"wallet": W1, "realized": 60000, "roi": 6.6}]
    status = sm.collect(tmp_path, "k", tmp_path / "lipsa.json", fetch=fetch)
    assert status["leaderboard"]["enriched"] == 1
    assert status["sample_keys"]["clasament"] == ["realized", "roi", "wallet"]
    assert "summary.winPercentage" in status["sample_keys"]["detalii"]
    assert "nu-se-raporteaza" not in json.dumps(status)                    # doar numele câmpurilor, nu valorile
    row = next(csv.DictReader((tmp_path / "smart_money" / "wallete.csv").open()))
    assert row["tokens"] == "25.0" and row["win_rate"] == "0.52" and row["passes"] == "1"


def test_a_failing_detail_call_keeps_the_leaderboard_row(tmp_path):
    def fetch(url, key):
        if "pnl" in url:
            raise ValueError("HTTP 404")
        return [{"wallet": W1, "realized": 5, "roi": 0.1}]
    status = sm.collect(tmp_path, "k", tmp_path / "lipsa.json", fetch=fetch)
    assert status["written"] == 1 and any("detalii" in e for e in status["errors"])
