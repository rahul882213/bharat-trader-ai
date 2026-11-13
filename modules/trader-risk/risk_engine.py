"""Module 6: Risk Management Engine (Strict INR Capital & Exposure Guardrails)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import get_symbol_sector, normalize_symbol
from backend.database.db import get_kv, query_all, set_kv

IST = ZoneInfo("Asia/Kolkata")
ROOT_DIR = Path(__file__).resolve().parents[2]
RISK_CONFIG_PATH = ROOT_DIR / "config" / "risk_config.json"


def get_risk_config() -> Dict[str, Any]:
    saved = get_kv("risk_config")
    if isinstance(saved, dict):
        return saved
    if RISK_CONFIG_PATH.exists():
        with RISK_CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "total_capital_inr": 1000000.0,
        "max_risk_per_trade_pct": 1.0,
        "max_daily_loss_pct": 3.0,
        "min_risk_reward_ratio": 2.0,
        "max_trades_per_day": 5,
        "max_open_positions": 4,
        "max_sector_exposure_pct": 30.0,
        "max_portfolio_exposure_pct": 80.0,
        "paper_trading_enabled": True,
        "fno_enabled": False,
    }


def update_risk_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    cfg = get_risk_config()
    allowed_keys = {
        "total_capital_inr",
        "max_risk_per_trade_pct",
        "max_daily_loss_pct",
        "min_risk_reward_ratio",
        "max_trades_per_day",
        "max_open_positions",
        "max_sector_exposure_pct",
        "max_portfolio_exposure_pct",
        "paper_trading_enabled",
        "fno_enabled",
    }
    for k, v in updates.items():
        if k in allowed_keys:
            cfg[k] = v
    set_kv("risk_config", cfg, datetime.now(tz=IST).isoformat())
    return cfg


def check_portfolio_risk() -> Dict[str, Any]:
    cfg = get_risk_config()
    capital = float(cfg.get("total_capital_inr", 1000000.0))
    today_str = datetime.now(tz=IST).strftime("%Y-%m-%d")

    positions = query_all("SELECT * FROM paper_positions")
    orders_today = query_all("SELECT * FROM paper_orders WHERE created_at LIKE ?", (f"{today_str}%",))
    trades_today = query_all("SELECT * FROM trade_journal WHERE closed_at LIKE ?", (f"{today_str}%",))

    daily_realized_pnl = sum(float(t.get("net_pnl", 0.0)) for t in trades_today)
    total_exposure_inr = sum(float(p["avg_price"]) * int(p["quantity"]) for p in positions)
    sector_exposure: Dict[str, float] = {}
    for p in positions:
        sec = p.get("sector") or get_symbol_sector(p["symbol"])
        val = float(p["avg_price"]) * int(p["quantity"])
        sector_exposure[sec] = round(sector_exposure.get(sec, 0.0) + val, 2)

    max_daily_loss_inr = capital * (float(cfg.get("max_daily_loss_pct", 3.0)) / 100.0)
    daily_loss_used_inr = max(0.0, -daily_realized_pnl)
    daily_loss_breached = daily_loss_used_inr >= max_daily_loss_inr

    return {
        "currency": "INR",
        "total_capital_inr": round(capital, 2),
        "max_risk_per_trade_inr": round(capital * (float(cfg.get("max_risk_per_trade_pct", 1.0)) / 100.0), 2),
        "max_daily_loss_inr": round(max_daily_loss_inr, 2),
        "daily_realized_pnl_inr": round(daily_realized_pnl, 2),
        "daily_loss_remaining_inr": round(max(0.0, max_daily_loss_inr - daily_loss_used_inr), 2),
        "daily_loss_breached": daily_loss_breached,
        "trades_today": len(orders_today),
        "max_trades_per_day": int(cfg.get("max_trades_per_day", 5)),
        "open_positions_count": len(positions),
        "max_open_positions": int(cfg.get("max_open_positions", 4)),
        "total_exposure_inr": round(total_exposure_inr, 2),
        "portfolio_exposure_pct": round((total_exposure_inr / capital) * 100.0, 2) if capital > 0 else 0.0,
        "max_portfolio_exposure_pct": float(cfg.get("max_portfolio_exposure_pct", 80.0)),
        "sector_exposure_inr": sector_exposure,
        "max_sector_exposure_pct": float(cfg.get("max_sector_exposure_pct", 30.0)),
        "min_risk_reward_ratio": float(cfg.get("min_risk_reward_ratio", 2.0)),
        "status": "BLOCKED" if daily_loss_breached else "NOMINAL",
        "config": cfg,
        "checked_at_ist": datetime.now(tz=IST).isoformat(),
    }


def evaluate_trade_risk(
    symbol: str,
    entry_price: float,
    stop_loss: float,
    target_price: float,
    quantity: int,
    sector: Optional[str] = None,
    charges_inr: float = 0.0,
) -> Dict[str, Any]:
    state = check_portfolio_risk()
    cfg = state["config"]
    capital = float(cfg.get("total_capital_inr", 1000000.0))
    sec = sector or get_symbol_sector(symbol)

    risk_per_share = abs(entry_price - stop_loss)
    reward_per_share = abs(target_price - entry_price)
    rr_ratio = round(reward_per_share / risk_per_share, 2) if risk_per_share > 0 else 0.0
    trade_risk_inr = round(risk_per_share * quantity + charges_inr, 2)
    trade_value_inr = round(entry_price * quantity, 2)

    violations: List[str] = []
    checks: List[Dict[str, Any]] = []

    # 1. Per-trade risk check
    max_trade_risk = state["max_risk_per_trade_inr"]
    ok_risk = trade_risk_inr <= max_trade_risk * 1.005  # tiny rounding tolerance
    checks.append({
        "rule": "Max Risk Per Trade",
        "passed": ok_risk,
        "actual": f"₹{trade_risk_inr:,.2f}",
        "limit": f"₹{max_trade_risk:,.2f} ({cfg.get('max_risk_per_trade_pct')}%)",
    })
    if not ok_risk:
        violations.append(f"Trade risk ₹{trade_risk_inr:,.2f} exceeds per-trade limit ₹{max_trade_risk:,.2f}.")

    # 2. Daily loss limit check
    ok_daily = not state["daily_loss_breached"]
    checks.append({
        "rule": "Max Daily Loss",
        "passed": ok_daily,
        "actual": f"₹{abs(min(0.0, state['daily_realized_pnl_inr'])):,.2f}",
        "limit": f"₹{state['max_daily_loss_inr']:,.2f} ({cfg.get('max_daily_loss_pct')}%)",
    })
    if not ok_daily:
        violations.append("Maximum daily loss limit breached; new entries blocked.")

    # 3. Minimum R:R check
    min_rr = float(cfg.get("min_risk_reward_ratio", 2.0))
    ok_rr = rr_ratio >= min_rr
    checks.append({
        "rule": "Minimum Risk-to-Reward",
        "passed": ok_rr,
        "actual": f"1:{rr_ratio:.2f}",
        "limit": f"1:{min_rr:.2f}",
    })
    if not ok_rr:
        violations.append(f"Risk-to-Reward 1:{rr_ratio:.2f} is below required 1:{min_rr:.2f}.")

    # 4. Max trades/day
    ok_trades = state["trades_today"] < state["max_trades_per_day"]
    checks.append({
        "rule": "Max Trades Per Day",
        "passed": ok_trades,
        "actual": str(state["trades_today"]),
        "limit": str(state["max_trades_per_day"]),
    })
    if not ok_trades:
        violations.append(f"Daily trade cap ({state['max_trades_per_day']}) reached.")

    # 5. Max open positions
    ok_pos = state["open_positions_count"] < state["max_open_positions"]
    checks.append({
        "rule": "Max Open Positions",
        "passed": ok_pos,
        "actual": str(state["open_positions_count"]),
        "limit": str(state["max_open_positions"]),
    })
    if not ok_pos:
        violations.append(f"Max open positions ({state['max_open_positions']}) reached.")

    # 6. Sector exposure
    cur_sec_exp = state["sector_exposure_inr"].get(sec, 0.0)
    new_sec_pct = ((cur_sec_exp + trade_value_inr) / capital) * 100.0 if capital > 0 else 100.0
    max_sec_pct = float(cfg.get("max_sector_exposure_pct", 30.0))
    ok_sec = new_sec_pct <= max_sec_pct
    checks.append({
        "rule": f"Sector Exposure ({sec})",
        "passed": ok_sec,
        "actual": f"{new_sec_pct:.1f}%",
        "limit": f"{max_sec_pct:.1f}%",
    })
    if not ok_sec:
        violations.append(f"Sector exposure for {sec} ({new_sec_pct:.1f}%) exceeds {max_sec_pct:.1f}%.")

    # 7. Total portfolio exposure
    new_port_pct = ((state["total_exposure_inr"] + trade_value_inr) / capital) * 100.0 if capital > 0 else 100.0
    max_port_pct = float(cfg.get("max_portfolio_exposure_pct", 80.0))
    ok_port = new_port_pct <= max_port_pct
    checks.append({
        "rule": "Total Portfolio Exposure",
        "passed": ok_port,
        "actual": f"{new_port_pct:.1f}%",
        "limit": f"{max_port_pct:.1f}%",
    })
    if not ok_port:
        violations.append(f"Portfolio exposure ({new_port_pct:.1f}%) exceeds {max_port_pct:.1f}%.")

    verdict = "PASS" if not violations else "BLOCK"
    return {
        "symbol": normalize_symbol(symbol),
        "verdict": verdict,
        "trade_risk_inr": trade_risk_inr,
        "trade_value_inr": trade_value_inr,
        "risk_reward_ratio": rr_ratio,
        "checks": checks,
        "violations": violations,
        "portfolio_state": state,
    }
