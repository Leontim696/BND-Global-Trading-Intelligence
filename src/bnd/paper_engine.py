"""Persistent paper-trading engine. Virtual money only; LIVE is refused.

State lives in one SQLite file, and every bar and order is processed in a
single transaction, so a crash or restart resumes from the last committed
state. Each order carries a client order id: submitting it again returns
the existing order instead of trading twice.

Mandatory risk controls run on every order and cannot be bypassed:
persistent kill switch, stale or gapped market data, per-instrument and
per-sector exposure, gross leverage, daily loss and drawdown limits, and
a protective stop on every opening order. An unexpected error during bar
processing rolls the bar back and trips the kill switch.
"""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import isfinite, log, sqrt
from pathlib import Path

from .market_data import Candle
from .safety import require_writable_account, trading_mode
from .risk_engine import Portfolio, RiskDecision, RiskLimits, TradeProposal, evaluate_risk

SECONDS_PER_YEAR = 365.25 * 24 * 3600


class TradingMode(str, Enum):
    MOCK = "MOCK"
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class PaperEngineError(Exception):
    """Raised for invalid engine use; risk refusals are rejected orders."""


@dataclass(frozen=True)
class Instrument:
    symbol: str
    asset_class: str
    sector: str = ""
    fee_pct: float = 0.05
    slippage_pct: float = 0.05
    carry_pct_annual: float = 0.0
    # Largest share of one bar's volume an order may take (None: no cap).
    max_participation: float | None = None
    # Forex only: the pair as quoted, e.g. "EURUSD" (long = long EUR, short USD).
    currency_pair: str = ""
    # Broker margin per unit of |notional|, in percent (3.33 = 30:1); 0 = none.
    margin_pct: float = 0.0

    def __post_init__(self):
        if not self.symbol.strip() or not self.asset_class.strip():
            raise PaperEngineError("Instrument symbol and asset class are required")
        for value in (self.fee_pct, self.slippage_pct, self.carry_pct_annual):
            if not isfinite(value) or value < 0:
                raise PaperEngineError("Costs must be finite and nonnegative")
        if self.max_participation is not None and not 0 < self.max_participation <= 1:
            raise PaperEngineError("max_participation must be in (0, 1]")
        if not isfinite(self.margin_pct) or not 0 <= self.margin_pct <= 100:
            raise PaperEngineError("margin_pct must be in [0, 100]")
        if self.currency_pair and not (len(self.currency_pair) == 6
                                       and self.currency_pair.isalpha()
                                       and self.currency_pair.isupper()):
            raise PaperEngineError("currency_pair must look like EURUSD")


@dataclass(frozen=True)
class EngineLimits:
    max_gross_leverage: float = 3.0
    max_position_pct: float = 100.0      # |position| / equity, per instrument
    max_sector_pct: float = 150.0        # |sector exposure| / equity
    max_currency_pct: float = 100.0      # |net exposure to one currency| / equity
    # Annual volatility of the whole book from recent joint returns, so
    # markets that move together count together (0 disables).
    max_portfolio_vol_pct: float = 40.0
    # Annual rate charged each calendar day on exposure above equity (a
    # margin loan, as for leveraged ETFs); 0 = none. Charged from the
    # previous closes when a new day starts.
    financing_pct_annual: float = 0.0
    vol_lookback: int = 60
    max_daily_loss_pct: float = 5.0      # kill switch trigger
    max_drawdown_pct: float = 25.0       # kill switch trigger
    max_risk_per_trade_pct: float = 2.0  # loss at the stop, as % of equity
    max_data_age: timedelta = timedelta(days=4)
    max_gap_pct: float = 15.0            # no new risk on a bar gapping more
    maintenance_margin_pct: float = 10.0 # liquidate below this % of gross
    # Broker close-out: liquidate when equity falls below this share of the
    # margin the positions require (ESMA retail rule: 50%).
    margin_closeout_pct: float = 50.0
    require_stop_loss: bool = True
    order_expiry_bars: int = 5

    def risk_limits(self) -> RiskLimits:
        return RiskLimits(
            max_risk_per_trade_pct=self.max_risk_per_trade_pct,
            max_daily_loss_pct=self.max_daily_loss_pct,
            max_drawdown_pct=self.max_drawdown_pct,
            max_gross_exposure_pct=100 * self.max_gross_leverage,
            max_leverage=self.max_gross_leverage,
        )


@dataclass(frozen=True)
class OrderRequest:
    client_order_id: str
    symbol: str
    side: str                   # "BUY" or "SELL"
    quantity: float
    order_type: str = "MARKET"  # or "LIMIT"
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop_pct: float | None = None
    reduce_only: bool = False
    source: str = ""            # e.g. the council decision id

    def __post_init__(self):
        if not self.client_order_id.strip():
            raise PaperEngineError("client_order_id is required")
        if self.side not in ("BUY", "SELL"):
            raise PaperEngineError("side must be BUY or SELL")
        if self.order_type not in ("MARKET", "LIMIT"):
            raise PaperEngineError("order_type must be MARKET or LIMIT")
        if not isfinite(self.quantity) or self.quantity <= 0:
            raise PaperEngineError("quantity must be positive")
        if self.order_type == "LIMIT" and not (self.limit_price and self.limit_price > 0):
            raise PaperEngineError("LIMIT orders need a positive limit_price")
        if self.trailing_stop_pct is not None and not 0 < self.trailing_stop_pct < 100:
            raise PaperEngineError("trailing_stop_pct must be in (0, 100)")


SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    currency TEXT NOT NULL, initial_capital REAL NOT NULL, cash REAL NOT NULL,
    peak_equity REAL NOT NULL, day TEXT, day_start_equity REAL NOT NULL,
    kill_switch INTEGER NOT NULL DEFAULT 0, kill_reason TEXT, kill_at TEXT,
    limits TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS instruments (symbol TEXT PRIMARY KEY, spec TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS marks (
    symbol TEXT PRIMARY KEY, price REAL NOT NULL, time TEXT NOT NULL,
    previous_close REAL
);
CREATE TABLE IF NOT EXISTS closes (
    symbol TEXT NOT NULL, time TEXT NOT NULL, price REAL NOT NULL,
    PRIMARY KEY (symbol, time)
);
CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY, quantity REAL NOT NULL, avg_price REAL NOT NULL,
    stop_loss REAL, take_profit REAL, trailing_stop_pct REAL,
    best_price REAL, opened_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    client_order_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
    order_type TEXT NOT NULL, quantity REAL NOT NULL, limit_price REAL,
    stop_loss REAL, take_profit REAL, trailing_stop_pct REAL,
    reduce_only INTEGER NOT NULL, source TEXT, status TEXT NOT NULL,
    filled_quantity REAL NOT NULL DEFAULT 0, average_price REAL,
    reason TEXT, bars_waited INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client_order_id TEXT, symbol TEXT NOT NULL,
    quantity REAL NOT NULL, price REAL NOT NULL, fee REAL NOT NULL,
    reason TEXT NOT NULL, time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL,
    kind TEXT NOT NULL, payload TEXT NOT NULL
);
"""


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PaperEngineError("Timezone-aware times required")
    return value.astimezone(timezone.utc).isoformat()


class PaperEngine:
    """Virtual account. Use ``create`` for a new account, ``open`` to resume."""

    mode = TradingMode.PAPER

    def __init__(self, path):
        # Orice cont virtual cere un mod permis (MOCK/PAPER): o configurare greșită
        # (BND_TRADING_MODE=LIVE sau o valoare necunoscută) oprește motorul aici,
        # indiferent de punctul de intrare.
        trading_mode()
        require_writable_account()
        self.path = str(Path(path))
        self._db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout = 30000")
        self._db.executescript(SCHEMA)

    # -- lifecycle -----------------------------------------------------

    @classmethod
    def create(cls, path, initial_capital: float, *, currency: str = "EUR",
               limits: EngineLimits | None = None, now: datetime | None = None):
        """Start a new account. The capital must be given explicitly."""
        if not isfinite(initial_capital) or initial_capital <= 0:
            raise PaperEngineError("Initial capital must be positive and confirmed")
        engine = cls(path)
        if engine._db.execute("SELECT 1 FROM account").fetchone():
            raise PaperEngineError("Account already exists; use PaperEngine.open")
        limits = limits or EngineLimits()
        now = _iso(now or datetime.now(timezone.utc))
        engine._db.execute(
            "INSERT INTO account (id, currency, initial_capital, cash, peak_equity,"
            " day_start_equity, limits, created_at) VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
            (currency, initial_capital, initial_capital, initial_capital,
             initial_capital, _limits_json(limits), now))
        engine._log("account_created", {"capital": initial_capital, "currency": currency}, now)
        return engine

    @classmethod
    def open(cls, path):
        if not Path(path).exists():
            raise PaperEngineError("No paper account at " + str(path))
        engine = cls(path)
        if not engine._db.execute("SELECT 1 FROM account").fetchone():
            raise PaperEngineError("File has no paper account")
        return engine

    def close(self):
        self._db.close()

    @staticmethod
    def require_mode(mode: TradingMode) -> None:
        """Real orders are never sent: only MOCK and PAPER are allowed."""
        if mode == TradingMode.LIVE:
            raise PaperEngineError("LIVE trading is not authorised in this system")

    @contextmanager
    def _transaction(self):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        else:
            self._db.execute("COMMIT")

    # -- reads ---------------------------------------------------------

    def account(self) -> dict:
        row = dict(self._db.execute("SELECT * FROM account").fetchone())
        row["limits"] = json.loads(row["limits"])
        return row

    def limits(self) -> EngineLimits:
        data = json.loads(self._db.execute("SELECT limits FROM account").fetchone()[0])
        data["max_data_age"] = timedelta(seconds=data["max_data_age"])
        return EngineLimits(**data)

    def instrument(self, symbol: str) -> Instrument:
        row = self._db.execute("SELECT spec FROM instruments WHERE symbol = ?", (symbol,)).fetchone()
        if row is None:
            raise PaperEngineError("Unknown instrument " + symbol)
        return Instrument(**json.loads(row[0]))

    def positions(self) -> list[dict]:
        return [dict(r) for r in self._db.execute("SELECT * FROM positions ORDER BY symbol")]

    def orders(self, status: str | None = None) -> list[dict]:
        query, args = "SELECT * FROM orders", ()
        if status:
            query, args = query + " WHERE status = ?", (status,)
        return [dict(r) for r in self._db.execute(query + " ORDER BY created_at, client_order_id", args)]

    def order(self, client_order_id: str) -> dict | None:
        row = self._db.execute("SELECT * FROM orders WHERE client_order_id = ?",
                               (client_order_id,)).fetchone()
        return dict(row) if row else None

    def fills(self) -> list[dict]:
        return [dict(r) for r in self._db.execute("SELECT * FROM fills ORDER BY id")]

    def journal(self, kind: str | None = None) -> list[dict]:
        query, args = "SELECT * FROM journal", ()
        if kind:
            query, args = query + " WHERE kind = ?", (kind,)
        rows = self._db.execute(query + " ORDER BY id", args)
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def mark(self, symbol: str) -> dict | None:
        row = self._db.execute("SELECT * FROM marks WHERE symbol = ?", (symbol,)).fetchone()
        return dict(row) if row else None

    def equity(self) -> float:
        cash = self._db.execute("SELECT cash FROM account").fetchone()[0]
        return cash + sum(p["quantity"] * self._price(p["symbol"]) for p in self.positions())

    def gross_exposure(self) -> float:
        return sum(abs(p["quantity"]) * self._price(p["symbol"]) for p in self.positions())

    def _price(self, symbol: str) -> float:
        mark = self.mark(symbol)
        if mark is None:
            raise PaperEngineError("No price for " + symbol)
        return mark["price"]

    def summary(self) -> dict:
        account = self.account()
        equity = self.equity()
        return {
            "currency": account["currency"],
            "initial_capital": account["initial_capital"],
            "cash": account["cash"],
            "equity": equity,
            "net_profit": equity - account["initial_capital"],
            "gross_leverage": self.gross_exposure() / equity if equity > 0 else None,
            "positions": self.positions(),
            "open_orders": [o for o in self.orders() if o["status"] in ("PENDING", "PARTIAL")],
            "kill_switch": bool(account["kill_switch"]),
            "kill_reason": account["kill_reason"],
            "fills": len(self.fills()),
        }

    # -- writes --------------------------------------------------------

    def register_instrument(self, instrument: Instrument) -> None:
        self._db.execute("INSERT OR REPLACE INTO instruments (symbol, spec) VALUES (?, ?)",
                         (instrument.symbol, json.dumps(asdict(instrument))))

    def record(self, kind: str, payload: dict, now: datetime) -> None:
        """Add an entry (e.g. a council decision) to the audit journal."""
        with self._transaction():
            self._log(kind, payload, _iso(now))

    def _log(self, kind: str, payload: dict, time: str) -> None:
        self._db.execute("INSERT INTO journal (time, kind, payload) VALUES (?, ?, ?)",
                         (time, kind, json.dumps(payload, default=str)))

    def submit_order(self, request: OrderRequest, now: datetime) -> dict:
        """Validate and queue an order for the next bar. Idempotent by id."""
        now_text = _iso(now)
        with self._transaction():
            existing = self.order(request.client_order_id)
            if existing is not None:
                self._log("duplicate_order_ignored", {"client_order_id": request.client_order_id}, now_text)
                return existing
            reason = self._pre_trade_check(request, now)
            status = OrderStatus.REJECTED if reason else OrderStatus.PENDING
            self._db.execute(
                "INSERT INTO orders (client_order_id, symbol, side, order_type, quantity,"
                " limit_price, stop_loss, take_profit, trailing_stop_pct, reduce_only, source,"
                " status, reason, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (request.client_order_id, request.symbol, request.side, request.order_type,
                 request.quantity, request.limit_price, request.stop_loss, request.take_profit,
                 request.trailing_stop_pct, int(request.reduce_only), request.source,
                 status.value, reason, now_text, now_text))
            self._log("order_" + status.value.lower(), {**asdict(request), "reason": reason}, now_text)
            return self.order(request.client_order_id)

    def cancel_order(self, client_order_id: str, now: datetime) -> dict:
        with self._transaction():
            order = self.order(client_order_id)
            if order is None:
                raise PaperEngineError("Unknown order " + client_order_id)
            if order["status"] in ("PENDING", "PARTIAL"):
                self._set_order(client_order_id, OrderStatus.CANCELLED, _iso(now), "Cancelled")
            return self.order(client_order_id)

    def reset_kill_switch(self, confirmation: str, now: datetime) -> None:
        """Manual, explicit restart after a kill switch."""
        if confirmation != "RESET-KILL-SWITCH":
            raise PaperEngineError("Confirmation text RESET-KILL-SWITCH required")
        with self._transaction():
            equity = self.equity()
            self._db.execute(
                "UPDATE account SET kill_switch = 0, kill_reason = NULL, kill_at = NULL,"
                " peak_equity = ?, day_start_equity = ?", (equity, equity))
            self._log("kill_switch_reset", {"equity": equity}, _iso(now))

    # -- risk ----------------------------------------------------------

    def _pre_trade_check(self, request: OrderRequest, now: datetime) -> str | None:
        account = self.account()
        limits = self.limits()
        if account["kill_switch"]:
            return "Kill switch active: " + (account["kill_reason"] or "")
        try:
            instrument = self.instrument(request.symbol)
        except PaperEngineError as exc:
            return str(exc)
        mark = self.mark(request.symbol)
        if mark is None:
            return "No market data for " + request.symbol
        if now - datetime.fromisoformat(mark["time"]) > limits.max_data_age:
            return "Stale market data for " + request.symbol
        price = request.limit_price or mark["price"]

        position = self._position(request.symbol)
        held = position["quantity"] if position else 0.0
        signed = request.quantity if request.side == "BUY" else -request.quantity
        after = held + signed
        reduces = abs(after) < abs(held) and (after == 0 or (after > 0) == (held > 0))
        if request.reduce_only and not reduces:
            return "reduce_only order would increase or flip the position"
        if reduces:
            return None  # Risk-reducing orders are always allowed.

        if limits.require_stop_loss and request.stop_loss is None:
            return "A protective stop_loss is required for opening orders"
        if request.stop_loss is not None:
            wrong_side = (request.stop_loss >= price) if signed > 0 else (request.stop_loss <= price)
            if wrong_side:
                return "stop_loss must be below entry for BUY and above for SELL"
        if mark["previous_close"] and abs(mark["price"] / mark["previous_close"] - 1) * 100 > limits.max_gap_pct:
            return "Extreme gap on the last bar: no new risk"

        equity = self.equity()
        if equity <= 0:
            return "No equity"
        if abs(after) * price / equity * 100 > limits.max_position_pct + 1e-9:
            return f"Position limit {limits.max_position_pct}% of equity for {request.symbol}"
        sector = instrument.sector or instrument.asset_class
        sector_exposure = sum(
            abs(p["quantity"]) * self._price(p["symbol"]) for p in self.positions()
            if p["symbol"] != request.symbol and
            (self.instrument(p["symbol"]).sector or self.instrument(p["symbol"]).asset_class) == sector
        ) + abs(after) * price
        if sector_exposure / equity * 100 > limits.max_sector_pct + 1e-9:
            return f"Sector limit {limits.max_sector_pct}% of equity for {sector}"

        if instrument.margin_pct:
            required = self.margin_required({request.symbol: after * price})
            if required > equity + 1e-9:
                return (f"Margin: positions would need {required:.2f}, "
                        f"equity is {equity:.2f}")

        if limits.max_portfolio_vol_pct:
            before_vol = self.portfolio_volatility()
            after_vol = self.portfolio_volatility({request.symbol: after * price})
            if (after_vol is not None and after_vol * 100 > limits.max_portfolio_vol_pct + 1e-9
                    and (before_vol is None or after_vol > before_vol + 1e-12)):
                return (f"Portfolio volatility {100 * after_vol:.1f}% would exceed "
                        f"{limits.max_portfolio_vol_pct}% (markets moving together)")

        if instrument.currency_pair:
            before = self.currency_exposure()
            now_exposure = self.currency_exposure({request.symbol: after * price})
            for currency in _pair_currencies(instrument.currency_pair):
                if currency == account["currency"]:
                    continue
                new = abs(now_exposure.get(currency, 0.0))
                if (new / equity * 100 > limits.max_currency_pct + 1e-9
                        and new > abs(before.get(currency, 0.0)) + 1e-9):
                    return f"Currency limit {limits.max_currency_pct}% of equity for {currency}"

        increase = abs(after) - abs(held) if (after > 0) == (held > 0) or held == 0 else abs(after)
        gross_other = self.gross_exposure() - abs(held) * self._price(request.symbol)
        stop_distance = (abs(price - request.stop_loss) / price * 100
                         if request.stop_loss is not None else 100.0)
        risk = evaluate_risk(
            Portfolio(
                equity=equity,
                daily_loss=max(0.0, account["day_start_equity"] - equity),
                drawdown=max(0.0, account["peak_equity"] - equity),
                gross_exposure=gross_other + abs(held) * price,
            ),
            TradeProposal(
                notional=increase * price,
                stop_loss_pct=min(100.0, max(stop_distance, 1e-6)),
                leverage=max(1.0, (gross_other + abs(after) * price) / equity),
            ),
            limits.risk_limits(),
        )
        if risk.decision == RiskDecision.REJECT:
            return "Risk engine: " + risk.reason
        if risk.decision == RiskDecision.APPROVE_REDUCED:
            return (f"Risk engine allows at most {risk.approved_notional:.2f} notional; "
                    "resubmit a smaller order")
        return None

    def currency_exposure(self, override: dict | None = None) -> dict:
        """Net exposure per currency from forex positions, in account money.

        A long EURUSD position worth N is +N EUR and -N USD. Other
        instruments are treated as priced in the account currency.
        ``override`` maps symbol -> signed value to use instead (what-if).
        """
        values = {p["symbol"]: p["quantity"] * self._price(p["symbol"]) for p in self.positions()}
        values.update(override or {})
        exposure: dict = {}
        for symbol, value in values.items():
            pair = self.instrument(symbol).currency_pair
            if pair:
                base, quote = _pair_currencies(pair)
                exposure[base] = exposure.get(base, 0.0) + value
                exposure[quote] = exposure.get(quote, 0.0) - value
        return exposure

    def _record_close(self, symbol, price, time):
        keep = self.limits().vol_lookback + 1
        self._db.execute("INSERT OR REPLACE INTO closes (symbol, time, price) VALUES (?, ?, ?)",
                         (symbol, time, price))
        self._db.execute(
            "DELETE FROM closes WHERE symbol = ? AND time NOT IN (SELECT time FROM closes"
            " WHERE symbol = ? ORDER BY time DESC LIMIT ?)", (symbol, symbol, keep))

    def margin_required(self, override: dict | None = None) -> float:
        """Broker margin the positions need: sum of |value| x margin_pct."""
        values = {p["symbol"]: p["quantity"] * self._price(p["symbol"]) for p in self.positions()}
        values.update(override or {})
        return sum(abs(value) * self.instrument(symbol).margin_pct / 100
                   for symbol, value in values.items())

    def portfolio_volatility(self, override: dict | None = None) -> float | None:
        """Annualised volatility of today's positions over recent joint returns.

        Each date's book return is the sum of value-weighted log returns of
        the markets that traded that day, so correlations are included.
        ``override`` maps symbol -> signed value to use instead (what-if).
        None while there are fewer than 20 return dates.
        """
        equity = self.equity()
        if equity <= 0:
            return None
        values = {p["symbol"]: p["quantity"] * self._price(p["symbol"]) for p in self.positions()}
        values.update(override or {})
        weights = {symbol: value / equity for symbol, value in values.items() if value}
        if not weights:
            return 0.0
        by_date: dict = {}
        for symbol, weight in weights.items():
            rows = self._db.execute("SELECT time, price FROM closes WHERE symbol = ? ORDER BY time",
                                    (symbol,)).fetchall()
            for (_, a), (time, b) in zip(rows, rows[1:]):
                day = time[:10]
                by_date[day] = by_date.get(day, 0.0) + weight * log(b / a)
        days = sorted(by_date)[-self.limits().vol_lookback:]
        if len(days) < 20:
            return None
        span = (datetime.fromisoformat(days[-1]) - datetime.fromisoformat(days[0])).days
        if span <= 0:
            return None
        series = [by_date[d] for d in days]
        mean = sum(series) / len(series)
        variance = sum((r - mean) ** 2 for r in series) / (len(series) - 1)
        return sqrt(variance * (len(series) - 1) * 365.25 / span)

    def stress_test(self, shocks_pct: dict) -> dict:
        """Equity after instantaneous price shocks, without changing state."""
        equity = self.equity()
        loss = sum(p["quantity"] * self._price(p["symbol"]) * shocks_pct.get(p["symbol"], 0.0) / 100
                   for p in self.positions())
        return {"equity": equity, "shocked_equity": equity + loss,
                "change_pct": 100 * loss / equity if equity else None}

    # -- bars ----------------------------------------------------------

    def on_bar(self, symbol: str, candle: Candle) -> None:
        """Process one closed bar: exits, fills, carry, marks, risk checks."""
        try:
            with self._transaction():
                self._process_bar(symbol, candle)
        except Exception as exc:
            # Safe stop: the bar was rolled back; refuse new risk until reset.
            with self._transaction():
                self._trip(f"Error while processing {symbol}: {type(exc).__name__}: {exc}",
                           _iso(candle.open_time))
            raise

    def _process_bar(self, symbol: str, candle: Candle) -> None:
        instrument = self.instrument(symbol)
        time = _iso(candle.open_time)
        mark = self.mark(symbol)
        if mark and datetime.fromisoformat(mark["time"]) >= candle.open_time:
            self._log("bar_ignored", {"symbol": symbol, "time": time, "reason": "not newer"}, time)
            return
        previous_close = mark["price"] if mark else None
        previous_time = datetime.fromisoformat(mark["time"]) if mark else None

        # The new day starts from the previous closes, before this open,
        # so an overnight gap counts against the new day's loss limit.
        self._new_day(candle.open_time)

        # Carry for the position held since the previous bar, charged
        # before this bar's fills so a new position pays nothing for the
        # time before it existed.
        if previous_time is not None and instrument.carry_pct_annual:
            position = self._position(symbol)
            if position:
                years = (candle.open_time - previous_time).total_seconds() / SECONDS_PER_YEAR
                carry = abs(position["quantity"]) * previous_close * instrument.carry_pct_annual / 100 * years
                self._add_cash(-carry)
                self._log("carry", {"symbol": symbol, "amount": carry}, time)

        self._set_mark(symbol, candle.open, time, previous_close)
        self._exit_checks(symbol, instrument, candle, time)
        self._fill_orders(symbol, instrument, candle, time)
        # A position opened at this open is also checked against this
        # bar's range for its fixed stop (the pessimistic assumption).
        # Older positions were already checked above: checking them again
        # would use this bar's high to move a trailing stop and then test
        # it against the same bar's low.
        position = self._position(symbol)
        if position and position["opened_at"] == time:
            self._exit_checks(symbol, instrument, candle, time, stops_only=True)

        self._set_mark(symbol, candle.close, time, previous_close)
        self._record_close(symbol, candle.close, time)
        self._after_mark(time)

    def _set_mark(self, symbol, price, time, previous_close):
        self._db.execute(
            "INSERT INTO marks (symbol, price, time, previous_close) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(symbol) DO UPDATE SET price = excluded.price, time = excluded.time,"
            " previous_close = excluded.previous_close", (symbol, price, time, previous_close))

    def _new_day(self, when: datetime) -> None:
        day = when.astimezone(timezone.utc).date().isoformat()
        account = self.account()
        if account["day"] != day:
            self._charge_financing(account["day"], day, when)
            # Day starts from the previous marks, so overnight gaps count.
            self._db.execute("UPDATE account SET day = ?, day_start_equity = ?",
                             (day, self.equity()))

    def _charge_financing(self, previous_day, day, when) -> None:
        """Interest on the borrowed part of the book for the days that passed."""
        rate = self.limits().financing_pct_annual
        if not rate or previous_day is None:
            return
        days = (datetime.fromisoformat(day) - datetime.fromisoformat(previous_day)).days
        borrowed = self.gross_exposure() - self.equity()
        if days <= 0 or borrowed <= 0:
            return
        interest = borrowed * rate / 100 * days / 365.25
        self._add_cash(-interest)
        self._log("financing", {"amount": interest, "borrowed": borrowed, "days": days},
                  _iso(when))

    def _position(self, symbol):
        row = self._db.execute("SELECT * FROM positions WHERE symbol = ?", (symbol,)).fetchone()
        return dict(row) if row else None

    def _add_cash(self, amount):
        self._db.execute("UPDATE account SET cash = cash + ?", (amount,))

    def _fill(self, symbol, instrument, quantity, raw_price, reason, time, order=None):
        """Trade ``quantity`` (signed) at ``raw_price`` plus slippage and fee."""
        slip = instrument.slippage_pct / 100
        price = raw_price * (1 + slip) if quantity > 0 else raw_price * (1 - slip)
        if order and order["order_type"] == "LIMIT" and order["limit_price"]:
            # A limit order never fills worse than its limit, slippage included.
            limit = order["limit_price"]
            price = min(price, limit) if quantity > 0 else max(price, limit)
        fee = abs(quantity) * price * instrument.fee_pct / 100
        self._add_cash(-quantity * price - fee)
        position = self._position(symbol)
        held = position["quantity"] if position else 0.0
        after = held + quantity
        if abs(after) < 1e-12:
            self._db.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        elif position is None or (held > 0) != (after > 0):
            stop = order["stop_loss"] if order else None
            self._db.execute(
                "INSERT OR REPLACE INTO positions (symbol, quantity, avg_price, stop_loss,"
                " take_profit, trailing_stop_pct, best_price, opened_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, after, price, stop, order["take_profit"] if order else None,
                 order["trailing_stop_pct"] if order else None, price, time))
        elif abs(after) > abs(held):
            average = (abs(held) * position["avg_price"] + abs(quantity) * price) / abs(after)
            self._db.execute("UPDATE positions SET quantity = ?, avg_price = ? WHERE symbol = ?",
                             (after, average, symbol))
        else:
            self._db.execute("UPDATE positions SET quantity = ? WHERE symbol = ?", (after, symbol))
        self._db.execute(
            "INSERT INTO fills (client_order_id, symbol, quantity, price, fee, reason, time)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (order["client_order_id"] if order else None, symbol, quantity, price, fee, reason, time))
        self._log("fill", {"symbol": symbol, "quantity": quantity, "price": price, "fee": fee,
                           "reason": reason, "order": order["client_order_id"] if order else None}, time)
        return price

    def _exit_checks(self, symbol, instrument, candle, time, stops_only=False):
        position = self._position(symbol)
        if not position:
            return
        long = position["quantity"] > 0
        best = position["best_price"] or position["avg_price"]
        stop = position["stop_loss"]
        if position["trailing_stop_pct"]:
            distance = position["trailing_stop_pct"] / 100
            trail = best * (1 - distance) if long else best * (1 + distance)
            stop = max(stop or trail, trail) if long else min(stop or trail, trail)
        exit_price = reason = None
        if stop is not None and (candle.low <= stop if long else candle.high >= stop):
            # A gap through the stop fills at the worse open.
            exit_price = min(candle.open, stop) if long else max(candle.open, stop)
            reason = "trailing_stop" if position["trailing_stop_pct"] and stop != position["stop_loss"] else "stop_loss"
        elif not stops_only and position["take_profit"] is not None and (
                candle.high >= position["take_profit"] if long else candle.low <= position["take_profit"]):
            target = position["take_profit"]
            exit_price = max(candle.open, target) if long else min(candle.open, target)
            reason = "take_profit"
        if exit_price is not None:
            self._fill(symbol, instrument, -position["quantity"], exit_price, reason, time)
            return
        if stops_only:
            return
        best = max(best, candle.high) if long else min(best, candle.low)
        self._db.execute("UPDATE positions SET best_price = ? WHERE symbol = ?", (best, symbol))

    def _fill_orders(self, symbol, instrument, candle, time):
        limits = self.limits()
        for order in self.orders():
            if order["symbol"] != symbol or order["status"] not in ("PENDING", "PARTIAL"):
                continue
            if self.account()["kill_switch"] and not order["reduce_only"]:
                self._set_order(order["client_order_id"], OrderStatus.CANCELLED, time,
                                "Kill switch active")
                continue
            remaining = order["quantity"] - order["filled_quantity"]
            buy = order["side"] == "BUY"
            if order["reduce_only"]:
                # Never let a reduce-only order open or flip a position.
                position = self._position(symbol)
                held = position["quantity"] if position else 0.0
                if held == 0 or (held > 0) == buy:
                    self._set_order(order["client_order_id"], OrderStatus.CANCELLED, time,
                                    "Nothing left to reduce")
                    continue
                remaining = min(remaining, abs(held))
            else:
                # Conditions may have changed since submission: check again.
                reason = self._pre_trade_check(_request_from(order, remaining), candle.open_time)
                if reason:
                    self._set_order(order["client_order_id"], OrderStatus.REJECTED, time,
                                    "At fill: " + reason)
                    continue
            if order["order_type"] == "LIMIT":
                limit = order["limit_price"]
                touched = candle.low <= limit if buy else candle.high >= limit
                if not touched:
                    self._age_order(order, limits, time)
                    continue
                raw = min(candle.open, limit) if buy else max(candle.open, limit)
            else:
                raw = candle.open
            quantity = remaining
            if instrument.max_participation is not None:
                quantity = min(remaining, candle.volume * instrument.max_participation)
            if quantity <= 0:
                self._age_order(order, limits, time, "No liquidity")
                continue
            price = self._fill(symbol, instrument, quantity if buy else -quantity, raw,
                               "order", time, order)
            filled = order["filled_quantity"] + quantity
            average = ((order["average_price"] or 0) * order["filled_quantity"] + price * quantity) / filled
            status = OrderStatus.FILLED if filled >= order["quantity"] - 1e-12 else OrderStatus.PARTIAL
            self._db.execute(
                "UPDATE orders SET filled_quantity = ?, average_price = ?, status = ?, updated_at = ?"
                " WHERE client_order_id = ?",
                (filled, average, status.value, time, order["client_order_id"]))
            if status == OrderStatus.PARTIAL:
                self._age_order(self.order(order["client_order_id"]), limits, time,
                                "Partially filled: limited by liquidity")

    def _age_order(self, order, limits, time, reason=None):
        waited = order["bars_waited"] + 1
        if waited >= limits.order_expiry_bars:
            self._set_order(order["client_order_id"], OrderStatus.EXPIRED, time,
                            reason or "Not filled in time")
        else:
            self._db.execute("UPDATE orders SET bars_waited = ?, reason = ? WHERE client_order_id = ?",
                             (waited, reason or order["reason"], order["client_order_id"]))

    def _set_order(self, client_order_id, status, time, reason):
        self._db.execute(
            "UPDATE orders SET status = ?, reason = ?, updated_at = ? WHERE client_order_id = ?",
            (status.value, reason, time, client_order_id))
        self._log("order_" + status.value.lower(), {"client_order_id": client_order_id,
                                                    "reason": reason}, time)

    def _after_mark(self, time):
        account = self.account()
        limits = self.limits()
        equity = self.equity()
        peak = max(account["peak_equity"], equity)
        self._db.execute("UPDATE account SET peak_equity = ?", (peak,))
        if account["kill_switch"]:
            return
        gross = self.gross_exposure()
        if equity <= gross * limits.maintenance_margin_pct / 100:
            self._liquidate("Margin below maintenance: liquidation", time)
            return
        required = self.margin_required()
        if required and equity < required * limits.margin_closeout_pct / 100:
            self._liquidate(f"Broker margin close-out: equity {equity:.2f} below "
                            f"{limits.margin_closeout_pct}% of required margin {required:.2f}",
                            time)
            return
        day_start = account["day_start_equity"]
        daily_loss = 100 * max(0.0, day_start - equity) / day_start if day_start > 0 else 0.0
        drawdown = 100 * (peak - equity) / peak if peak > 0 else 0.0
        if daily_loss >= limits.max_daily_loss_pct:
            self._liquidate(f"Daily loss {daily_loss:.2f}% reached the limit", time)
        elif drawdown >= limits.max_drawdown_pct:
            self._liquidate(f"Drawdown {drawdown:.2f}% reached the limit", time)

    def _liquidate(self, reason, time):
        """Close everything: now where today's price is known, else at the next open.

        Markets are fed one by one, so when one bar trips the switch another
        market's bar for the same moment may not be processed yet. Selling
        that market at its old mark would ignore a gap it is about to show;
        a reduce-only order fills it at its own next open instead.
        """
        for position in self.positions():
            symbol = position["symbol"]
            if self.mark(symbol)["time"] >= time:
                self._fill(symbol, self.instrument(symbol), -position["quantity"],
                           self._price(symbol), "kill_switch", time)
                continue
            order_id = f"kill-switch:{time}:{symbol}"
            side = "SELL" if position["quantity"] > 0 else "BUY"
            self._db.execute(
                "INSERT OR IGNORE INTO orders (client_order_id, symbol, side, order_type,"
                " quantity, reduce_only, source, status, reason, created_at, updated_at)"
                " VALUES (?, ?, ?, 'MARKET', ?, 1, 'kill_switch', 'PENDING', ?, ?, ?)",
                (order_id, symbol, side, abs(position["quantity"]),
                 "Kill switch: close at the next open", time, time))
            self._log("order_pending", {"client_order_id": order_id, "symbol": symbol,
                                        "reason": "kill switch close at next open"}, time)
        self._trip(reason, time)

    def _trip(self, reason, time):
        self._db.execute("UPDATE account SET kill_switch = 1, kill_reason = ?, kill_at = ?",
                         (reason, time))
        for order in self.orders():
            if order["status"] in ("PENDING", "PARTIAL") and not order["reduce_only"]:
                self._db.execute("UPDATE orders SET status = 'CANCELLED', reason = ?"
                                 " WHERE client_order_id = ?", ("Kill switch", order["client_order_id"]))
        self._log("kill_switch", {"reason": reason}, time)


def _pair_currencies(pair: str) -> tuple[str, str]:
    return pair[:3], pair[3:]


def _request_from(order: dict, quantity: float) -> OrderRequest:
    return OrderRequest(
        client_order_id=order["client_order_id"], symbol=order["symbol"],
        side=order["side"], quantity=quantity, order_type=order["order_type"],
        limit_price=order["limit_price"], stop_loss=order["stop_loss"],
        take_profit=order["take_profit"], trailing_stop_pct=order["trailing_stop_pct"],
        reduce_only=bool(order["reduce_only"]), source=order["source"] or "")


def _limits_json(limits: EngineLimits) -> str:
    data = asdict(limits)
    data["max_data_age"] = limits.max_data_age.total_seconds()
    return json.dumps(data)
