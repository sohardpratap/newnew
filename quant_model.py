import yfinance as yf
import pandas as pd
import numpy as np

def run_backtest(ticker="SPY", start_date="2020-01-01", end_date=None, short_window=50, long_window=200):
    print(f"Downloading data for {ticker}...")
    data = yf.download(ticker, start=start_date, end=end_date)

    if data.empty:
        print("No data retrieved.")
        return None

    print(f"Calculating {short_window}-day and {long_window}-day moving averages...")

    # Check if 'Close' is multi-index (often the case with newer yfinance versions)
    if isinstance(data.columns, pd.MultiIndex):
        # Flatten columns or get specifically the ticker's close
        close_prices = data[('Close', ticker)]
    else:
        close_prices = data['Close']

    df = pd.DataFrame(index=data.index)
    df['Close'] = close_prices
    df['Short_MA'] = df['Close'].rolling(window=short_window, min_periods=1).mean()
    df['Long_MA'] = df['Close'].rolling(window=long_window, min_periods=1).mean()

    # Strategy: Buy when Short_MA > Long_MA (Signal = 1)
    # Sell / Go flat when Short_MA < Long_MA (Signal = 0)
    df['Signal'] = 0
    df.loc[df['Short_MA'] > df['Long_MA'], 'Signal'] = 1

    # Daily returns
    df['Returns'] = df['Close'].pct_change()

    # Strategy returns (shifted by 1 to avoid lookahead bias: signal generated today affects tomorrow's return)
    df['Strategy_Returns'] = df['Returns'] * df['Signal'].shift(1)

    # Cumulative returns
    df['Cumulative_Market'] = (1 + df['Returns'].fillna(0)).cumprod()
    df['Cumulative_Strategy'] = (1 + df['Strategy_Returns'].fillna(0)).cumprod()

    # Summary
    total_market_return = (df['Cumulative_Market'].iloc[-1] - 1) * 100
    total_strategy_return = (df['Cumulative_Strategy'].iloc[-1] - 1) * 100

    print("\n--- Backtest Summary ---")
    print(f"Ticker: {ticker}")
    print(f"Period: {df.index[0].date()} to {df.index[-1].date()}")
    print(f"Buy & Hold Return: {total_market_return:.2f}%")
    print(f"Strategy Return:   {total_strategy_return:.2f}%")

    if total_strategy_return > total_market_return:
        print("Result: Strategy outperformed the market.")
    else:
        print("Result: Strategy underperformed the market.")

    return df

if __name__ == "__main__":
    run_backtest(ticker="SPY", start_date="2020-01-01")
