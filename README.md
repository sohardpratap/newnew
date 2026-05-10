# Professional Indian Quant Fund Dashboard

This repository contains a full-stack Django application that implements a professional quantitative trading dashboard. It currently features a backtesting engine tailored for Indian equities (e.g., RELIANCE.NS, ^NSEI) using a classic trend-following strategy.

## Features
- **Web Dashboard**: Built with Django and Bootstrap for a clean, professional user interface.
- **Dynamic Backtesting**: Input any Yahoo Finance ticker (defaults to RELIANCE.NS) to instantly backtest a Moving Average Crossover strategy (50-day vs 200-day).
- **Recent Signals Table**: View the last 10 days of pricing, moving averages, and exact trading signals.

## Prerequisites

Make sure you have Python installed. Install the necessary dependencies:

```bash
pip install -r requirements.txt
```

## Running the Application

1. **Apply Migrations** (optional but recommended for standard Django setup):
   ```bash
   python manage.py migrate
   ```

2. **Run the Development Server**:
   ```bash
   python manage.py runserver
   ```

3. **View the Dashboard**:
   Open your web browser and navigate to:
   `http://127.0.0.1:8000/`

Enter any Indian ticker symbol (like `INFY.NS`, `TCS.NS`, or `^NSEI`) and click "Run Backtest" to see the strategy's historical performance compared to a standard Buy & Hold approach.
