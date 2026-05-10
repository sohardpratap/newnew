from __future__ import annotations

import argparse
import os

from dashboard.quant_engine import (
    INDIAN_DEFAULT_UNIVERSE,
    AutoTrader,
    GrowwBroker,
    IndianEquityMomentumModel,
    KiteBroker,
    PaperBroker,
    ProfitProtectionConfig,
    RiskConfig,
    StrategyConfig,
    YahooIndianDataProvider,
)


def parse_universe(value: str) -> list[str]:
    if value.lower() == "nifty-core":
        return list(INDIAN_DEFAULT_UNIVERSE)
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def build_live_broker(name: str):
    if name == "groww":
        return GrowwBroker(
            access_token=os.environ.get("GROWW_ACCESS_TOKEN"),
            api_key=os.environ.get("GROWW_API_KEY"),
            api_secret=os.environ.get("GROWW_API_SECRET"),
            totp_token=os.environ.get("GROWW_TOTP_TOKEN"),
            totp=os.environ.get("GROWW_TOTP"),
            totp_secret=os.environ.get("GROWW_TOTP_SECRET"),
        )
    if name == "kite":
        return KiteBroker(os.environ["KITE_API_KEY"], os.environ["KITE_ACCESS_TOKEN"])
    raise ValueError(f"Unsupported broker: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Indian-market quant model with paper/live execution controls.")
    parser.add_argument("--universe", default="nifty-core", help="Comma-separated Yahoo NSE symbols or 'nifty-core'.")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--short-window", type=int, default=20)
    parser.add_argument("--long-window", type=int, default=100)
    parser.add_argument("--capital", type=float, default=1_000_000)
    parser.add_argument("--paper", action="store_true", help="Write simulated orders to paper_orders.csv.")
    parser.add_argument("--live", action="store_true", help="Send real CNC market orders after profit-protection checks pass.")
    parser.add_argument("--broker", choices=("groww", "kite"), default="groww", help="Live broker adapter to use with --live.")
    parser.add_argument("--min-sharpe", type=float, default=0.50, help="Minimum backtest Sharpe required before live orders.")
    parser.add_argument("--min-return", type=float, default=0.0, help="Minimum total return percent required before live orders.")
    parser.add_argument("--max-drawdown", type=float, default=25.0, help="Maximum absolute drawdown percent allowed before live orders.")
    args = parser.parse_args()

    if args.paper and args.live:
        raise SystemExit("Choose either --paper or --live, not both.")

    tickers = parse_universe(args.universe)
    provider = YahooIndianDataProvider()
    market_data = provider.download(tickers, start=args.start)
    model = IndianEquityMomentumModel(
        StrategyConfig(short_window=args.short_window, long_window=args.long_window),
        RiskConfig(initial_capital=args.capital),
    )
    profit_gate = ProfitProtectionConfig(
        min_total_return_pct=args.min_return,
        min_sharpe=args.min_sharpe,
        max_drawdown_pct=args.max_drawdown,
    )
    protection = model.profit_protection_report(market_data, profit_gate)

    print("Backtest")
    print(protection["backtest"])
    print("\nProfit-protection gate")
    print({"approved": protection["approved"], "reasons": protection["reasons"], "config": protection.get("config")})
    print("\nLatest ranked signals")
    for signal in model.rank_signals(market_data, capital=args.capital):
        print(signal)

    if args.paper or args.live:
        if args.live:
            broker = build_live_broker(args.broker)
            trader = AutoTrader(model, broker, require_profit_gate=True, profit_gate=profit_gate)
        else:
            broker = PaperBroker()
            trader = AutoTrader(model, broker)
        orders = trader.run_once(market_data)
        print("\nOrders")
        for order in orders:
            print(order)


if __name__ == "__main__":
    main()
