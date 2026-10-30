"""Safety guards: the mode check, and a scan for real-order code and leaked keys."""

import re
from pathlib import Path

import pytest

from src.bnd import paper_runner
from src.bnd.safety import SafetyError, trading_mode

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("value, expected", [(None, "PAPER"), ("paper", "PAPER"),
                                             (" MOCK ", "MOCK"), ("", "PAPER")])
def test_allowed_modes(value, expected):
    env = {} if value is None else {"BND_TRADING_MODE": value}

    assert trading_mode(env) == expected


@pytest.mark.parametrize("value", ["LIVE", "live", "REAL", "paper-live"])
def test_live_and_unknown_modes_are_refused(value):
    with pytest.raises(SafetyError, match="refused"):
        trading_mode({"BND_TRADING_MODE": value})


def test_paper_runner_refuses_live_mode_before_touching_the_account(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BND_TRADING_MODE", "LIVE")
    state = tmp_path / "paper.sqlite"

    code = paper_runner.main(["--state", str(state), "--data-dir", str(tmp_path),
                              "--capital", "1000"])

    assert code == 2 and "refused" in capsys.readouterr().err
    assert not state.exists()


def source_files():
    for folder in ("src", "scripts", ".github"):
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.suffix in (".py", ".yml", ".yaml", ".sh"):
                yield path


# Endpoints and client calls that would place real orders with a broker
# or exchange. Market-data endpoints (klines, chart) are fine.
ORDER_PATTERNS = [
    r"/api/v3/order", r"/fapi/v\d/order", r"/dapi/v\d/order", r"/sapi/v\d/margin/order",
    r"/v\d/orders\b", r"/accounts/[^\s\"']*/orders", r"\bcreate_?order\s*\(",
    r"\bplace_?order\s*\(", r"\bsubmit_order\s*\(\s*symbol=", r"\bimport ccxt\b",
    r"\bfrom ccxt\b", r"alpaca_trade_api", r"api\.kraken\.com/0/private",
    r"api-fxtrade\.oanda\.com", r"/openapi/trade",
]
SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{20,}", r"sk-or-v1-[0-9a-f]{20,}", r"AKIA[0-9A-Z]{16}",
    r"ghp_[A-Za-z0-9]{30,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"xox[abp]-[A-Za-z0-9-]{10,}",
]


def scan(patterns):
    hits = []
    for path in source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{path.relative_to(ROOT)}:{line}: {match.group(0)}")
    return hits


def test_no_code_can_send_real_orders():
    assert scan(ORDER_PATTERNS) == []


def test_no_secrets_in_code_or_workflows():
    assert scan(SECRET_PATTERNS) == []


def test_scanner_finds_what_it_should(tmp_path):
    sample = "requests.post('https://api.binance.com/api/v3/order')\nkey = 'sk-" + "a" * 30 + "'\n"

    assert re.search(ORDER_PATTERNS[0], sample)
    assert re.search(SECRET_PATTERNS[0], sample)
