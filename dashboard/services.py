import yfinance as yf
import pandas as pd
import numpy as np

def run_backtest(ticker="RELIANCE.NS", start_date="2020-01-01", end_date=None, short_window=50, long_window=200):
    data = yf.download(ticker, start=start_date, end=end_date)

    if data.empty:
        return {"error": "No data retrieved."}

    if isinstance(data.columns, pd.MultiIndex):
        close_prices = data[('Close', ticker)]
    else:
        close_prices = data['Close']

    df = pd.DataFrame(index=data.index)
    df['Close'] = close_prices
    df['Short_MA'] = df['Close'].rolling(window=short_window, min_periods=1).mean()
    df['Long_MA'] = df['Close'].rolling(window=long_window, min_periods=1).mean()

    df['Signal'] = 0
    df.loc[df['Short_MA'] > df['Long_MA'], 'Signal'] = 1

    df['Returns'] = df['Close'].pct_change()
    df['Strategy_Returns'] = df['Returns'] * df['Signal'].shift(1)

    df['Cumulative_Market'] = (1 + df['Returns'].fillna(0)).cumprod()
    df['Cumulative_Strategy'] = (1 + df['Strategy_Returns'].fillna(0)).cumprod()

    total_market_return = (df['Cumulative_Market'].iloc[-1] - 1) * 100
    total_strategy_return = (df['Cumulative_Strategy'].iloc[-1] - 1) * 100

    performance = "Outperformed" if total_strategy_return > total_market_return else "Underperformed"

    # Get last 10 records for display
    tail_records = []
    for date, row in df.tail(10).iterrows():
        tail_records.append({
            "date": date.strftime("%Y-%m-%d"),
            "close": round(row['Close'], 2) if not pd.isna(row['Close']) else None,
            "short_ma": round(row['Short_MA'], 2) if not pd.isna(row['Short_MA']) else None,
            "long_ma": round(row['Long_MA'], 2) if not pd.isna(row['Long_MA']) else None,
            "signal": "Buy" if row['Signal'] == 1 else "Hold/Sell"
        })

    return {
        "ticker": ticker,
        "start_date": df.index[0].date().strftime("%Y-%m-%d"),
        "end_date": df.index[-1].date().strftime("%Y-%m-%d"),
        "market_return": round(total_market_return, 2),
        "strategy_return": round(total_strategy_return, 2),
        "performance": performance,
        "tail_records": tail_records
    }
