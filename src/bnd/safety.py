"""One place that decides the trading mode: MOCK or PAPER, never LIVE.

Every entry point that could act on a market calls ``trading_mode()``
first. The mode comes from ``BND_TRADING_MODE`` (default PAPER). LIVE and
anything unknown are refused here, so no configuration mistake, workflow
input or environment variable can switch the system to real orders: that
would need a code change, reviewed in a pull request. The engines keep
their own refusals as well (``PaperEngine.require_mode``).
"""

import os

ENV_VAR = "BND_TRADING_MODE"
ALLOWED = ("MOCK", "PAPER")


class SafetyError(RuntimeError):
    """The requested mode is not allowed in this system."""


def trading_mode(environ=None) -> str:
    """The active mode, or SafetyError for LIVE or an unknown value."""
    environ = os.environ if environ is None else environ
    mode = (environ.get(ENV_VAR) or "PAPER").strip().upper()
    if mode not in ALLOWED:
        raise SafetyError(f"{ENV_VAR}={mode!r} refused: only {', '.join(ALLOWED)} are allowed; "
                          "real (LIVE) trading does not exist in this system")
    return mode


OBSERVER_VAR = "BND_OBSERVER_ONLY"


def observer_only(environ=None) -> bool:
    """True dacă instanța e doar observator (ex. pe Proxmox): nu are voie să deschidă un cont pentru scriere."""
    environ = os.environ if environ is None else environ
    return (environ.get(OBSERVER_VAR) or "").strip().lower() in ("1", "true", "yes", "da")


def require_writable_account(environ=None) -> None:
    """Oprește orice cale care ar scrie în contul virtual când instanța e observer-only."""
    if observer_only(environ):
        raise SafetyError(f"{OBSERVER_VAR}=true: această instanță doar observă; "
                          "nu poate rula runnerul și nu poate scrie în contul virtual")
