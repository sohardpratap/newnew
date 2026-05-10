from __future__ import annotations

import argparse
import os

from dashboard.quant_engine import (
    INDIAN_DEFAULT_UNIVERSE,
    AutoTrader,
    IndianEquityMomentumModel,
    KiteBroker,
    PaperBroker,
    RiskConfig,
    StrategyConfig,
    YahooIndianDataProvider,
)


def parse_universe(value: str) -> list[str]:
    if value.lower() == "nifty-core":
        return list(INDIAN_DEFAULT_UNIVERSE)
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Indian-market quant model with paper/live execution controls.")
    parser.add_argument("--universe", default="nifty-core", help="Comma-separated Yahoo NSE symbols or 'nifty-core'.")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--short-window", type=int, default=20)
    parser.add_argument("--long-window", type=int, default=100)
    parser.add_argument("--capital", type=float, default=1_000_000)
    parser.add_argument("--paper", action="store_true", help="Write simulated orders to paper_orders.csv.")
    parser.add_argument("--live", action="store_true", help="Send real CNC market orders through Zerodha Kite.")
    args = parser.parse_args()

    tickers = parse_universe(args.universe)
    provider = YahooIndianDataProvider()
    market_data = provider.download(tickers, start=args.start)
    model = IndianEquityMomentumModel(
        StrategyConfig(short_window=args.short_window, long_window=args.long_window),
        RiskConfig(initial_capital=args.capital),
    )

    print("Backtest")
    print(model.backtest(market_data))
    print("\nLatest ranked signals")
    for signal in model.rank_signals(market_data, capital=args.capital):
        print(signal)

    if args.paper or args.live:
        if args.live:
            broker = KiteBroker(os.environ["KITE_API_KEY"], os.environ["KITE_ACCESS_TOKEN"])
        else:
            broker = PaperBroker()
        orders = AutoTrader(model, broker).run_once(market_data)
        print("\nOrders")
        for order in orders:
            print(order)


if __name__ == "__main__":
    main()
