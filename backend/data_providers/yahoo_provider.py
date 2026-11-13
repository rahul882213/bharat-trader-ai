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

    def get_candles(
        self, symbol: str, interval: str = "1d", range_str: Optional[str] = None, exchange: str = "NSE"
    ) -> Dict[str, Any]:
        self._throttle()
        yahoo_sym = to_yahoo_symbol(symbol, exchange)
        iv, rng = self._map_interval_and_range(interval, range_str)
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_sym)}"
            f"?interval={iv}&range={rng}&includePrePost=false"
        )
        fetched_at = datetime.now(tz=IST).isoformat()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            result = (raw.get("chart") or {}).get("result")
            if not result:
                err = (raw.get("chart") or {}).get("error")
                return {
                    "available": False,
                    "symbol": normalize_symbol(symbol),
                    "yahoo_symbol": yahoo_sym,
                    "exchange": exchange,
                    "source": self.provider_label,
                    "is_unofficial": True,
                    "is_delayed": True,
                    "fetched_at_ist": fetched_at,
                    "error": f"No data returned for {yahoo_sym}: {err}",
                    "candles": [],
                }
            res = result[0]
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

            return {
                "available": len(candles) > 0,
                "symbol": normalize_symbol(symbol) if not symbol.startswith("^") else symbol,
                "yahoo_symbol": yahoo_sym,
                "exchange": meta.get("exchangeName", exchange),
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
                    "longName": meta.get("longName") or meta.get("shortName"),
                },
                "candles": candles,
            }
        except Exception as exc:
            return {
                "available": False,
                "symbol": normalize_symbol(symbol) if not symbol.startswith("^") else symbol,
                "yahoo_symbol": yahoo_sym,
                "exchange": exchange,
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
            "exchange": exchange,
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
        self._throttle()
        yahoo_sym = to_yahoo_symbol(symbol, exchange)
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
        for attempt in range(2):
            try:
                opener, crumb = self._ensure_crumb()
                url = (
                    f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
                    f"{urllib.parse.quote(yahoo_sym)}?modules={modules}&crumb={urllib.parse.quote(crumb)}"
                )
                raw = json.loads(opener.open(url, timeout=10).read().decode("utf-8"))
                res_list = (raw.get("quoteSummary") or {}).get("result")
                if not res_list:
                    return {
                        "available": False,
                        "symbol": normalize_symbol(symbol),
                        "yahoo_symbol": yahoo_sym,
                        "source": self.provider_label,
                        "is_unofficial": True,
                        "fetched_at_ist": fetched_at,
                        "error": f"No fundamental data available for {yahoo_sym}",
                    }
                return {
                    "available": True,
                    "symbol": normalize_symbol(symbol),
                    "yahoo_symbol": yahoo_sym,
                    "exchange": exchange,
                    "source": self.provider_label,
                    "is_unofficial": True,
                    "fetched_at_ist": fetched_at,
                    "raw": res_list[0],
                }
            except urllib.error.HTTPError as e:
                if e.code in (401, 403) and attempt == 0:
                    self._crumb = None
                    self._opener = None
                    continue
                return {
                    "available": False,
                    "symbol": normalize_symbol(symbol),
                    "yahoo_symbol": yahoo_sym,
                    "source": self.provider_label,
                    "is_unofficial": True,
                    "fetched_at_ist": fetched_at,
                    "error": f"HTTP {e.code}: {e.reason}",
                }
            except Exception as exc:
                return {
                    "available": False,
                    "symbol": normalize_symbol(symbol),
                    "yahoo_symbol": yahoo_sym,
                    "source": self.provider_label,
                    "is_unofficial": True,
                    "fetched_at_ist": fetched_at,
                    "error": str(exc),
                }
        return {
            "available": False,
            "symbol": normalize_symbol(symbol),
            "source": self.provider_label,
            "error": "Failed after retry",
        }
