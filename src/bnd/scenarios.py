"""Stress scenarios: what today's positions would lose in a repeat of a crisis.

Each scenario is an instantaneous price shock per market, in percent,
roughly the peak-to-trough move of that episode in USD (stylised and
rounded, not exact history). Markets without their own value take their
asset class's default. Crypto values for 2008 are hypothetical: it did
not trade then. Forex moves are for the pair as quoted (EURUSD -20 means
the euro fell 20% against the dollar; USDJPY +30 means the dollar rose).

A shock is applied all at once to the current positions, without stops
or rebalancing, so it is a pessimistic view of a fast crash and an
optimistic one of a slow grind (where stops and sizing would react).
"""

from .paper_engine import PaperEngine

SCENARIOS = {
    "crisis_2008": {
        "description": "Global financial crisis, Sep-Nov 2008",
        "classes": {"index": -40, "bond": 8, "commodity": -40, "forex": 0, "crypto": -70, "stock": -45},
        "markets": {
            "EMERGING": -55, "US20Y_BOND": 20, "GOLD": -15, "SILVER": -45,
            "CRUDE_OIL": -65, "COPPER": -60, "NATURAL_GAS": -45,
            "EURUSD": -20, "GBPUSD": -30, "AUDUSD": -35, "USDJPY": -20,
            "USDCHF": 5, "USDCAD": 25,
        },
    },
    "covid_2020": {
        "description": "Covid crash, Feb-Mar 2020",
        "classes": {"index": -33, "bond": 5, "commodity": -25, "forex": 0, "crypto": -50, "stock": -35},
        "markets": {
            "NASDAQ100": -28, "GERMANY": -38, "DAX": -38, "GOLD": -5, "SILVER": -30,
            "CRUDE_OIL": -70, "US20Y_BOND": 10, "ETHEREUM": -60,
            "EURUSD": -3, "GBPUSD": -10, "AUDUSD": -15, "USDCAD": 10,
        },
    },
    "rates_2022": {
        "description": "Inflation and rate hikes, Jan-Oct 2022",
        "classes": {"index": -25, "bond": -15, "commodity": 10, "forex": 0, "crypto": -70, "stock": -28},
        "markets": {
            "NASDAQ100": -35, "EMERGING": -35, "US20Y_BOND": -35, "GOLD": -15,
            "SILVER": -20, "COPPER": -20, "NATURAL_GAS": 60, "CRUDE_OIL": 30,
            "ETHEREUM": -75, "EURUSD": -15, "GBPUSD": -20, "AUDUSD": -15,
            "USDJPY": 30, "USDCHF": 10, "USDCAD": 10,
        },
    },
    "flash_crash": {
        "description": "One-day crash like October 1987",
        "classes": {"index": -20, "bond": 3, "commodity": -10, "forex": 0, "crypto": -30, "stock": -22},
        "markets": {"GOLD": -3, "USDJPY": -5, "AUDUSD": -8},
    },
    "dollar_spike": {
        "description": "Sharp dollar rally",
        "classes": {"index": -5, "bond": 0, "commodity": -8, "forex": 0, "crypto": -10, "stock": -6},
        "markets": {
            "EMERGING": -12, "GOLD": -8, "SILVER": -12, "EURUSD": -10, "GBPUSD": -10,
            "AUDUSD": -12, "USDJPY": 10, "USDCHF": 8, "USDCAD": 8,
        },
    },
    "crypto_crash": {
        "description": "Crypto collapse within a week",
        "classes": {"index": -3, "bond": 0, "commodity": 0, "forex": 0, "crypto": -50, "stock": -4},
        "markets": {"ETHEREUM": -60},
    },
}


def shocks_for(scenario: str, instruments: dict) -> dict:
    """Per-symbol shock in percent; ``instruments`` maps symbol -> asset class."""
    spec = SCENARIOS[scenario]
    return {symbol: spec["markets"].get(symbol, spec["classes"].get(asset_class, 0))
            for symbol, asset_class in instruments.items()}


def run_scenarios(engine: PaperEngine) -> list[dict]:
    """Every scenario against the engine's current positions, worst first."""
    held = {p["symbol"]: p for p in engine.positions()}
    instruments = {s: engine.instrument(s).asset_class for s in held}
    limit = engine.limits().max_drawdown_pct
    peak = engine.account()["peak_equity"]
    rows = []
    for name, spec in SCENARIOS.items():
        shocks = shocks_for(name, instruments)
        result = engine.stress_test(shocks)
        losses = {s: p["quantity"] * engine.mark(s)["price"] * shocks[s] / 100
                  for s, p in held.items()}
        worst = min(losses, key=losses.get) if losses else None
        change = result["change_pct"] or 0.0
        rows.append({
            "scenario": name,
            "description": spec["description"],
            "change_pct": change,
            "shocked_equity": result["shocked_equity"],
            "worst_market": worst if worst and losses[worst] < 0 else None,
            # Drawdown is measured from the peak, as the kill switch does.
            "beyond_kill_switch": 100 * (peak - result["shocked_equity"]) / peak >= limit,
        })
    rows.sort(key=lambda row: row["change_pct"])
    return rows
