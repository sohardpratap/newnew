# Indian Quant Autopilot

A Django dashboard and CLI for researching and automating a conservative Indian cash-equity quant strategy.

> **Important:** No software can guarantee profits. This project is an execution-ready scaffold with paper trading by default, explicit live-trading opt-in, and risk controls. Use it only after your own validation and after confirming broker, exchange, tax, and SEBI compliance.

## What changed from a toy model

- Multi-stock Indian NSE universe support via Yahoo symbols such as `RELIANCE.NS`.
- Volatility-adjusted momentum ranking instead of a single-ticker moving-average demo.
- Realistic backtest metrics: total return, CAGR, Sharpe ratio, max drawdown, trading days, and an equity curve.
- Cost modeling for brokerage and slippage.
- Position sizing with max positions, max position percentage, risk-per-trade, and stop-distance sizing.
- Automation hooks:
  - `PaperBroker` writes simulated orders to `paper_orders.csv`.
  - `KiteBroker` can submit Zerodha Kite CNC market orders only when `--live` is explicitly used and credentials are supplied.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Dashboard

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/` and enter comma-separated NSE symbols, for example:

```text
RELIANCE.NS,TCS.NS,HDFCBANK.NS,INFY.NS,ICICIBANK.NS
```

## CLI research mode

```bash
python quant_model.py --universe nifty-core --start 2020-01-01
```

## Paper-trading automation

```bash
python quant_model.py --universe nifty-core --paper
```

This produces a `paper_orders.csv` ledger and does not place real orders.

## Live trading

Live trading is deliberately gated behind an explicit flag and environment variables:

```bash
export KITE_API_KEY="..."
export KITE_ACCESS_TOKEN="..."
python quant_model.py --universe RELIANCE.NS,TCS.NS --live
```

Before using live trading, install the broker SDK, confirm that your broker account permits API/algo orders, verify order tags/registration requirements, and test the exact flow in paper mode.

## Tests

```bash
python manage.py test
```
