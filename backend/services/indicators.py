"""Quantitative Technical Indicators & Pattern Recognition (Pure Python, Zero Mandatory C-Deps)."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def sma(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    running = sum(values[:period])
    out[period - 1] = running / period
    for i in range(period, len(values)):
        running += values[i] - values[i - period]
        out[i] = running / period
    return out


def ema(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        val = values[i] * k + prev * (1.0 - k)
        out[i] = val
        prev = val
    return out


def rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        g = max(diff, 0.0)
        l = max(-diff, 0.0)
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))
    return out


def macd(
    closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line: List[Optional[float]] = [None] * len(closes)
    valid_vals: List[float] = []
    valid_indices: List[int] = []
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            val = float(ema_fast[i]) - float(ema_slow[i])
            macd_line[i] = val
            valid_vals.append(val)
            valid_indices.append(i)
    sig_line: List[Optional[float]] = [None] * len(closes)
    hist: List[Optional[float]] = [None] * len(closes)
    sig_vals = ema(valid_vals, signal)
    for idx_pos, orig_idx in enumerate(valid_indices):
        if sig_vals[idx_pos] is not None:
            sig_line[orig_idx] = sig_vals[idx_pos]
            if macd_line[orig_idx] is not None:
                hist[orig_idx] = float(macd_line[orig_idx]) - float(sig_vals[idx_pos])
    return macd_line, sig_line, hist


def bollinger_bands(
    closes: List[float], period: int = 20, num_std: float = 2.0
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    mid = sma(closes, period)
    upper: List[Optional[float]] = [None] * len(closes)
    lower: List[Optional[float]] = [None] * len(closes)
    bandwidth: List[Optional[float]] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        m = mid[i]
        if m is None:
            continue
        window = closes[i - period + 1 : i + 1]
        var = sum((x - m) ** 2 for x in window) / period
        sd = math.sqrt(var)
        u = m + num_std * sd
        l = m - num_std * sd
        upper[i] = u
        lower[i] = l
        bandwidth[i] = ((u - l) / m * 100.0) if m > 0 else 0.0
    return upper, mid, lower, bandwidth


def atr(candles: List[Dict[str, Any]], period: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(candles)
    if len(candles) <= period:
        return out
    trs: List[float] = []
    for i, c in enumerate(candles):
        h = float(c["high"])
        l = float(c["low"])
        if i == 0:
            trs.append(h - l)
        else:
            pc = float(candles[i - 1]["close"])
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    first_atr = sum(trs[1 : period + 1]) / period
    out[period] = first_atr
    prev = first_atr
    for i in range(period + 1, len(candles)):
        val = (prev * (period - 1) + trs[i]) / period
        out[i] = val
        prev = val
    return out


def session_vwap(candles: List[Dict[str, Any]]) -> List[Optional[float]]:
    """Compute VWAP anchored per IST calendar date (resets each trading day for intraday)."""
    out: List[Optional[float]] = []
    cum_pv = 0.0
    cum_vol = 0.0
    last_day: Optional[str] = None
    for c in candles:
        ts_str = str(c.get("date") or c.get("time") or "")
        day_key = ts_str[:10] if len(ts_str) >= 10 else "all"
        if last_day is not None and day_key != last_day:
            cum_pv = 0.0
            cum_vol = 0.0
        last_day = day_key
        tp = (float(c["high"]) + float(c["low"]) + float(c["close"])) / 3.0
        vol = max(float(c.get("volume", 0.0)), 0.0)
        cum_pv += tp * vol
        cum_vol += vol
        out.append((cum_pv / cum_vol) if cum_vol > 0 else tp)
    return out


def support_resistance_levels(candles: List[Dict[str, Any]], lookback: int = 60) -> Dict[str, List[float]]:
    window = candles[-lookback:] if len(candles) > lookback else candles
    if len(window) < 5:
        return {"supports": [], "resistances": [], "pivot": 0.0}
    swing_highs: List[float] = []
    swing_lows: List[float] = []
    for i in range(2, len(window) - 2):
        h = float(window[i]["high"])
        l = float(window[i]["low"])
        if h > float(window[i - 1]["high"]) and h > float(window[i - 2]["high"]) and h >= float(window[i + 1]["high"]) and h >= float(window[i + 2]["high"]):
            swing_highs.append(round(h, 2))
        if l < float(window[i - 1]["low"]) and l < float(window[i - 2]["low"]) and l <= float(window[i + 1]["low"]) and l <= float(window[i + 2]["low"]):
            swing_lows.append(round(l, 2))

    last_close = float(window[-1]["close"])
    supports = sorted({s for s in swing_lows if s <= last_close}, reverse=True)[:3]
    resistances = sorted({r for r in swing_highs if r >= last_close})[:3]

    # Standard floor pivot from latest completed bar
    prev = window[-2] if len(window) >= 2 else window[-1]
    ph, pl, pc = float(prev["high"]), float(prev["low"]), float(prev["close"])
    pivot = round((ph + pl + pc) / 3.0, 2)
    if not supports:
        supports = [round(2 * pivot - ph, 2), round(pivot - (ph - pl), 2)]
    if not resistances:
        resistances = [round(2 * pivot - pl, 2), round(pivot + (ph - pl), 2)]
    return {"supports": supports, "resistances": resistances, "pivot": pivot}


def detect_chart_patterns(candles: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    if len(candles) < 3:
        return []
    patterns: List[Dict[str, str]] = []
    c1 = candles[-2]
    c2 = candles[-1]
    o1, h1, l1, cl1 = float(c1["open"]), float(c1["high"]), float(c1["low"]), float(c1["close"])
    o2, h2, l2, cl2 = float(c2["open"]), float(c2["high"]), float(c2["low"]), float(c2["close"])
    body2 = abs(cl2 - o2)
    range2 = max(h2 - l2, 1e-6)
    lower_wick2 = min(o2, cl2) - l2
    upper_wick2 = h2 - max(o2, cl2)

    if cl1 < o1 and cl2 > o2 and o2 <= cl1 and cl2 >= o1:
        patterns.append({"name": "Bullish Engulfing", "bias": "BULLISH"})
    if cl1 > o1 and cl2 < o2 and o2 >= cl1 and cl2 <= o1:
        patterns.append({"name": "Bearish Engulfing", "bias": "BEARISH"})
    if lower_wick2 >= 2.0 * max(body2, range2 * 0.05) and upper_wick2 <= range2 * 0.25:
        patterns.append({"name": "Hammer / Pin Bar", "bias": "BULLISH"})
    if upper_wick2 >= 2.0 * max(body2, range2 * 0.05) and lower_wick2 <= range2 * 0.25:
        patterns.append({"name": "Shooting Star", "bias": "BEARISH"})
    if h2 < h1 and l2 > l1:
        patterns.append({"name": "Inside Bar Consolidation", "bias": "NEUTRAL"})
    return patterns


def compute_all_indicators(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candles:
        return {}
    closes = [float(c["close"]) for c in candles]
    volumes = [float(c.get("volume", 0.0)) for c in candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    rsi14 = rsi(closes, 14)
    macd_line, sig_line, macd_hist = macd(closes)
    bb_upper, bb_mid, bb_lower, bb_bw = bollinger_bands(closes, 20, 2.0)
    atr14 = atr(candles, 14)
    vwap_series = session_vwap(candles)
    vol_sma20 = sma(volumes, 20)
    sr = support_resistance_levels(candles)
    patterns = detect_chart_patterns(candles)

    return {
        "series": {
            "ema9": ema9,
            "ema21": ema21,
            "ema50": ema50,
            "ema200": ema200,
            "rsi14": rsi14,
            "macd": macd_line,
            "macd_signal": sig_line,
            "macd_hist": macd_hist,
            "bb_upper": bb_upper,
            "bb_mid": bb_mid,
            "bb_lower": bb_lower,
            "bb_bandwidth": bb_bw,
            "atr14": atr14,
            "vwap": vwap_series,
            "vol_sma20": vol_sma20,
        },
        "latest": {
            "close": closes[-1],
            "ema9": ema9[-1],
            "ema21": ema21[-1],
            "ema50": ema50[-1],
            "ema200": ema200[-1],
            "rsi14": rsi14[-1],
            "macd": macd_line[-1],
            "macd_signal": sig_line[-1],
            "macd_hist": macd_hist[-1],
            "bb_upper": bb_upper[-1],
            "bb_mid": bb_mid[-1],
            "bb_lower": bb_lower[-1],
            "bb_bandwidth": bb_bw[-1],
            "atr14": atr14[-1],
            "vwap": vwap_series[-1],
            "volume": volumes[-1],
            "vol_sma20": vol_sma20[-1],
            "volume_ratio": round(volumes[-1] / vol_sma20[-1], 2) if vol_sma20[-1] and vol_sma20[-1] > 0 else None,
        },
        "support_resistance": sr,
        "patterns": patterns,
    }
