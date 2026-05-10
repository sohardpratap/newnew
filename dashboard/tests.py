from django.test import SimpleTestCase

import pandas as pd

from dashboard.quant_engine import IndianEquityMomentumModel, PaperBroker, RiskConfig, StrategyConfig


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
