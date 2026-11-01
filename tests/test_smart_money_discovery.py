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


def test_discover_needs_repeated_wins_and_tags_early_repeaters():
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
    assert result["tokens_checked"] == 2 and result["candidates"] == 1            # doar W1 câștigă pe 2 monede
    row = result["rows"][0]
    assert row[1] == W1 and row[2] == 2 and row[HEADER_INDEX("passes")] == 1


def HEADER_INDEX(name):
    return sd.HEADER.index(name)


def test_discover_survives_failing_lists():
    result = sd.discover("k", fetch=lambda p, k: (500, "eroare"), pause=0)
    assert result["rows"] == [] and result["tokens_checked"] == 0 and result["errors"]
