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
from typing import Any, Iterable

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
        equity = pd.Series(dtype=float)
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
            raise RuntimeError("Install kiteconnect before using --live mode.")
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


class AutoTrader:
    def __init__(self, model: IndianEquityMomentumModel, broker: PaperBroker | KiteBroker, max_orders: int = 5):
        self.model = model
        self.broker = broker
        self.max_orders = max_orders

    def run_once(self, market_data: dict[str, pd.DataFrame]) -> list[Order]:
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
