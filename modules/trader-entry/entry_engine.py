"""Module 3: Entry Timing Engine (Strict Completed-Candle Breakout Validation)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager
from backend.services.indicators import compute_all_indicators
from backend.services.market_calendar import get_market_status

IST = ZoneInfo("Asia/Kolkata")


def evaluate_entry_from_candles(
    symbol: str,
    candles: List[Dict[str, Any]],
    timeframe: str = "15m",
    is_live_session: bool = False,
    exchange: str = "NSE",
    source: str = "Yahoo Finance (Unofficial)",
) -> Dict[str, Any]:
    """
    Evaluate entry timing strictly using completed candles when market is live.
    Outputs: WAIT / WATCH / ENTRY TRIGGERED / SETUP INVALIDATED
    """
    if len(candles) < 25:
        return {
            "available": False,
            "symbol": normalize_symbol(symbol),
            "status": "WAIT",
            "reason": "Insufficient completed candle history (minimum 25 bars required).",
        }

    # CRITICAL RULE: Never declare a breakout based on an incomplete forming candle.
    # When market is open, exclude the current forming bar (candles[-1]) from breakout confirmation.
    confirmed_candles = candles[:-1] if is_live_session and len(candles) > 26 else candles
    forming_candle = candles[-1] if is_live_session and len(candles) > 26 else None

    ind = compute_all_indicators(confirmed_candles)
    latest = ind["latest"]
    sr = ind["support_resistance"]
    c_conf = confirmed_candles[-1]
    c_prev = confirmed_candles[-2]

    close = float(c_conf["close"])
    open_p = float(c_conf["open"])
    high = float(c_conf["high"])
    low = float(c_conf["low"])
    prev_high = float(c_prev["high"])
    prev_low = float(c_prev["low"])

    ema9 = latest.get("ema9") or close
    ema21 = latest.get("ema21") or close
    ema50 = latest.get("ema50") or close
    vwap_val = latest.get("vwap") or close
    rsi14 = latest.get("rsi14") or 50.0
    vol_ratio = latest.get("volume_ratio") or 1.0
    atr14 = latest.get("atr14") or (close * 0.015)

    supports = sr.get("supports", [round(close - 1.5 * atr14, 2)])
    resistances = sr.get("resistances", [round(close + 2.5 * atr14, 2)])
    nearest_sup = supports[0] if supports else round(close - 1.5 * atr14, 2)
    nearest_res = resistances[0] if resistances else round(close + 2.5 * atr14, 2)

    vwap_above = close > vwap_val
    ema_bullish = ema9 > ema21 and close > ema21
    ema_full_aligned = ema9 > ema21 > ema50
    vol_confirmed = vol_ratio >= 1.3
    bullish_candle = close > open_p and close > prev_high * 0.998

    # Preliminary stop & target for R:R check
    sl_ref = min(nearest_sup, round(close - 1.5 * atr14, 2))
    risk = max(close - sl_ref, atr14 * 0.5)
    target_ref = max(nearest_res, round(close + 2.2 * risk, 2))
    rr_ratio = round((target_ref - close) / risk, 2) if risk > 0 else 0.0

    # Determine status
    if close < ema50 * 0.985 and close < vwap_val * 0.992 and rsi14 < 40:
        status = "SETUP INVALIDATED"
        ideal_entry = None
        summary = "Price broke below VWAP and EMA(50) with weak momentum; long setup invalidated."
    elif vwap_above and ema_bullish and bullish_candle and vol_confirmed and 45 <= rsi14 <= 75 and rr_ratio >= 1.8:
        status = "ENTRY TRIGGERED"
        ideal_entry = round(close, 2)
        summary = (
            f"Completed confirmation candle closed at ₹{close:.2f} above VWAP (₹{vwap_val:.2f}) "
            f"with {vol_ratio:.2f}x volume and bullish EMA alignment."
        )
    elif (vwap_above or ema9 > ema21) and rsi14 <= 78:
        status = "WATCH"
        ideal_entry = round(max(close, vwap_val, prev_high), 2)
        missing = []
        if not vol_confirmed:
            missing.append(f"volume expansion (currently {vol_ratio:.2f}x < 1.30x)")
        if not bullish_candle:
            missing.append("strong bullish candle close above prior high")
        if not vwap_above:
            missing.append(f"reclaim above VWAP ₹{vwap_val:.2f}")
        summary = "Setup developing; awaiting " + (", ".join(missing) if missing else "next completed confirmation bar.")
    else:
        status = "WAIT"
        ideal_entry = round(max(vwap_val, ema21), 2)
        summary = "No confirmed trend or VWAP/EMA alignment yet; remain on sidelines."

    return {
        "available": True,
        "symbol": normalize_symbol(symbol),
        "exchange": exchange,
        "timeframe": timeframe,
        "status": status,
        "ideal_entry_price": ideal_entry,
        "confirmation_candle": {
            "date": c_conf.get("date"),
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": int(c_conf.get("volume", 0)),
            "is_complete_candle": True,
        },
        "forming_candle_ignored_for_breakout": forming_candle is not None,
        "live_forming_price": float(forming_candle["close"]) if forming_candle else close,
        "checks": {
            "vwap_position": "ABOVE" if vwap_above else "BELOW",
            "vwap_value": round(vwap_val, 2),
            "ema_alignment": "STRONG_BULLISH (9>21>50)" if ema_full_aligned else ("BULLISH (9>21)" if ema_bullish else "BEARISH/MIXED"),
            "ema9": round(ema9, 2),
            "ema21": round(ema21, 2),
            "ema50": round(ema50, 2),
            "volume_confirmation": vol_confirmed,
            "volume_ratio": vol_ratio,
            "rsi14": round(rsi14, 2),
            "atr14": round(atr14, 2),
        },
        "support_resistance": sr,
        "preliminary_rr_ratio": rr_ratio,
        "summary": summary,
        "source": source,
        "evaluated_at_ist": datetime.now(tz=IST).isoformat(),
    }


def evaluate_entry(symbol: str, timeframe: str = "15m", exchange: str = "NSE") -> Dict[str, Any]:
    pm = get_provider_manager()
    rng = "5d" if timeframe == "1m" else ("1mo" if timeframe in {"5m", "15m", "30m"} else ("3mo" if timeframe == "1h" else "1y"))
    data = pm.get_candles(symbol, interval=timeframe, range_str=rng, exchange=exchange)
    if not data.get("available"):
        return {
            "available": False,
            "symbol": normalize_symbol(symbol),
            "status": "WAIT",
            "error": data.get("error", "Market data unavailable"),
        }
    mkt = get_market_status()
    return evaluate_entry_from_candles(
        symbol=symbol,
        candles=data["candles"],
        timeframe=timeframe,
        is_live_session=bool(mkt.get("is_market_open")),
        exchange=exchange,
        source=data.get("source", "Yahoo Finance (Unofficial)"),
    )
