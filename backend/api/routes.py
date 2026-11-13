"""Complete FastAPI Router for Bharat Trader AI (Render / Production Ready)."""
from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo

try:
    from fastapi import APIRouter, HTTPException, Query
    from pydantic import BaseModel, Field
except ImportError:  # Allows Python CLI & stdlib tests without pip fastapi installed
    APIRouter = None  # type: ignore
    HTTPException = Exception  # type: ignore
    BaseModel = object  # type: ignore
    Field = lambda *a, **kw: None  # type: ignore
    Query = lambda *a, **kw: None  # type: ignore

from backend.database.db import check_db_health, execute_sql, query_all
from backend.database.stock_master_db import _discover_many_via_yahoo, resolve_stock, search_stock_master
from backend.data_providers.provider_manager import get_provider_manager
from backend.services.indicators import compute_all_indicators
from backend.services.workflow import load_module_fn, run_analysis

IST = ZoneInfo("Asia/Kolkata")
API_VERSION = "2.0.0"

_CACHE_LOCK = threading.Lock()
_TTL_CACHE: Dict[str, tuple[float, Any]] = {}


def _cache_get(key: str, ttl_sec: float) -> Optional[Any]:
    with _CACHE_LOCK:
        hit = _TTL_CACHE.get(key)
        if hit and (time.monotonic() - hit[0]) < ttl_sec:
            return hit[1]
    return None


def _cache_set(key: str, value: Any) -> None:
    with _CACHE_LOCK:
        _TTL_CACHE[key] = (time.monotonic(), value)


def _cache_clear() -> None:
    with _CACHE_LOCK:
        _TTL_CACHE.clear()


def build_root_health_payload() -> Dict[str, Any]:
    db_info = check_db_health()
    if db_info.get("connected") and db_info.get("stock_master_count", 0) == 0:
        try:
            from backend.database.stock_master_db import sync_stock_master

            sync_stock_master(force=False)
            db_info = check_db_health()
        except Exception:
            pass
    gemini_ok = bool(os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_KEY") != "MY_GEMINI_API_KEY")
    trading_mode = os.getenv("TRADING_MODE", "paper").lower()
    return {
        "status": "ok" if db_info.get("connected") else "degraded",
        "service": "Bharat Trader AI FastAPI",
        "api_version": API_VERSION,
        "trading_mode": trading_mode,
        "database": db_info,
        "data_providers": {
            "yahoo_finance": {"available": True, "type": "OHLCV & Quotes (Unofficial)"},
            "nse_master": {
                "available": db_info.get("stock_master_count", 0) > 0,
                "symbols_count": db_info.get("stock_master_count", 0),
            },
            "indian_rss_news": {"available": True, "type": "RBI / SEBI / ET / Moneycontrol / BS"},
            "screener_importer": {"available": True, "type": "CSV & XLSX Financial Importer"},
            "gemini_ai": {"available": gemini_ok, "configured": gemini_ok},
        },
        "last_updated": db_info.get("last_data_update"),
        "server_time_ist": datetime.now(tz=IST).isoformat(),
    }


def _invoke_gemini_research(symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key or api_key == "MY_GEMINI_API_KEY":
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured in backend environment variables. Quantitative metrics remain operational.",
        )

    prompt = (
        f"Analyze the Indian equity {symbol} strictly based on the verified quantitative, fundamental, and news context provided below. "
        f"Never invent prices, revenue figures, or guaranteed return predictions. Clearly distinguish reported facts from analytical interpretation.\n\n"
        f"CONTEXT JSON:\n{json.dumps(context)[:14000]}"
    )
    sys_instruction = (
        "You are a senior Indian equity research analyst and algorithmic risk officer at an institutional NSE/BSE desk. "
        "Output strictly structured JSON in INR (₹) with keys: thesis_headline, technical_stance, fundamental_assessment, "
        "key_catalysts (array of strings), key_risks (array of strings), actionable_desk_note."
    )
    model_name = os.getenv("GEMINI_MODEL", "gemini-4-hydrogen")

    # Prefer official google-genai Python SDK if installed; otherwise direct REST API call
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=sys_instruction,
                response_mime_type="application/json",
            ),
        )
        parsed = json.loads((resp.text or "{}").strip())
        return {"available": True, "symbol": symbol, "model": model_name, "synthesis": parsed}
    except ImportError:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "systemInstruction": {"parts": [{"text": sys_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            raise HTTPException(status_code=502, detail=f"Gemini API HTTP {err.code}")
        text = raw.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
        parsed = json.loads(text.strip())
        return {"available": True, "symbol": symbol, "model": model_name, "synthesis": parsed}


# --- Pydantic Request Schemas ---
class WatchlistAddRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32)
    exchange: Literal["NSE", "BSE"] = "NSE"
    sector: str = Field(default="Indian Equities", max_length=120)


class WorkflowRunRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    exchange: Literal["NSE", "BSE"] = "NSE"
    company_name: Optional[str] = Field(default=None, max_length=200)
    analysis_type: Literal["full", "technical", "fundamental", "swing", "intraday"] = "full"
    timeframe: Literal["1m", "5m", "15m", "30m", "1h", "1d"] = "1d"
    strategy: str = Field(default="ema_crossover", max_length=40)


class ScreenerCsvImportRequest(BaseModel):
    csv_text: str = Field(..., min_length=5, max_length=10_000_000)
    filename: str = Field(default="screener_export.csv", max_length=255)
    screen_name: Optional[str] = Field(default=None, max_length=255)
    screener_url: Optional[str] = Field(default=None, max_length=512)
    statement_scope: Literal["Consolidated", "Standalone", "Unspecified"] = "Consolidated"
    update_existing: bool = True


class ScreenerXlsxImportRequest(BaseModel):
    content_base64: str = Field(..., min_length=16, max_length=18_000_000)
    filename: str = Field(default="screener_company.xlsx", max_length=255)
    symbol_hint: Optional[str] = Field(default=None, max_length=40)
    screener_url: Optional[str] = Field(default=None, max_length=512)
    statement_scope: Literal["Consolidated", "Standalone", "Unspecified"] = "Consolidated"
    update_existing: bool = True


class ScreenerUrlRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    screener_url: str = Field(..., min_length=8, max_length=512)
    statement_scope: Optional[Literal["Consolidated", "Standalone", "Unspecified"]] = None


class BusinessNotesRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    notes: Dict[str, Any]


class OptionalPublicFetchRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    statement_scope: Literal["Consolidated", "Standalone", "Unspecified"] = "Consolidated"


class BacktestRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    strategy: str = Field(default="ema_crossover", max_length=40)
    timeframe: Literal["5m", "15m", "30m", "1h", "1d"] = "1d"
    capital: float = Field(default=1000000.0, gt=1000, le=1_000_000_000)
    trade_type: Literal["equity_intraday", "equity_delivery", "fno_futures", "fno_options"] = "equity_intraday"
    runs: int = Field(default=10000, ge=100, le=20000)
    exchange: Literal["NSE", "BSE"] = "NSE"


class RiskEvaluateRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    entry_price: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    target_price: float = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    charges_inr: float = Field(default=0.0, ge=0)


class BudgetCalculateRequest(BaseModel):
    capital_inr: float = Field(default=1000000.0, gt=1000)
    risk_pct: float = Field(default=1.0, gt=0, le=10)
    entry_price: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    segment: str = "cash_equity"
    trade_type: str = "equity_intraday"
    broker: str = "zerodha"
    lot_size: int = Field(default=1, ge=1)
    fno_enabled: bool = False


class OrderExecuteRequest(BaseModel):
    order: Dict[str, Any]
    mode: Literal["paper", "live"] = "paper"
    broker: str = Field(default="paper", max_length=32)
    explicit_user_approval: bool = False
    skip_risk_check: bool = False


class PositionCloseRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    exchange: Literal["NSE", "BSE"] = "NSE"
    product: str = Field(default="MIS", max_length=16)
    exit_price: Optional[float] = Field(default=None, gt=0)


class AlertCreateRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    condition: str = Field(..., min_length=2, max_length=64)
    threshold: Optional[float] = None
    exchange: Literal["NSE", "BSE"] = "NSE"
    telegram_notify: bool = False
    message: str = Field(default="", max_length=280)


class AiResearchRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    context: Dict[str, Any] = Field(default_factory=dict)


def build_router():
    if APIRouter is None:
        return None
    router = APIRouter(prefix="/api")

    # --- HEALTH ---
    @router.get("/health")
    def health():
        return build_root_health_payload()

    # --- MARKET OVERVIEW & DAILY BRIEFING ---
    @router.get("/market/overview")
    def market_overview(refresh: Optional[str] = None):
        if refresh != "1":
            cached = _cache_get("market_overview", 45.0)
            if cached is not None:
                return cached
        mod = load_module_fn("trader-intelligence", "market_intelligence.py")
        data = mod.get_market_overview()
        _cache_set("market_overview", data)
        return data

    @router.get("/report/daily")
    def report_daily():
        cached = _cache_get("daily_report", 60.0)
        if cached is not None:
            return cached
        mod = load_module_fn("trader-intelligence", "market_intelligence.py")
        data = mod.generate_daily_briefing()
        _cache_set("daily_report", data)
        return data

    # --- UNIVERSAL STOCK MASTER SEARCH & RESOLUTION ---
    @router.get("/stocks/master/stats")
    def stocks_master_stats():
        cached = _cache_get("master_stats", 60.0)
        if cached is not None:
            return cached
        from backend.database.stock_master_db import get_master_stats

        data = get_master_stats()
        _cache_set("master_stats", data)
        return data

    @router.get("/stocks/resolve/{query}")
    def stocks_resolve(query: str, exchange: str = "NSE"):
        return resolve_stock(query, exchange=exchange)

    @router.get("/symbols/search")
    def symbols_search(
        q: str = "",
        sector: str = "ALL",
        industry: str = "ALL",
        cap_tier: str = "ALL",
        exchange: str = "ALL",
        limit: int = Query(default=25, ge=1, le=200),
    ):
        rows = search_stock_master(
            query=q.strip(),
            sector=sector,
            industry=industry,
            cap_tier=cap_tier,
            exchange=exchange,
            limit=limit,
        )
        if not rows and len(q.strip()) >= 2:
            rows = _discover_many_via_yahoo(q.strip(), limit=min(limit, 8))
            if not rows:
                rec = resolve_stock(q.strip())
                if rec and rec.get("trading_status") != "UNVERIFIED":
                    rows = [rec]
        q_clean = q.strip().upper()
        out = []
        for r in rows:
            matched_by_bse = bool(q_clean and r.get("bse_code") and (q_clean == str(r.get("bse_code")).upper() or q_clean.endswith(".BO")))
            ex_val = "BSE" if (matched_by_bse or exchange.upper() == "BSE") else (r.get("exchange") or "NSE")
            out.append(
                {
                    "stock_id": r.get("stock_id"),
                    "symbol": (r.get("bse_code") if (ex_val == "BSE" and not r.get("nse_symbol")) else None)
                    or r.get("nse_symbol")
                    or r.get("bse_code")
                    or r.get("stock_id"),
                    "nse_symbol": r.get("nse_symbol"),
                    "bse_code": r.get("bse_code"),
                    "name": r.get("company_name"),
                    "company_name": r.get("company_name"),
                    "series": r.get("series") or "EQ",
                    "isin": r.get("isin") or "",
                    "exchange": ex_val,
                    "sector": r.get("sector") or "Indian Equities",
                    "industry": r.get("industry") or "Indian Listed Equity",
                    "market_cap_cr": r.get("market_cap_cr"),
                    "cap_tier": r.get("cap_tier"),
                    "screener_url": r.get("screener_url"),
                }
            )
        return {"results": out}

    # --- WATCHLIST ---
    @router.get("/watchlist")
    def get_watchlist():
        rows = query_all("SELECT symbol, exchange, sector, added_at FROM watchlists ORDER BY added_at DESC")
        if rows:
            return {"watchlist": rows, "updated_at": rows[0]["added_at"]}
        from backend.database.db import ROOT_DIR

        wl_path = ROOT_DIR / "trader" / "watchlist.json"
        if wl_path.exists():
            return json.loads(wl_path.read_text(encoding="utf-8"))
        return {"watchlist": [], "updated_at": datetime.now(tz=IST).isoformat()}

    @router.post("/watchlist")
    def add_watchlist(payload: WatchlistAddRequest):
        clean = payload.symbol.strip().upper().replace(".NS", "").replace(".BO", "")
        now_iso = datetime.now(tz=IST).isoformat()
        execute_sql(
            """
            INSERT INTO watchlists (symbol, exchange, sector, added_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol, exchange) DO UPDATE SET sector = excluded.sector, added_at = excluded.added_at
            """,
            (clean, payload.exchange, payload.sector, now_iso),
        )
        rows = query_all("SELECT symbol, exchange, sector, added_at FROM watchlists ORDER BY added_at DESC")
        return {"watchlist": rows, "updated_at": now_iso}

    @router.delete("/watchlist/{symbol}")
    def delete_watchlist(symbol: str, exchange: Optional[str] = None):
        clean = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
        if exchange:
            execute_sql("DELETE FROM watchlists WHERE UPPER(symbol) = ? AND UPPER(exchange) = ?", (clean, exchange.upper()))
        else:
            execute_sql("DELETE FROM watchlists WHERE UPPER(symbol) = ?", (clean,))
        rows = query_all("SELECT symbol, exchange, sector, added_at FROM watchlists ORDER BY added_at DESC")
        return {"watchlist": rows, "updated_at": datetime.now(tz=IST).isoformat()}

    # --- SCANNERS ---
    @router.get("/scanner")
    def scanner(
        strategy: str = "daily",
        timeframe: str = "1d",
        universe: str = "nifty50",
        limit: int = Query(default=25, ge=1, le=120),
        exchange: str = "NSE",
        refresh: Optional[str] = None,
    ):
        ck = f"scan:{strategy}:{timeframe}:{universe}:{limit}:{exchange}"
        if refresh != "1":
            cached = _cache_get(ck, 45.0)
            if cached is not None:
                return cached
        mod = load_module_fn("trader-scanner", "scanner.py")
        data = mod.scan_market(strategy=strategy, timeframe=timeframe, universe=universe, limit=limit, exchange=exchange)
        _cache_set(ck, data)
        return data

    @router.get("/scanner/market-wide")
    def scanner_market_wide(
        cap_tier: str = "ALL",
        sector: str = "ALL",
        industry: str = "ALL",
        strategy: str = "all",
        timeframe: str = "1d",
        universe: str = "all",
        limit: int = Query(default=40, ge=1, le=120),
        min_mcap: Optional[float] = None,
        max_mcap: Optional[float] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_volume: Optional[int] = None,
        refresh: Optional[str] = None,
    ):
        ck = f"mw:{cap_tier}:{sector}:{industry}:{strategy}:{timeframe}:{universe}:{limit}:{min_mcap}:{max_mcap}:{min_price}:{max_price}:{min_volume}"
        if refresh != "1":
            cached = _cache_get(ck, 45.0)
            if cached is not None:
                return cached
        mod = load_module_fn("trader-scanner", "scanner.py")
        data = mod.scan_entire_market(
            cap_tier=cap_tier,
            sector=sector,
            industry=industry,
            strategy=strategy,
            timeframe=timeframe,
            universe=universe,
            limit=limit,
            min_market_cap_cr=min_mcap,
            max_market_cap_cr=max_mcap,
            min_price=min_price,
            max_price=max_price,
            min_volume=min_volume,
        )
        _cache_set(ck, data)
        return data

    # --- CHART, ENTRY, EXIT, WORKFLOW ---
    @router.get("/chart/{symbol}")
    def chart(symbol: str, timeframe: str = "1d", exchange: str = "NSE", range: Optional[str] = None):
        pm = get_provider_manager()
        rng = range or ("5d" if timeframe == "1m" else ("1mo" if timeframe in {"5m", "15m", "30m"} else ("3mo" if timeframe == "1h" else "1y")))
        data = pm.get_candles(symbol.upper(), interval=timeframe, range_str=rng, exchange=exchange)
        if data.get("available"):
            data["indicators"] = compute_all_indicators(data["candles"])
        return data

    @router.get("/entry/{symbol}")
    def entry(symbol: str, timeframe: str = "15m", exchange: str = "NSE"):
        mod = load_module_fn("trader-entry", "entry_engine.py")
        return mod.analyze_entry(symbol.upper(), timeframe=timeframe, exchange=exchange)

    @router.get("/exit/{symbol}")
    def exit_plan(
        symbol: str,
        timeframe: str = "1d",
        product: str = "MIS",
        exchange: str = "NSE",
        entry: Optional[float] = None,
    ):
        mod = load_module_fn("trader-exit", "exit_planner.py")
        return mod.generate_exit_plan(
            symbol.upper(),
            entry_price=entry,
            timeframe=timeframe,
            product=product,
            exchange=exchange,
        )

    @router.get("/workflow/{symbol}")
    def workflow_get(
        symbol: str,
        timeframe: str = "1d",
        type: str = "full",
        exchange: str = "NSE",
    ):
        return run_analysis(symbol=symbol.upper(), exchange=exchange, analysis_type=type, timeframe=timeframe)

    @router.post("/workflow/run")
    def workflow_run(payload: WorkflowRunRequest):
        return run_analysis(
            symbol=payload.symbol.upper(),
            exchange=payload.exchange,
            analysis_type=payload.analysis_type,
            timeframe=payload.timeframe,
            strategy=payload.strategy,
            company_name=payload.company_name,
        )

    # --- FUNDAMENTALS & SCREENER.IN DATA CENTER ---
    @router.get("/fundamentals/{symbol}")
    def fundamentals(symbol: str, exchange: str = "NSE", refresh: Optional[str] = None):
        ck = f"fund:{symbol.upper()}:{exchange}"
        if refresh != "1":
            cached = _cache_get(ck, 120.0)
            if cached is not None:
                return cached
        mod = load_module_fn("trader-analyst", "fundamental_analyst.py")
        data = mod.analyze_fundamentals(symbol.upper(), exchange=exchange)
        _cache_set(ck, data)
        return data

    @router.get("/screener/companies")
    def screener_companies():
        mod = load_module_fn("trader-screener", "screener_importer.py")
        return mod.list_imported_companies()

    @router.get("/screener/screens")
    def screener_screens():
        mod = load_module_fn("trader-screener", "screener_importer.py")
        return mod.list_imported_screens()

    @router.get("/screener/template-csv")
    def screener_template_csv():
        mod = load_module_fn("trader-screener", "screener_importer.py")
        return {"csv": mod.get_sample_csv_template()}

    @router.get("/screener/company/{symbol}")
    def screener_company(symbol: str):
        mod = load_module_fn("trader-screener", "screener_importer.py")
        return mod.get_screener_company_data(symbol.upper())

    @router.post("/screener/import-csv")
    def screener_import_csv(payload: ScreenerCsvImportRequest):
        mod = load_module_fn("trader-screener", "screener_importer.py")
        res = mod.import_screener_csv(
            csv_text=payload.csv_text,
            filename=payload.filename,
            screen_name=payload.screen_name,
            screener_url=payload.screener_url,
            statement_scope=payload.statement_scope,
            update_existing=payload.update_existing,
        )
        _cache_clear()
        return res

    @router.post("/screener/import-xlsx")
    def screener_import_xlsx(payload: ScreenerXlsxImportRequest):
        raw_b64 = payload.content_base64.split(",", 1)[1] if "," in payload.content_base64 else payload.content_base64
        try:
            xlsx_bytes = base64.b64decode(raw_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 Excel payload.")
        mod = load_module_fn("trader-screener", "screener_importer.py")
        res = mod.import_screener_xlsx(
            xlsx_bytes=xlsx_bytes,
            filename=payload.filename,
            symbol_hint=payload.symbol_hint,
            screener_url=payload.screener_url,
            statement_scope=payload.statement_scope,
            update_existing=payload.update_existing,
        )
        _cache_clear()
        return res

    @router.post("/screener/associate-url")
    def screener_associate_url(payload: ScreenerUrlRequest):
        mod = load_module_fn("trader-screener", "screener_importer.py")
        res = mod.associate_screener_url(payload.symbol, payload.screener_url, payload.statement_scope)
        _cache_clear()
        return res

    @router.post("/screener/business-notes")
    def screener_business_notes(payload: BusinessNotesRequest):
        mod = load_module_fn("trader-screener", "screener_importer.py")
        res = mod.update_business_notes(payload.symbol, payload.notes)
        _cache_clear()
        return res

    @router.post("/screener/optional-public-fetch")
    def screener_optional_public_fetch(payload: OptionalPublicFetchRequest):
        adapter_mod = load_module_fn("trader-screener", "provider_adapter.py")
        return adapter_mod.ScreenerPublicPageAdapter().fetch_company(
            payload.symbol,
            statement_scope=payload.statement_scope,
        )

    # --- NEWS ---
    @router.get("/news")
    def news(symbol: Optional[str] = None, limit: int = Query(default=30, ge=1, le=100), refresh: Optional[str] = None):
        sym = symbol.upper() if symbol else None
        ck = f"news:{sym or 'ALL'}:{limit}"
        if refresh != "1":
            cached = _cache_get(ck, 60.0)
            if cached is not None:
                return cached
        mod = load_module_fn("trader-news", "news_analyst.py")
        data = mod.fetch_market_news(symbol=sym, limit=limit)
        _cache_set(ck, data)
        return data

    # --- BACKTESTER ---
    @router.post("/backtest")
    def backtest_post(payload: BacktestRequest):
        mod = load_module_fn("trader-backtest", "backtester.py")
        return mod.run_backtest(
            symbol=payload.symbol.upper(),
            strategy=payload.strategy,
            timeframe=payload.timeframe,
            initial_capital=payload.capital,
            trade_type=payload.trade_type,
            monte_carlo_runs=payload.runs,
            exchange=payload.exchange,
        )

    @router.get("/backtest")
    def backtest_get(
        symbol: str,
        strategy: str = "ema_crossover",
        timeframe: str = "1d",
        capital: float = 1000000.0,
        trade_type: str = "equity_intraday",
    ):
        mod = load_module_fn("trader-backtest", "backtester.py")
        return mod.run_backtest(symbol=symbol.upper(), strategy=strategy, timeframe=timeframe, initial_capital=capital, trade_type=trade_type)

    @router.get("/backtest/history")
    def backtest_history(limit: int = Query(default=25, ge=1, le=100)):
        rows = query_all(
            "SELECT backtest_id, symbol, strategy, timeframe, trade_type, initial_capital, final_capital, net_pnl, win_rate_pct, sharpe_ratio, max_drawdown_pct, created_at FROM backtest_results ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return {"history": rows}

    # --- RISK & POSITION SIZING ---
    @router.get("/risk")
    def risk_status():
        mod = load_module_fn("trader-risk", "risk_engine.py")
        return mod.check_portfolio_risk()

    @router.post("/risk/config")
    def risk_config_update(payload: Dict[str, Any]):
        mod = load_module_fn("trader-risk", "risk_engine.py")
        return mod.update_risk_config(payload)

    @router.post("/risk/evaluate")
    def risk_evaluate(payload: RiskEvaluateRequest):
        mod = load_module_fn("trader-risk", "risk_engine.py")
        return mod.evaluate_trade_risk(
            symbol=payload.symbol,
            entry_price=payload.entry_price,
            stop_loss=payload.stop_loss,
            target_price=payload.target_price,
            quantity=payload.quantity,
            charges_inr=payload.charges_inr,
        )

    @router.post("/budget/calculate")
    def budget_calculate(payload: BudgetCalculateRequest):
        mod = load_module_fn("trader-budget", "position_sizer.py")
        return mod.calculate_position_size(
            capital_inr=payload.capital_inr,
            risk_pct=payload.risk_pct,
            entry_price=payload.entry_price,
            stop_loss=payload.stop_loss,
            segment=payload.segment,
            trade_type=payload.trade_type,
            broker=payload.broker,
            lot_size=payload.lot_size,
            fno_enabled=payload.fno_enabled,
        )

    # --- PORTFOLIO, PAPER TRADING & BROKER ADAPTERS ---
    @router.get("/portfolio")
    def portfolio(live: Optional[str] = None):
        mod = load_module_fn("trader-broker", "broker_executor.py")
        return mod.get_portfolio_summary(fetch_ltp=(live == "1"))

    @router.get("/brokers/status")
    def brokers_status():
        mod = load_module_fn("trader-broker", "broker_executor.py")
        return mod.get_broker_status()

    @router.post("/orders/preview")
    def orders_preview(payload: Dict[str, Any]):
        mod = load_module_fn("trader-broker", "broker_executor.py")
        return mod.preview_live_order(payload)

    @router.post("/orders/execute")
    def orders_execute(payload: OrderExecuteRequest):
        broker_mod = load_module_fn("trader-broker", "broker_executor.py")
        risk_mod = load_module_fn("trader-risk", "risk_engine.py")
        order = payload.order
        if not payload.skip_risk_check and order.get("stop_loss") and order.get("target"):
            rc = risk_mod.evaluate_trade_risk(
                symbol=str(order["symbol"]),
                entry_price=float(order["price"]),
                stop_loss=float(order["stop_loss"]),
                target_price=float(order["target"]),
                quantity=int(order["quantity"]),
            )
            if rc.get("verdict") == "BLOCK":
                return {"executed": False, "blocked_by_risk": True, "risk_check": rc}
        return broker_mod.execute_order(
            order,
            mode=payload.mode,
            broker=payload.broker,
            explicit_user_approval=payload.explicit_user_approval,
        )

    @router.post("/positions/close")
    def positions_close(payload: PositionCloseRequest):
        from backend.broker_adapters.paper_adapter import PaperBrokerAdapter

        return PaperBrokerAdapter().close_position(
            symbol=payload.symbol,
            exchange=payload.exchange,
            product=payload.product,
            exit_price=payload.exit_price,
        )

    # --- ALERTS ---
    @router.get("/alerts")
    def alerts_list():
        mod = load_module_fn("trader-alerts", "alert_engine.py")
        return {"alerts": mod.list_alerts()}

    @router.post("/alerts")
    def alerts_create(payload: AlertCreateRequest):
        mod = load_module_fn("trader-alerts", "alert_engine.py")
        return mod.create_alert(
            symbol=payload.symbol,
            condition=payload.condition,
            threshold=payload.threshold,
            exchange=payload.exchange,
            telegram_notify=payload.telegram_notify,
            message=payload.message,
        )

    @router.post("/alerts/check")
    def alerts_check():
        mod = load_module_fn("trader-alerts", "alert_engine.py")
        return mod.check_alerts()

    @router.delete("/alerts/{alert_id}")
    def alerts_delete(alert_id: str):
        mod = load_module_fn("trader-alerts", "alert_engine.py")
        return mod.delete_alert(alert_id)

    # --- SERVER-SIDE GEMINI AI RESEARCH ---
    @router.post("/ai/research")
    def ai_research(payload: AiResearchRequest):
        return _invoke_gemini_research(payload.symbol.upper(), payload.context)

    return router
