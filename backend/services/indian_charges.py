"""Indian Equity & F&O Statutory Brokerage and Transaction Cost Calculator (INR)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

RISK_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "risk_config.json"


def _load_profiles() -> Dict[str, Any]:
    if RISK_CONFIG_PATH.exists():
        with RISK_CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f).get("charge_profiles", {})
    return {}


def calculate_indian_charges(
    buy_price: float,
    sell_price: float,
    quantity: int,
    trade_type: str = "equity_intraday",
    broker: str = "zerodha",
    exchange: str = "NSE",
) -> Dict[str, float]:
    """
    Calculate complete Indian statutory taxes & brokerage for a round-trip trade.
    trade_type: 'equity_intraday' | 'equity_delivery' | 'fno_futures'
    """
    if quantity <= 0 or buy_price <= 0 or sell_price <= 0:
        return {
            "buy_value": 0.0,
            "sell_value": 0.0,
            "turnover": 0.0,
            "brokerage": 0.0,
            "stt": 0.0,
            "exchange_txn_charge": 0.0,
            "sebi_charges": 0.0,
            "stamp_duty": 0.0,
            "gst": 0.0,
            "total_charges": 0.0,
            "breakeven_points": 0.0,
            "net_pnl": 0.0,
        }

    buy_val = buy_price * quantity
    sell_val = sell_price * quantity
    turnover = buy_val + sell_val

    profiles = _load_profiles()
    profile_key = f"zerodha_{trade_type}"
    profile = profiles.get(profile_key, {})

    if trade_type == "equity_delivery":
        # Zerodha / discount brokers: ₹0 delivery brokerage; traditional ~0.1%
        if broker.lower() in {"zerodha", "dhan", "upstox", "angel"}:
            brok_buy = 0.0
            brok_sell = 0.0
        else:
            brok_buy = buy_val * 0.001
            brok_sell = sell_val * 0.001
        brokerage = brok_buy + brok_sell
        stt = round(turnover * float(profile.get("stt_buy_sell_pct", 0.001)))
        exch_rate = 0.0000297 if exchange.upper() == "NSE" else 0.0000375
        exchange_txn = turnover * exch_rate
        sebi_charges = turnover * float(profile.get("sebi_fee_pct", 0.000001))
        stamp_duty = round(buy_val * float(profile.get("stamp_duty_buy_pct", 0.00015)))
    elif trade_type == "fno_futures":
        flat = float(profile.get("brokerage_flat_per_order_inr", 20.0))
        brokerage = flat * 2.0
        stt = round(sell_val * float(profile.get("stt_sell_pct", 0.0002)))
        exch_rate = 0.0000173 if exchange.upper() == "NSE" else 0.0000173
        exchange_txn = turnover * exch_rate
        sebi_charges = turnover * float(profile.get("sebi_fee_pct", 0.000001))
        stamp_duty = round(buy_val * float(profile.get("stamp_duty_buy_pct", 0.00002)))
    else:  # equity_intraday (MIS)
        rate = float(profile.get("brokerage_pct", 0.0003))
        cap = float(profile.get("brokerage_max_per_order_inr", 20.0))
        brok_buy = min(buy_val * rate, cap)
        brok_sell = min(sell_val * rate, cap)
        brokerage = brok_buy + brok_sell
        stt = round(sell_val * float(profile.get("stt_sell_pct", 0.00025)))
        exch_rate = 0.0000297 if exchange.upper() == "NSE" else 0.0000375
        exchange_txn = turnover * exch_rate
        sebi_charges = turnover * float(profile.get("sebi_fee_pct", 0.000001))
        stamp_duty = round(buy_val * float(profile.get("stamp_duty_buy_pct", 0.00003)))

    gst = (brokerage + exchange_txn + sebi_charges) * float(profile.get("gst_pct", 0.18))
    total_charges = brokerage + stt + exchange_txn + sebi_charges + stamp_duty + gst
    gross_pnl = sell_val - buy_val
    net_pnl = gross_pnl - total_charges

    return {
        "buy_value": round(buy_val, 2),
        "sell_value": round(sell_val, 2),
        "turnover": round(turnover, 2),
        "brokerage": round(brokerage, 2),
        "stt": round(float(stt), 2),
        "exchange_txn_charge": round(exchange_txn, 2),
        "sebi_charges": round(sebi_charges, 2),
        "stamp_duty": round(float(stamp_duty), 2),
        "gst": round(gst, 2),
        "total_charges": round(total_charges, 2),
        "breakeven_points": round(total_charges / quantity, 2),
        "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(net_pnl, 2),
    }
