"""Garanția „doar paper”: niciun traseu nu poate trimite ordine reale.

Testele sunt negative: încearcă să forțeze LIVE (mediu, argumente, configurări
greșite) și verifică ce fel de cod există în depozit (fără clienți de broker,
fără puncte de trimitere de ordine, doar gazde de rețea cunoscute).
"""

import re
from pathlib import Path

import pytest

from src.bnd import paper_runner
from src.bnd.paper_engine import PaperEngine, PaperEngineError, TradingMode
from src.bnd.safety import ALLOWED, SafetyError, trading_mode

ROOT = Path(__file__).resolve().parents[1]
BAD_MODES = ["LIVE", "live", " Live ", "REAL", "PRODUCTION", "PAPER;LIVE", "PAPER LIVE",
             "LIVE\n", "1", "true", "paper-live", "demo"]


@pytest.mark.parametrize("value", BAD_MODES)
def test_bad_modes_are_refused(value):
    with pytest.raises(SafetyError):
        trading_mode({"BND_TRADING_MODE": value})


def test_missing_or_blank_mode_falls_back_to_paper_never_live():
    assert trading_mode({}) == "PAPER"
    assert trading_mode({"BND_TRADING_MODE": ""}) == "PAPER"
    assert set(ALLOWED) == {"MOCK", "PAPER"}


@pytest.mark.parametrize("value", BAD_MODES)
def test_engine_refuses_to_open_or_create_an_account_in_a_bad_mode(tmp_path, monkeypatch, value):
    monkeypatch.setenv("BND_TRADING_MODE", value)
    with pytest.raises(SafetyError):
        PaperEngine.create(tmp_path / "x.sqlite", 1000.0)
    assert not (tmp_path / "x.sqlite").exists()


@pytest.mark.parametrize("value", ["LIVE", "live", "anything"])
def test_runner_exits_without_creating_an_account(tmp_path, monkeypatch, value):
    monkeypatch.setenv("BND_TRADING_MODE", value)
    state = tmp_path / "paper.sqlite"

    code = paper_runner.main(["--state", str(state), "--data-dir", str(tmp_path),
                              "--capital", "1000"])

    assert code == 2 and not state.exists()


def test_engine_class_refuses_the_live_enum():
    with pytest.raises(PaperEngineError):
        PaperEngine.require_mode(TradingMode.LIVE)
    assert PaperEngine.mode == TradingMode.PAPER


def _sources():
    files = list((ROOT / "src").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py"))
    return {path: path.read_text(encoding="utf-8") for path in files}


def test_no_broker_or_exchange_trading_client_in_the_code():
    forbidden = re.compile(r"\b(ccxt|alpaca|ibapi|ib_insync|oandapyV20|python-binance|binance\.client|"
                           r"krakenex|robin_stocks|tradier|metatrader|MetaTrader5)\b", re.I)
    for path, text in _sources().items():
        assert not forbidden.search(text), f"{path} pare să folosească un client de broker"


def test_no_order_endpoint_is_called():
    endpoints = re.compile(r"/(api|fapi|dapi)/v\d/(order|orders|batchOrders|account|withdraw)|"
                           r"/v2/orders|/v3/orders|/order/place|/trade/order", re.I)
    for path, text in _sources().items():
        assert not endpoints.search(text), f"{path} conține un endpoint de ordine/retragere"


def test_network_hosts_are_only_the_known_data_ai_and_notification_services():
    allowed = {"openrouter.ai", "ntfy.sh", "query1.finance.yahoo.com", "localhost",
               "fapi.binance.com", "data-api.binance.vision", "fonts.googleapis.com",
               "api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com",
               "api.x.ai", "api.deepseek.com", "github.com", "x-access-token",
               "api.alternative.me", "www.okx.com",
               "nfs.faireconomy.media"}   # calendar economic public, doar citire (calendar_data.py)
    hosts = set()
    for text in _sources().values():
        hosts |= set(re.findall(r"https?://([A-Za-z0-9.-]+)", text))
    # funding.py citește doar rata de finanțare publică; nu trimite nimic.
    assert hosts <= allowed, f"gazde noi: {sorted(hosts - allowed)}"
    assert not any("withdraw" in h for h in hosts)


def test_workflows_never_set_a_live_trading_mode():
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "BND_TRADING_MODE" in line:
                assert re.search(r"BND_TRADING_MODE:\s*\"?(PAPER|MOCK)\"?\s*$", line), \
                    f"{path.name}: {line.strip()}"
        # Nicio intrare de workflow nu poate ajunge în modul de tranzacționare.
        assert not re.search(r"BND_TRADING_MODE:\s*\$\{\{", text), path.name


def test_live_ai_flag_is_never_on_in_the_trading_workflows():
    for name in ("paper-trading.yml", "cripto-ai.yml", "bot-ai-unificat.yml", "rapoarte-bot.yml", "reguli-ls.yml", "cont-unic.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert re.search(r'BND_ALLOW_LIVE_AI:\s*"false"', text), name
