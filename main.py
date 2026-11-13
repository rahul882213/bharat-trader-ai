#!/usr/bin/env python3
"""
Bharat Trader AI — Unified Command Line Interface
Examples:
  python3 main.py market overview
  python3 main.py scanner daily
  python3 main.py scanner orb
  python3 main.py scanner volume-breakout
  python3 main.py analyse RELIANCE
  python3 main.py analyse ORIANA
  python3 main.py news --symbol HAL
  python3 main.py entry RELIANCE
  python3 main.py exit RELIANCE
  python3 main.py backtest --strategy orb
  python3 main.py risk check
  python3 main.py budget calculate
  python3 main.py alerts check
  python3 main.py portfolio
  python3 main.py report daily
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.data_providers.nse_master import search_symbols
from backend.data_providers.provider_manager import get_provider_manager
from backend.services.indicators import compute_all_indicators
from backend.services.workflow import load_module_fn, run_full_analysis_workflow


def _emit(data: dict, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(prog="bharat-trader", description="Bharat Trader AI — Indian Stock Market CLI")
    parser.add_argument("--json", action="store_true", help="Emit clean JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    # market overview
    p_mkt = sub.add_parser("market", help="Indian market intelligence & overview")
    p_mkt.add_argument("action", nargs="?", default="overview", choices=["overview"])

    # scanner <mode>
    p_scan = sub.add_parser("scanner", help="Scan NSE/BSE universe for setups")
    p_scan.add_argument("mode", nargs="?", default="daily", help="daily | orb | volume-breakout | vwap-breakout | ema-crossover | ...")
    p_scan.add_argument("--timeframe", default=None, help="1m, 5m, 15m, 30m, 1h, 1d")
    p_scan.add_argument("--universe", default="nifty50", help="nifty50, banknifty, finnifty, niftynext50, midcap_smallcap, all")
    p_scan.add_argument("--limit", type=int, default=25)
    p_scan.add_argument("--exchange", default="NSE")

    # analyse <SYMBOL>
    p_ana = sub.add_parser("analyse", help="Run full technical + fundamental + news + trade plan analysis")
    p_ana.add_argument("symbol", help="Indian NSE/BSE stock symbol (e.g. RELIANCE, ORIANA, HAL)")
    p_ana.add_argument("--timeframe", default="1d")
    p_ana.add_argument("--exchange", default="NSE")

    # chart <SYMBOL>
    p_chart = sub.add_parser("chart", help="Fetch OHLCV candles and indicators")
    p_chart.add_argument("symbol")
    p_chart.add_argument("--timeframe", default="1d")
    p_chart.add_argument("--range", dest="range_str", default=None)
    p_chart.add_argument("--exchange", default="NSE")

    # search <QUERY>
    p_search = sub.add_parser("search", help="Search NSE equity master symbols")
    p_search.add_argument("query")

    # news --symbol <SYM>
    p_news = sub.add_parser("news", help="Fetch & classify Indian market / stock news")
    p_news.add_argument("--symbol", default=None)
    p_news.add_argument("--limit", type=int, default=25)

    # entry <SYMBOL>
    p_entry = sub.add_parser("entry", help="Evaluate entry timing on completed candles")
    p_entry.add_argument("symbol")
    p_entry.add_argument("--timeframe", default="15m")
    p_entry.add_argument("--exchange", default="NSE")

    # exit <SYMBOL>
    p_exit = sub.add_parser("exit", help="Plan initial SL, trailing SL, and Targets 1-3")
    p_exit.add_argument("symbol")
    p_exit.add_argument("--entry", type=float, default=None)
    p_exit.add_argument("--timeframe", default="1d")
    p_exit.add_argument("--product", default="MIS")
    p_exit.add_argument("--exchange", default="NSE")

    # backtest --strategy <STRAT>
    p_bt = sub.add_parser("backtest", help="Run historical backtest + 10,000 Monte Carlo simulations")
    p_bt.add_argument("--symbol", default="RELIANCE")
    p_bt.add_argument("--strategy", default="orb")
    p_bt.add_argument("--timeframe", default="1d")
    p_bt.add_argument("--capital", type=float, default=1000000.0)
    p_bt.add_argument("--trade-type", default="equity_intraday")
    p_bt.add_argument("--runs", type=int, default=10000)

    # fundamentals <SYMBOL>
    p_fund = sub.add_parser("fundamentals", help="Run deep Indian company fundamental analysis")
    p_fund.add_argument("symbol")
    p_fund.add_argument("--exchange", default="NSE")
    p_fund.add_argument("--no-peers", action="store_true")

    # risk check
    p_risk = sub.add_parser("risk", help="Check portfolio risk limits")
    p_risk.add_argument("action", nargs="?", default="check", choices=["check"])

    # budget calculate
    p_bud = sub.add_parser("budget", help="Calculate INR position size")
    p_bud.add_argument("action", nargs="?", default="calculate", choices=["calculate"])
    p_bud.add_argument("--capital", type=float, default=1000000.0)
    p_bud.add_argument("--risk", type=float, default=1.0)
    p_bud.add_argument("--entry", type=float, default=500.0)
    p_bud.add_argument("--sl", type=float, default=480.0)
    p_bud.add_argument("--segment", default="cash_equity")
    p_bud.add_argument("--lot-size", type=int, default=1)
    p_bud.add_argument("--fno-enabled", action="store_true")

    # alerts check
    p_al = sub.add_parser("alerts", help="Check or manage alerts")
    p_al.add_argument("action", nargs="?", default="check", choices=["check", "list"])

    # portfolio
    p_port = sub.add_parser("portfolio", help="Show paper/broker portfolio & open positions")
    p_port.add_argument("--broker", default="paper")
    p_port.add_argument("--live-ltp", action="store_true")

    # report daily
    p_rep = sub.add_parser("report", help="Generate daily Indian market intelligence briefing")
    p_rep.add_argument("period", nargs="?", default="daily", choices=["daily"])

    args = parser.parse_args()

    if args.command == "market":
        mod = load_module_fn("trader-intelligence", "market_intelligence.py")
        _emit(mod.get_market_overview(), args.json)
    elif args.command == "scanner":
        mod = load_module_fn("trader-scanner", "scanner.py")
        mode = args.mode.lower()
        tf = args.timeframe or ("5m" if mode == "orb" else "1d")
        strat = "all" if mode == "daily" else mode
        _emit(mod.scan_market(strategy=strat, timeframe=tf, universe=args.universe, limit=args.limit, exchange=args.exchange), args.json)
    elif args.command == "analyse":
        _emit(run_full_analysis_workflow(args.symbol, timeframe=args.timeframe, exchange=args.exchange), args.json)
    elif args.command == "chart":
        pm = get_provider_manager()
        rng = args.range_str or ("5d" if args.timeframe == "1m" else ("1mo" if args.timeframe in {"5m", "15m", "30m"} else ("3mo" if args.timeframe == "1h" else "1y")))
        res = pm.get_candles(args.symbol, interval=args.timeframe, range_str=rng, exchange=args.exchange)
        if res.get("available"):
            res["indicators"] = compute_all_indicators(res["candles"])
        _emit(res, args.json)
    elif args.command == "search":
        _emit({"results": search_symbols(args.query)}, args.json)
    elif args.command == "news":
        mod = load_module_fn("trader-news", "news_analyst.py")
        _emit(mod.fetch_market_news(symbol=args.symbol, limit=args.limit), args.json)
    elif args.command == "entry":
        mod = load_module_fn("trader-entry", "entry_engine.py")
        _emit(mod.evaluate_entry(args.symbol, timeframe=args.timeframe, exchange=args.exchange), args.json)
    elif args.command == "exit":
        mod = load_module_fn("trader-exit", "exit_planner.py")
        _emit(mod.plan_exit(args.symbol, entry_price=args.entry, timeframe=args.timeframe, product=args.product, exchange=args.exchange), args.json)
    elif args.command == "backtest":
        mod = load_module_fn("trader-backtest", "backtester.py")
        _emit(mod.run_backtest(symbol=args.symbol, strategy=args.strategy, timeframe=args.timeframe, initial_capital=args.capital, trade_type=args.trade_type, monte_carlo_runs=args.runs), args.json)
    elif args.command == "fundamentals":
        mod = load_module_fn("trader-analyst", "fundamental_analyst.py")
        _emit(mod.analyze_fundamentals(args.symbol, exchange=args.exchange, include_peers=not args.no_peers), args.json)
    elif args.command == "risk":
        mod = load_module_fn("trader-risk", "risk_engine.py")
        _emit(mod.check_portfolio_risk(), args.json)
    elif args.command == "budget":
        mod = load_module_fn("trader-budget", "position_sizer.py")
        _emit(mod.calculate_position_size(args.capital, args.risk, args.entry, args.sl, segment=args.segment, lot_size=args.lot_size, fno_enabled=args.fno_enabled), args.json)
    elif args.command == "alerts":
        mod = load_module_fn("trader-alerts", "alert_engine.py")
        if args.action == "list":
            _emit({"alerts": mod.list_alerts()}, args.json)
        else:
            _emit(mod.check_alerts(), args.json)
    elif args.command == "portfolio":
        mod = load_module_fn("trader-broker", "broker_executor.py")
        _emit(mod.get_portfolio_summary(broker=args.broker, fetch_ltp=args.live_ltp), args.json)
    elif args.command == "report":
        mod = load_module_fn("trader-intelligence", "market_intelligence.py")
        _emit(mod.get_daily_briefing(), args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
