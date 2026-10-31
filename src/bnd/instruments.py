"""Harta instrumentelor: ce cumperi de fapt pentru fiecare piață din test.

Pentru fiecare piață: ETF-ul folosit în teste, contractul futures echivalent și
CFD-ul tipic (nume de simbol la brokeri; poate diferi puțin de la unul la altul).
Marja minimă și costul de tranzacționare sunt cele din modelul BND. Nu e o
recomandare de broker sau de produs: e o legătură între simbolurile folosite în
cercetare și instrumentele prin care ar putea fi tranzacționate.

    python -m src.bnd.instruments > docs/INSTRUMENTE.md
"""

import sys

from .universe import UNIVERSES, esma_margin_pct

# nume -> (ETF sau activ spot, contract futures, CFD tipic)
INSTRUMENTS = {
    "GOLD": ("GLD", "GC (COMEX)", "XAUUSD"),
    "SILVER": ("SLV", "SI (COMEX)", "XAGUSD"),
    "CRUDE_OIL": ("USO", "CL (NYMEX)", "USOIL / WTI"),
    "NATURAL_GAS": ("UNG", "NG (NYMEX)", "NATGAS"),
    "COPPER": ("CPER", "HG (COMEX)", "COPPER"),
    "AGRICULTURE": ("DBA", "ZC / ZW / ZS (CBOT)", "–"),
    "BROAD_COMMODITIES": ("DBC", "–", "–"),
    "CORN": ("–", "ZC (CBOT)", "CORN"),
    "WHEAT": ("–", "ZW (CBOT)", "WHEAT"),
    "SOYBEANS": ("–", "ZS (CBOT)", "SOYBEAN"),
    "SP500": ("SPY", "ES (CME)", "US500"),
    "NASDAQ100": ("QQQ", "NQ (CME)", "US100"),
    "GERMANY": ("EWG", "FDAX (Eurex)", "GER40"),
    "DAX": ("EWG", "FDAX (Eurex)", "GER40"),
    "JAPAN": ("EWJ", "NK (CME)", "JP225"),
    "NIKKEI": ("EWJ", "NK (CME)", "JP225"),
    "UK": ("EWU", "Z (ICE)", "UK100"),
    "FTSE100": ("EWU", "Z (ICE)", "UK100"),
    "EMERGING": ("EEM", "MES (CME, indice MSCI EM)", "–"),
    "US10Y_NOTE": ("IEF", "ZN (CBOT)", "US10Y"),
    "US20Y_BOND": ("TLT", "ZB (CBOT)", "US30Y"),
    "EURUSD": ("EUR/USD spot", "6E (CME)", "EURUSD"),
    "GBPUSD": ("GBP/USD spot", "6B (CME)", "GBPUSD"),
    "USDJPY": ("USD/JPY spot", "6J (CME, invers)", "USDJPY"),
    "AUDUSD": ("AUD/USD spot", "6A (CME)", "AUDUSD"),
    "USDCHF": ("USD/CHF spot", "6S (CME, invers)", "USDCHF"),
    "USDCAD": ("USD/CAD spot", "6C (CME, invers)", "USDCAD"),
    "BITCOIN": ("BTC spot (sau un ETF spot pe Bitcoin)", "BTC (CME)", "BTCUSD"),
    "ETHEREUM": ("ETH spot (sau un ETF spot pe Ethereum)", "ETH (CME)", "ETHUSD"),
}


def instrument(name: str) -> tuple[str, str, str]:
    """(activ/ETF, futures, CFD) pentru o piață; KeyError dacă nu e cunoscută."""
    if name in INSTRUMENTS:
        return INSTRUMENTS[name]
    stock_names = {m.name for m in UNIVERSES["stocks"]}
    if name in stock_names:
        return (name, "–", f"{name} (CFD pe acțiune)")
    raise KeyError(name)


def table() -> str:
    seen, rows = set(), []
    for universe in ("etf", "futures", "stocks"):
        for market in UNIVERSES[universe]:
            if market.name in seen:
                continue
            seen.add(market.name)
            asset, future, cfd = instrument(market.name)
            rows.append(f"| {market.name} | {market.asset_class} | {asset} | {future} | {cfd} | "
                        f"{esma_margin_pct(market):.2f}% | "
                        f"{market.fee_pct + market.slippage_pct:.3f}% |")
    return "\n".join([
        "# Instrumente pentru fiecare piață", "",
        "Generat cu `python -m src.bnd.instruments`. Nu e o recomandare de produs sau broker.", "",
        "| Piață | Clasă | Activ / ETF din teste | Futures echivalent | CFD tipic | Marjă minimă (ESMA) "
        "| Cost pe tranzacție (comision + alunecare) |",
        "|---|---|---|---|---|---:|---:|", *rows, ""])


def main() -> int:
    sys.stdout.write(table())
    return 0


if __name__ == "__main__":
    sys.exit(main())
