# Simple Quant Fund Model

This repository contains a basic quantitative trading model implemented in Python.

## Overview

The `quant_model.py` script demonstrates a simple trend-following strategy using a **Moving Average Crossover**.
It uses `yfinance` to download historical stock data and `pandas` to calculate moving averages and simulate a backtest.

### Strategy Rules
1. **Short-Term Moving Average (SMA 50)**: A 50-day moving average.
2. **Long-Term Moving Average (SMA 200)**: A 200-day moving average.
3. **Signal**:
   - Buy (or go long) when the 50-day SMA is greater than the 200-day SMA.
   - Sell (or go flat) when the 50-day SMA is less than the 200-day SMA.

The strategy computes cumulative returns and compares them against a simple Buy & Hold approach on the given asset (default is `SPY`, the S&P 500 ETF).

## Prerequisites

Make sure you have Python installed. Install dependencies using:

```bash
pip install -r requirements.txt
```

## Running the Model

Simply execute the script:

```bash
python quant_model.py
```

It will output the backtest summary, showing the performance of the strategy compared to the market baseline.
