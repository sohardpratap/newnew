from __future__ import annotations

from dashboard.quant_engine import (
    GROWW_RATE_LIMITS,
    INDIAN_DEFAULT_UNIVERSE,
    IndianEquityMomentumModel,
    ProfitProtectionConfig,
    RiskConfig,
    StrategyConfig,
    YahooIndianDataProvider,
)


def run_backtest(
    ticker: str = "RELIANCE.NS",
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    short_window: int = 20,
    long_window: int = 100,
):
    universe = [item.strip().upper() for item in ticker.split(",") if item.strip()]
    if not universe:
        universe = list(INDIAN_DEFAULT_UNIVERSE)

    provider = YahooIndianDataProvider()
    market_data = provider.download(universe, start=start_date, end=end_date)
    if not market_data:
        return {"error": "No data retrieved. Use Yahoo NSE symbols like RELIANCE.NS or a comma-separated NSE universe."}

    model = IndianEquityMomentumModel(
        StrategyConfig(short_window=short_window, long_window=long_window),
        RiskConfig(),
    )
    protection = model.profit_protection_report(market_data, ProfitProtectionConfig())
    backtest = protection["backtest"]
    if "error" in backtest:
        return backtest

    signals = model.rank_signals(market_data)
    return {
        "ticker": ", ".join(universe),
        "universe_size": len(universe),
        "start_date": start_date,
        "end_date": end_date or "latest available",
        "strategy": f"{short_window}/{long_window} volatility-adjusted trend model",
        "backtest": backtest,
        "profit_gate": protection,
        "signals": [signal.__dict__ for signal in signals],
        "groww": {
            "rate_limits": GROWW_RATE_LIMITS,
            "auth_options": [
                "GROWW_ACCESS_TOKEN for an already generated access token",
                "GROWW_API_KEY + GROWW_API_SECRET for Groww's daily approval API key/secret flow",
                "GROWW_TOTP_TOKEN + GROWW_TOTP_SECRET for Groww's TOTP flow via pyotp",
            ],
            "live_command": "python quant_model.py --universe RELIANCE.NS,TCS.NS --live --broker groww",
        },
        "disclaimer": "Research and automation scaffold only; profits are not guaranteed. Groww/Zerodha live trading requires explicit CLI opt-in, credentials, and broker/SEBI compliance.",
    }
