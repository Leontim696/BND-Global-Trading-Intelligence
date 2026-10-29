"""Opt-in connectivity test for Gemini, DeepSeek, Grok; no trading."""
import json
import os
from decimal import Decimal
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

AGENTS = {"GEMINI": "google/", "DEEPSEEK": "deepseek/", "GROK": "x-ai/"}
CAP = Decimal("0.50")
MAX_OUTPUT = 150
MAX_INPUT = 1500
URL = "https://openrouter.ai/api/v1/chat/completions"


def preflight():
    if os.getenv("CONFIRM") != "YES" or os.getenv("LIMIT_CONFIRM") != "YES":
        raise RuntimeError("Manual approval and provider-side $0.50 cap required")
    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        raise RuntimeError("Missing API key")
    estimate = Decimal(0)
    for agent, prefix in AGENTS.items():
        model = os.getenv(agent + "_MODEL", "").strip()
        if not model.startswith(prefix) or model.lower().endswith("/auto"):
            raise RuntimeError("Explicit correct model required for " + agent)
        prices = []
        for kind in ("IN", "OUT"):
            price = Decimal(os.environ[agent + "_" + kind])
            if not price.is_finite() or price <= 0:
                raise RuntimeError("Invalid price for " + agent)
            prices.append(price)
        estimate += (MAX_INPUT * prices[0] + MAX_OUTPUT * prices[1]) / 1000000
    if estimate > CAP:
        raise RuntimeError("Preflight estimate exceeds USD 0.50")
    print("Preflight OK; three calls, estimate USD", estimate,
          "(provider-side limit is mandatory)")


def execute():
    preflight()
    for agent in AGENTS:
        model = os.environ[agent + "_MODEL"].strip()
        payload = {"model": model, "max_tokens": MAX_OUTPUT,
                   "provider": {"allow_fallbacks": False},
                   "messages": [
                       {"role": "system", "content": "Answer as a Python code reviewer. No trading."},
                       {"role": "user", "content": "In one sentence, identify a useful edge case test for a function that rejects an empty ticker."},
                   ]}
        request = Request(URL, data=json.dumps(payload).encode(),
                          headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
                                   "Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=25) as response:
                result = json.loads(response.read(100001))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(agent + " failed; no retries") from exc
        if result.get("model") != model:
            raise RuntimeError(agent + " returned unexpected model")
        answer = result["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError(agent + " empty answer")
        usage = result.get("usage", {})
        print(agent, "verified:", model, "usage:", json.dumps(usage))
        print(agent, "answer:", answer[:800])


if __name__ == "__main__":
    execute()
