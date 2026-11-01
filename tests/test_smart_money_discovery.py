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
