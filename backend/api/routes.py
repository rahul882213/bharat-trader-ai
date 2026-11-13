"""FastAPI Router for Bharat Trader AI (used when running standalone FastAPI server)."""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from fastapi import APIRouter, Query
    from pydantic import BaseModel
except ImportError:  # Allows Python CLI & stdlib tests without pip fastapi installed
    APIRouter = None  # type: ignore
    BaseModel = object  # type: ignore
    Query = lambda *a, **kw: None  # type: ignore

from backend.data_providers.nse_master import search_symbols
from backend.data_providers.provider_manager import get_provider_manager
from backend.services.indicators import compute_all_indicators
from backend.services.workflow import load_module_fn, run_full_analysis_workflow


def build_router():
    if APIRouter is None:
        return None
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health():
        return {"status": "ok", "service": "Bharat Trader AI FastAPI"}

    @router.get("/market/overview")
    def market_overview():
        mod = load_module_fn("trader-intelligence", "market_intelligence.py")
        return mod.get_market_overview()

    @router.get("/scanner")
    def scanner(strategy: str = "all", timeframe: str = "1d", universe: str = "nifty50", limit: int = 30):
        mod = load_module_fn("trader-scanner", "scanner.py")
        return mod.scan_market(strategy=strategy, timeframe=timeframe, universe=universe, limit=limit)

    @router.get("/symbols/search")
    def symbols_search(q: str = ""):
        return {"results": search_symbols(q)}

    @router.get("/chart/{symbol}")
    def chart(symbol: str, timeframe: str = "1d", exchange: str = "NSE"):
        pm = get_provider_manager()
        rng = "5d" if timeframe == "1m" else ("1mo" if timeframe in {"5m", "15m", "30m"} else ("3mo" if timeframe == "1h" else "1y"))
        data = pm.get_candles(symbol, interval=timeframe, range_str=rng, exchange=exchange)
        if data.get("available"):
            data["indicators"] = compute_all_indicators(data["candles"])
        return data

    @router.get("/analyse/{symbol}")
    def analyse(symbol: str, timeframe: str = "1d", strategy: str = "ema_crossover", exchange: str = "NSE"):
        return run_full_analysis_workflow(symbol, timeframe=timeframe, strategy=strategy, exchange=exchange)

    @router.get("/news")
    def news(symbol: Optional[str] = None, limit: int = 30):
        mod = load_module_fn("trader-news", "news_analyst.py")
        return mod.fetch_market_news(symbol=symbol, limit=limit)

    @router.get("/fundamentals/{symbol}")
    def fundamentals(symbol: str, exchange: str = "NSE"):
        mod = load_module_fn("trader-analyst", "fundamental_analyst.py")
        return mod.analyze_fundamentals(symbol, exchange=exchange)

    @router.get("/backtest")
    def backtest(
        symbol: str = "RELIANCE",
        strategy: str = "ema_crossover",
        timeframe: str = "1d",
        capital: float = 1000000.0,
        trade_type: str = "equity_intraday",
    ):
        mod = load_module_fn("trader-backtest", "backtester.py")
        return mod.run_backtest(symbol=symbol, strategy=strategy, timeframe=timeframe, initial_capital=capital, trade_type=trade_type)

    @router.get("/risk")
    def risk_status():
        mod = load_module_fn("trader-risk", "risk_engine.py")
        return mod.check_portfolio_risk()

    @router.get("/portfolio")
    def portfolio():
        mod = load_module_fn("trader-broker", "broker_executor.py")
        return mod.get_portfolio_summary(fetch_ltp=True)

    return router
