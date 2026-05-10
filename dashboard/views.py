from django.shortcuts import render

from .services import run_backtest


def _int_param(request, name: str, default: int) -> int:
    try:
        return int(request.GET.get(name, default))
    except (TypeError, ValueError):
        return default


def index(request):
    ticker = request.GET.get("ticker", "RELIANCE.NS,TCS.NS,HDFCBANK.NS,INFY.NS,ICICIBANK.NS")
    results = run_backtest(
        ticker=ticker,
        short_window=_int_param(request, "short_window", 20),
        long_window=_int_param(request, "long_window", 100),
    )
    return render(request, "dashboard/index.html", {"results": results})
