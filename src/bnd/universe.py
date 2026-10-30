"""Default multi-asset universe: forex, commodities, indices, bonds, crypto.

Symbols are Yahoo Finance tickers. Costs are per fill, in percent, and
deliberately conservative for a retail account.

Caveats, stated rather than hidden:
- Futures tickers (=F) are front-month series that are not back-adjusted:
  contract rolls show up as price jumps that no trader could capture.
- Indices (^) are not directly tradable; they stand in for index futures
  or CFDs.
- Forex quotes ignore swap points; financing on leverage is charged
  separately by the portfolio backtester.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    name: str
    symbol: str
    asset_class: str
    fee_pct: float
    slippage_pct: float


# Per-fill costs by asset class (fee %, slippage %).
CLASS_COSTS = {
    "forex": (0.002, 0.005),
    "index": (0.01, 0.02),
    "bond": (0.005, 0.01),
    "commodity": (0.02, 0.05),
    "crypto": (0.10, 0.05),
}

_DEFAULT = (
    ("EURUSD", "EURUSD=X", "forex"),
    ("GBPUSD", "GBPUSD=X", "forex"),
    ("USDJPY", "JPY=X", "forex"),
    ("AUDUSD", "AUDUSD=X", "forex"),
    ("USDCHF", "CHF=X", "forex"),
    ("USDCAD", "CAD=X", "forex"),
    ("GOLD", "GC=F", "commodity"),
    ("SILVER", "SI=F", "commodity"),
    ("CRUDE_OIL", "CL=F", "commodity"),
    ("NATURAL_GAS", "NG=F", "commodity"),
    ("COPPER", "HG=F", "commodity"),
    ("CORN", "ZC=F", "commodity"),
    ("WHEAT", "ZW=F", "commodity"),
    ("SOYBEANS", "ZS=F", "commodity"),
    ("SP500", "^GSPC", "index"),
    ("NASDAQ100", "^NDX", "index"),
    ("DAX", "^GDAXI", "index"),
    ("NIKKEI", "^N225", "index"),
    ("FTSE100", "^FTSE", "index"),
    ("US10Y_NOTE", "ZN=F", "bond"),
    ("BITCOIN", "BTC-USD", "crypto"),
    ("ETHEREUM", "ETH-USD", "crypto"),
)

DEFAULT_UNIVERSE = tuple(
    Market(name, symbol, asset_class, *CLASS_COSTS[asset_class])
    for name, symbol, asset_class in _DEFAULT
)


def select(names=None, classes=None) -> tuple[Market, ...]:
    """Filter the default universe by market names and/or asset classes."""

    markets = DEFAULT_UNIVERSE
    if names:
        wanted = {name.upper() for name in names}
        unknown = wanted - {m.name for m in markets}
        if unknown:
            raise ValueError("Unknown markets: " + ", ".join(sorted(unknown)))
        markets = tuple(m for m in markets if m.name in wanted)
    if classes:
        wanted = {name.lower() for name in classes}
        unknown = wanted - set(CLASS_COSTS)
        if unknown:
            raise ValueError("Unknown asset classes: " + ", ".join(sorted(unknown)))
        markets = tuple(m for m in markets if m.asset_class in wanted)
    if not markets:
        raise ValueError("No markets selected")
    return markets
