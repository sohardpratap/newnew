# Indian Quant Autopilot

A Django dashboard and CLI for researching and automating a conservative Indian cash-equity quant strategy.

> **Important:** No software can guarantee profits. This project is an execution-ready scaffold with paper trading by default, explicit live-trading opt-in, and risk controls. Use it only after your own validation and after confirming broker, exchange, tax, and SEBI compliance.

## What changed from a toy model

- Multi-stock Indian NSE universe support via Yahoo symbols such as `RELIANCE.NS`.
- Volatility-adjusted momentum ranking instead of a single-ticker moving-average demo.
- Realistic backtest metrics: total return, CAGR, Sharpe ratio, max drawdown, trading days, and an equity curve.
- Cost modeling for brokerage and slippage.
- Position sizing with max positions, max position percentage, risk-per-trade, and stop-distance sizing.
- Profit-protection gates that block live orders unless the recent backtest clears configurable return, Sharpe, drawdown, and history thresholds.
- Automation hooks:
  - `PaperBroker` writes simulated orders to `paper_orders.csv`.
  - `GrowwBroker` can submit Groww NSE cash CNC market orders when `--live --broker groww` is explicitly used and Groww credentials are supplied.
  - `KiteBroker` can submit Zerodha Kite CNC market orders when `--live --broker kite` is explicitly used and credentials are supplied.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Groww live trading requires an active Groww Trading API subscription and the official SDK credentials. Keep API keys in environment variables or a secret manager; do not commit them.

## Dashboard

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/` and enter comma-separated NSE symbols, for example:

```text
RELIANCE.NS,TCS.NS,HDFCBANK.NS,INFY.NS,ICICIBANK.NS
```

The dashboard shows the backtest, current ranked signals, and whether the live-trading profit-protection gate would pass.

## CLI research mode

```bash
python quant_model.py --universe nifty-core --start 2020-01-01
```

## Paper-trading automation

```bash
python quant_model.py --universe nifty-core --paper
```

This produces a `paper_orders.csv` ledger and does not place real orders.

## Groww live trading

Live trading is deliberately gated behind an explicit flag, Groww credentials, and the profit-protection checks. You can use an existing access token:

```bash
export GROWW_ACCESS_TOKEN="..."
python quant_model.py --universe RELIANCE.NS,TCS.NS --live --broker groww
```

Or generate an access token from an API key and secret through the Groww SDK flow:

```bash
export GROWW_API_KEY="..."
export GROWW_API_SECRET="..."
python quant_model.py --universe RELIANCE.NS,TCS.NS --live --broker groww
```

Tune the live-order gate if your validated strategy needs different thresholds:

```bash
python quant_model.py --live --broker groww --min-sharpe 0.75 --min-return 5 --max-drawdown 15
```

If the backtest fails the configured gate, the CLI raises an error instead of sending live orders. Passing the gate is not a profit guarantee; it is only a risk-control filter.

## Zerodha Kite live trading

```bash
export KITE_API_KEY="..."
export KITE_ACCESS_TOKEN="..."
python quant_model.py --universe RELIANCE.NS,TCS.NS --live --broker kite
```

Before using any live broker, install the broker SDK, confirm that your account permits API/algo orders, verify order tags/registration requirements, and test the exact flow in paper mode.

## Tests

```bash
python manage.py test
```
