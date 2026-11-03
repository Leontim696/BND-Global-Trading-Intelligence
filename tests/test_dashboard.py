"""Datele aplicației de pe telefon: doar citire, fără rețea."""

from datetime import datetime, timedelta, timezone

import pytest

from src.bnd import dashboard
from src.bnd.decision_registry import DecisionRegistry
from src.bnd.paper_engine import PaperEngine

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def test_missing_accounts_are_reported_not_fatal(tmp_path):
    data = dashboard.collect(tmp_path, None, None, tmp_path, NOW)

    assert [a["exists"] for a in data["accounts"]] == [False] * 6
    assert data["council"] == {"exists": False}


def test_existing_account_is_summarised(tmp_path):
    PaperEngine.create(tmp_path / "paper.sqlite", 5_000.0, currency="USD", now=NOW).close()

    data = dashboard.collect(tmp_path, None, None, None, NOW)

    account = data["accounts"][0]
    assert account["exists"] and account["equity"] == 5_000.0
    assert account["positions"] == [] and account["kill_switch"] is False


def test_render_puts_data_in_the_template_and_escapes_script_ends():
    html = dashboard.render({"x": "</script>"}, "<script>const D = /*DATA*/null;</script>")

    assert "</script>\"" not in html.split("const D = ")[1]
    with pytest.raises(ValueError):
        dashboard.render({}, "fără loc pentru date")


def test_real_template_has_the_data_slot():
    from pathlib import Path
    assert "/*DATA*/null" in (Path(dashboard.__file__).parent / "dashboard_template.html").read_text(encoding="utf-8")


def test_live_prices_change_the_valuation_and_alerts_are_listed(tmp_path):
    from datetime import timedelta
    from src.bnd.paper_engine import Instrument, OrderRequest
    from src.bnd.market_data import Candle

    def candle(time, o, h, l, c):
        return Candle(time, o, h, l, c, 1000)

    engine = PaperEngine.create(tmp_path / "paper.sqlite", 10_000.0, currency="USD", now=NOW)
    engine.register_instrument(Instrument(symbol="AAA", asset_class="index", fee_pct=0, slippage_pct=0))
    engine.on_bar("AAA", candle(NOW - timedelta(days=1), 100, 101, 99, 100))
    engine.submit_order(OrderRequest("o1", "AAA", "BUY", 10, stop_loss=90), NOW)
    engine.on_bar("AAA", candle(NOW, 100, 101, 99, 100))
    engine.record("daily_run", {"time": (NOW - timedelta(hours=50)).isoformat(), "equity": 10_000.0}, NOW)
    engine.close()

    data = dashboard.collect(None, None, None, None, NOW, unic=tmp_path,
                             quotes={"time": NOW.isoformat(), "quotes": {"AAA": [110.0, NOW.isoformat()]}},
                             runs=[{"workflowName": "Cont unic (virtual)", "event": "schedule",
                                    "conclusion": "failure", "createdAt": "2026-10-31T05:00:00Z"}])

    account = next(a for a in data["accounts"] if a["key"] == "unic")
    assert account["live"] and account["live_equity"] > account["equity"]
    assert any("mai veche" in a for a in data["alerts"])
    assert any("a eșuat" in a for a in data["alerts"])


def test_quotes_snapshot_collects_names_and_times():
    from src.bnd import quotes_snapshot
    seen = []

    def fetch(symbol):
        seen.append(symbol)
        return 12.5, NOW

    result = quotes_snapshot.snapshot(fetch)

    assert result["quotes"]["BITCOIN"] == [12.5, NOW.isoformat()]
    assert "SPY" in seen and "SOL-USD" in seen
    assert "LINKUSDT" in seen and "SHIBUSDT" in seen and "AMZN" in seen     # toate piețele contului unic
    assert result["quotes"]["LINK"][0] == 12.5 and seen.count("SPY") == 1


def test_remaining_budget_starts_at_the_owners_confirmed_figure(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "costs.sqlite")
    db.execute("CREATE TABLE usage_records (id INTEGER PRIMARY KEY, agent TEXT, model TEXT,"
               " input_tokens INT, output_tokens INT, cost_usd TEXT, timestamp TEXT)")
    db.execute("INSERT INTO usage_records (cost_usd, timestamp) VALUES ('0.36590888092', '2026-10-31T09:00:00+00:00')")
    db.commit()
    assert dashboard.read_costs(tmp_path)["remaining"] == 37.97
    db.execute("INSERT INTO usage_records (cost_usd, timestamp) VALUES ('0.25', '2026-11-01T22:00:00+00:00')")
    db.commit()
    db.close()
    assert dashboard.read_costs(tmp_path)["remaining"] == pytest.approx(37.72)


def test_low_key_balance_raises_an_alert(tmp_path):
    import sqlite3
    (tmp_path / "registry.sqlite").write_bytes(b"")
    from src.bnd.decision_registry import DecisionRegistry
    (tmp_path / "registry.sqlite").unlink()
    DecisionRegistry(tmp_path / "registry.sqlite")
    db = sqlite3.connect(tmp_path / "costs.sqlite")
    db.execute("CREATE TABLE usage_records (id INTEGER PRIMARY KEY, agent TEXT, model TEXT,"
               " input_tokens INT, output_tokens INT, cost_usd TEXT, timestamp TEXT)")
    db.execute("INSERT INTO usage_records (cost_usd, timestamp) VALUES ('37', '2026-11-10T09:00:00+00:00')")
    db.commit(); db.close()

    data = dashboard.collect(None, None, None, tmp_path, NOW)

    assert any("Soldul cheii" in a for a in data["alerts"])


def test_status_json_is_flat_and_safe_for_sensors(tmp_path):
    PaperEngine.create(tmp_path / "paper.sqlite", 5_000.0, currency="USD", now=NOW).close()

    status = dashboard.status_summary(dashboard.collect(tmp_path, None, None, None, NOW))

    assert status["ok"] is True and status["alerts"] == []
    assert status["accounts"]["paper"] == {"equity": 5000.0, "currency": "USD", "return_pct": 0.0,
                                           "drawdown_pct": 0.0, "positions": 0, "orders": 0,
                                           "kill_switch": False, "reconciled": True}


def test_accounting_mismatch_and_failed_agent_raise_alerts(tmp_path, series_for_alerts):
    engine = PaperEngine.open(tmp_path / "paper.sqlite")
    engine._db.execute("UPDATE account SET cash = cash + 7")
    engine.close()

    data = dashboard.collect(tmp_path, None, None, tmp_path, NOW)

    assert any("discrepanță contabilă" in a for a in data["alerts"])
    assert any("Agentul grok a eșuat" in a for a in data["alerts"])
    assert data["council"]["last_round"]["agents"]["grok"]["failed"] == 1
    assert data["council"]["models"]["gpt"]["model"]


import pytest as _pytest


@_pytest.fixture
def series_for_alerts(tmp_path):
    from src.bnd.decision_rules import CouncilDecision, DecisionRule
    from src.bnd.fusion_council import FusionCouncil, Vote
    PaperEngine.create(tmp_path / "paper.sqlite", 5_000.0, currency="USD", now=NOW).close()
    registry = DecisionRegistry(tmp_path / "registry.sqlite")
    trace = {"agents": {"grok": {"status": "failed", "latency_s": None},
                        "gpt": {"status": "ok", "latency_s": 3.0}}}
    registry.record("2026-10-31:X", NOW, "X", 10.0, FusionCouncil(),
                    CouncilDecision(Vote.HOLD, DecisionRule.MAJORITY, {}, (), (), True, ()),
                    meta={"trace": trace})


def test_council_markets_carry_the_net_buy_sell_signal_for_the_permanent_strip(tmp_path):
    from src.bnd.decision_rules import CouncilDecision, DecisionRule
    from src.bnd.fusion_council import FusionCouncil, Opinion, Vote
    registry = DecisionRegistry(tmp_path / "registry.sqlite")
    council = FusionCouncil()
    for agent, vote in (("gpt", Vote.SELL), ("claude", Vote.SELL), ("gemini", Vote.BUY),
                        ("grok", Vote.SELL), ("deepseek", Vote.HOLD)):
        council.submit(Opinion(agent, vote, "x", 0.6))
    registry.record("2026-11-01:BITCOIN", NOW, "BITCOIN", 70000.0, council,
                    CouncilDecision(Vote.SELL, DecisionRule.MAJORITY, {}, (), (), False, ()),
                    meta={"bot_signal": -1})

    market = dashboard.collect(None, None, None, tmp_path, NOW)["council"]["markets"][0]

    assert market["symbol"] == "BITCOIN" and market["net"] == -2 and market["bot"] == -1
    assert market["conf"] == {"claude": 0.6, "deepseek": 0.6, "gemini": 0.6, "gpt": 0.6, "grok": 0.6}   # încrederea fiecărui agent
    html = (__import__("pathlib").Path(dashboard.__file__).parent / "dashboard_template.html").read_text()
    assert 'id="signals"' in html and "signalsBar()" in html


def test_account_shows_its_rules_the_planned_exposure_and_order_kinds(tmp_path):
    from src.bnd.paper_engine import Instrument, OrderRequest
    from src.bnd.market_data import Candle
    engine = PaperEngine.create(tmp_path / "paper.sqlite", 10_000.0, currency="USD", now=NOW)
    engine.record("runner_settings", {"strategy": "ai_council", "no_shorts": False, "max_leverage": 2.0,
                                      "portfolio_vol": 15.0, "financing": 5.0}, NOW)
    engine.record("daily_run", {"time": NOW.isoformat(), "equity": 10_000.0,
                                "weights": {"AAA": 0.2, "BBB": -0.5, "CCC": -0.4}}, NOW)
    engine.register_instrument(Instrument("AAA", "index", fee_pct=0, slippage_pct=0))
    engine.register_instrument(Instrument("BBB", "index", fee_pct=0, slippage_pct=0))
    for name in ("AAA", "BBB"):
        engine.on_bar(name, Candle(NOW - timedelta(days=1), 100, 100, 100, 100, 1))
    engine.submit_order(OrderRequest("l", "AAA", "BUY", 1, stop_loss=99), NOW)
    engine.submit_order(OrderRequest("s", "BBB", "SELL", 1, stop_loss=101), NOW)
    engine.close()

    account = dashboard.collect(tmp_path, None, None, None, NOW)["accounts"][0]

    assert account["rules"]["shorts"] is True and account["rules"]["max_leverage"] == 2.0
    assert round(account["plan"]["gross"], 2) == 1.1 and round(account["plan"]["short"], 2) == 0.9
    assert account["limits"]["max_drawdown_pct"] == 25.0 and account["limits"]["max_daily_loss_pct"] == 5.0   # pragurile oprii de siguranță
    assert {o["symbol"]: o["kind"] for o in account["orders"]} == {"AAA": "long", "BBB": "short"}


def test_long_only_settings_are_reported_as_such(tmp_path):
    engine = PaperEngine.create(tmp_path / "paper.sqlite", 10_000.0, currency="USD", now=NOW)
    engine.record("runner_settings", {"strategy": "sma_crossover", "no_shorts": True,
                                      "max_leverage": 1.0}, NOW)
    engine.close()

    rules = dashboard.collect(tmp_path, None, None, None, NOW)["accounts"][0]["rules"]

    assert rules["shorts"] is False and rules["max_leverage"] == 1.0


def test_every_market_gets_a_category_and_the_template_groups_by_it():
    from src.bnd import market_groups
    from src.bnd.universe import UNIVERSES
    assert market_groups.group_of("BITCOIN") == "crypto" and market_groups.group_of("DOGE") == "memecoin"
    assert market_groups.group_of("AAPL") == "actiuni" and market_groups.group_of("RHEINMETALL") == "aparare"
    assert market_groups.group_of("SP500") == "indici" and market_groups.group_of("GOLD") == "marfuri"
    assert market_groups.group_of("EURUSD") == "forex" and market_groups.group_of("US10Y_NOTE") == "obligatiuni"
    assert market_groups.group_of("NU_EXISTA") == "alte"
    assert "alte" not in {market_groups.group_of(m.name) for m in UNIVERSES["unic"]}
    html = (__import__("pathlib").Path(dashboard.__file__).parent / "dashboard_template.html").read_text()
    assert "byGroup(c.markets)" in html and "byGroup(a.positions)" in html and "Semnale pe categorii" in html
    labels = [g["key"] for g in market_groups.labels()]
    assert labels[:3] == ["indici", "actiuni", "aparare"] and labels[-1] == "alte"


def test_template_has_a_category_filter_bar_that_filters_every_grouped_view():
    html = (__import__("pathlib").Path(dashboard.__file__).parent / "dashboard_template.html").read_text()
    assert 'id="filters"' in html and "filtersBar()" in html and "bnd-filtru" in html
    assert "g => !FILTER || g.key === FILTER" in html               # byGroup respectă filtrul
    for view in ("byGroup(c.markets)", "byGroup(a.positions)", "byGroup(a.orders)", "byGroup(cm)"):
        assert view in html, view
    assert "FILTER === \"memecoin\"" in html                        # și fila Top 50 se filtrează
    assert "try { FILTER = localStorage" in html                    # stocarea poate lipsi


def test_data_has_the_test_window_and_the_latest_scheduled_runs():
    runs = [{"workflowName": "Cont unic (virtual)", "event": "schedule", "conclusion": "failure", "createdAt": "2026-10-31T22:25:00Z"},
            {"workflowName": "Cont unic (virtual)", "event": "schedule", "conclusion": "success", "createdAt": "2026-11-01T22:25:00Z"},
            {"workflowName": "Cont unic (virtual)", "event": "workflow_dispatch", "conclusion": "failure", "createdAt": "2026-11-02T01:00:00Z"},
            {"workflowName": "Alt flux", "event": "schedule", "conclusion": "failure", "createdAt": "2026-11-01T01:00:00Z"}]
    status = dashboard.system_status(runs)
    assert status == [{"name": "contul unic", "conclusion": "success", "time": "2026-11-01T22:25:00Z"}]
    data = dashboard.collect(None, None, None, None, NOW, runs=runs)
    assert data["system"] == status
    assert {k: data["test"][k] for k in ("start", "end", "report")} == {"start": "2026-10-31", "end": "2026-11-30", "report": "2026-12-01"}
    assert [m["date"] for m in data["test"]["milestones"]] == ["2026-11-06", "2026-11-17", "2026-11-30", "2026-12-01"]
    assert dashboard.system_status(None) == []


def test_template_modern_features_are_present_and_safe():
    html = (__import__("pathlib").Path(dashboard.__file__).parent / "dashboard_template.html").read_text()
    for needle in ('class="dock-in"', 'id="theme"', 'id="q"', 'id="sort"', "testCard()", "systemPanel()", "allocation(a)",
                   "data-cons", "data-sort", "bnd-tema", "prefers-reduced-motion", "env(safe-area-inset-bottom",
                   "openPalette()", "openMarket(", "agreement(", "data-fav", "bnd-fav", "bnd-moneda", "bnd-vedere",
                   'class="heat"', "favoritesPanel()", "feedPanel()", "[hidden]{display:none!important}",
                   "navigator.clipboard", "prefers-color-scheme: light"):
        assert needle in html, needle
    assert "eval(" not in html and "document.write" not in html and "outerHTML =" not in html
    assert html.count("localStorage") <= 4                         # doar prin store() și blocul try
    assert "e.preventDefault(); const first" in html                # Enter în căutare nu declanșează butonul de închidere
    for token in ("--bg", "--fg", "--accent", "--glass", "--gain", "--loss"):   # jetoane definite pe :root, nu doar în teme
        assert html.index(token + ":") < html.index("@media (prefers-color-scheme")


def test_schedule_in_the_app_matches_the_workflow_crons():
    import re
    root = __import__("pathlib").Path(dashboard.__file__).resolve().parents[2] / ".github" / "workflows"
    crons = {"Consiliul AI": "consiliu-umbra.yml", "Cont unic": "cont-unic.yml"}
    for entry in dashboard.SCHEDULE:
        minute, hour = re.search(r"cron: '(\d+) (\d+) \* \* \*'", (root / crons[entry["name"]]).read_text()).groups()
        assert entry["utc"] == f"{int(hour):02d}:{int(minute):02d}", entry


def test_practical_blocks_are_in_the_template_and_data_carries_limits_and_confidence(tmp_path):
    html = (__import__("pathlib").Path(dashboard.__file__).parent / "dashboard_template.html").read_text()
    for needle in ("briefing()", "riskPanel(a)", "ordersPreview(a)", "stressPanel(a)", "convictionPanel(", "openGlossary(",
                   "data-stress-mode", "data-note", "nextRuns()", "const TERMS", "bnd-nota-"):
        assert needle in html, needle
    assert "outerHTML" not in html                                   # nicio înlocuire de HTML brut
    # semnalul combinat din aplicație folosește aceeași formulă ca contul (50% reguli + 50% consiliu)
    assert "sgn(m.net) * Math.min(1, Math.abs(m.net) / 2)" in html and "0.5 * (m.bot || 0) + 0.5 * cSig(m)" in html


def test_council_history_counts_days_series_and_flips(tmp_path):
    from src.bnd.decision_rules import CouncilDecision, DecisionRule
    from src.bnd.fusion_council import FusionCouncil, Opinion, Vote
    registry = DecisionRegistry(tmp_path / "registry.sqlite")

    def day(key, symbol, votes):
        council = FusionCouncil()
        for agent, vote in zip(("gpt", "claude", "gemini", "grok", "deepseek"), votes):
            council.submit(Opinion(agent, vote, "x", 0.6))
        registry.record(f"{key}:{symbol}", NOW, symbol, 10.0, council,
                        CouncilDecision(Vote.HOLD, DecisionRule.MAJORITY, {}, (), (), False, ()), meta={})
    B, S, H = Vote.BUY, Vote.SELL, Vote.HOLD
    day("2026-11-01", "BITCOIN", (B, B, B, H, H))          # +3
    day("2026-11-01", "GOLD", (S, S, H, H, H))             # -2
    day("2026-11-01", "SP500", (H, H, H, H, H))            # 0
    day("2026-11-02", "BITCOIN", (S, S, H, H, H))          # -2: și-a schimbat partea
    day("2026-11-02", "GOLD", (S, B, H, H, H))             # 0 cu dezacord: tot schimbare (de la -2)
    day("2026-11-02", "SP500", (H, H, H, H, B))            # +1: schimbare (de la 0)
    h = dashboard.read_council(tmp_path, None, NOW)["history"]
    assert [d["day"] for d in h["days"]] == ["2026-11-01", "2026-11-02"]
    assert h["days"][0] == {"day": "2026-11-01", "n": 3, "up": 1, "down": 1, "split": 0}
    assert h["days"][1]["split"] == 1 and h["days"][1]["n"] == 3
    assert h["series"]["BITCOIN"] == [3, -2] and h["series_days"] == ["2026-11-01", "2026-11-02"]
    assert {f["symbol"] for f in h["flips"]} == {"BITCOIN", "GOLD", "SP500"}
    assert h["flips"][0]["symbol"] == "BITCOIN" and h["flips_between"] == ["2026-11-01", "2026-11-02"]


def test_pulse_blocks_are_in_the_template():
    html = (__import__("pathlib").Path(dashboard.__file__).parent / "dashboard_template.html").read_text()
    for needle in ("pulsePanel(c)", "marketHistory(sym)", "moodWord(", "Pulsul consiliului", "Ultimele zile"):
        assert needle in html, needle


def test_every_watched_workflow_exists_with_that_exact_name_and_manual_means_manual():
    """Un nume greșit în WATCHED nu dă eroare: alertele pur și simplu nu pornesc niciodată. Păzim potrivirea."""
    import re
    root = __import__("pathlib").Path(dashboard.__file__).resolve().parents[2] / ".github" / "workflows"
    names = {}
    for path in root.glob("*.yml"):
        body = path.read_text(encoding="utf-8")
        name = re.search(r"^name:\s*(.+)$", body, re.M).group(1).strip().strip("'\"")
        names[name] = body
        if "manual" in name.lower():
            assert "schedule:" not in body, f"{path.name}: numele spune „manual”, dar rulează programat"
    for watched in dashboard.WATCHED:
        assert watched in names, f"WATCHED cere un workflow care nu există: {watched}"
        assert "schedule:" in names[watched], f"{watched} e urmărit, dar nu rulează programat"

def test_top50_marks_coins_whose_data_stopped_updating(tmp_path):
    """Regresie: O monedă nu a primit lumânări din 30.06, dar apărea în Top 50 ca și cum prețul ar fi actual."""
    from datetime import datetime, timedelta, timezone

    from src.bnd import crypto50
    from src.bnd.market_data import Candle, save_csv
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def candles(days):
        return [Candle(start + timedelta(days=i), 10 + i * .01, 50, 5, 10 + i * .01, 1) for i in range(days)]
    save_csv(candles(200), tmp_path / "BTC.csv")
    save_csv(candles(100), tmp_path / "ETH.csv")                  # se oprește cu 100 de zile mai devreme
    rows = {r["name"]: r for r in crypto50.summary(tmp_path)}
    assert rows["BTC"]["stale_days"] == 0 and rows["ETH"]["stale_days"] == 100
    html = (__import__("pathlib").Path(dashboard.__file__).parent / "dashboard_template.html").read_text()
    assert "r.stale_days > 3" in html


def test_interface_3_has_command_deck_maps_and_safe_accent_handling():
    html = (__import__("pathlib").Path(dashboard.__file__).parent / "dashboard_template.html").read_text()
    for needle in ("bridge()", "polar(", "treemap(", "orbit(m)", "radar(rows)", "countUp(", "cycleAccent()", "const ACTIONS",
                   'class="aurora"', "data-gfilter", "bnd-accent", "@supports (color: oklch(0 0 0))"):
        assert needle in html, needle
    assert "eval(" not in html and "innerHTML +=" not in html.replace("box.innerHTML += actHtml", "")   # singura adăugare permisă: paleta de comenzi


def test_account_chart_ends_with_the_value_at_current_prices():
    from pathlib import Path
    t = Path("src/bnd/dashboard_template.html").read_text(encoding="utf-8")
    assert "function spark(history, initial, key, big, live)" in t
    assert t.count("a.live ? {v: a.live_equity, t: DATA.quotes_time || DATA.generated} : null") == 3
    assert '"acum"' in t and 'p.now ? " · acum"' in t


def test_rules_versus_ai_tab_compares_the_two_accounts():
    from pathlib import Path
    t = Path("src/bnd/dashboard_template.html").read_text(encoding="utf-8")
    assert '["comparatie","Reguli vs AI"]' in t and 'key === "comparatie" ? compareView()' in t
    assert 'portfolioPanel("control", "Pozițiile deschise · Reguli matematice")' in t
    titles = {k: title for k, title, _ in dashboard.ACCOUNTS}
    assert titles["control"] == "Reguli matematice" and "arhivat" in titles["paper"]
