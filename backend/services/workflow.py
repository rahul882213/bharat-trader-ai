"""12-Step Connected Dynamic AI Trading Workflow Orchestrator (Supports Every NSE/BSE Stock)."""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager
from backend.database.db import execute_sql
from backend.database.stock_master_db import resolve_stock
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


def run_analysis(
    symbol: str,
    exchange: str = "NSE",
    analysis_type: str = "full",
    timeframe: str = "1d",
    strategy: str = "ema_crossover",
    execute_paper_if_ready: bool = False,
) -> Dict[str, Any]:
    """
    Reusable dynamic 12-stage analysis pipeline for ANY Indian stock (NSE, BSE, SME, ISIN, BSE Code, or Company Name):
    Stock Resolution -> Market Candles -> News & Filings -> Technical Indicators -> Screener & AI Fundamentals ->
    Entry Timing -> Exit Planner -> Backtest + Monte Carlo -> Position Sizing -> Risk Gate -> Trade Plan -> Alerts & Portfolio.
    """
    stock_meta = resolve_stock(symbol, exchange=exchange)
    clean = stock_meta.get("nse_symbol") or stock_meta.get("bse_code") or normalize_symbol(symbol)
    resolved_exchange = stock_meta.get("exchange") or exchange
    pm = get_provider_manager()

    news_mod = load_module_fn("trader-news", "news_analyst.py")
    entry_mod = load_module_fn("trader-entry", "entry_engine.py")
    exit_mod = load_module_fn("trader-exit", "exit_planner.py")
    bt_mod = load_module_fn("trader-backtest", "backtester.py")
    budget_mod = load_module_fn("trader-budget", "position_sizer.py")
    risk_mod = load_module_fn("trader-risk", "risk_engine.py")
    analyst_mod = load_module_fn("trader-analyst", "fundamental_analyst.py")
    broker_mod = load_module_fn("trader-broker", "broker_executor.py")
    alerts_mod = load_module_fn("trader-alerts", "alert_engine.py")

    # Stage 1: Candles + Technical Indicators
    rng = "5d" if timeframe == "1m" else ("1mo" if timeframe in {"5m", "15m", "30m"} else ("3mo" if timeframe == "1h" else "1y"))
    candle_res = pm.get_candles(clean, interval=timeframe, range_str=rng, exchange=exchange)
    candles = candle_res.get("candles") or []
    if not candle_res.get("available") and analysis_type != "fundamental":
        return {
            "available": False,
            "symbol": clean,
            "stock_meta": stock_meta,
            "error": candle_res.get("error", f"Market data unavailable for {clean}."),
        }

    tech = (
        compute_all_indicators(candles)
        if len(candles) >= 5
        else {
            "latest": {"close": candles[-1]["close"] if candles else None, "volume": candles[-1]["volume"] if candles else 0},
            "support_resistance": {},
            "patterns": [],
        }
    )

    # Stage 2: News & Filings
    news_res = news_mod.fetch_market_news(symbol=clean, limit=12)

    # Stage 3: Screener.in + Fundamental AI Analyst
    fund_res = analyst_mod.analyze_fundamentals(stock_meta["stock_id"], exchange=exchange, include_peers=False)

    # Refresh stock_meta (market cap / sector may now be enriched)
    stock_meta = resolve_stock(stock_meta["stock_id"], exchange=exchange)
    sector = stock_meta.get("sector") or "Indian Equities"

    analysis_payload = {
        "generated_at": datetime.now(tz=IST).isoformat(),
        "analysis_type": analysis_type,
        "symbol": clean,
        "company_name": stock_meta.get("company_name") or clean,
        "isin": stock_meta.get("isin"),
        "bse_code": stock_meta.get("bse_code"),
        "exchange": resolved_exchange,
        "sector": sector,
        "industry": stock_meta.get("industry") or "Indian Listed Equity",
        "cap_tier": stock_meta.get("cap_tier"),
        "timeframe": timeframe,
        "source": candle_res.get("source", fund_res.get("source", "Bharat Trader Registry")),
        "technical": {
            "available": len(candles) >= 5,
            "latest": tech.get("latest", {}),
            "support_resistance": tech.get("support_resistance", {}),
            "patterns": tech.get("patterns", []),
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

    mkt = get_market_status()
    product = "MIS" if timeframe in {"1m", "5m", "15m", "30m", "1h"} else "CNC"

    if analysis_type == "fundamental" or len(candles) < 15:
        entry_res = {"available": False, "status": "FUNDAMENTAL_ONLY", "summary": "Technical timing skipped for fundamental-only pass or insufficient candle depth."}
        exit_res = {"available": False}
        bt_res = {"available": False}
        pos_res = {"allowed": False, "quantity": 0}
        risk_res = {"verdict": "SKIPPED", "violations": []}
        trade_plan = {
            "generated_at": datetime.now(tz=IST).isoformat(),
            "symbol": clean,
            "company_name": stock_meta.get("company_name"),
            "exchange": resolved_exchange,
            "sector": sector,
            "entry": entry_res,
            "exit": exit_res,
            "backtest_summary": {"available": False},
            "position_sizing": pos_res,
            "risk_check": risk_res,
        }
        execution_result = None
    else:
        # Stage 4: Entry Timing Engine
        entry_res = entry_mod.evaluate_entry_from_candles(
            clean, candles, timeframe=timeframe, is_live_session=bool(mkt.get("is_market_open")), exchange=exchange
        )
        ref_entry = float(entry_res.get("ideal_entry_price") or tech["latest"]["close"])

        # Stage 5: Exit Planner
        exit_res = exit_mod.plan_exit_from_candles(clean, candles, entry_price=ref_entry, side="BUY", product=product, exchange=exchange)

        # Stage 6: Backtesting Engine
        bt_res = bt_mod.run_backtest(clean, strategy=strategy, timeframe=timeframe, monte_carlo_runs=2500, exchange=exchange)

        # Stage 7: Position Size Calculator
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

        # Stage 8: Risk Management Gate
        qty = int(pos_res.get("quantity", 0)) if pos_res.get("allowed") else 0
        chg_inr = float(pos_res.get("estimated_charges_inr", 0.0)) if pos_res.get("allowed") else 0.0
        risk_res = risk_mod.evaluate_trade_risk(
            symbol=clean,
            entry_price=ref_entry,
            stop_loss=sl_val,
            target_price=target2_val,
            quantity=max(qty, 1),
            sector=sector,
            charges_inr=chg_inr,
        )

        # Stage 9: Trade Plan & Approval Preview
        trade_plan = {
            "generated_at": datetime.now(tz=IST).isoformat(),
            "symbol": clean,
            "company_name": stock_meta.get("company_name"),
            "exchange": resolved_exchange,
            "sector": sector,
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

    result_payload = {
        "available": True,
        "symbol": clean,
        "stock_meta": stock_meta,
        "exchange": resolved_exchange,
        "analysis_type": analysis_type,
        "market_status": mkt,
        "analysis": analysis_payload,
        "trade_plan": trade_plan,
        "paper_execution": execution_result,
        "alerts_checked": alerts_snapshot["checked_count"],
        "portfolio": portfolio_snapshot["portfolio"],
    }

    # Persist into central ai_trading_analyses and technical_signals tables
    try:
        now_iso = datetime.now(tz=IST).isoformat()
        execute_sql(
            """
            INSERT INTO ai_trading_analyses
            (stock_id, symbol, analysis_type, entry_status, risk_verdict, workflow_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_id) DO UPDATE SET
                symbol = excluded.symbol,
                analysis_type = excluded.analysis_type,
                entry_status = excluded.entry_status,
                risk_verdict = excluded.risk_verdict,
                workflow_json = excluded.workflow_json,
                updated_at = excluded.updated_at
            """,
            (
                stock_meta["stock_id"],
                clean,
                analysis_type,
                entry_res.get("status", "UNKNOWN"),
                risk_res.get("verdict", "UNKNOWN"),
                json.dumps(result_payload),
                now_iso,
            ),
        )
        sig_id = f"SIG-{stock_meta['stock_id']}-{timeframe}-{strategy}"
        execute_sql(
            """
            INSERT INTO technical_signals
            (signal_id, stock_id, symbol, exchange, timeframe, strategy, signal_direction, score, price, reasons_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(signal_id) DO UPDATE SET
                signal_direction = excluded.signal_direction,
                score = excluded.score,
                price = excluded.price,
                reasons_json = excluded.reasons_json,
                created_at = excluded.created_at
            """,
            (
                sig_id,
                stock_meta["stock_id"],
                clean,
                resolved_exchange,
                timeframe,
                strategy,
                entry_res.get("status", "WATCH"),
                float(indicators.get("rsi14") or 0.0),
                float(latest_price or 0.0),
                json.dumps(entry_res.get("reasons", [])),
                now_iso,
            ),
        )
    except Exception:
        pass

    return result_payload


def run_full_analysis_workflow(
    symbol: str,
    timeframe: str = "1d",
    strategy: str = "ema_crossover",
    exchange: str = "NSE",
    execute_paper_if_ready: bool = False,
) -> Dict[str, Any]:
    """Backwards-compatible alias delegating to dynamic run_analysis()."""
    return run_analysis(
        symbol=symbol,
        exchange=exchange,
        analysis_type="full",
        timeframe=timeframe,
        strategy=strategy,
        execute_paper_if_ready=execute_paper_if_ready,
    )
