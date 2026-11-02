"""Consiliul AI în umbră: rulare completă cu agenți simulați, fără rețea și fără bani."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest

from src.bnd import council_daily as cd
from src.bnd.ai_gateway import AIGateway, GatewayMode
from src.bnd.decision_registry import DecisionRegistry
from src.bnd.fusion_council import AGENTS
from src.bnd.market_data import load_csv
from tests.test_multi_market_cli import START, run_cli, write_markets  # noqa: F401

MARKETS = ("SP500", "GOLD", "BITCOIN", "EURUSD")


@pytest.fixture
def series(tmp_path):
    write_markets(tmp_path, list(MARKETS), days=800)
    return {m: load_csv(tmp_path / f"{m}.csv") for m in MARKETS}


def upto(series, count):
    return {m: candles[:count] for m, candles in series.items()}


def test_simulated_round_records_every_market_once(tmp_path, series):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    data = upto(series, 700)
    now = data["SP500"][-1].open_time + timedelta(days=1)

    first = cd.run_markets(data, MARKETS, cd.simulated_gateway(), registry, now, Decimal("0.6"))
    again = cd.run_markets(data, MARKETS, cd.simulated_gateway(), registry, now, Decimal("0.6"))

    assert [m["status"] for m in first["markets"]] == ["ok"] * 4
    assert all(set(m["agents"]) == set(AGENTS) for m in first["markets"])
    assert [m["status"] for m in again["markets"]] == ["deja_facut"] * 4
    assert all(registry.has(f"{now.date().isoformat()}:{m}") for m in MARKETS)


def test_decisions_are_settled_and_compared_after_the_horizon(tmp_path, series):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    first_day = series["SP500"][699].open_time + timedelta(days=1)
    cd.run_markets(upto(series, 700), MARKETS, cd.simulated_gateway(), registry, first_day,
                   Decimal("0.6"))

    later = first_day + timedelta(days=7)
    report = cd.run_markets(upto(series, 710), MARKETS, cd.simulated_gateway(), registry, later,
                            Decimal("0.6"))

    assert report["settled_today"] == 4
    comparison = report["comparison"]
    assert comparison["settled_decisions"] > 0
    assert comparison["always_long"]["calls"] == comparison["settled_decisions"]
    assert 0 <= comparison["council"]["calls"] <= comparison["settled_decisions"]
    text = cd.render(report)
    assert "## Cine a ghicit mai des" in text and "Consiliul AI" in text


def test_a_missing_agent_makes_the_round_incomplete_and_no_trade(tmp_path, series):
    gateway = AIGateway(GatewayMode.MOCK)
    for agent in AGENTS[:4]:
        gateway.register(agent, cd.SimulatedProvider(agent))
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    data = upto(series, 700)
    now = data["SP500"][-1].open_time + timedelta(days=1)

    report = cd.run_markets(data, ("GOLD",), gateway, registry, now, Decimal("0.6"),
                            sleep=lambda _: None)

    market = report["markets"][0]
    assert market["status"] == "incomplet" and market["decision"] == "HOLD" and market["uncertain"]
    assert "incompletă" in cd.render(report)


def test_report_is_in_romanian_with_votes_and_cost(tmp_path, series):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    data = upto(series, 700)
    now = data["SP500"][-1].open_time + timedelta(days=1)

    text = cd.render(cd.run_markets(data, MARKETS, cd.simulated_gateway(), registry, now,
                                    Decimal("0.6")))

    for part in ("# Consiliul AI în umbră", "nu se tranzacționează nimic", "## SP500",
                 "| Agent | Vot | Încredere | Motiv |", "Cost total azi", "Nicio decizie încheiată"):
        assert part in text


def test_pricing_comes_from_the_catalogue_and_unknown_models_are_refused():
    catalogue = {"data": [
        {"id": m, "pricing": {"prompt": "0.000002", "completion": "0.00001"}}
        for m in cd.DEFAULT_MODELS.values()]}

    pricing = cd.pricing_from_catalogue(cd.DEFAULT_MODELS, catalogue)

    assert pricing["openai/gpt-6-astra"].input_per_million == Decimal("2")
    assert pricing["openai/gpt-6-astra"].output_per_million == Decimal("10")
    with pytest.raises(ValueError, match="negăsite"):
        cd.pricing_from_catalogue({**cd.DEFAULT_MODELS, "gpt": "openai/nu-exista"}, catalogue)


def test_live_gateway_is_authorised_for_a_short_time_and_never_calls_without_the_flag(
        tmp_path, series, monkeypatch):
    from src.bnd import openrouter_adapter

    def forbidden(*args, **kwargs):
        raise AssertionError("niciun apel către rețea fără BND_ALLOW_LIVE_AI")

    monkeypatch.setattr(openrouter_adapter, "urlopen", forbidden)
    monkeypatch.delenv("BND_ALLOW_LIVE_AI", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "cheie-de-test")
    data = upto(series, 700)
    now = data["SP500"][-1].open_time + timedelta(days=1)
    catalogue = {"data": [{"id": m, "pricing": {"prompt": "0.000002", "completion": "0.00001"}}
                          for m in cd.DEFAULT_MODELS.values()]}
    gateway = cd.live_gateway(cd.DEFAULT_MODELS, cd.pricing_from_catalogue(cd.DEFAULT_MODELS, catalogue),
                              tmp_path / "costs.sqlite", now, Decimal("0.6"), Decimal("1.6"),
                              Decimal("12"))
    registry = DecisionRegistry(tmp_path / "r.sqlite")

    assert gateway.live_authorization.expires_at - now == timedelta(hours=3)
    report = cd.run_markets(data, ("GOLD",), gateway, registry, now, Decimal("0.6"),
                            sleep=lambda _: None)

    assert report["markets"][0]["status"] == "incomplet"
    assert Decimal(report["markets"][0]["cost_usd"]) == 0


def test_cli_mock_mode_writes_the_report_and_validates_input(tmp_path, capsys):
    write_markets(tmp_path, list(cd.DEFAULT_MARKETS), days=300)
    base = ["--data-dir", str(tmp_path), "--registry", str(tmp_path / "r.sqlite")]

    assert cd.main(base + ["--report", str(tmp_path / "raport.md"),
                           "--json", str(tmp_path / "raport.json")]) == 0
    assert "# Consiliul AI" in (tmp_path / "raport.md").read_text(encoding="utf-8")
    assert len(json.loads((tmp_path / "raport.json").read_text())["markets"]) == 10
    capsys.readouterr()

    assert cd.main(base + ["--markets", "SP500,SP500"]) == 2
    assert cd.main(base + ["--markets", "NEEXISTA"]) == 2
    assert cd.main(base + ["--markets", "../SP500"]) == 2          # nume care ies din folder
    assert cd.main(base + ["--mode", "live"]) == 2          # lipsește --costs
    assert cd.main(base + ["--round-budget", "-1"]) == 2
    capsys.readouterr()


def test_default_gpt_is_astra_and_the_variable_can_override(tmp_path, monkeypatch):
    assert cd.DEFAULT_MODELS["gpt"] == "openai/gpt-6-astra"
    monkeypatch.setenv("BND_MODEL_GPT", "openai/gpt-6-astra")

    models = {a: __import__("os").getenv(f"BND_MODEL_{a.upper()}", "").strip() or cd.DEFAULT_MODELS[a]
              for a in AGENTS}

    assert models["gpt"] == "openai/gpt-6-astra"


def test_default_markets_all_exist_with_a_class_and_a_label():
    from src.bnd.council_context import LABELS
    from src.bnd.universe import select

    universe = {m.name: m.asset_class for m in select(universe="etf")}

    assert len(cd.DEFAULT_MARKETS) == 10 and len(set(cd.DEFAULT_MARKETS)) == 10
    for name in cd.DEFAULT_MARKETS:
        assert universe[name] == cd.ASSET_CLASS[name], name
        assert name in LABELS, name


def test_workflow_default_markets_match_the_code():
    text = open(".github/workflows/consiliu-umbra.yml", encoding="utf-8").read()

    assert ",".join(cd.DEFAULT_MARKETS) in text


def test_lean_is_the_direction_of_the_non_hold_votes_and_is_compared_after_settling(
        tmp_path, series):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    first_day = series["SP500"][699].open_time + timedelta(days=1)
    report = cd.run_markets(upto(series, 700), MARKETS, cd.simulated_gateway(), registry,
                            first_day, Decimal("0.6"))

    for market in report["markets"]:
        votes = [a["vote"] for a in market["agents"].values()]
        expected = (votes.count("BUY") > votes.count("SELL")) - (votes.count("SELL") > votes.count("BUY"))
        assert market["lean"] == expected
    later = cd.run_markets(upto(series, 710), MARKETS, cd.simulated_gateway(), registry,
                           first_day + timedelta(days=7), Decimal("0.6"))

    leans = later["comparison"]["lean"]
    assert leans["calls"] == sum(m["lean"] != 0 for m in report["markets"])
    text = cd.render(later)
    assert "Înclinația consiliului" in text and "## Pe agenți" in text
    assert "înclină spre" in text or "fără înclinație" in text


def test_workflow_default_is_the_base_markets_plus_the_extra_coins_and_the_defense_stocks():
    from src.bnd.crypto50 import EXTRA
    from src.bnd.universe import DEFENSE_NAMES, STOCK_NAMES
    text = open(".github/workflows/consiliu-umbra.yml", encoding="utf-8").read()
    expected = ",".join(cd.BASE_PEERS + EXTRA + DEFENSE_NAMES + STOCK_NAMES)
    assert text.count(expected) == 2                    # intrarea manuală și valoarea implicită
    assert '--daily-budget "${DAILY_CAP:-3.00}" --monthly-budget "${MONTHLY_CAP:-38}"' in text and "timeout-minutes: 45" in text


def test_new_coins_get_a_class_and_a_label_and_old_markets_keep_the_same_context(tmp_path, series):
    from src.bnd.council_context import build_context, label
    assert cd.ASSET_CLASS["DOGE"] == "memecoin" and cd.ASSET_CLASS["LINK"] == "crypto"
    assert "memecoin" in label("PEPE") and label("LINK") == "LINK (criptomonedă)"
    assert label("SP500") == "S&P 500 (ETF)"
    data = upto(series, 700)
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    now = data["SP500"][-1].open_time + timedelta(days=1)
    extra = {**data, "DOGE": data["GOLD"]}                # monedă nouă în plus față de piețele vechi
    seen = []

    class Spy(cd.CouncilRunner):
        def run_round(self, market, symbol, context, budget, *a, **k):
            seen.append((symbol, context))
            return super().run_round(market, symbol, context, budget, *a, **k)

    original = cd.CouncilRunner
    cd.CouncilRunner = Spy
    try:
        cd.run_markets(extra, ("SP500", "DOGE"), cd.simulated_gateway(), registry, now,
                       Decimal("0.6"), peers=cd.BASE_PEERS)
    finally:
        cd.CouncilRunner = original
    contexts = dict(seen)
    assert "DOGE" not in contexts["SP500"]                # piețele noi nu apar în contextul celor vechi
    assert contexts["SP500"] == build_context("SP500", data["SP500"],
                                              {k: v for k, v in data.items() if k in cd.BASE_PEERS})


def test_short_report_is_one_line_per_market(tmp_path, series):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    data = upto(series, 700)
    now = data["SP500"][-1].open_time + timedelta(days=1)
    report = cd.run_markets(data, MARKETS, cd.simulated_gateway(), registry, now, Decimal("0.6"))

    short = cd.render_short(report)

    assert short.count("\n| ") == len(MARKETS) + 1 and "Cost total" in short and len(short) < 3000


def test_missing_data_for_one_market_skips_it_and_the_rest_still_run(tmp_path, series):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_markets(data_dir, ["SP500", "GOLD"], days=700)
    code = cd.main(["--data-dir", str(data_dir), "--registry", str(tmp_path / "r.sqlite"),
                    "--markets", "SP500,GOLD,DOGE", "--mode", "mock", "--report", str(tmp_path / "r.md"),
                    "--report-short", str(tmp_path / "s.md"), "--json", str(tmp_path / "r.json")])
    assert code == 0
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["no_data"] == ["DOGE"] and [m["market"] for m in report["markets"]] == ["SP500", "GOLD"]
    assert "Fără date azi" in (tmp_path / "r.md").read_text()
    assert "DOGE" in (tmp_path / "s.md").read_text()
    assert cd.main(["--data-dir", str(data_dir), "--registry", str(tmp_path / "x.sqlite"),
                    "--markets", "DOGE,PEPE", "--mode", "mock"]) == 2        # nicio piață cu date


def test_a_market_with_too_little_history_is_skipped_not_fatal(tmp_path, series):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    data = upto(series, 700)
    data["NOU"] = data["GOLD"][:30]
    now = data["SP500"][-1].open_time + timedelta(days=1)

    report = cd.run_markets(data, ("SP500", "NOU", "GOLD"), cd.simulated_gateway(), registry, now,
                            Decimal("0.6"))

    assert [m["status"] for m in report["markets"]] == ["ok", "date_insuficiente", "ok"]
    assert "date insuficiente" in cd.render(report) and not registry.has(f"{now.date()}:NOU")


def test_a_market_whose_data_stopped_is_skipped_instead_of_voted_on_old_prices(tmp_path, series):
    """Regresie: TON a fost votată pe 1.11 cu ultima lumânare din 30.06."""
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    data = upto(series, 700)
    data["VECHE"] = data["GOLD"][:600]                      # se oprește cu 100 de zile înainte
    data["WEEKEND"] = data["GOLD"][:697]                    # 3 zile fără lumânare: e normal (weekend)
    now = data["SP500"][-1].open_time + timedelta(days=1)

    report = cd.run_markets(data, ("SP500", "VECHE", "WEEKEND"), cd.simulated_gateway(), registry, now,
                            Decimal("0.6"))

    assert [m["status"] for m in report["markets"]] == ["ok", "date_insuficiente", "ok"]
    assert "zile" in report["markets"][1]["error"] and not registry.has(f"{now.date()}:VECHE")
