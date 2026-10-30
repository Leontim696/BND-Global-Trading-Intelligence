"""Two-call manual connectivity check, no trading and no automatic retries.

Provider-side key limit is required: estimates alone cannot cap spending.
The first GPT answer is passed to Claude for review. Never print secrets.
"""
import argparse
import json
import os
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CAP = Decimal("0.50")
MAX_OUTPUT = 250
MAX_INPUT_ESTIMATE = 2500
TASK = "Suggest one unit test for a Python function that rejects empty market symbols."
URL = "https://openrouter.ai/api/v1/chat/completions"


def preflight():
    if os.getenv("CONFIRM") != "YES" or os.getenv("LIMIT_CONFIRM") != "YES":
        raise RuntimeError("Explicit paid-test and provider-side key cap confirmations required")
    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        raise RuntimeError("OPENROUTER_API_KEY missing")
    costs = []
    for agent in ("GPT", "CLAUDE"):
        model = os.getenv(agent + "_MODEL", "").strip()
        if not model or model.lower() == "openrouter/auto":
            raise RuntimeError("Explicit model IDs required")
        if agent == "GPT" and "openai/" not in model.lower():
            raise RuntimeError("GPT model must be from OpenAI")
        if agent == "CLAUDE" and "anthropic/" not in model.lower():
            raise RuntimeError("Claude model must be from Anthropic")
        prices = []
        for suffix in ("IN", "OUT"):
            try:
                price = Decimal(os.getenv(agent + "_" + suffix, "").strip())
            except InvalidOperation:
                raise RuntimeError("Missing or non-numeric price for " + agent) from None
            if not price.is_finite() or price <= 0:
                raise RuntimeError("Positive finite prices required")
            prices.append(price)
        costs.append((prices[0] * MAX_INPUT_ESTIMATE + prices[1] * MAX_OUTPUT)
                     / Decimal(1_000_000))
    worst = sum(costs)
    if worst > CAP:
        raise RuntimeError("Conservative estimate exceeds USD 0.50")
    print("Preflight passed; two calls; estimated upper bound based on supplied prices:",
          str(worst), "USD (not a hard cap)")
    return worst


def call(agent, prompt):
    model = os.environ[agent + "_MODEL"].strip()
    payload = {
        "model": model,
        "provider": {"allow_fallbacks": False},
        "max_tokens": MAX_OUTPUT,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "You are a software code reviewer. "
             "Never place orders. Be concise. No secrets."},
            {"role": "user", "content": prompt[:6000]},
        ],
    }
    request = Request(URL, data=json.dumps(payload).encode(),
                      headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
                               "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=25) as response:
            raw = response.read(100001)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("OpenRouter request failed (no retry)") from exc
    if len(raw) > 100000:
        raise RuntimeError("Response too large")
    try:
        result = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("OpenRouter returned invalid JSON") from exc
    actual_model = result.get("model", "")
    if actual_model != model:
        raise RuntimeError("Model mismatch; aborting")
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("OpenRouter response has no message content") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Empty model response")
    usage = result.get("usage") or {}
    print(agent, "model verified; token usage:", json.dumps(usage))
    print(agent, "response:", content[:2500])
    return content


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    preflight()
    if args.execute:
        proposal = call("GPT", TASK)
        call("CLAUDE", "Review this GPT proposal for correctness and tests:\n"
             + proposal[:2500] + "\nOriginal task: " + TASK)


if __name__ == "__main__":
    main()
