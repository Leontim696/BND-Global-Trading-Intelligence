"""Istoricul ratei de finanțare (funding) pentru perpetuele crypto, de la Binance.

Binance plătește funding la fiecare 8 ore (rata pe interval). Rata anuală
aproximativă = media pe interval × 3 × 365. Se folosește ca să se verifice
constanta de 10% pe an din modelul de costuri, nu înlocuiește simularea.

    python -m src.bnd.funding --symbol BTCUSDT --days 365
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from statistics import mean
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def parse_funding(rows) -> list[tuple[datetime, float]]:
    out = []
    for row in rows:
        try:
            out.append((datetime.fromtimestamp(int(row["fundingTime"]) / 1000, timezone.utc),
                        float(row["fundingRate"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Rând de funding invalid") from exc
    return sorted(out)


def annual_funding_pct(rates: list[tuple[datetime, float]]) -> dict:
    if not rates:
        raise ValueError("Niciun rând de funding")
    values = [r for _, r in rates]
    return {"intervals": len(values), "mean_per_interval_pct": 100 * mean(values),
            "annualised_pct": 100 * mean(values) * 3 * 365,
            "share_positive": sum(v > 0 for v in values) / len(values),
            "first": rates[0][0].isoformat(), "last": rates[-1][0].isoformat()}


def fetch_funding(symbol: str, days: int = 365, timeout: float = 30.0) -> list[tuple[datetime, float]]:
    if not symbol.isalnum() or not 1 <= days <= 1500:
        raise ValueError("Simbol sau număr de zile invalid")
    end = datetime.now(timezone.utc)
    start, rows = end - timedelta(days=days), []
    while start < end:
        query = urlencode({"symbol": symbol.upper(), "startTime": int(start.timestamp() * 1000),
                           "limit": 1000})
        request = Request(FUNDING_URL + "?" + query, method="GET")
        try:
            # Reviewed: fixed https URL constant.
            with urlopen(request, timeout=timeout) as response:  # nosec B310
                batch = json.loads(response.read(5_000_001))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise ValueError("Binance nu răspunde pentru funding") from exc
        if not batch:
            break
        rows += batch
        last = int(batch[-1]["fundingTime"]) / 1000
        if last <= start.timestamp():
            break
        start = datetime.fromtimestamp(last + 1, timezone.utc)
    return parse_funding(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="funding")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(annual_funding_pct(fetch_funding(args.symbol, args.days)), indent=2))
    except ValueError as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
