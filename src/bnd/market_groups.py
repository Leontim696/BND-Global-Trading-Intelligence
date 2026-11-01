"""Categoriile piețelor, pentru afișare grupată în aplicație (crypto la crypto, acțiuni la acțiuni etc.)."""

GROUPS = (
    ("indici", "Indici bursieri"),
    ("actiuni", "Acțiuni americane"),
    ("aparare", "Apărare și armament"),
    ("marfuri", "Mărfuri și metale"),
    ("forex", "Forex"),
    ("obligatiuni", "Obligațiuni"),
    ("crypto", "Crypto"),
    ("memecoin", "Memecoin-uri"),
    ("alte", "Altele"),
)
_BY_CLASS = {"index": "indici", "commodity": "marfuri", "forex": "forex", "bond": "obligatiuni"}
_cache: dict = {}


def _build() -> dict:
    from .universe import UNIVERSES
    mapping = {}
    for universe in ("unic", "defense", "stocks", "etf", "crypto"):
        for market in UNIVERSES[universe]:
            if market.name in mapping:
                continue
            if market.asset_class == "stock":
                mapping[market.name] = "aparare" if market.sector == "armament" else "actiuni"
            elif market.asset_class == "crypto":
                mapping[market.name] = "memecoin" if market.sector == "memecoin" else "crypto"
            else:
                mapping[market.name] = _BY_CLASS.get(market.asset_class, "alte")
    return mapping


def group_of(name: str) -> str:
    if not _cache:
        _cache.update(_build())
    return _cache.get(name, "alte")


def labels() -> list:
    return [{"key": key, "label": label} for key, label in GROUPS]
