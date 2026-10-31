"""Run one five-agent round: parallel, budgeted, retried, with failover.

Independence: every agent receives the same market context and nothing
from the other agents; the request fingerprint is recorded per agent so
an audit can confirm it.

Each attempt is a separate gateway call, so each one reserves and
records its own cost. Before an attempt, its worst-case estimate must fit
the remaining round budget and the model's per-round cap; otherwise the
agent is skipped (fail closed). Retries are bounded; after the primary
gateway's attempts, an optional fallback gateway (e.g. an alternative
model for the same agent) is tried.
"""

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal
from threading import Lock

from .ai_cache import cache_key
from .ai_gateway import AIGateway, AIRequest, GatewayError
from .cost_tracker import BudgetExceeded, money
from .fusion_council import AGENTS, FusionCouncil


@dataclass
class AgentHealth:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    last_error: str | None = None
    last_latency_s: float | None = None

    @property
    def availability(self) -> float | None:
        return self.successes / self.attempts if self.attempts else None


@dataclass
class _Budget:
    round_usd: Decimal
    per_model_usd: dict
    spent: Decimal = Decimal("0")
    reserved: Decimal = Decimal("0")
    by_model: dict = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def reserve(self, model: str, estimate: Decimal) -> bool:
        with self.lock:
            model_total = self.by_model.get(model, Decimal("0"))
            cap = self.per_model_usd.get(model)
            if self.spent + self.reserved + estimate > self.round_usd:
                return False
            if cap is not None and model_total + estimate > cap:
                return False
            self.reserved += estimate
            self.by_model[model] = model_total + estimate
            return True

    def settle(self, model: str, estimate: Decimal, actual: Decimal) -> None:
        with self.lock:
            self.reserved -= estimate
            self.spent += actual
            self.by_model[model] = self.by_model.get(model, Decimal("0")) - estimate + actual


class CouncilRunner:
    def __init__(self, primary: AIGateway, fallback: AIGateway | None = None,
                 max_attempts: int = 2, backoff_seconds: float = 1.0,
                 sleep=time.sleep, clock=time.monotonic, cache=None):
        if not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        self.primary, self.fallback = primary, fallback
        self.max_attempts, self.backoff_seconds = max_attempts, backoff_seconds
        self.sleep, self.clock = sleep, clock
        # Optional ai_cache.ResponseCache: identical questions are not paid twice.
        self.cache = cache
        self.health = {agent: AgentHealth() for agent in AGENTS}

    def availability(self) -> dict:
        return {agent: {**vars(h), "availability": h.availability}
                for agent, h in self.health.items()}

    def _attempt_agent(self, agent, market, symbol, context, budget):
        request = AIRequest(agent=agent, market=market, symbol=symbol, context=context)
        record = {"agent": agent, "status": "failed", "attempts": [],
                  "request_sha256": hashlib.sha256(
                      f"{market}\n{symbol}\n{context}".encode()).hexdigest()}
        gateways = [g for g in (self.primary, self.fallback) if g is not None]
        if self.cache is not None:
            key = cache_key(agent, self.primary._expected_model(agent), market, symbol, context)
            cached = self.cache.get(key)
            if cached is not None:
                record.update(status="ok", cached=True, model=cached.model,
                              provider=cached.provider, route="cache", cost_usd="0",
                              latency_s=0.0, input_tokens=cached.input_tokens,
                              output_tokens=cached.output_tokens)
                return record, cached
        for route, gateway in enumerate(gateways):
            for attempt in range(self.max_attempts):
                model = gateway._expected_model(agent)
                try:
                    estimate = gateway.estimate_cost(agent)
                except GatewayError as exc:
                    record["attempts"].append({"route": route, "model": model,
                                               "error": type(exc).__name__})
                    break
                if not budget.reserve(model, estimate):
                    record["status"] = "skipped_budget"
                    record["attempts"].append({"route": route, "model": model,
                                               "error": "round_or_model_budget"})
                    return record, None
                health = self.health[agent]
                health.attempts += 1
                started = self.clock()
                try:
                    response = gateway.analyze(request)
                except BudgetExceeded as exc:
                    # Persistent daily/monthly budget refused or overran: stop.
                    budget.settle(model, estimate, Decimal("0"))
                    health.failures += 1
                    health.consecutive_failures += 1
                    health.last_error = type(exc).__name__
                    record["status"] = "skipped_budget"
                    record["attempts"].append({"route": route, "model": model,
                                               "error": type(exc).__name__})
                    return record, None
                except Exception as exc:    # GatewayError sau o eroare neașteptată a unui adaptor
                    # Un singur agent defect nu poate opri runda: se notează și se merge mai departe,
                    # fără să se inventeze un vot.
                    budget.settle(model, estimate, Decimal("0"))
                    health.failures += 1
                    health.consecutive_failures += 1
                    health.last_error = type(exc).__name__
                    record["attempts"].append({"route": route, "model": model,
                                               "error": type(exc).__name__})
                    if attempt + 1 < self.max_attempts:
                        self.sleep(self.backoff_seconds * (attempt + 1))
                    continue
                latency = self.clock() - started
                cost = gateway.actual_cost(response)
                budget.settle(model, estimate, cost)
                health.successes += 1
                health.consecutive_failures = 0
                health.last_latency_s = latency
                record.update(status="ok", model=response.model, provider=response.provider,
                              route="primary" if route == 0 else "fallback",
                              cost_usd=str(cost), latency_s=latency,
                              input_tokens=response.input_tokens,
                              output_tokens=response.output_tokens)
                record["attempts"].append({"route": route, "model": response.model, "error": None})
                if self.cache is not None:
                    self.cache.put(cache_key(agent, model, market, symbol, context),
                                   response, cost)
                return record, response
        return record, None

    def run_round(self, market: str, symbol: str, context: str, round_budget_usd,
                  per_model_budget_usd: dict | None = None, parallel: bool = True) -> dict:
        """Ask all five agents independently; build the council from valid answers."""

        budget = _Budget(money(round_budget_usd),
                         {model: money(cap) for model, cap in (per_model_budget_usd or {}).items()})
        if self.primary.live_authorization is not None and \
                budget.round_usd > self.primary.live_authorization.max_round_usd:
            raise ValueError("Round budget exceeds the authorised maximum")

        def one(agent):
            return self._attempt_agent(agent, market, symbol, context, budget)

        if parallel:
            with ThreadPoolExecutor(max_workers=len(AGENTS)) as pool:
                results = list(pool.map(one, AGENTS))
        else:
            results = [one(agent) for agent in AGENTS]

        council = FusionCouncil()
        agents = {}
        for record, response in results:
            agents[record["agent"]] = record
            if response is not None:
                council.submit(response.to_opinion())
        complete = len(council.initial_opinions) == len(AGENTS)
        return {
            "market": market,
            "symbol": symbol,
            "complete": complete,
            "agents": agents,
            "spent_usd": str(budget.spent),
            "round_budget_usd": str(budget.round_usd),
            "council": council,
            "audit": council.audit_log(),
            "note": None if complete else
                    "Incomplete round: decisions need all five agents, so the outcome is NO TRADE.",
        }
