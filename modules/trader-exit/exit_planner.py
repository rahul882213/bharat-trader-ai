"""Module 4: Quantitative Exit Planner (ATR, Swing Structure, S/R, and Time-Based Exits)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager
from backend.services.indicators import compute_all_indicators

IST = ZoneInfo("Asia/Kolkata")


def plan_exit_from_candles(
    symbol: str,
    candles: List[Dict[str, Any]],
    entry_price: Optional[float] = None,
    side: str = "BUY",
    product: str = "MIS",
    exchange: str = "NSE",
    source: str = "Yahoo Finance (Unofficial)",
) -> Dict[str, Any]:
    if len(candles) < 20:
        return {"available": False, "symbol": normalize_symbol(symbol), "error": "Insufficient candles"}

    ind = compute_all_indicators(candles)
    latest = ind["latest"]
    sr = ind["support_resistance"]
    atr14 = float(latest.get("atr14") or (float(latest["close"]) * 0.015))
    entry = float(entry_price or latest["close"])

    recent_swing_low = min(float(c["low"]) for c in candles[-10:])
    recent_swing_high = max(float(c["high"]) for c in candles[-10:])
    supports = sr.get("supports", [])
    resistances = sr.get("resistances", [])

    if side.upper() == "BUY":
        atr_sl = entry - 1.5 * atr14
        struct_sl = min(recent_swing_low, supports[0]) if supports else recent_swing_low
        # Choose tighter logical SL bounded between 0.8*ATR and 2.5*ATR
        initial_sl = max(min(atr_sl, struct_sl), entry - 2.5 * atr14)
        initial_sl = min(initial_sl, entry - 0.8 * atr14)
        risk = max(entry - initial_sl, 0.5)

        t1 = round(entry + 1.5 * risk, 2)
        t2_struct = resistances[0] if resistances and resistances[0] > entry + 1.8 * risk else (entry + 2.2 * risk)
        t2 = round(max(t2_struct, entry + 2.0 * risk), 2)
        t3 = round(entry + 3.5 * risk, 2)
        trailing_rule = f"Trail stop-loss to breakeven at Target 1 (₹{t1:.2f}); then trail by 1.2x ATR (₹{1.2 * atr14:.2f}) or below EMA(21)."
    else:
        atr_sl = entry + 1.5 * atr14
        struct_sl = max(recent_swing_high, resistances[0]) if resistances else recent_swing_high
        initial_sl = min(max(atr_sl, struct_sl), entry + 2.5 * atr14)
        initial_sl = max(initial_sl, entry + 0.8 * atr14)
        risk = max(initial_sl - entry, 0.5)

        t1 = round(entry - 1.5 * risk, 2)
        t2_struct = supports[0] if supports and supports[0] < entry - 1.8 * risk else (entry - 2.2 * risk)
        t2 = round(min(t2_struct, entry - 2.0 * risk), 2)
        t3 = round(entry - 3.5 * risk, 2)
        trailing_rule = f"Trail stop-loss to breakeven at Target 1 (₹{t1:.2f}); then trail by 1.2x ATR (₹{1.2 * atr14:.2f}) or above EMA(21)."

    initial_sl = round(initial_sl, 2)
    trailing_sl_initial = round(entry - 1.8 * atr14 if side.upper() == "BUY" else entry + 1.8 * atr14, 2)
    rr_t1 = round(abs(t1 - entry) / risk, 2)
    rr_t2 = round(abs(t2 - entry) / risk, 2)
    rr_t3 = round(abs(t3 - entry) / risk, 2)

    time_exit = (
        "Mandatory Intraday MIS square-off at 15:15 IST (15 minutes before NSE/BSE close)."
        if product.upper() == "MIS"
        else "Swing/Delivery CNC review after 10 trading sessions if Target 1 is not reached."
    )

    return {
        "available": True,
        "symbol": normalize_symbol(symbol),
        "exchange": exchange,
        "side": side.upper(),
        "product": product.upper(),
        "entry_price": round(entry, 2),
        "initial_stop_loss": initial_sl,
        "trailing_stop_loss": trailing_sl_initial,
        "trailing_rule": trailing_rule,
        "target_1": t1,
        "target_2": t2,
        "target_3": t3,
        "risk_per_share_inr": round(risk, 2),
        "risk_reward": {
            "target_1_rr": rr_t1,
            "target_2_rr": rr_t2,
            "target_3_rr": rr_t3,
        },
        "atr14": round(atr14, 2),
        "swing_high_10": round(recent_swing_high, 2),
        "swing_low_10": round(recent_swing_low, 2),
        "support_resistance": sr,
        "exit_conditions": [
            f"Hard stop-loss execution at ₹{initial_sl:.2f} (capital protection)",
            f"Book 40% partial profit at Target 1 (₹{t1:.2f}) and move stop to cost",
            f"Book 40% at Target 2 (₹{t2:.2f}); trail remaining 20% toward Target 3 (₹{t3:.2f})",
            "Exit immediately if a full candle closes below VWAP & EMA(21) on heavy volume",
        ],
        "time_based_exit": time_exit,
        "source": source,
        "generated_at_ist": datetime.now(tz=IST).isoformat(),
    }


def plan_exit(
    symbol: str,
    entry_price: Optional[float] = None,
    timeframe: str = "1d",
    side: str = "BUY",
    product: str = "MIS",
    exchange: str = "NSE",
) -> Dict[str, Any]:
    pm = get_provider_manager()
    rng = "1mo" if timeframe in {"5m", "15m", "30m"} else "6mo"
    data = pm.get_candles(symbol, interval=timeframe, range_str=rng, exchange=exchange)
    if not data.get("available"):
        return {"available": False, "symbol": normalize_symbol(symbol), "error": data.get("error", "Unavailable")}
    return plan_exit_from_candles(
        symbol=symbol,
        candles=data["candles"],
        entry_price=entry_price,
        side=side,
        product=product,
        exchange=exchange,
        source=data.get("source", "Yahoo Finance (Unofficial)"),
    )
