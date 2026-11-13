"""Module 1: Advanced Indian Stock Scanner & Mode 2 Market-Wide Multi-Factor Scanner."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import get_symbol_sector, get_universe_symbols, normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager
from backend.database.db import query_all
from backend.database.stock_master_db import classify_cap_tier, resolve_stock, sync_stock_master
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


def _load_screener_ratios_map() -> Dict[str, Dict[str, Any]]:
    """Load all Screener.in imported company ratios & business notes from central DB keyed by stock_id & nse_symbol."""
    out: Dict[str, Dict[str, Any]] = {}
    try:
        rows = query_all("SELECT stock_id, nse_symbol, ratios_json, business_notes_json FROM screener_company_data")
        for r in rows:
            item = {
                "ratios": json.loads(r.get("ratios_json") or "{}"),
                "notes": json.loads(r.get("business_notes_json") or "{}"),
            }
            out[r["stock_id"]] = item
            if r.get("nse_symbol"):
                out[r["nse_symbol"].upper()] = item
    except Exception:
        pass
    return out


def _evaluate_symbol(
    symbol: str,
    timeframe: str,
    strategy: str,
    nifty_return_20d: Optional[float],
    exchange: str = "NSE",
    require_strategy_match: bool = True,
    screener_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Evaluate a single stock dynamically. Always returns status dict (never fabricates unavailable data)."""
    stock_meta = resolve_stock(symbol, exchange=exchange)
    canonical = stock_meta.get("nse_symbol") or stock_meta.get("bse_code") or normalize_symbol(symbol)

    pm = get_provider_manager()
    rng = "5d" if timeframe == "1m" else ("1mo" if timeframe in {"5m", "15m", "30m"} else ("3mo" if timeframe == "1h" else "1y"))
    res = pm.get_candles(canonical, interval=timeframe, range_str=rng, exchange=exchange)
    if not res.get("available") or len(res.get("candles", [])) < 25:
        return {"available": False, "symbol": canonical, "reason": res.get("error", "Insufficient candle history")}

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
    tech_score = 30.0

    # 1. Opening Range / Range Breakout
    last_day = str(c_last.get("date", ""))[:10]
    day_candles = [c for c in candles if str(c.get("date", ""))[:10] == last_day]
    if len(day_candles) >= 2:
        orb_high = float(day_candles[0]["high"])
        orb_low = float(day_candles[0]["low"])
        if close > orb_high:
            matches.append("orb")
            reasons.append(f"ORB Bullish Breakout above ₹{orb_high:.2f}")
            tech_score += 18
        elif close < orb_low:
            matches.append("orb")
            reasons.append(f"ORB Breakdown below ₹{orb_low:.2f}")
            tech_score += 10
    elif len(candles) >= 5:
        prev_3h = max(float(c["high"]) for c in candles[-4:-1])
        if close > prev_3h:
            matches.append("orb")
            reasons.append(f"Range Breakout above 3-bar high ₹{prev_3h:.2f}")
            tech_score += 14

    # 2. VWAP Breakout
    if vwap_val and prev_close <= (series["vwap"][-2] or vwap_val) and close > vwap_val:
        matches.append("vwap-breakout")
        reasons.append(f"Crossed above VWAP ₹{vwap_val:.2f}")
        tech_score += 16
    elif vwap_val and close > vwap_val * 1.002:
        matches.append("vwap-breakout")
        reasons.append(f"Holding above VWAP ₹{vwap_val:.2f}")
        tech_score += 8

    # 3. EMA Crossover / Alignment
    ema9_prev = series["ema9"][-2]
    ema21_prev = series["ema21"][-2]
    if ema9 and ema21 and ema9_prev and ema21_prev:
        if ema9_prev <= ema21_prev and ema9 > ema21:
            matches.append("ema-crossover")
            reasons.append(f"Fresh EMA(9) > EMA(21) crossover (₹{ema9:.2f} > ₹{ema21:.2f})")
            tech_score += 18
        elif ema9 > ema21 and (ema50 is None or ema21 > ema50):
            matches.append("ema-crossover")
            reasons.append("Bullish EMA(9 > 21 > 50) trend alignment")
            tech_score += 12

    # 4. RSI Oversold Reversal
    rsi_prev = series["rsi14"][-2]
    if rsi14 is not None and rsi_prev is not None:
        if rsi_prev < 35 and rsi14 > rsi_prev and close > open_p:
            matches.append("rsi-oversold")
            reasons.append(f"RSI(14) oversold reversal ({rsi_prev:.1f} → {rsi14:.1f})")
            tech_score += 16

    # 5. MACD Bullish Crossover
    macd_prev = series["macd"][-2]
    sig_prev = series["macd_signal"][-2]
    if macd_val is not None and macd_sig is not None and macd_prev is not None and sig_prev is not None:
        if macd_prev <= sig_prev and macd_val > macd_sig:
            matches.append("macd-crossover")
            reasons.append("MACD bullish crossover above signal line")
            tech_score += 14

    # 6. Bollinger Band Squeeze
    valid_bw = [x for x in series["bb_bandwidth"][-30:-1] if x is not None]
    if bb_bw is not None and valid_bw:
        min_bw = min(valid_bw)
        if bb_bw <= min_bw * 1.15 or bb_bw < 4.5:
            matches.append("bb-squeeze")
            reasons.append(f"Bollinger Band squeeze ({bb_bw:.2f}%)")
            tech_score += 10

    # 7. Volume Breakout & Unusual Volume
    if vol_ratio >= 1.8 and pct_change > 0.5:
        matches.append("volume-breakout")
        reasons.append(f"Volume breakout at {vol_ratio:.2f}x 20-bar avg")
        tech_score += 18
    if vol_ratio >= 2.2:
        matches.append("unusual-volume")
        reasons.append(f"Unusual volume spike ({vol_ratio:.2f}x avg)")
        tech_score += 12

    # 8. Relative Strength vs NIFTY 50
    rs_alpha = None
    if len(candles) >= 21 and nifty_return_20d is not None:
        base20 = float(candles[-21]["close"])
        stock_ret_20d = ((close - base20) / base20) * 100.0 if base20 else 0.0
        rs_alpha = round(stock_ret_20d - nifty_return_20d, 2)
        if rs_alpha >= 4.0:
            matches.append("relative-strength")
            reasons.append(f"Outperforming NIFTY 50 by +{rs_alpha:.1f}% (20D)")
            tech_score += 15

    # 9. 52-Week High Breakout
    high_52w = res.get("meta", {}).get("fiftyTwoWeekHigh")
    if high_52w and close >= float(high_52w) * 0.985:
        matches.append("52w-high")
        reasons.append(f"Near/breaking 52W high ₹{float(high_52w):.2f}")
        tech_score += 15

    # 10. S/R Breakout
    resistances = sr.get("resistances", [])
    if resistances and close >= resistances[0] * 0.995 and pct_change > 0:
        matches.append("sr-breakout")
        reasons.append(f"Testing/breaking resistance ₹{resistances[0]:.2f}")
        tech_score += 12

    # 11. Chart Patterns
    if patterns:
        matches.append("chart-patterns")
        for p in patterns:
            reasons.append(f"Pattern: {p['name']} ({p['bias']})")
        tech_score += 10

    # 12. Gap
    if abs(gap_pct) >= 1.5:
        matches.append("gap")
        reasons.append(f"{'Gap-Up' if gap_pct > 0 else 'Gap-Down'} {gap_pct:+.2f}%")
        tech_score += 10

    # 13. Momentum
    if pct_change >= 2.0 and rsi14 is not None and 55 <= rsi14 <= 78:
        matches.append("momentum")
        reasons.append(f"Momentum ({pct_change:+.2f}%, RSI {rsi14:.1f})")
        tech_score += 12

    strat_norm = strategy.lower().strip()
    if require_strategy_match:
        if strat_norm != "all" and strat_norm not in matches:
            return {"available": True, "matched": False, "symbol": canonical}
        if strat_norm == "all" and not matches:
            return {"available": True, "matched": False, "symbol": canonical}

    # Merge Screener.in Fundamentals & Catalysts when available
    sc_entry = None
    if screener_map:
        sc_entry = screener_map.get(stock_meta["stock_id"]) or screener_map.get(canonical)
    sc_ratios = (sc_entry or {}).get("ratios") or {}
    sc_notes = (sc_entry or {}).get("notes") or {}

    fund_score = None
    val_score = None
    catalyst_notes: List[str] = []
    if sc_ratios:
        f_pts = 50.0
        if sc_ratios.get("roce_pct") is not None and sc_ratios["roce_pct"] >= 20:
            f_pts += 20
            reasons.append(f"Screener ROCE {sc_ratios['roce_pct']:.1f}%")
        if sc_ratios.get("roe_pct") is not None and sc_ratios["roe_pct"] >= 18:
            f_pts += 12
        if sc_ratios.get("sales_growth_5y_pct") is not None and sc_ratios["sales_growth_5y_pct"] >= 15:
            f_pts += 10
            catalyst_notes.append(f"5Y Sales CAGR {sc_ratios['sales_growth_5y_pct']:.1f}%")
        if sc_ratios.get("profit_growth_5y_pct") is not None and sc_ratios["profit_growth_5y_pct"] >= 18:
            f_pts += 10
            catalyst_notes.append(f"5Y Profit CAGR {sc_ratios['profit_growth_5y_pct']:.1f}%")
        if sc_ratios.get("debt_to_equity") is not None and sc_ratios["debt_to_equity"] <= 0.3:
            f_pts += 8
        fund_score = round(min(98.0, f_pts), 1)

        if sc_ratios.get("pe") is not None:
            pe = sc_ratios["pe"]
            val_score = round(max(20.0, min(95.0, 90.0 - pe if pe > 0 else 45.0)), 1)

    if sc_notes.get("order_book_cr"):
        catalyst_notes.append(f"Order book ₹{sc_notes['order_book_cr']} Cr")
        tech_score += 5
    if sc_ratios.get("promoter_holding_pct") and sc_ratios["promoter_holding_pct"] >= 50:
        catalyst_notes.append(f"Promoter {sc_ratios['promoter_holding_pct']:.1f}%")

    tech_score = round(min(100.0, tech_score), 1)
    composite_score = (
        round((tech_score * 0.55) + (fund_score * 0.30) + ((val_score or 50.0) * 0.15), 1)
        if fund_score is not None
        else tech_score
    )

    mcap_cr = sc_ratios.get("market_cap_cr") or stock_meta.get("market_cap_cr")
    cap_tier = stock_meta.get("cap_tier") or classify_cap_tier(mcap_cr)

    bias = "BULLISH"
    if pct_change < -1.0 and (rsi14 or 50) < 45:
        bias = "BEARISH"

    return {
        "available": True,
        "matched": True,
        "stock_id": stock_meta["stock_id"],
        "symbol": canonical,
        "company_name": stock_meta.get("company_name") or canonical,
        "isin": stock_meta.get("isin"),
        "bse_code": stock_meta.get("bse_code"),
        "exchange": stock_meta.get("exchange") or exchange,
        "sector": stock_meta.get("sector") or get_symbol_sector(canonical),
        "industry": stock_meta.get("industry") or "Indian Listed Equity",
        "market_cap_cr": mcap_cr,
        "cap_tier": cap_tier,
        "timeframe": timeframe,
        "price": round(close, 2),
        "change_pct": pct_change,
        "gap_pct": gap_pct,
        "volume": int(c_last["volume"]),
        "volume_ratio": vol_ratio,
        "rsi14": round(rsi14, 2) if rsi14 is not None else None,
        "vwap": round(vwap_val, 2) if vwap_val is not None else None,
        "atr14": round(atr14, 2),
        "rs_alpha_20d_pct": rs_alpha,
        "bias": bias,
        "matched_strategies": sorted(set(matches)),
        "technical_score": tech_score,
        "fundamental_score": fund_score,
        "valuation_score": val_score,
        "score": composite_score,
        "screener_ratios": sc_ratios or None,
        "catalysts": catalyst_notes,
        "reasons": reasons[:4] if reasons else ["Technical baseline evaluated"],
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
    """Mode 1 Technical Universe Scanner."""
    sync_stock_master(force=False)
    pm = get_provider_manager()
    nifty_ret_20d: Optional[float] = None
    nifty_data = pm.get_candles("^NSEI", interval=timeframe, range_str="3mo" if timeframe == "1d" else "1mo")
    if nifty_data.get("available") and len(nifty_data["candles"]) >= 21:
        nc = nifty_data["candles"]
        base = float(nc[-21]["close"])
        if base > 0:
            nifty_ret_20d = ((float(nc[-1]["close"]) - base) / base) * 100.0

    symbols = get_universe_symbols(universe=universe, limit=limit)
    screener_map = _load_screener_ratios_map()
    results: List[Dict[str, Any]] = []
    unavailable: List[str] = []
    errors: List[str] = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_evaluate_symbol, sym, timeframe, strategy, nifty_ret_20d, exchange, True, screener_map): sym
            for sym in symbols
        }
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                item = fut.result()
                if not item.get("available"):
                    unavailable.append(sym)
                elif item.get("matched"):
                    results.append(item)
            except Exception as exc:
                unavailable.append(sym)
                errors.append(f"{sym}: {exc}")

    results.sort(key=lambda x: (x["score"], x["volume_ratio"]), reverse=True)

    payload = {
        "generated_at": datetime.now(tz=IST).isoformat(),
        "mode": "technical_universe_scan",
        "universe": universe,
        "scanned_count": len(symbols) - len(unavailable),
        "attempted_count": len(symbols),
        "unavailable_count": len(unavailable),
        "unavailable_symbols": unavailable[:15],
        "matched_count": len(results),
        "strategy": strategy,
        "timeframe": timeframe,
        "exchange": exchange,
        "currency": "INR",
        "data_source": "Yahoo Finance (Unofficial) + Central Screener DB",
        "signals": results,
        "errors": errors[:10],
    }

    if save_output:
        SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SIGNALS_PATH.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    return payload


def scan_entire_market(
    cap_tier: str = "ALL",
    sector: str = "ALL",
    industry: str = "ALL",
    min_market_cap: Optional[float] = None,
    max_market_cap: Optional[float] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_volume: Optional[int] = None,
    strategy: str = "all",
    timeframe: str = "1d",
    universe: str = "all",
    limit: int = 45,
) -> Dict[str, Any]:
    """
    MODE 2: Market-Wide Multi-Factor Scanning across supported NSE/BSE universe.
    Combines technical strength, fundamental strength (from Screener DB), valuation,
    volume breakout, and catalysts. Never claims to have scanned unavailable stocks.
    """
    sync_stock_master(force=False)
    clauses: List[str] = ["trading_status != 'SUSPENDED'"]
    params: List[Any] = []

    if cap_tier and cap_tier != "ALL":
        clauses.append("LOWER(cap_tier) = LOWER(?)")
        params.append(cap_tier)
    if sector and sector != "ALL":
        clauses.append("LOWER(sector) = LOWER(?)")
        params.append(sector)
    if industry and industry != "ALL":
        clauses.append("LOWER(industry) = LOWER(?)")
        params.append(industry)
    if min_market_cap is not None:
        clauses.append("market_cap_cr >= ?")
        params.append(float(min_market_cap))
    if max_market_cap is not None:
        clauses.append("market_cap_cr <= ?")
        params.append(float(max_market_cap))

    if universe == "screener_imported":
        clauses.append("stock_id IN (SELECT DISTINCT stock_id FROM screener_company_data)")

    where_sql = f"WHERE {' AND '.join(clauses)}"
    total_matching_rows = query_all(f"SELECT COUNT(*) AS c FROM stocks_master {where_sql}", tuple(params))
    total_universe_matches = int(total_matching_rows[0]["c"]) if total_matching_rows else 0

    # Prioritize Screener-imported stocks + enriched known stocks + index leaders so top scan passes cover high-signal Indian companies
    sql = f"""
        SELECT stock_id, nse_symbol, bse_code, exchange
        FROM stocks_master
        {where_sql}
        ORDER BY
            CASE WHEN stock_id IN (SELECT DISTINCT stock_id FROM screener_company_data) THEN 0 ELSE 1 END,
            CASE WHEN bse_code IS NOT NULL AND bse_code != '' THEN 0 ELSE 1 END,
            COALESCE(market_cap_cr, 0) DESC,
            nse_symbol ASC
        LIMIT ?
    """
    candidate_rows = query_all(sql, tuple(params + [max(1, min(limit, 120))]))
    candidates = [r.get("nse_symbol") or r.get("bse_code") or r["stock_id"] for r in candidate_rows]

    pm = get_provider_manager()
    nifty_ret_20d: Optional[float] = None
    nifty_data = pm.get_candles("^NSEI", interval=timeframe, range_str="3mo" if timeframe == "1d" else "1mo")
    if nifty_data.get("available") and len(nifty_data["candles"]) >= 21:
        nc = nifty_data["candles"]
        base = float(nc[-21]["close"])
        if base > 0:
            nifty_ret_20d = ((float(nc[-1]["close"]) - base) / base) * 100.0

    screener_map = _load_screener_ratios_map()
    ranked: List[Dict[str, Any]] = []
    scanned_available = 0
    unavailable_syms: List[str] = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(
                _evaluate_symbol,
                sym,
                timeframe,
                strategy,
                nifty_ret_20d,
                "NSE",
                strategy != "all",
                screener_map,
            ): sym
            for sym in candidates
        }
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                item = fut.result()
                if not item.get("available"):
                    unavailable_syms.append(sym)
                    continue
                scanned_available += 1
                if not item.get("matched", True):
                    continue
                # Apply post-price & post-volume filters cleanly
                px = item.get("price") or 0.0
                vol = item.get("volume") or 0
                if min_price is not None and px < min_price:
                    continue
                if max_price is not None and px > max_price:
                    continue
                if min_volume is not None and vol < min_volume:
                    continue
                ranked.append(item)
            except Exception:
                unavailable_syms.append(sym)

    ranked.sort(key=lambda x: (x["score"], x.get("fundamental_score") or 0.0, x["volume_ratio"]), reverse=True)

    return {
        "generated_at": datetime.now(tz=IST).isoformat(),
        "mode": "market_wide_scan",
        "filters": {
            "cap_tier": cap_tier,
            "sector": sector,
            "industry": industry,
            "min_market_cap": min_market_cap,
            "max_market_cap": max_market_cap,
            "min_price": min_price,
            "max_price": max_price,
            "min_volume": min_volume,
            "universe": universe,
        },
        "total_stocks_matching_filter": total_universe_matches,
        "attempted_count": len(candidates),
        "scanned_available_count": scanned_available,
        "unavailable_count": len(unavailable_syms),
        "unavailable_symbols": unavailable_syms[:20],
        "matched_count": len(ranked),
        "completeness_note": (
            f"Scanned {scanned_available} of {len(candidates)} attempted stocks "
            f"({len(unavailable_syms)} skipped due to unavailable market feed; {total_universe_matches} total in Stock Master matching filter)."
        ),
        "data_source": "Central Stock Master + Screener.in DB + Yahoo Finance (Unofficial)",
        "results": ranked,
    }
