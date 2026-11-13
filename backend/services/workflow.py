"""12-Step Connected AI Trading Workflow Orchestrator (Structured JSON Pipeline)."""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import get_symbol_sector, normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager
from backend.services.indicators import compute_all_indicators
from backend.services.market_calendar import get_market_status

IST = ZoneInfo("Asia/Kolkata")
ROOT_DIR = Path(__file__).resolve().parents[2]
TRADER_DIR = ROOT_DIR / "trader"


def load_module_fn(folder_name: str, file_name: str):
    path = ROOT_DIR / "modules" / folder_name / file_name
    spec = importlib.util.spec_from_file_location(f"{folder_name.replace('-', '_')}_{file_name[:-3]}", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def run_full_analysis_workflow(
    symbol: str,
    timeframe: str = "1d",
    strategy: str = "ema_crossover",
    exchange: str = "NSE",
    execute_paper_if_ready: bool = False,
) -> Dict[str, Any]:
    """
    Execute the connected research workflow for a symbol:
    Scanner -> News Analyst -> Technical Analysis -> Entry Timing -> Exit Planner ->
    Backtesting Engine -> Position Size Calculator -> Risk Management -> Trade Approval Plan ->
    (Optional Paper Execution) -> Price Alerts -> Trade Journal Snapshot.
    """
    clean = normalize_symbol(symbol)
    pm = get_provider_manager()

    # Load independent modules cleanly
    news_mod = load_module_fn("trader-news", "news_analyst.py")
    entry_mod = load_module_fn("trader-entry", "entry_engine.py")
    exit_mod = load_module_fn("trader-exit", "exit_planner.py")
    bt_mod = load_module_fn("trader-backtest", "backtester.py")
    budget_mod = load_module_fn("trader-budget", "position_sizer.py")
    risk_mod = load_module_fn("trader-risk", "risk_engine.py")
    analyst_mod = load_module_fn("trader-analyst", "fundamental_analyst.py")
    broker_mod = load_module_fn("trader-broker", "broker_executor.py")
    alerts_mod = load_module_fn("trader-alerts", "alert_engine.py")

    # 1 & 3. Candles + Technical Analysis
    rng = "5d" if timeframe == "1m" else ("1mo" if timeframe in {"5m", "15m", "30m"} else ("3mo" if timeframe == "1h" else "1y"))
    candle_res = pm.get_candles(clean, interval=timeframe, range_str=rng, exchange=exchange)
    if not candle_res.get("available"):
        return {"available": False, "symbol": clean, "error": candle_res.get("error", "Market data unavailable.")}

    candles = candle_res["candles"]
    tech = compute_all_indicators(candles)

    # 2. News Analyst
    news_res = news_mod.fetch_market_news(symbol=clean, limit=12)

    # 10. Fundamental Analyst (parallel-safe quick call)
    fund_res = analyst_mod.analyze_fundamentals(clean, exchange=exchange, include_peers=False)

    # Save trader/analysis.json
    analysis_payload = {
        "generated_at": datetime.now(tz=IST).isoformat(),
        "symbol": clean,
        "exchange": exchange,
        "sector": get_symbol_sector(clean),
        "timeframe": timeframe,
        "source": candle_res["source"],
        "technical": {
            "latest": tech["latest"],
            "support_resistance": tech["support_resistance"],
            "patterns": tech["patterns"],
        },
        "fundamental": fund_res if fund_res.get("available") else {"available": False, "error": fund_res.get("error")},
        "news": {
            "overall_sentiment": news_res.get("overall_sentiment"),
            "counts": news_res.get("counts"),
            "top_articles": news_res.get("articles", [])[:5],
        },
    }
    TRADER_DIR.mkdir(parents=True, exist_ok=True)
    with (TRADER_DIR / "analysis.json").open("w", encoding="utf-8") as f:
        json.dump(analysis_payload, f, indent=2)

    # 4. Entry Timing Engine
    mkt = get_market_status()
    entry_res = entry_mod.evaluate_entry_from_candles(
        clean, candles, timeframe=timeframe, is_live_session=bool(mkt.get("is_market_open")), exchange=exchange
    )
    ref_entry = float(entry_res.get("ideal_entry_price") or tech["latest"]["close"])

    # 5. Exit Planner
    product = "MIS" if timeframe in {"1m", "5m", "15m", "30m", "1h"} else "CNC"
    exit_res = exit_mod.plan_exit_from_candles(clean, candles, entry_price=ref_entry, side="BUY", product=product, exchange=exchange)

    # 6. Backtesting Engine (on daily 2y or current timeframe)
    bt_res = bt_mod.run_backtest(clean, strategy=strategy, timeframe=timeframe, monte_carlo_runs=2500, exchange=exchange)

    # 7. Position Size Calculator
    risk_cfg = risk_mod.get_risk_config()
    sl_val = float(exit_res.get("initial_stop_loss") or (ref_entry * 0.98))
    target2_val = float(exit_res.get("target_2") or (ref_entry * 1.04))
    pos_res = budget_mod.calculate_position_size(
        capital_inr=float(risk_cfg.get("total_capital_inr", 1000000.0)),
        risk_pct=float(risk_cfg.get("max_risk_per_trade_pct", 1.0)),
        entry_price=ref_entry,
        stop_loss=sl_val,
        segment="cash_equity",
        trade_type="equity_delivery" if product == "CNC" else "equity_intraday",
    )

    # 8. Risk Management Gate
    qty = int(pos_res.get("quantity", 0)) if pos_res.get("allowed") else 0
    chg_inr = float(pos_res.get("estimated_charges_inr", 0.0)) if pos_res.get("allowed") else 0.0
    risk_res = risk_mod.evaluate_trade_risk(
        symbol=clean,
        entry_price=ref_entry,
        stop_loss=sl_val,
        target_price=target2_val,
        quantity=max(qty, 1),
        sector=get_symbol_sector(clean),
        charges_inr=chg_inr,
    )

    # 9. Trade Plan & Approval Preview
    trade_plan = {
        "generated_at": datetime.now(tz=IST).isoformat(),
        "symbol": clean,
        "exchange": exchange,
        "sector": get_symbol_sector(clean),
        "entry": entry_res,
        "exit": exit_res,
        "backtest_summary": {
            "available": bt_res.get("available"),
            "strategy": strategy,
            "total_trades": (bt_res.get("metrics") or {}).get("total_trades"),
            "win_rate_pct": (bt_res.get("metrics") or {}).get("win_rate_pct"),
            "profit_factor": (bt_res.get("metrics") or {}).get("profit_factor"),
            "net_pnl_inr": bt_res.get("net_pnl"),
            "monte_carlo_prob_profit_pct": (bt_res.get("monte_carlo") or {}).get("probability_of_profit_pct"),
        },
        "position_sizing": pos_res,
        "risk_check": risk_res,
        "approval_preview": broker_mod.preview_live_order({
            "symbol": clean,
            "exchange": exchange,
            "side": "BUY",
            "quantity": qty,
            "price": ref_entry,
            "stop_loss": sl_val,
            "target": target2_val,
            "product": product,
            "broker": "paper",
        }),
    }
    with (TRADER_DIR / "trade_plan.json").open("w", encoding="utf-8") as f:
        json.dump(trade_plan, f, indent=2)

    execution_result = None
    if execute_paper_if_ready and risk_res["verdict"] == "PASS" and entry_res["status"] == "ENTRY TRIGGERED" and qty > 0:
        execution_result = broker_mod.execute_order(
            {
                "symbol": clean,
                "exchange": exchange,
                "side": "BUY",
                "quantity": qty,
                "price": ref_entry,
                "stop_loss": sl_val,
                "target": target2_val,
                "product": product,
                "order_type": "LIMIT",
                "strategy": strategy,
                "notes": "Automated Workflow Paper Entry",
            },
            mode="paper",
            broker="paper",
        )

    alerts_snapshot = alerts_mod.check_alerts()
    portfolio_snapshot = broker_mod.get_portfolio_summary(broker="paper")

    return {
        "available": True,
        "symbol": clean,
        "exchange": exchange,
        "market_status": mkt,
        "analysis": analysis_payload,
        "trade_plan": trade_plan,
        "paper_execution": execution_result,
        "alerts_checked": alerts_snapshot["checked_count"],
        "portfolio": portfolio_snapshot["portfolio"],
    }
