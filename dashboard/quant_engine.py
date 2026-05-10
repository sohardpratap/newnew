"""Production-oriented quant engine for Indian equities.

The module is intentionally conservative: it can run fully automated in paper mode
and only sends real orders when an operator explicitly chooses ``--live`` and
provides broker credentials. No strategy can guarantee profits; this engine focuses
on repeatable research, realistic costs, risk limits, and auditable orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from time import sleep
from typing import Any, Iterable, Protocol
from uuid import uuid4

import numpy as np
import pandas as pd
import yfinance as yf


INDIAN_DEFAULT_UNIVERSE = (
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "LT.NS",
    "SBIN.NS",
    "AXISBANK.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
)


GROWW_RATE_LIMITS = {
    "orders": {"per_second": 10, "per_minute": 250, "apis": "Create, modify, and cancel orders"},
    "live_data": {"per_second": 10, "per_minute": 300, "apis": "Market quote, LTP, and OHLC"},
    "non_trading": {"per_second": 20, "per_minute": 500, "apis": "Order status/list, trades, positions, holdings, margin"},
    "live_feed": {"subscriptions": 1000, "apis": "WebSocket market/order feeds"},
}


@dataclass(frozen=True)
class RiskConfig:
    initial_capital: float = 1_000_000.0
    max_positions: int = 5
    risk_per_trade: float = 0.01
    max_position_pct: float = 0.20
    stop_loss_pct: float = 0.07
    take_profit_pct: float = 0.16
    max_daily_loss_pct: float = 0.02
    brokerage_bps: float = 3.0
    slippage_bps: float = 5.0

    @property
    def round_trip_cost(self) -> float:
        return 2 * (self.brokerage_bps + self.slippage_bps) / 10_000


@dataclass(frozen=True)
class StrategyConfig:
    short_window: int = 20
    long_window: int = 100
    volatility_window: int = 20
    min_history: int = 120


@dataclass(frozen=True)
class ProfitProtectionConfig:
    """Pre-trade gates that block live orders when recent research is weak.

    These checks cannot guarantee profit. They are deliberately conservative
    circuit breakers that require a strategy to show positive historical edge,
    acceptable drawdown, and enough observations before live execution.
    """

    min_total_return_pct: float = 0.0
    min_sharpe: float = 0.50
    max_drawdown_pct: float = 25.0
    min_trading_days: int = 120


@dataclass(frozen=True)
class Signal:
    ticker: str
    action: str
    close: float
    score: float
    short_ma: float
    long_ma: float
    volatility: float
    quantity: int = 0
    reason: str = ""


@dataclass
class Order:
    ticker: str
    side: str
    quantity: int
    price: float
    mode: str
    status: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    broker_order_id: str | None = None


class Broker(Protocol):
    def place_order(self, signal: Signal) -> Order:
        """Submit or record an order for a signal."""


class YahooIndianDataProvider:
    """Downloads daily NSE/BSE prices from Yahoo Finance symbols such as RELIANCE.NS."""

    def download(self, tickers: Iterable[str], start: str, end: str | None = None) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        for ticker in tickers:
            raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            frame = raw[["Open", "High", "Low", "Close", "Volume"]].dropna().copy()
            frame.index = pd.to_datetime(frame.index)
            frames[ticker] = frame
        return frames


class IndianEquityMomentumModel:
    """Volatility-adjusted trend model with long-only Indian cash-equity signals."""

    def __init__(self, strategy: StrategyConfig | None = None, risk: RiskConfig | None = None):
        self.strategy = strategy or StrategyConfig()
        self.risk = risk or RiskConfig()

    def enrich(self, prices: pd.DataFrame) -> pd.DataFrame:
        df = prices.copy()
        df["returns"] = df["Close"].pct_change()
        df["short_ma"] = df["Close"].rolling(self.strategy.short_window).mean()
        df["long_ma"] = df["Close"].rolling(self.strategy.long_window).mean()
        df["volatility"] = df["returns"].rolling(self.strategy.volatility_window).std() * np.sqrt(252)
        df["trend_strength"] = (df["short_ma"] / df["long_ma"]) - 1
        df["raw_signal"] = (df["short_ma"] > df["long_ma"]).astype(int)
        return df

    def latest_signal(self, ticker: str, prices: pd.DataFrame, capital: float | None = None) -> Signal:
        df = self.enrich(prices).dropna()
        if len(df) < 2:
            return Signal(ticker, "WAIT", 0.0, 0.0, 0.0, 0.0, 0.0, reason="Not enough clean history")

        last = df.iloc[-1]
        prev = df.iloc[-2]
        action = "HOLD"
        reason = "Trend is still active"
        if last.raw_signal == 1 and prev.raw_signal == 0:
            action, reason = "BUY", "Bullish moving-average crossover"
        elif last.raw_signal == 0 and prev.raw_signal == 1:
            action, reason = "SELL", "Bearish moving-average crossover"
        elif last.raw_signal == 0:
            action, reason = "WAIT", "No confirmed uptrend"

        budget = (capital or self.risk.initial_capital) * self.risk.max_position_pct
        risk_budget = (capital or self.risk.initial_capital) * self.risk.risk_per_trade
        stop_distance = float(last.Close) * self.risk.stop_loss_pct
        quantity = int(max(0, min(budget / float(last.Close), risk_budget / stop_distance)))
        return Signal(
            ticker=ticker,
            action=action,
            close=float(last.Close),
            score=float(last.trend_strength / max(last.volatility, 1e-9)),
            short_ma=float(last.short_ma),
            long_ma=float(last.long_ma),
            volatility=float(last.volatility),
            quantity=quantity,
            reason=reason,
        )

    def rank_signals(self, market_data: dict[str, pd.DataFrame], capital: float | None = None) -> list[Signal]:
        signals = [self.latest_signal(ticker, prices, capital) for ticker, prices in market_data.items()]
        eligible = [signal for signal in signals if signal.action in {"BUY", "HOLD"} and signal.quantity > 0]
        eligible.sort(key=lambda signal: signal.score, reverse=True)
        return eligible[: self.risk.max_positions]

    def backtest(self, market_data: dict[str, pd.DataFrame]) -> dict[str, Any]:
        returns_by_ticker: dict[str, pd.Series] = {}
        positions_by_ticker: dict[str, pd.Series] = {}

        for ticker, prices in market_data.items():
            df = self.enrich(prices).dropna().copy()
            if len(df) < self.strategy.min_history:
                continue
            df["strategy_returns"] = df["returns"] * df["raw_signal"].shift(1).fillna(0)
            trades = df["raw_signal"].diff().abs().fillna(0)
            df["strategy_returns"] -= trades * self.risk.round_trip_cost / 2
            returns_by_ticker[ticker] = df["strategy_returns"]
            positions_by_ticker[ticker] = df["raw_signal"]

        if not returns_by_ticker:
            return {"error": "No ticker had enough history for a realistic backtest."}

        returns = pd.DataFrame(returns_by_ticker).fillna(0)
        active = pd.DataFrame(positions_by_ticker).reindex(returns.index).fillna(0)
        active_count = active.sum(axis=1).clip(lower=1)
        portfolio_returns = (returns * active.div(active_count, axis=0)).sum(axis=1)
        equity = self.risk.initial_capital * (1 + portfolio_returns).cumprod()
        drawdown = equity / equity.cummax() - 1
        years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1 / 365.25)
        total_return = equity.iloc[-1] / self.risk.initial_capital - 1
        cagr = (equity.iloc[-1] / self.risk.initial_capital) ** (1 / years) - 1
        sharpe = np.sqrt(252) * portfolio_returns.mean() / portfolio_returns.std() if portfolio_returns.std() else 0.0

        return {
            "initial_capital": self.risk.initial_capital,
            "ending_equity": float(equity.iloc[-1]),
            "total_return_pct": float(total_return * 100),
            "cagr_pct": float(cagr * 100),
            "max_drawdown_pct": float(drawdown.min() * 100),
            "sharpe": float(sharpe),
            "trading_days": int(len(equity)),
            "last_equity": [
                {"date": idx.strftime("%Y-%m-%d"), "equity": round(float(value), 2)}
                for idx, value in equity.tail(10).items()
            ],
        }

    def profit_protection_report(
        self,
        market_data: dict[str, pd.DataFrame],
        config: ProfitProtectionConfig | None = None,
    ) -> dict[str, Any]:
        config = config or ProfitProtectionConfig()
        backtest = self.backtest(market_data)
        if "error" in backtest:
            return {"approved": False, "reasons": [backtest["error"]], "backtest": backtest}

        reasons: list[str] = []
        if backtest["total_return_pct"] < config.min_total_return_pct:
            reasons.append(f"Total return {backtest['total_return_pct']:.2f}% is below {config.min_total_return_pct:.2f}%.")
        if backtest["sharpe"] < config.min_sharpe:
            reasons.append(f"Sharpe {backtest['sharpe']:.2f} is below {config.min_sharpe:.2f}.")
        if abs(backtest["max_drawdown_pct"]) > config.max_drawdown_pct:
            reasons.append(f"Max drawdown {backtest['max_drawdown_pct']:.2f}% exceeds {config.max_drawdown_pct:.2f}%.")
        if backtest["trading_days"] < config.min_trading_days:
            reasons.append(f"Only {backtest['trading_days']} trading days; need at least {config.min_trading_days}.")

        return {
            "approved": not reasons,
            "reasons": reasons or ["Backtest passed configured live-trading gates."],
            "backtest": backtest,
            "config": config.__dict__,
        }


class PaperBroker:
    def __init__(self, ledger_path: str | Path = "paper_orders.csv"):
        self.ledger_path = Path(ledger_path)

    def place_order(self, signal: Signal) -> Order:
        order = Order(signal.ticker, "BUY" if signal.action in {"BUY", "HOLD"} else "SELL", signal.quantity, signal.close, "paper", "filled")
        frame = pd.DataFrame([order.__dict__])
        frame.to_csv(self.ledger_path, mode="a", header=not self.ledger_path.exists(), index=False)
        return order


class KiteBroker:
    """Minimal Zerodha Kite adapter. Requires KITE_API_KEY and KITE_ACCESS_TOKEN."""

    def __init__(self, api_key: str, access_token: str):
        if find_spec("kiteconnect") is None:
            raise RuntimeError("Install kiteconnect before using --live mode with Zerodha Kite.")
        kite_module = import_module("kiteconnect")
        self.kite = kite_module.KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)

    def place_order(self, signal: Signal) -> Order:
        exchange_symbol = signal.ticker.replace(".NS", "")
        order_id = self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=self.kite.EXCHANGE_NSE,
            tradingsymbol=exchange_symbol,
            transaction_type=self.kite.TRANSACTION_TYPE_BUY if signal.action in {"BUY", "HOLD"} else self.kite.TRANSACTION_TYPE_SELL,
            quantity=signal.quantity,
            product=self.kite.PRODUCT_CNC,
            order_type=self.kite.ORDER_TYPE_MARKET,
        )
        return Order(signal.ticker, signal.action, signal.quantity, signal.close, "live", "submitted", broker_order_id=order_id)


class GrowwBroker:
    """Groww Trading API adapter for NSE/BSE cash CNC market orders.

    Supported authentication paths mirror Groww's official SDK docs:

    - ``access_token``: use a pre-generated API auth token.
    - ``api_key`` + ``api_secret``: API key/secret flow, which Groww documents as
      requiring daily approval on the Groww Cloud API Keys page.
    - ``totp_token`` + (``totp`` or ``totp_secret``): TOTP flow. Supplying
      ``totp_secret`` lets the adapter generate the current TOTP through
      ``pyotp``.
    """

    def __init__(
        self,
        access_token: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        totp_token: str | None = None,
        totp: str | None = None,
        totp_secret: str | None = None,
    ):
        if find_spec("growwapi") is None:
            raise RuntimeError("Install growwapi before using --live mode with Groww.")
        groww_module = import_module("growwapi")
        groww_api = groww_module.GrowwAPI
        token = access_token
        if token is None:
            token = self._build_access_token(groww_api, api_key, api_secret, totp_token, totp, totp_secret)
        self.groww = groww_api(token)

    def _build_access_token(
        self,
        groww_api: Any,
        api_key: str | None,
        api_secret: str | None,
        totp_token: str | None,
        totp: str | None,
        totp_secret: str | None,
    ) -> str:
        if api_key and api_secret:
            return groww_api.get_access_token(api_key=api_key, secret=api_secret)
        if totp_token and (totp or totp_secret):
            current_totp = totp or self._generate_totp(totp_secret)
            return groww_api.get_access_token(api_key=totp_token, totp=current_totp)
        raise RuntimeError(
            "Set GROWW_ACCESS_TOKEN, GROWW_API_KEY/GROWW_API_SECRET, or "
            "GROWW_TOTP_TOKEN with GROWW_TOTP or GROWW_TOTP_SECRET for Groww live trading."
        )

    def _generate_totp(self, totp_secret: str | None) -> str:
        if not totp_secret:
            raise RuntimeError("Set GROWW_TOTP_SECRET or GROWW_TOTP when using Groww TOTP auth.")
        if find_spec("pyotp") is None:
            raise RuntimeError("Install pyotp before using Groww TOTP auth.")
        pyotp_module = import_module("pyotp")
        return pyotp_module.TOTP(totp_secret).now()

    def place_order(self, signal: Signal) -> Order:
        trading_symbol = signal.ticker.replace(".NS", "").replace(".BO", "")
        exchange = self.groww.EXCHANGE_BSE if signal.ticker.endswith(".BO") else self.groww.EXCHANGE_NSE
        side = "BUY" if signal.action in {"BUY", "HOLD"} else "SELL"
        transaction_type = self.groww.TRANSACTION_TYPE_BUY if side == "BUY" else self.groww.TRANSACTION_TYPE_SELL
        response = self.groww.place_order(
            trading_symbol=trading_symbol,
            quantity=signal.quantity,
            validity=self.groww.VALIDITY_DAY,
            exchange=exchange,
            segment=self.groww.SEGMENT_CASH,
            product=self.groww.PRODUCT_CNC,
            order_type=self.groww.ORDER_TYPE_MARKET,
            transaction_type=transaction_type,
            order_reference_id=f"QM-{uuid4().hex[:17]}",
        )
        broker_order_id = response.get("groww_order_id") if isinstance(response, dict) else None
        status = response.get("order_status", "submitted") if isinstance(response, dict) else "submitted"
        return Order(signal.ticker, side, signal.quantity, signal.close, "live-groww", status, broker_order_id=broker_order_id)


class AutoTrader:
    def __init__(
        self,
        model: IndianEquityMomentumModel,
        broker: Broker,
        max_orders: int = 5,
        require_profit_gate: bool = False,
        profit_gate: ProfitProtectionConfig | None = None,
    ):
        self.model = model
        self.broker = broker
        self.max_orders = max_orders
        self.require_profit_gate = require_profit_gate
        self.profit_gate = profit_gate or ProfitProtectionConfig()

    def run_once(self, market_data: dict[str, pd.DataFrame]) -> list[Order]:
        if self.require_profit_gate:
            report = self.model.profit_protection_report(market_data, self.profit_gate)
            if not report["approved"]:
                reasons = "; ".join(report["reasons"])
                raise RuntimeError(f"Live trading blocked by profit-protection gate: {reasons}")

        orders: list[Order] = []
        for signal in self.model.rank_signals(market_data)[: self.max_orders]:
            if signal.action in {"BUY", "SELL"} and signal.quantity > 0:
                orders.append(self.broker.place_order(signal))
        return orders

    def run_forever(self, provider: YahooIndianDataProvider, tickers: Iterable[str], start: str, interval_seconds: int = 3600) -> None:
        while True:
            data = provider.download(tickers, start=start)
            self.run_once(data)
            sleep(interval_seconds)
