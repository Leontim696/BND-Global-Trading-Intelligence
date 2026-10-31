"""Default multi-asset universe: forex, commodities, indices, bonds, crypto.

Symbols are Yahoo Finance tickers. Costs are per fill, in percent, and
deliberately conservative for a retail account.

Caveats, stated rather than hidden:
- Futures tickers (=F) are front-month series that are not back-adjusted:
  contract rolls show up as price jumps that no trader could capture.
- Indices (^) are not directly tradable; they stand in for index futures
  or CFDs.
- Forex quotes ignore swap points (the interest differential), which can
  add or subtract a few percent a year.

Carry: futures need only margin, so no financing is charged on their
notional; the cost of carry is part of the futures price. Crypto
perpetuals pay funding on the whole position (about 10%/yr historically).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    name: str
    symbol: str
    asset_class: str
    fee_pct: float
    slippage_pct: float
    # Annual carry charged on |notional| while a position is open.
    carry_pct_annual: float = 0.0
    # Optional group for concentration limits (for shares: the sector).
    sector: str = ""


# Per-fill costs by asset class (fee %, slippage %, annual carry %).
CLASS_COSTS = {
    "forex": (0.002, 0.005, 0.0),
    "index": (0.01, 0.02, 0.0),
    "bond": (0.005, 0.01, 0.0),
    "commodity": (0.02, 0.05, 0.0),
    "crypto": (0.10, 0.05, 10.0),
    "stock": (0.02, 0.03, 0.0),
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

# Tradable, roll-free stand-ins: exchange-traded funds for commodities,
# indices and bonds. ETF prices already include the cost of rolling
# futures (contango) and, adjusted, their dividends; there are no
# artificial roll jumps. Forex and crypto are the same as above.
_ETF = (
    ("GOLD", "GLD", "commodity"),
    ("SILVER", "SLV", "commodity"),
    ("CRUDE_OIL", "USO", "commodity"),
    ("NATURAL_GAS", "UNG", "commodity"),
    ("COPPER", "CPER", "commodity"),
    ("AGRICULTURE", "DBA", "commodity"),
    ("BROAD_COMMODITIES", "DBC", "commodity"),
    ("SP500", "SPY", "index"),
    ("NASDAQ100", "QQQ", "index"),
    ("GERMANY", "EWG", "index"),
    ("JAPAN", "EWJ", "index"),
    ("UK", "EWU", "index"),
    ("EMERGING", "EEM", "index"),
    ("US10Y_NOTE", "IEF", "bond"),
    ("US20Y_BOND", "TLT", "bond"),
)
_ETF_COSTS = {"commodity": (0.01, 0.03, 0.0), "index": (0.005, 0.01, 0.0),
              "bond": (0.005, 0.01, 0.0)}
ETF_UNIVERSE = tuple(
    Market(name, symbol, asset_class, *_ETF_COSTS[asset_class])
    for name, symbol, asset_class in _ETF
) + tuple(m for m in DEFAULT_UNIVERSE if m.asset_class in ("forex", "crypto"))

# Large US shares across six sectors (Yahoo prices are adjusted for splits and
# dividends). Sixteen names is a sample for testing, not a recommendation.
_STOCKS = (
    ("AAPL", "tehnologie"), ("MSFT", "tehnologie"), ("NVDA", "tehnologie"),
    ("GOOGL", "tehnologie"), ("AMZN", "consum"), ("WMT", "consum"), ("KO", "consum"),
    ("PG", "consum"), ("JNJ", "sănătate"), ("UNH", "sănătate"), ("XOM", "energie"),
    ("CVX", "energie"), ("JPM", "financiar"), ("GS", "financiar"), ("CAT", "industrie"),
    ("BA", "industrie"),
)
STOCK_UNIVERSE = tuple(
    Market(ticker, ticker, "stock", *CLASS_COSTS["stock"], sector=sector)
    for ticker, sector in _STOCKS
)

# Cinci criptomonede mari, prețuri zilnice gratuite (Yahoo). Folosit de contul
# virtual de cripto condus de consiliul AI; nu schimbă celelalte universuri.
_CRYPTO = (
    ("BITCOIN", "BTC-USD"), ("ETHEREUM", "ETH-USD"), ("SOLANA", "SOL-USD"),
    ("BNB", "BNB-USD"), ("XRP", "XRP-USD"),
)
CRYPTO_UNIVERSE = tuple(
    Market(name, symbol, "crypto", *CLASS_COSTS["crypto"]) for name, symbol in _CRYPTO
)

UNIVERSES = {"futures": DEFAULT_UNIVERSE, "etf": ETF_UNIVERSE, "stocks": STOCK_UNIVERSE,
             "crypto": CRYPTO_UNIVERSE}


def select(names=None, classes=None, universe: str = "futures") -> tuple[Market, ...]:
    """Filter a universe by market names and/or asset classes."""

    if universe not in UNIVERSES:
        raise ValueError("Unknown universe: " + universe)
    markets = UNIVERSES[universe]
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


# ESMA retail CFD initial margins (percent of notional): major currency
# pairs 3.33% (30:1); other pairs, gold and major indices 5% (20:1); other
# commodities and indices 10%; everything else (bonds, shares) 20%;
# crypto 50% (2:1). A broker may ask more, never less.
_MAJOR_CURRENCIES = {"USD", "EUR", "JPY", "GBP", "CAD", "CHF"}
_MAJOR_INDICES = {"SP500", "NASDAQ100", "DAX", "GERMANY", "NIKKEI", "JAPAN", "FTSE100", "UK"}


def esma_margin_pct(market: Market) -> float:
    """Minimum retail margin for this market under the ESMA CFD rules."""
    name, cls = market.name, market.asset_class
    if cls == "forex":
        pair = {name[:3], name[3:]}
        return 3.33 if len(name) == 6 and pair <= _MAJOR_CURRENCIES else 5.0
    if cls == "crypto":
        return 50.0
    if name == "GOLD" or (cls == "index" and name in _MAJOR_INDICES):
        return 5.0
    if cls in ("commodity", "index"):
        return 10.0
    return 20.0
