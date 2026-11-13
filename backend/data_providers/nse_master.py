"""NSE India Equity Master & Index Constituents Registry."""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

CACHE_FILE = Path(__file__).resolve().parents[2] / "trader" / "nse_equity_cache.json"
NSE_EQUITY_CSV_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

# Core NIFTY 50 constituents & sectors (used for fast index filtering & sector exposure)
NIFTY_50_SECTORS: Dict[str, str] = {
    "RELIANCE": "Energy",
    "TCS": "IT",
    "HDFCBANK": "Banking",
    "BHARTIARTL": "Telecom",
    "ICICIBANK": "Banking",
    "INFY": "IT",
    "SBIN": "Banking",
    "HINDUNILVR": "FMCG",
    "ITC": "FMCG",
    "LT": "Infrastructure",
    "BAJFINANCE": "Financial Services",
    "HCLTECH": "IT",
    "MARUTI": "Auto",
    "SUNPHARMA": "Pharma",
    "ADANIENT": "Metals & Conglomerate",
    "KOTAKBANK": "Banking",
    "TITAN": "Consumer Durables",
    "ONGC": "Energy",
    "TATAMOTORS": "Auto",
    "AXISBANK": "Banking",
    "NTPC": "Power",
    "ULTRACEMCO": "Cement",
    "ASIANPAINT": "Consumer Durables",
    "WIPRO": "IT",
    "M&M": "Auto",
    "POWERGRID": "Power",
    "BAJAJFINSV": "Financial Services",
    "NESTLEIND": "FMCG",
    "JSWSTEEL": "Metals",
    "TATASTEEL": "Metals",
    "COALINDIA": "Energy",
    "ADANIPORTS": "Infrastructure",
    "TECHM": "IT",
    "HINDALCO": "Metals",
    "INDUSINDBK": "Banking",
    "GRASIM": "Cement",
    "SBILIFE": "Financial Services",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "HDFCLIFE": "Financial Services",
    "BAJAJ-AUTO": "Auto",
    "EICHERMOT": "Auto",
    "HEROMOTOCO": "Auto",
    "BPCL": "Energy",
    "TATACONSUM": "FMCG",
    "APOLLOHOSP": "Healthcare",
    "TRENT": "Retail",
    "BEL": "Defence",
    "SHRIRAMFIN": "Financial Services",
    "JIOFIN": "Financial Services",
}

BANK_NIFTY_SYMBOLS = [
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK",
    "INDUSINDBK", "BANKBARODA", "PNB", "FEDERALBNK", "IDFCFIRSTB", "AUBANK", "CANBK",
]

FIN_NIFTY_SYMBOLS = [
    "HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE", "KOTAKBANK", "AXISBANK",
    "BAJAJFINSV", "SBILIFE", "HDFCLIFE", "SHRIRAMFIN", "CHOLAFIN", "PFC", "RECLTD", "JIOFIN",
]

NIFTY_NEXT_50_SAMPLE = [
    "HAL", "MAZDOCK", "DIXON", "VBL", "ZOMATO", "DLF", "SIEMENS", "ABB",
    "PIDILITIND", "HAVELLS", "CHOLAFIN", "GAIL", "IOC", "INDIGO", "TORNTPHARM",
    "VEDL", "PNB", "BANKBARODA", "AMBUJACEM", "TVSMOTOR", "CGPOWER", "LODHA",
    "IRFC", "PFC", "RECLTD", "JINDALSTEL", "DIVISLAB", "LTIM", "GODREJCP", "DABUR",
]

MIDCAP_SMALLCAP_ACTIVE = [
    "ORIANA", "KPITTECH", "PERSISTENT", "COFORGE", "BSE", "CDSL", "MCX",
    "SUZLON", "IREDA", "RVNL", "IRCTC", "TATAELXSI", "POLYCAB", "KEI",
    "ASTRAL", "DEEPAKNTR", "NAVINFLUOR", "BHEL", "NHPC", "SJVN",
]

SECTOR_OVERRIDES: Dict[str, str] = {
    **NIFTY_50_SECTORS,
    "HAL": "Defence",
    "MAZDOCK": "Defence",
    "COCHINSHIP": "Defence",
    "GRSE": "Defence",
    "ORIANA": "Renewables",
    "SUZLON": "Renewables",
    "IREDA": "Financial Services",
    "DIXON": "Electronics",
    "ZOMATO": "Consumer Tech",
    "BSE": "Capital Markets",
    "CDSL": "Capital Markets",
    "MCX": "Capital Markets",
    "KPITTECH": "IT",
    "PERSISTENT": "IT",
    "COFORGE": "IT",
    "TATAELXSI": "IT",
    "POLYCAB": "Cables & Electricals",
    "BANKBARODA": "Banking",
    "PNB": "Banking",
    "CANBK": "Banking",
    "FEDERALBNK": "Banking",
    "IDFCFIRSTB": "Banking",
    "AUBANK": "Banking",
    "CHOLAFIN": "Financial Services",
    "PFC": "Financial Services",
    "RECLTD": "Financial Services",
    "RVNL": "Railways & Infra",
    "IRFC": "Financial Services",
    "IRCTC": "Travel & Tourism",
    "INDIGO": "Aviation",
    "VEDL": "Metals",
    "JINDALSTEL": "Metals",
    "TVSMOTOR": "Auto",
    "BHEL": "Capital Goods",
    "SIEMENS": "Capital Goods",
    "ABB": "Capital Goods",
}


def get_symbol_sector(symbol: str) -> str:
    clean = normalize_symbol(symbol)
    return SECTOR_OVERRIDES.get(clean, "Indian Equities")


def normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        s = s[:-3]
    if s.startswith("NSE:") or s.startswith("BSE:"):
        s = s.split(":", 1)[1]
    return s


def to_yahoo_symbol(symbol: str, exchange: str = "NSE") -> str:
    s = symbol.strip().upper()
    if s.startswith("^") or s.endswith("=X") or s.endswith("=F") or s.endswith(".NS") or s.endswith(".BO"):
        return s
    clean = normalize_symbol(s)
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    return f"{clean}{suffix}"


def fetch_nse_equity_master(force_refresh: bool = False) -> Dict[str, Any]:
    """Fetch official NSE equity master list from archives.nseindia.com/content/equities/EQUITY_L.csv."""
    if not force_refresh and CACHE_FILE.exists():
        try:
            age = time.time() - CACHE_FILE.stat().st_mtime
            if age < 86400:  # 24h cache
                with CACHE_FILE.open("r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    try:
        req = urllib.request.Request(
            NSE_EQUITY_CSV_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BharatTraderAI/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_text = resp.read().decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(raw_text))
        equities: List[Dict[str, str]] = []
        for row in reader:
            sym = (row.get("SYMBOL") or "").strip()
            name = (row.get("NAME OF COMPANY") or "").strip()
            series = (row.get(" SERIES") or row.get("SERIES") or "").strip()
            isin = (row.get(" ISIN NUMBER") or row.get("ISIN NUMBER") or "").strip()
            if sym and series in {"EQ", "BE", "BZ", "SM", "ST"}:
                equities.append({
                    "symbol": sym,
                    "name": name,
                    "series": series,
                    "isin": isin,
                    "exchange": "NSE",
                    "sector": get_symbol_sector(sym),
                })
        payload = {
            "source": "NSE India Official Equity Master (EQUITY_L.csv)",
            "count": len(equities),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "equities": equities,
        }
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
        return payload
    except Exception as exc:
        if CACHE_FILE.exists():
            with CACHE_FILE.open("r", encoding="utf-8") as f:
                cached = json.load(f)
                cached["warning"] = f"Using cached NSE master after fetch error: {exc}"
                return cached
        # Minimal fallback list of symbols (NO fake prices)
        fallback = [
            {"symbol": s, "name": s, "series": "EQ", "isin": "", "exchange": "NSE", "sector": get_symbol_sector(s)}
            for s in list(NIFTY_50_SECTORS.keys()) + NIFTY_NEXT_50_SAMPLE + MIDCAP_SMALLCAP_ACTIVE
        ]
        return {
            "source": "Curated NSE Index Registry (Offline Fallback)",
            "count": len(fallback),
            "fetched_at": None,
            "error": str(exc),
            "equities": fallback,
        }


def get_universe_symbols(universe: str = "nifty50", limit: int = 50) -> List[str]:
    u = universe.lower().strip()
    if u in {"nifty50", "nifty_50"}:
        syms = list(NIFTY_50_SECTORS.keys())
    elif u in {"banknifty", "bank_nifty"}:
        syms = list(BANK_NIFTY_SYMBOLS)
    elif u in {"finnifty", "fin_nifty"}:
        syms = list(FIN_NIFTY_SYMBOLS)
    elif u in {"niftynext50", "nifty_next_50"}:
        syms = list(NIFTY_NEXT_50_SAMPLE)
    elif u in {"nifty100", "nifty_100"}:
        syms = list(NIFTY_50_SECTORS.keys()) + NIFTY_NEXT_50_SAMPLE
    elif u in {"midcap_smallcap", "midcap150", "smallcap250"}:
        syms = list(MIDCAP_SMALLCAP_ACTIVE)
    elif u in {"all", "nse_all", "nifty500", "nifty_500"}:
        master = fetch_nse_equity_master()
        priority = list(NIFTY_50_SECTORS.keys()) + NIFTY_NEXT_50_SAMPLE + MIDCAP_SMALLCAP_ACTIVE
        seen = set(priority)
        extra = [e["symbol"] for e in master.get("equities", []) if e["symbol"] not in seen]
        syms = priority + extra
    else:
        syms = list(NIFTY_50_SECTORS.keys())
    return syms[:limit] if limit > 0 else syms


def search_symbols(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    q = query.strip()
    if not q:
        return []
    try:
        from backend.database.stock_master_db import search_stock_master
        rows = search_stock_master(query=q, limit=limit)
        return [
            {
                "stock_id": r.get("stock_id"),
                "symbol": r.get("nse_symbol") or r.get("bse_code") or r.get("stock_id"),
                "nse_symbol": r.get("nse_symbol"),
                "bse_code": r.get("bse_code"),
                "name": r.get("company_name"),
                "company_name": r.get("company_name"),
                "series": r.get("series") or "EQ",
                "isin": r.get("isin") or "",
                "exchange": r.get("exchange") or "NSE",
                "sector": r.get("sector") or "Indian Equities",
                "industry": r.get("industry") or "Indian Listed Equity",
                "market_cap_cr": r.get("market_cap_cr"),
                "cap_tier": r.get("cap_tier"),
                "trading_status": r.get("trading_status") or "ACTIVE",
                "screener_url": r.get("screener_url"),
            }
            for r in rows
        ]
    except Exception:
        qu = q.upper()
        master = fetch_nse_equity_master()
        matches: List[Dict[str, Any]] = []
        for eq in master.get("equities", []):
            if qu in eq["symbol"].upper() or qu in eq["name"].upper() or qu in eq.get("isin", "").upper():
                matches.append(eq)
                if len(matches) >= limit:
                    break
        return matches

