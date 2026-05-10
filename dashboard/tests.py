from django.test import SimpleTestCase

import pandas as pd
from unittest.mock import patch

from dashboard.quant_engine import (
    AutoTrader,
    GrowwBroker,
    IndianEquityMomentumModel,
    PaperBroker,
    ProfitProtectionConfig,
    RiskConfig,
    Signal,
    StrategyConfig,
)


def synthetic_prices(days=260):
    index = pd.date_range("2024-01-01", periods=days, freq="B")
    close = pd.Series(range(100, 100 + days), index=index, dtype=float)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": 100000,
        }
    )


class FakeGrowwAPI:
    VALIDITY_DAY = "DAY"
    EXCHANGE_NSE = "NSE"
    SEGMENT_CASH = "CASH"
    PRODUCT_CNC = "CNC"
    ORDER_TYPE_MARKET = "MARKET"
    TRANSACTION_TYPE_BUY = "BUY"
    TRANSACTION_TYPE_SELL = "SELL"

    @staticmethod
    def get_access_token(api_key, secret):
        return f"token-{api_key}-{secret}"

    def __init__(self, access_token):
        self.access_token = access_token
        self.orders = []

    def place_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"groww_order_id": "GROWW123", "order_status": "OPEN"}


class FakeGrowwModule:
    GrowwAPI = FakeGrowwAPI


class QuantEngineTests(SimpleTestCase):
    def test_backtest_returns_metrics_for_valid_history(self):
        model = IndianEquityMomentumModel(StrategyConfig(short_window=5, long_window=20, min_history=30))
        result = model.backtest({"RELIANCE.NS": synthetic_prices()})

        self.assertNotIn("error", result)
        self.assertGreater(result["ending_equity"], 0)
        self.assertIn("max_drawdown_pct", result)
        self.assertIn("sharpe", result)

    def test_latest_signal_sizes_position_with_risk_limits(self):
        model = IndianEquityMomentumModel(
            StrategyConfig(short_window=5, long_window=20),
            RiskConfig(initial_capital=100000, risk_per_trade=0.01, max_position_pct=0.2),
        )
        signal = model.latest_signal("RELIANCE.NS", synthetic_prices(), capital=100000)

        self.assertIn(signal.action, {"BUY", "HOLD", "WAIT", "SELL"})
        self.assertGreaterEqual(signal.quantity, 0)
        self.assertLessEqual(signal.quantity * signal.close, 20000)

    def test_paper_broker_writes_order(self):
        path = self.enterContext(__import__("tempfile").TemporaryDirectory())
        ledger = f"{path}/orders.csv"
        model = IndianEquityMomentumModel(StrategyConfig(short_window=5, long_window=20))
        signal = model.latest_signal("RELIANCE.NS", synthetic_prices())
        order = PaperBroker(ledger).place_order(signal)

        self.assertEqual(order.status, "filled")
        self.assertTrue(pd.read_csv(ledger).shape[0] == 1)

    def test_profit_protection_blocks_weak_backtest(self):
        model = IndianEquityMomentumModel(StrategyConfig(short_window=5, long_window=20, min_history=30))
        falling = synthetic_prices()
        falling["Close"] = falling["Close"].iloc[::-1].to_numpy()
        falling["Open"] = falling["Close"]
        falling["High"] = falling["Close"] * 1.01
        falling["Low"] = falling["Close"] * 0.99

        report = model.profit_protection_report(
            {"RELIANCE.NS": falling},
            ProfitProtectionConfig(min_total_return_pct=1, min_sharpe=1),
        )

        self.assertFalse(report["approved"])
        self.assertTrue(report["reasons"])

    def test_auto_trader_raises_when_profit_gate_fails(self):
        model = IndianEquityMomentumModel(StrategyConfig(short_window=5, long_window=20, min_history=30))
        trader = AutoTrader(
            model,
            PaperBroker("/tmp/not-used.csv"),
            require_profit_gate=True,
            profit_gate=ProfitProtectionConfig(min_total_return_pct=999),
        )

        with self.assertRaisesMessage(RuntimeError, "Live trading blocked"):
            trader.run_once({"RELIANCE.NS": synthetic_prices()})

    def test_groww_broker_places_cash_cnc_market_order(self):
        with patch("dashboard.quant_engine.find_spec", return_value=True), patch(
            "dashboard.quant_engine.import_module", return_value=FakeGrowwModule
        ):
            broker = GrowwBroker(api_key="key", api_secret="secret")
            order = broker.place_order(
                Signal("RELIANCE.NS", "BUY", close=2500, score=1, short_ma=1, long_ma=1, volatility=0.1, quantity=2)
            )

        self.assertEqual(order.broker_order_id, "GROWW123")
        self.assertEqual(order.mode, "live-groww")
        self.assertEqual(broker.groww.access_token, "token-key-secret")
        self.assertEqual(broker.groww.orders[0]["trading_symbol"], "RELIANCE")
        self.assertEqual(broker.groww.orders[0]["product"], "CNC")
