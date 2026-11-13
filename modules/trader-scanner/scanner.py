"""Module 1: Advanced Indian Stock Scanner (NSE / BSE)."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import get_symbol_sector, get_universe_symbols, normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager
from backend.services.indicators import compute_all_indicators

IST = ZoneInfo("Asia/Kolkata")
ROOT_DIR = Path(__file__).resolve().parents[2]
SIGNALS_PATH = ROOT_DIR / "trader" / "signals.json"

STRATEGIES = [
    "all",
    "orb",
    "vwap-breakout",
    "ema-crossover",
    "rsi-oversold",
    "macd-crossover",
    "bb-squeeze",
    "volume-breakout",
    "relative-strength",
    "52w-high",
    "sr-breakout",
    "chart-patterns",
    "gap",
    "momentum",
    "unusual-volume",
]


def _evaluate_symbol(
    symbol: str,
    timeframe: str,
    strategy: str,
    nifty_return_20d: Optional[float],
    exchange: str = "NSE",
) -> Optional[Dict[str, Any]]:
    pm = get_provider_manager()
    rng = "5d" if timeframe == "1m" else ("1mo" if timeframe in {"5m", "15m", "30m"} else ("3mo" if timeframe == "1h" else "1y"))
    res = pm.get_candles(symbol, interval=timeframe, range_str=rng, exchange=exchange)
    if not res.get("available") or len(res.get("candles", [])) < 25:
        return None

    candles = res["candles"]
    ind = compute_all_indicators(candles)
    latest = ind["latest"]
    series = ind["series"]
    sr = ind["support_resistance"]
    patterns = ind["patterns"]

    c_last = candles[-1]
    c_prev = candles[-2]
    close = float(c_last["close"])
    prev_close = float(c_prev["close"])
    open_p = float(c_last["open"])
    pct_change = round(((close - prev_close) / prev_close) * 100.0, 2) if prev_close else 0.0
    gap_pct = round(((open_p - prev_close) / prev_close) * 100.0, 2) if prev_close else 0.0

    ema9 = latest.get("ema9")
    ema21 = latest.get("ema21")
    ema50 = latest.get("ema50")
    rsi14 = latest.get("rsi14")
    macd_val = latest.get("macd")
    macd_sig = latest.get("macd_signal")
    vwap_val = latest.get("vwap")
    vol_ratio = latest.get("volume_ratio") or 1.0
    bb_bw = latest.get("bb_bandwidth")
    atr14 = latest.get("atr14") or (close * 0.015)

    matches: List[str] = []
    reasons: List[str] = []
    score = 0.0

    # 1. Opening Range Breakout (for intraday: breakout above first candle of latest day; for daily: breakout above prior 3-day range)
    last_day = str(c_last.get("date", ""))[:10]
    day_candles = [c for c in candles if str(c.get("date", ""))[:10] == last_day]
    if len(day_candles) >= 2:
        orb_high = float(day_candles[0]["high"])
        orb_low = float(day_candles[0]["low"])
        if close > orb_high:
            matches.append("orb")
            reasons.append(f"ORB Bullish Breakout above opening range high ₹{orb_high:.2f}")
            score += 22
        elif close < orb_low:
            matches.append("orb")
            reasons.append(f"ORB Breakdown below opening range low ₹{orb_low:.2f}")
            score += 18
    elif len(candles) >= 5:
        prev_3h = max(float(c["high"]) for c in candles[-4:-1])
        if close > prev_3h:
            matches.append("orb")
            reasons.append(f"Range Breakout above 3-bar high ₹{prev_3h:.2f}")
            score += 18

    # 2. VWAP Breakout
    if vwap_val and prev_close <= (series["vwap"][-2] or vwap_val) and close > vwap_val:
        matches.append("vwap-breakout")
        reasons.append(f"Crossed above session VWAP ₹{vwap_val:.2f}")
        score += 20
    elif vwap_val and close > vwap_val * 1.002:
        matches.append("vwap-breakout")
        reasons.append(f"Holding above VWAP ₹{vwap_val:.2f}")
        score += 10

    # 3. EMA Crossover (9 / 21)
    ema9_prev = series["ema9"][-2]
    ema21_prev = series["ema21"][-2]
    if ema9 and ema21 and ema9_prev and ema21_prev:
        if ema9_prev <= ema21_prev and ema9 > ema21:
            matches.append("ema-crossover")
            reasons.append(f"Fresh EMA(9) crossed above EMA(21) (₹{ema9:.2f} > ₹{ema21:.2f})")
            score += 24
        elif ema9 > ema21 and (ema50 is None or ema21 > ema50):
            matches.append("ema-crossover")
            reasons.append("Bullish EMA(9 > 21 > 50) alignment")
            score += 10

    # 4. RSI Oversold Reversal
    rsi_prev = series["rsi14"][-2]
    if rsi14 is not None and rsi_prev is not None:
        if rsi_prev < 35 and rsi14 > rsi_prev and close > open_p:
            matches.append("rsi-oversold")
            reasons.append(f"RSI(14) oversold reversal from {rsi_prev:.1f} to {rsi14:.1f}")
            score += 22

    # 5. MACD Bullish Crossover
    macd_prev = series["macd"][-2]
    sig_prev = series["macd_signal"][-2]
    if macd_val is not None and macd_sig is not None and macd_prev is not None and sig_prev is not None:
        if macd_prev <= sig_prev and macd_val > macd_sig:
            matches.append("macd-crossover")
            reasons.append("MACD bullish crossover above signal line")
            score += 20

    # 6. Bollinger Band Squeeze
    valid_bw = [x for x in series["bb_bandwidth"][-30:-1] if x is not None]
    if bb_bw is not None and valid_bw:
        min_bw = min(valid_bw)
        if bb_bw <= min_bw * 1.15 or bb_bw < 4.5:
            matches.append("bb-squeeze")
            reasons.append(f"Bollinger Band squeeze (Bandwidth {bb_bw:.2f}%)")
            score += 16

    # 7. Volume Breakout & 14. Unusual Volume
    if vol_ratio >= 1.8 and pct_change > 0.5:
        matches.append("volume-breakout")
        reasons.append(f"Volume breakout at {vol_ratio:.2f}x 20-bar average")
        score += 22
    if vol_ratio >= 2.2:
        matches.append("unusual-volume")
        reasons.append(f"Unusual volume spike ({vol_ratio:.2f}x average)")
        score += 16

    # 8. Relative Strength Breakout vs NIFTY 50
    if len(candles) >= 21 and nifty_return_20d is not None:
        base20 = float(candles[-21]["close"])
        stock_ret_20d = ((close - base20) / base20) * 100.0 if base20 else 0.0
        rs_alpha = stock_ret_20d - nifty_return_20d
        if rs_alpha >= 4.0:
            matches.append("relative-strength")
            reasons.append(f"Outperforming NIFTY 50 by +{rs_alpha:.1f}% over 20 bars")
            score += 18

    # 9. 52-Week High Breakout
    high_52w = res.get("meta", {}).get("fiftyTwoWeekHigh")
    if high_52w and close >= float(high_52w) * 0.985:
        matches.append("52w-high")
        reasons.append(f"Near/breaking 52-week high ₹{float(high_52w):.2f}")
        score += 20

    # 10. Support & Resistance Breakout
    resistances = sr.get("resistances", [])
    if resistances and close >= resistances[0] * 0.995 and pct_change > 0:
        matches.append("sr-breakout")
        reasons.append(f"Testing/breaking resistance ₹{resistances[0]:.2f}")
        score += 16

    # 11. Chart Patterns
    if patterns:
        matches.append("chart-patterns")
        for p in patterns:
            reasons.append(f"Pattern: {p['name']} ({p['bias']})")
        score += 15

    # 12. Gap-up / Gap-down
    if abs(gap_pct) >= 1.5:
        matches.append("gap")
        direction = "Gap-Up" if gap_pct > 0 else "Gap-Down"
        reasons.append(f"{direction} of {gap_pct:+.2f}% at open")
        score += 16

    # 13. Momentum Stocks
    if pct_change >= 2.0 and rsi14 is not None and 55 <= rsi14 <= 78:
        matches.append("momentum")
        reasons.append(f"Strong price momentum ({pct_change:+.2f}%, RSI {rsi14:.1f})")
        score += 16

    strat_norm = strategy.lower().strip()
    if strat_norm != "all" and strat_norm not in matches:
        return None
    if strat_norm == "all" and not matches:
        return None

    bias = "BULLISH"
    if pct_change < -1.0 and (rsi14 or 50) < 45:
        bias = "BEARISH"

    return {
        "symbol": normalize_symbol(symbol),
        "exchange": exchange,
        "sector": get_symbol_sector(symbol),
        "timeframe": timeframe,
        "price": round(close, 2),
        "change_pct": pct_change,
        "gap_pct": gap_pct,
        "volume": int(c_last["volume"]),
        "volume_ratio": vol_ratio,
        "rsi14": round(rsi14, 2) if rsi14 is not None else None,
        "vwap": round(vwap_val, 2) if vwap_val is not None else None,
        "atr14": round(atr14, 2),
        "bias": bias,
        "matched_strategies": sorted(set(matches)),
        "score": round(min(score, 100.0), 1),
        "reasons": reasons[:4],
        "source": res["source"],
        "is_unofficial": res["is_unofficial"],
        "last_bar_ist": res.get("last_bar_ist"),
        "fetched_at_ist": res.get("fetched_at_ist"),
    }


def scan_market(
    strategy: str = "all",
    timeframe: str = "1d",
    universe: str = "nifty50",
    limit: int = 35,
    exchange: str = "NSE",
    save_output: bool = True,
) -> Dict[str, Any]:
    """Scan Indian stock universe for quantitative technical setups."""
    pm = get_provider_manager()
    # Compute NIFTY 50 20-bar return for Relative Strength calculations
    nifty_ret_20d: Optional[float] = None
    nifty_data = pm.get_candles("^NSEI", interval=timeframe, range_str="3mo" if timeframe == "1d" else "1mo")
    if nifty_data.get("available") and len(nifty_data["candles"]) >= 21:
        nc = nifty_data["candles"]
        base = float(nc[-21]["close"])
        if base > 0:
            nifty_ret_20d = ((float(nc[-1]["close"]) - base) / base) * 100.0

    symbols = get_universe_symbols(universe=universe, limit=limit)
    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_evaluate_symbol, sym, timeframe, strategy, nifty_ret_20d, exchange): sym
            for sym in symbols
        }
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                item = fut.result()
                if item is not None:
                    results.append(item)
            except Exception as exc:
                errors.append(f"{sym}: {exc}")

    results.sort(key=lambda x: (x["score"], x["volume_ratio"]), reverse=True)

    payload = {
        "generated_at": datetime.now(tz=IST).isoformat(),
        "universe": universe,
        "scanned_count": len(symbols),
        "matched_count": len(results),
        "strategy": strategy,
        "timeframe": timeframe,
        "exchange": exchange,
        "currency": "INR",
        "data_source": "Yahoo Finance (Unofficial)",
        "signals": results,
        "errors": errors[:10],
    }

    if save_output:
        SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SIGNALS_PATH.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    return payload
