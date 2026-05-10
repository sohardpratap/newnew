from django.shortcuts import render
from .services import run_backtest

def index(request):
    ticker = request.GET.get('ticker', 'RELIANCE.NS')
    results = run_backtest(ticker=ticker)
    return render(request, 'dashboard/index.html', {'results': results})
