"""List the models OpenRouter offers, with their real prices. Free, no key.

Reads the public catalogue (https://openrouter.ai/api/v1/models), which
needs no API key and costs nothing, keeps the vendors BND uses and prints
a Markdown table: exact model id, context size and price per million
tokens. Use it to choose BND_MODEL_* values and to price a council round.

    python -m src.bnd.openrouter_models [--vendors openai,anthropic] [--match opus]
"""

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from urllib.error import URLError
from urllib.request import Request, urlopen

URL = "https://openrouter.ai/api/v1/models"
VENDORS = ("openai", "anthropic", "google", "deepseek", "x-ai")
# Typical council call, to turn prices into a cost per agent and per round.
TOKENS_IN, TOKENS_OUT = 3000, 600


def per_million(value) -> Decimal | None:
    """OpenRouter quotes USD per token; convert to USD per million."""
    try:
        return Decimal(str(value)) * 1_000_000
    except (InvalidOperation, TypeError):
        return None


def parse(payload: dict, vendors=VENDORS, match: str = "") -> list[dict]:
    rows = []
    for item in payload.get("data", []):
        model = str(item.get("id", ""))
        if model.split("/")[0] not in vendors or match.lower() not in model.lower():
            continue
        prices = item.get("pricing") or {}
        price_in, price_out = per_million(prices.get("prompt")), per_million(prices.get("completion"))
        if price_in is None or price_out is None or price_in < 0 or price_out < 0:
            continue
        rows.append({
            "id": model, "context": item.get("context_length"),
            "input_per_million": price_in, "output_per_million": price_out,
            "call_usd": (price_in * TOKENS_IN + price_out * TOKENS_OUT) / 1_000_000,
        })
    rows.sort(key=lambda row: (row["id"].split("/")[0], row["call_usd"]))
    return rows


def render(rows: list[dict]) -> str:
    lines = [f"# Modele OpenRouter (preț per milion de tokeni; apel tipic = {TOKENS_IN} intrare "
             f"+ {TOKENS_OUT} ieșire)", "", f"{len(rows)} modele.", "",
             "| Model | Context | Intrare $/M | Ieșire $/M | Un apel $ |",
             "|---|---:|---:|---:|---:|"]
    lines += [f"| `{r['id']}` | {r['context'] or '–'} | {r['input_per_million']:.2f} | "
              f"{r['output_per_million']:.2f} | {r['call_usd']:.4f} |" for r in rows]
    return "\n".join(lines) + "\n"


def fetch(timeout: int = 30) -> dict:
    request = Request(URL, headers={"User-Agent": "bnd-research"}, method="GET")
    # Reviewed: fixed https URL constant, public catalogue, no credentials sent.
    with urlopen(request, timeout=timeout) as response:  # nosec B310
        return json.loads(response.read(20_000_000))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="openrouter_models")
    parser.add_argument("--vendors", default=",".join(VENDORS))
    parser.add_argument("--match", default="", help="keep ids containing this text")
    args = parser.parse_args(argv)
    try:
        rows = parse(fetch(), tuple(v.strip() for v in args.vendors.split(",")), args.match)
    except (URLError, OSError, ValueError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    sys.stdout.write(render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
