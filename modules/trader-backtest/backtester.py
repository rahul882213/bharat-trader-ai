"""Module 5: Historical Backtesting Engine with Indian Charges & 10,000 Monte Carlo Simulations."""
from __future__ import annotations

import math
import random
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager
from backend.services.indian_charges import calculate_indian_charges
from backend.services.indicators import atr, ema, macd, rsi, session_vwap

IST = ZoneInfo("Asia/Kolkata")


def _run_monte_carlo(trade_pnls: List[float], initial_capital: float, iterations: int = 10000, seed: int = 42) -> Dict[str, Any]:
    if not trade_pnls:
        return {
            "iterations": 0,
            "disclaimer": "No historical trades generated; Monte Carlo simulation skipped.",
            "percentiles_inr": {},
        }
    rng = random.Random(seed)
    n = len(trade_pnls)
    finals: List[float] = []
    max_dds: List[float] = []

    for _ in range(iterations):
        eq = initial_capital
        peak = initial_capital
        max_dd = 0.0
        for _t in range(n):
            pnl = trade_pnls[rng.randrange(n)]
            eq += pnl
            if eq > peak:
                peak = eq
            dd = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        finals.append(eq)
        max_dds.append(max_dd)

    finals.sort()
    max_dds.sort()

    def pct(arr: List[float], p: float) -> float:
        idx = min(max(int(p * (len(arr) - 1)), 0), len(arr) - 1)
        return round(arr[idx], 2)

    profitable_runs = sum(1 for x in finals if x > initial_capital)
    # Build histogram buckets (12 bins) for UI visualization
    low_v, high_v = finals[0], finals[-1]
    span = max(high_v - low_v, 1.0)
    bins = 12
    step = span / bins
    hist = []
    for b in range(bins):
        b_start = low_v + b * step
        b_end = b_start + step
        count = sum(1 for v in finals if (b_start <= v < b_end) or (b == bins - 1 and v == high_v))
        hist.append({
            "range_label": f"₹{round(b_start/100000, 2)}L",
            "min_equity": round(b_start, 2),
            "max_equity": round(b_end, 2),
            "runs": count,
        })

    return {
        "iterations": iterations,
        "disclaimer": (
            "STATISTICAL SIMULATION ONLY: Monte Carlo results reflect bootstrap resampling of "
            "past backtested trade outcomes and are NOT guaranteed future predictions."
        ),
        "probability_of_profit_pct": round((profitable_runs / iterations) * 100.0, 2),
        "percentiles_inr": {
            "p5": pct(finals, 0.05),
            "p25": pct(finals, 0.25),
            "median_p50": pct(finals, 0.50),
            "p75": pct(finals, 0.75),
            "p95": pct(finals, 0.95),
        },
        "drawdown_95th_pct": pct(max_dds, 0.95),
        "median_drawdown_pct": pct(max_dds, 0.50),
        "distribution_histogram": hist,
    }


def run_backtest_on_candles(
    symbol: str,
    candles: List[Dict[str, Any]],
    strategy: str = "ema_crossover",
    timeframe: str = "1d",
    initial_capital: float = 1000000.0,
    risk_per_trade_pct: float = 1.0,
    trade_type: str = "equity_intraday",
    broker: str = "zerodha",
    monte_carlo_runs: int = 10000,
    source: str = "Yahoo Finance (Unofficial)",
) -> Dict[str, Any]:
    """
    Walk-forward bar-by-bar backtester (no look-ahead bias: signals computed on bar i close,
    execution at bar i+1 open, exits checked strictly on subsequent bars).
    """
    if len(candles) < 35:
        return {
            "available": False,
            "symbol": normalize_symbol(symbol),
            "error": "Insufficient historical candles (minimum 35 bars required for backtest).",
        }

    closes = [float(c["close"]) for c in candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    macd_line, sig_line, _ = macd(closes)
    vwap_line = session_vwap(candles)
    atr14 = atr(candles, 14)

    strat = strategy.lower().strip().replace("-", "_")
    capital = float(initial_capital)
    peak_equity = capital
    max_dd_pct = 0.0
    max_dd_inr = 0.0

    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = [
        {"date": candles[25].get("date"), "equity": round(capital, 2)}
    ]

    in_pos = False
    entry_price = 0.0
    sl_price = 0.0
    target_price = 0.0
    qty = 0
    entry_date = ""
    pending_signal = False
    pending_atr = 0.0

    for i in range(25, len(candles)):
        c = candles[i]
        o, h, l, cl = float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])
        dt = str(c.get("date"))

        # Execute pending entry strictly at bar i open (no look-ahead!)
        if pending_signal and not in_pos and o > 0:
            risk_budget = capital * (risk_per_trade_pct / 100.0)
            stop_dist = max(1.5 * pending_atr, o * 0.008)
            raw_qty = int(risk_budget // stop_dist)
            max_afford = int((capital * 0.95) // o)
            qty = max(min(raw_qty, max_afford), 0)
            if qty > 0:
                in_pos = True
                entry_price = o
                sl_price = round(entry_price - stop_dist, 2)
                target_price = round(entry_price + 2.2 * stop_dist, 2)
                entry_date = dt
            pending_signal = False

        # Manage active position intra-bar (conservative: SL checked before Target if both hit in same bar)
        if in_pos:
            exit_price: Optional[float] = None
            exit_reason = ""
            if l <= sl_price:
                exit_price = sl_price
                exit_reason = "Stop-Loss"
            elif h >= target_price:
                exit_price = target_price
                exit_reason = "Target (2.2R)"
            elif i == len(candles) - 1:
                exit_price = cl
                exit_reason = "End of Window"

            if exit_price is not None:
                charges = calculate_indian_charges(
                    buy_price=entry_price,
                    sell_price=exit_price,
                    quantity=qty,
                    trade_type=trade_type,
                    broker=broker,
                )
                net_pnl = charges["net_pnl"]
                capital += net_pnl
                if capital > peak_equity:
                    peak_equity = capital
                dd_inr = peak_equity - capital
                dd_pct = (dd_inr / peak_equity) * 100.0 if peak_equity > 0 else 0.0
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct
                if dd_inr > max_dd_inr:
                    max_dd_inr = dd_inr

                trades.append({
                    "entry_date": entry_date,
                    "exit_date": dt,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "stop_loss": sl_price,
                    "target": target_price,
                    "quantity": qty,
                    "gross_pnl": charges["gross_pnl"],
                    "charges_inr": charges["total_charges"],
                    "net_pnl": net_pnl,
                    "exit_reason": exit_reason,
                })
                equity_curve.append({"date": dt, "equity": round(capital, 2)})
                in_pos = False
                continue

        # Evaluate entry signal on completed bar i for execution on bar i+1
        if not in_pos and i < len(candles) - 1:
            e9, e21 = ema9[i], ema21[i]
            e9_p, e21_p = ema9[i - 1], ema21[i - 1]
            r_cur, r_prev = rsi14[i], rsi14[i - 1]
            m_cur, s_cur = macd_line[i], sig_line[i]
            m_prev, s_prev = macd_line[i - 1], sig_line[i - 1]
            vw = vwap_line[i]
            vw_p = vwap_line[i - 1]
            cur_atr = atr14[i] or (cl * 0.015)

            trig = False
            if strat in {"ema_crossover", "ema"} and all(x is not None for x in (e9, e21, e9_p, e21_p)):
                trig = (e9_p <= e21_p) and (e9 > e21)
            elif strat in {"vwap_breakout", "vwap"} and vw is not None and vw_p is not None:
                trig = (float(candles[i - 1]["close"]) <= vw_p) and (cl > vw)
            elif strat in {"rsi_reversal", "rsi_oversold", "rsi"} and r_cur is not None and r_prev is not None:
                trig = (r_prev < 38.0) and (r_cur > r_prev) and (cl > o)
            elif strat in {"macd_crossover", "macd"} and all(x is not None for x in (m_cur, s_cur, m_prev, s_prev)):
                trig = (m_prev <= s_prev) and (m_cur > s_cur)
            elif strat == "orb":
                prev_3h = max(float(candles[j]["high"]) for j in range(max(0, i - 3), i))
                trig = cl > prev_3h and cl > o
            else:
                # Default composite momentum setup
                if e9 is not None and e21 is not None and r_cur is not None:
                    trig = (e9 > e21) and (50.0 <= r_cur <= 70.0) and (cl > float(candles[i - 1]["high"]))

            if trig:
                pending_signal = True
                pending_atr = float(cur_atr)

    total_trades = len(trades)
    wins = [t["net_pnl"] for t in trades if t["net_pnl"] > 0]
    losses = [t["net_pnl"] for t in trades if t["net_pnl"] <= 0]
    win_rate = round((len(wins) / total_trades) * 100.0, 2) if total_trades > 0 else 0.0
    sum_wins = sum(wins)
    sum_losses = abs(sum(losses))
    profit_factor = round(sum_wins / sum_losses, 2) if sum_losses > 0 else (round(sum_wins, 2) if sum_wins > 0 else 0.0)
    avg_win = round(sum_wins / len(wins), 2) if wins else 0.0
    avg_loss = round(-sum_losses / len(losses), 2) if losses else 0.0
    expectancy = round(sum(t["net_pnl"] for t in trades) / total_trades, 2) if total_trades > 0 else 0.0
    total_charges = round(sum(t["charges_inr"] for t in trades), 2)
    net_profit = round(capital - initial_capital, 2)

    # Consecutive losses
    max_consec_losses = 0
    cur_consec = 0
    for t in trades:
        if t["net_pnl"] <= 0:
            cur_consec += 1
            max_consec_losses = max(max_consec_losses, cur_consec)
        else:
            cur_consec = 0

    # Annualized Sharpe Ratio from per-trade returns
    sharpe = 0.0
    if total_trades >= 2:
        rets = [t["net_pnl"] / initial_capital for t in trades]
        mean_r = sum(rets) / len(rets)
        var_r = sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)
        std_r = math.sqrt(var_r)
        if std_r > 0:
            trades_per_year = max(total_trades, 12)
            sharpe = round((mean_r / std_r) * math.sqrt(trades_per_year), 2)

    mc = _run_monte_carlo(
        [t["net_pnl"] for t in trades],
        initial_capital=initial_capital,
        iterations=max(100, min(monte_carlo_runs, 20000)),
    )

    return {
        "available": True,
        "symbol": normalize_symbol(symbol),
        "strategy": strategy,
        "timeframe": timeframe,
        "trade_type": trade_type,
        "broker": broker,
        "currency": "INR",
        "initial_capital": round(initial_capital, 2),
        "final_capital": round(capital, 2),
        "net_pnl": net_profit,
        "return_pct": round((net_profit / initial_capital) * 100.0, 2),
        "metrics": {
            "total_trades": total_trades,
            "win_rate_pct": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_pct": round(max_dd_pct, 2),
            "max_drawdown_inr": round(max_dd_inr, 2),
            "avg_winning_trade_inr": avg_win,
            "avg_losing_trade_inr": avg_loss,
            "expectancy_inr": expectancy,
            "sharpe_ratio": sharpe,
            "max_consecutive_losses": max_consec_losses,
            "total_charges_inr": total_charges,
        },
        "bias_controls": {
            "look_ahead_bias_prevented": True,
            "execution_rule": "Signal evaluated on closed bar T; order filled strictly at bar T+1 open; intra-bar SL checked prior to Target.",
            "survivorship_bias_notice": "Historical test runs on currently listed symbol; survivorship bias may apply for long-horizon universe studies.",
        },
        "monte_carlo": mc,
        "equity_curve": equity_curve,
        "trades": trades[-50:],
        "source": source,
        "generated_at_ist": datetime.now(tz=IST).isoformat(),
    }


def run_backtest(
    symbol: str,
    strategy: str = "ema_crossover",
    timeframe: str = "1d",
    range_str: Optional[str] = None,
    initial_capital: float = 1000000.0,
    risk_per_trade_pct: float = 1.0,
    trade_type: str = "equity_intraday",
    broker: str = "zerodha",
    monte_carlo_runs: int = 10000,
    exchange: str = "NSE",
) -> Dict[str, Any]:
    pm = get_provider_manager()
    rng = range_str or ("1mo" if timeframe in {"5m", "15m", "30m"} else ("3mo" if timeframe == "1h" else "2y"))
    data = pm.get_candles(symbol, interval=timeframe, range_str=rng, exchange=exchange)
    if not data.get("available"):
        return {
            "available": False,
            "symbol": normalize_symbol(symbol),
            "error": data.get("error", "Historical data unavailable."),
        }
    res = run_backtest_on_candles(
        symbol=symbol,
        candles=data["candles"],
        strategy=strategy,
        timeframe=timeframe,
        initial_capital=initial_capital,
        risk_per_trade_pct=risk_per_trade_pct,
        trade_type=trade_type,
        broker=broker,
        monte_carlo_runs=monte_carlo_runs,
        source=data.get("source", "Yahoo Finance (Unofficial)"),
    )
    if res.get("available"):
        try:
            import json as _json
            import uuid as _uuid
            from backend.database.db import execute_sql

            m = res.get("metrics", {})
            bt_id = f"BT-{_uuid.uuid4().hex[:10].upper()}"
            execute_sql(
                """
                INSERT INTO backtest_results
                (backtest_id, stock_id, symbol, strategy, timeframe, trade_type,
                 initial_capital, final_capital, net_pnl, win_rate_pct, sharpe_ratio,
                 max_drawdown_pct, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bt_id,
                    (data.get("stock_meta") or {}).get("stock_id"),
                    res["symbol"],
                    strategy,
                    timeframe,
                    trade_type,
                    res["initial_capital"],
                    res["final_capital"],
                    res["net_pnl"],
                    m.get("win_rate_pct", 0.0),
                    m.get("sharpe_ratio", 0.0),
                    m.get("max_drawdown_pct", 0.0),
                    _json.dumps(res),
                    res["generated_at_ist"],
                ),
            )
        except Exception:
            pass
    return res
