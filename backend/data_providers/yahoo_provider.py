"""Yahoo Finance Unofficial Market Data Adapter for NSE (.NS) & BSE (.BO) Stocks."""
from __future__ import annotations

import http.cookiejar
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from .base import MarketDataProvider
from .nse_master import normalize_symbol, to_yahoo_symbol
from backend.database.db import execute_sql
from backend.database.stock_master_db import classify_cap_tier, resolve_stock, upsert_stock_record

IST = ZoneInfo("Asia/Kolkata")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


class YahooUnofficialProvider(MarketDataProvider):
    provider_id = "yahoo_unofficial"
    provider_label = "Yahoo Finance (Unofficial)"
    is_unofficial = True
    is_delayed = True

    def __init__(self, min_delay_sec: float = 0.08):
        self._min_delay = min_delay_sec
        self._last_req = 0.0
        self._lock = threading.Lock()
        self._crumb: Optional[str] = None
        self._opener: Optional[urllib.request.OpenerDirector] = None

    def _throttle(self) -> None:
        with self._lock:
            now = time.time()
            wait = self._min_delay - (now - self._last_req)
            if wait > 0:
                time.sleep(wait)
            self._last_req = time.time()

    def _ensure_crumb(self) -> tuple[urllib.request.OpenerDirector, str]:
        if self._opener is not None and self._crumb:
            return self._opener, self._crumb
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        opener.addheaders = [("User-Agent", USER_AGENT)]
        try:
            opener.open("https://fc.yahoo.com", timeout=5)
        except Exception:
            pass
        crumb = opener.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=6).read().decode("utf-8").strip()
        self._opener = opener
        self._crumb = crumb
        return opener, crumb

    def _map_interval_and_range(self, interval: str, range_str: Optional[str] = None) -> tuple[str, str]:
        iv_map = {
            "1m": ("1m", "5d"),
            "5m": ("5m", "1mo"),
            "15m": ("15m", "1mo"),
            "30m": ("30m", "1mo"),
            "1h": ("60m", "3mo"),
            "60m": ("60m", "3mo"),
            "1d": ("1d", "1y"),
            "1wk": ("1wk", "2y"),
        }
        mapped_iv, default_range = iv_map.get(interval, ("1d", "1y"))
        return mapped_iv, (range_str or default_range)

    def _resolve_target(self, symbol: str, exchange: str) -> tuple[str, str, Optional[Dict[str, Any]]]:
        raw = (symbol or "").strip()
        if raw.startswith("^") or "=X" in raw or "=F" in raw:
            return raw, raw, None
        rec = resolve_stock(raw, exchange=exchange)
        ysym = rec.get("effective_yahoo_symbol") or to_yahoo_symbol(raw, exchange)
        canonical_sym = rec.get("nse_symbol") or rec.get("bse_code") or normalize_symbol(raw)
        return canonical_sym, ysym, rec

    def _fetch_chart_json(self, yahoo_sym: str, iv: str, rng: str) -> Optional[Dict[str, Any]]:
        self._throttle()
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_sym)}"
            f"?interval={iv}&range={rng}&includePrePost=false"
        )
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        result = (raw.get("chart") or {}).get("result")
        if result:
            return result[0]
        return None

    def get_candles(
        self, symbol: str, interval: str = "1d", range_str: Optional[str] = None, exchange: str = "NSE"
    ) -> Dict[str, Any]:
        canonical_sym, yahoo_sym, stock_rec = self._resolve_target(symbol, exchange)
        iv, rng = self._map_interval_and_range(interval, range_str)
        fetched_at = datetime.now(tz=IST).isoformat()
        try:
            res = None
            try:
                res = self._fetch_chart_json(yahoo_sym, iv, rng)
            except Exception:
                res = None

            # Auto-try -SM.NS or .NS/.BO if primary lookup returned nothing or <5 bars
            if (res is None or len((res.get("timestamp") or [])) < 5) and not canonical_sym.startswith("^") and "=" not in canonical_sym:
                fallbacks: List[str] = []
                if yahoo_sym.endswith("-SM.NS"):
                    fallbacks.append(f"{canonical_sym}.NS")
                elif yahoo_sym.endswith(".NS"):
                    fallbacks.append(f"{canonical_sym}-SM.NS")
                    fallbacks.append(f"{canonical_sym}.BO")
                elif yahoo_sym.endswith(".BO"):
                    fallbacks.append(f"{canonical_sym}.NS")
                best_len = len((res or {}).get("timestamp") or [])
                for fb in fallbacks:
                    try:
                        fb_res = self._fetch_chart_json(fb, iv, rng)
                        fb_len = len((fb_res or {}).get("timestamp") or [])
                        if fb_res is not None and fb_len > best_len:
                            res = fb_res
                            best_len = fb_len
                            yahoo_sym = fb
                            if stock_rec and stock_rec.get("stock_id"):
                                execute_sql(
                                    "UPDATE stocks_master SET yahoo_symbol = ?, updated_at = ? WHERE stock_id = ?",
                                    (fb, fetched_at, stock_rec["stock_id"]),
                                )
                    except Exception:
                        continue

            if not res:
                return {
                    "available": False,
                    "symbol": canonical_sym,
                    "yahoo_symbol": yahoo_sym,
                    "exchange": (stock_rec or {}).get("exchange", exchange),
                    "stock_meta": stock_rec,
                    "source": self.provider_label,
                    "is_unofficial": True,
                    "is_delayed": True,
                    "fetched_at_ist": fetched_at,
                    "error": f"No market data returned for {yahoo_sym}",
                    "candles": [],
                }
            meta = res.get("meta", {})
            timestamps = res.get("timestamp") or []
            quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
            opens = quote.get("open") or []
            highs = quote.get("high") or []
            lows = quote.get("low") or []
            closes = quote.get("close") or []
            volumes = quote.get("volume") or []

            candles: List[Dict[str, Any]] = []
            for i, ts in enumerate(timestamps):
                o = opens[i] if i < len(opens) else None
                h = highs[i] if i < len(highs) else None
                l = lows[i] if i < len(lows) else None
                c = closes[i] if i < len(closes) else None
                v = volumes[i] if i < len(volumes) else 0
                if o is None or h is None or l is None or c is None:
                    continue
                dt_ist = datetime.fromtimestamp(ts, tz=IST)
                candles.append({
                    "timestamp": ts,
                    "time": ts if iv in {"1m", "5m", "15m", "30m", "60m"} else dt_ist.strftime("%Y-%m-%d"),
                    "date": dt_ist.strftime("%Y-%m-%d %H:%M:%S" if iv != "1d" else "%Y-%m-%d"),
                    "open": round(float(o), 2),
                    "high": round(float(h), 2),
                    "low": round(float(l), 2),
                    "close": round(float(c), 2),
                    "volume": int(v or 0),
                })

            last_ts = candles[-1]["timestamp"] if candles else None
            stale = False
            stale_reason = None
            if last_ts is not None:
                age_sec = time.time() - last_ts
                if iv in {"1m", "5m", "15m"} and age_sec > 3600 * 96:
                    stale = True
                    stale_reason = f"Latest intraday bar is {int(age_sec // 3600)}h old (outside market session or delayed)."

            # Cache latest daily/intraday price into central market_price_cache
            if candles and stock_rec and stock_rec.get("stock_id"):
                last_c = float(candles[-1]["close"])
                prev_c = float(candles[-2]["close"]) if len(candles) >= 2 else last_c
                chg_pct = round(((last_c - prev_c) / prev_c) * 100.0, 2) if prev_c else 0.0
                try:
                    execute_sql(
                        """
                        INSERT INTO market_price_cache
                        (stock_id, symbol, last_price, change_pct, volume, source, last_bar_ist, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(stock_id) DO UPDATE SET
                            symbol = excluded.symbol,
                            last_price = excluded.last_price,
                            change_pct = excluded.change_pct,
                            volume = excluded.volume,
                            source = excluded.source,
                            last_bar_ist = excluded.last_bar_ist,
                            fetched_at = excluded.fetched_at
                        """,
                        (
                            stock_rec["stock_id"],
                            canonical_sym,
                            last_c,
                            chg_pct,
                            int(candles[-1]["volume"]),
                            self.provider_label,
                            candles[-1]["date"],
                            fetched_at,
                        ),
                    )
                except Exception:
                    pass

            return {
                "available": len(candles) > 0,
                "symbol": canonical_sym,
                "yahoo_symbol": yahoo_sym,
                "exchange": (stock_rec or {}).get("exchange") or meta.get("exchangeName", exchange),
                "stock_meta": stock_rec,
                "currency": meta.get("currency", "INR"),
                "interval": interval,
                "range": rng,
                "source": self.provider_label,
                "is_unofficial": True,
                "is_delayed": True,
                "fetched_at_ist": fetched_at,
                "last_bar_ist": candles[-1]["date"] if candles else None,
                "stale": stale,
                "stale_reason": stale_reason,
                "meta": {
                    "regularMarketPrice": meta.get("regularMarketPrice"),
                    "chartPreviousClose": meta.get("chartPreviousClose"),
                    "previousClose": meta.get("previousClose"),
                    "fiftyTwoWeekHigh": meta.get("fiftyTwoWeekHigh"),
                    "fiftyTwoWeekLow": meta.get("fiftyTwoWeekLow"),
                    "regularMarketVolume": meta.get("regularMarketVolume"),
                    "regularMarketDayHigh": meta.get("regularMarketDayHigh"),
                    "regularMarketDayLow": meta.get("regularMarketDayLow"),
                    "longName": (stock_rec or {}).get("company_name") or meta.get("longName") or meta.get("shortName"),
                },
                "candles": candles,
            }
        except Exception as exc:
            return {
                "available": False,
                "symbol": canonical_sym,
                "yahoo_symbol": yahoo_sym,
                "exchange": (stock_rec or {}).get("exchange", exchange),
                "stock_meta": stock_rec,
                "source": self.provider_label,
                "is_unofficial": True,
                "is_delayed": True,
                "fetched_at_ist": fetched_at,
                "error": str(exc),
                "candles": [],
            }

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        data = self.get_candles(symbol, interval="1d", range_str="1mo", exchange=exchange)
        if not data.get("available"):
            return data
        candles = data["candles"]
        meta = data.get("meta", {})
        last_close = float(candles[-1]["close"])
        price = float(meta.get("regularMarketPrice") or last_close)
        prev_close = float(
            meta.get("chartPreviousClose")
            or meta.get("previousClose")
            or (candles[-2]["close"] if len(candles) >= 2 else last_close)
        )
        # Note: for range=1mo chartPreviousClose is 1 month ago; use penultimate candle close for 1-day change
        if len(candles) >= 2:
            prev_day_close = float(candles[-2]["close"])
        else:
            prev_day_close = prev_close
        change = round(price - prev_day_close, 2)
        change_pct = round((change / prev_day_close) * 100.0, 2) if prev_day_close else 0.0
        return {
            "available": True,
            "symbol": data["symbol"],
            "yahoo_symbol": data["yahoo_symbol"],
            "name": meta.get("longName") or data["symbol"],
            "exchange": data.get("exchange", exchange),
            "stock_meta": data.get("stock_meta"),
            "currency": data.get("currency", "INR"),
            "price": round(price, 2),
            "prev_close": round(prev_day_close, 2),
            "change": change,
            "change_pct": change_pct,
            "day_high": round(float(meta.get("regularMarketDayHigh") or candles[-1]["high"]), 2),
            "day_low": round(float(meta.get("regularMarketDayLow") or candles[-1]["low"]), 2),
            "volume": int(meta.get("regularMarketVolume") or candles[-1]["volume"]),
            "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
            "source": self.provider_label,
            "is_unofficial": True,
            "is_delayed": True,
            "fetched_at_ist": data["fetched_at_ist"],
            "last_bar_ist": data["last_bar_ist"],
        }

    def get_fundamentals(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        canonical_sym, yahoo_sym, stock_rec = self._resolve_target(symbol, exchange)
        fetched_at = datetime.now(tz=IST).isoformat()
        modules = ",".join([
            "assetProfile",
            "summaryDetail",
            "financialData",
            "defaultKeyStatistics",
            "majorHoldersBreakdown",
            "incomeStatementHistory",
            "incomeStatementHistoryQuarterly",
            "balanceSheetHistory",
            "cashflowStatementHistory",
            "earningsTrend",
        ])
        candidates = [yahoo_sym]
        if yahoo_sym.endswith(".NS") and "-SM.NS" not in yahoo_sym:
            candidates.append(f"{canonical_sym}-SM.NS")

        last_error = "No fundamental data available"
        for cand_sym in candidates:
            for attempt in range(2):
                try:
                    self._throttle()
                    opener, crumb = self._ensure_crumb()
                    url = (
                        f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
                        f"{urllib.parse.quote(cand_sym)}?modules={modules}&crumb={urllib.parse.quote(crumb)}"
                    )
                    raw = json.loads(opener.open(url, timeout=10).read().decode("utf-8"))
                    res_list = (raw.get("quoteSummary") or {}).get("result")
                    if not res_list:
                        last_error = f"No fundamental data available for {cand_sym}"
                        break

                    raw_obj = res_list[0]
                    # Enrich central stocks_master with real market cap, cap tier, sector & industry
                    if stock_rec:
                        sd = raw_obj.get("summaryDetail") or {}
                        prof = raw_obj.get("assetProfile") or {}
                        mc_raw = (sd.get("marketCap") or {}).get("raw")
                        mc_cr = round(float(mc_raw) / 1e7, 2) if isinstance(mc_raw, (int, float)) and mc_raw > 0 else None
                        upsert_stock_record({
                            "isin": stock_rec.get("isin"),
                            "nse_symbol": stock_rec.get("nse_symbol"),
                            "bse_code": stock_rec.get("bse_code"),
                            "sector": prof.get("sector") or stock_rec.get("sector"),
                            "industry": prof.get("industry") or stock_rec.get("industry"),
                            "market_cap_cr": mc_cr,
                            "cap_tier": classify_cap_tier(mc_cr) if mc_cr else stock_rec.get("cap_tier"),
                        })
                        stock_rec = resolve_stock(stock_rec.get("stock_id") or canonical_sym, exchange=exchange)

                    return {
                        "available": True,
                        "symbol": canonical_sym,
                        "yahoo_symbol": cand_sym,
                        "exchange": (stock_rec or {}).get("exchange", exchange),
                        "stock_meta": stock_rec,
                        "source": self.provider_label,
                        "is_unofficial": True,
                        "fetched_at_ist": fetched_at,
                        "raw": raw_obj,
                    }
                except urllib.error.HTTPError as e:
                    if e.code in (401, 403) and attempt == 0:
                        self._crumb = None
                        self._opener = None
                        continue
                    last_error = f"HTTP {e.code}: {e.reason}"
                    break
                except Exception as exc:
                    last_error = str(exc)
                    break

        return {
            "available": False,
            "symbol": canonical_sym,
            "yahoo_symbol": yahoo_sym,
            "stock_meta": stock_rec,
            "source": self.provider_label,
            "is_unofficial": True,
            "fetched_at_ist": fetched_at,
            "error": last_error,
        }

