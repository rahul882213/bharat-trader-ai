"""Central Universal Stock Master Database (NSE EQ + NSE SME + BSE Aliases + Dynamic Discovery)."""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import get_symbol_sector, normalize_symbol
from backend.database.db import execute_many, execute_sql, get_kv, query_all, set_kv

IST = ZoneInfo("Asia/Kolkata")
NSE_EQ_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_SME_URL = "https://archives.nseindia.com/content/equities/SME_EQUITY_L.csv"
USER_AGENT = "Mozilla/5.0 (compatible; BharatTraderAI/1.0)"

# Canonical enrichment for BSE codes, SME suffixes, common alternative spellings & sectors
KNOWN_EQUITY_ENRICHMENT: List[Dict[str, Any]] = [
    {"isin": "INE002A01018", "nse_symbol": "RELIANCE", "bse_code": "500325", "company_name": "Reliance Industries Limited", "sector": "Energy", "industry": "Refineries & Petrochemicals", "cap_tier": "Large Cap"},
    {"isin": "INE467B01029", "nse_symbol": "TCS", "bse_code": "532540", "company_name": "Tata Consultancy Services Limited", "sector": "IT", "industry": "IT Services & Consulting", "cap_tier": "Large Cap"},
    {"isin": "INE040A01034", "nse_symbol": "HDFCBANK", "bse_code": "500180", "company_name": "HDFC Bank Limited", "sector": "Banking", "industry": "Private Sector Bank", "cap_tier": "Large Cap"},
    {"isin": "INE066F01020", "nse_symbol": "HAL", "bse_code": "541154", "company_name": "Hindustan Aeronautics Limited", "sector": "Defence", "industry": "Aerospace & Defence", "cap_tier": "Large Cap"},
    {"isin": "INE249Z01020", "nse_symbol": "MAZDOCK", "bse_code": "543237", "company_name": "Mazagon Dock Shipbuilders Limited", "sector": "Defence", "industry": "Shipbuilding & Defence", "cap_tier": "Mid Cap"},
    {"isin": "INE0M2301015", "nse_symbol": "ORIANA", "bse_code": "", "yahoo_symbol": "ORIANA.NS", "company_name": "Oriana Power Limited", "sector": "Renewables", "industry": "Solar EPC & Clean Energy", "exchange": "NSE", "cap_tier": "Small Cap", "aliases": ["ORIANAPOWER", "ORIANA POWER", "ORIANA-SM"]},
    {"isin": "INE292B01021", "nse_symbol": "HBLENGINE", "bse_code": "517271", "company_name": "HBL Engineering Limited", "sector": "Capital Goods", "industry": "Industrial Batteries & Railway Electronics", "cap_tier": "Mid Cap", "aliases": ["HBLENGINEERING", "HBL POWER", "HBLPOWER"]},
    {"isin": "INE0Q3J01015", "nse_symbol": "KRN", "bse_code": "544263", "company_name": "KRN Heat Exchanger and Refrigeration Limited", "sector": "Capital Goods", "industry": "HVAC & Heat Exchangers", "cap_tier": "Small Cap", "aliases": ["KRN HEAT EXCHANGER"]},
    {"isin": "INE732A01036", "nse_symbol": "KIRLOSBROS", "bse_code": "500241", "company_name": "Kirloskar Brothers Limited", "sector": "Capital Goods", "industry": "Pumps & Fluid Management", "cap_tier": "Small Cap", "aliases": ["KIRLOSKAR BROTHERS"]},
    {"isin": "INE024F01011", "nse_symbol": "SHILCTECH", "bse_code": "531201", "company_name": "Shilchar Technologies Limited", "sector": "Capital Goods", "industry": "Power & Electronics Transformers", "cap_tier": "Small Cap", "aliases": ["SHILCHAR", "SHILCHAR TECHNOLOGIES"]},
    {"isin": "INE200A01026", "nse_symbol": "GVT&D", "bse_code": "522275", "company_name": "GE Vernova T&D India Limited", "sector": "Power", "industry": "Transmission & Distribution Equipment", "cap_tier": "Mid Cap", "aliases": ["GEVERNOVA", "GE VERNOVA", "GET&D"]},
    {"isin": "INE531E01026", "nse_symbol": "HINDCOPPER", "bse_code": "513599", "company_name": "Hindustan Copper Limited", "sector": "Metals", "industry": "Copper Mining & Smelting", "cap_tier": "Mid Cap", "aliases": ["HINDUSTAN COPPER"]},
    {"isin": "INE009A01021", "nse_symbol": "INFY", "bse_code": "500209", "company_name": "Infosys Limited", "sector": "IT", "industry": "IT Services & Consulting", "cap_tier": "Large Cap"},
    {"isin": "INE090A01021", "nse_symbol": "ICICIBANK", "bse_code": "532174", "company_name": "ICICI Bank Limited", "sector": "Banking", "industry": "Private Sector Bank", "cap_tier": "Large Cap"},
    {"isin": "INE062A01020", "nse_symbol": "SBIN", "bse_code": "500112", "company_name": "State Bank of India", "sector": "Banking", "industry": "Public Sector Bank", "cap_tier": "Large Cap"},
    {"isin": "INE018A01030", "nse_symbol": "LT", "bse_code": "500510", "company_name": "Larsen & Toubro Limited", "sector": "Infrastructure", "industry": "EPC & Heavy Engineering", "cap_tier": "Large Cap"},
    {"isin": "INE155A01022", "nse_symbol": "TATAMOTORS", "bse_code": "500570", "company_name": "Tata Motors Limited", "sector": "Auto", "industry": "Automobiles", "cap_tier": "Large Cap"},
    {"isin": "INE397D01024", "nse_symbol": "BHARTIARTL", "bse_code": "532454", "company_name": "Bharti Airtel Limited", "sector": "Telecom", "industry": "Telecom Services", "cap_tier": "Large Cap"},
    {"isin": "INE044A01036", "nse_symbol": "SUNPHARMA", "bse_code": "524715", "company_name": "Sun Pharmaceutical Industries Limited", "sector": "Pharma", "industry": "Pharmaceuticals", "cap_tier": "Large Cap"},
]


def classify_cap_tier(market_cap_cr: Optional[float]) -> Optional[str]:
    if market_cap_cr is None or market_cap_cr <= 0:
        return None
    if market_cap_cr >= 20000:
        return "Large Cap"
    if market_cap_cr >= 5000:
        return "Mid Cap"
    if market_cap_cr >= 500:
        return "Small Cap"
    return "Micro Cap"


def _fetch_csv_rows(url: str) -> List[Dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def sync_stock_master(force: bool = False) -> Dict[str, Any]:
    """Populate central `stocks_master` table from NSE Mainboard EQ + NSE SME + curated BSE/alias enrichments."""
    last_sync = get_kv("stocks_master_synced_at")
    existing_cnt_rows = query_all("SELECT COUNT(*) AS cnt FROM stocks_master")
    existing_cnt = int(existing_cnt_rows[0]["cnt"]) if existing_cnt_rows else 0

    if not force and existing_cnt >= 1000 and last_sync:
        return {"synced": False, "count": existing_cnt, "last_synced_at": last_sync}

    now = datetime.now(tz=IST).isoformat()
    records_by_id: Dict[str, Dict[str, Any]] = {}
    enrichment_by_isin = {e["isin"]: e for e in KNOWN_EQUITY_ENRICHMENT if e.get("isin")}
    enrichment_by_nse = {e["nse_symbol"]: e for e in KNOWN_EQUITY_ENRICHMENT if e.get("nse_symbol")}

    # 1. Load NSE Mainboard & SME CSVs
    for exchange_label, url in [("NSE", NSE_EQ_URL), ("NSE-SME", NSE_SME_URL)]:
        try:
            rows = _fetch_csv_rows(url)
            for r in rows:
                sym = (r.get("SYMBOL") or "").strip().upper()
                name = (r.get("NAME OF COMPANY") or "").strip()
                series = (r.get(" SERIES") or r.get("SERIES") or "EQ").strip().upper()
                isin = (r.get(" ISIN NUMBER") or r.get("ISIN NUMBER") or "").strip().upper()
                if not sym or not name:
                    continue
                if exchange_label == "NSE" and series not in {"EQ", "BE", "BZ", "SM", "ST"}:
                    continue
                stock_id = isin or f"{exchange_label}:{sym}"
                enr = enrichment_by_isin.get(isin) or enrichment_by_nse.get(sym) or {}
                yahoo_sym = enr.get("yahoo_symbol") or (
                    f"{sym}-SM.NS" if (exchange_label == "NSE-SME" or series in {"SM", "ST"}) else f"{sym}.NS"
                )
                records_by_id[stock_id] = {
                    "stock_id": stock_id,
                    "isin": isin or None,
                    "nse_symbol": sym,
                    "bse_code": enr.get("bse_code", ""),
                    "yahoo_symbol": yahoo_sym,
                    "company_name": enr.get("company_name") or name,
                    "series": series,
                    "sector": enr.get("sector") or get_symbol_sector(sym),
                    "industry": enr.get("industry") or "Indian Listed Equity",
                    "exchange": enr.get("exchange") or exchange_label,
                    "market_cap_cr": enr.get("market_cap_cr"),
                    "cap_tier": enr.get("cap_tier"),
                    "trading_status": "ACTIVE",
                    "screener_url": f"https://www.screener.in/company/{sym}/",
                    "aliases_json": json.dumps(enr.get("aliases", [])),
                    "updated_at": now,
                }
        except Exception:
            pass

    # 2. Ensure all enrichment entries (e.g. ORIANA SME if SME CSV was short) are present
    for enr in KNOWN_EQUITY_ENRICHMENT:
        sid = enr.get("isin") or f"NSE:{enr['nse_symbol']}"
        if sid not in records_by_id:
            sym = enr["nse_symbol"]
            records_by_id[sid] = {
                "stock_id": sid,
                "isin": enr.get("isin"),
                "nse_symbol": sym,
                "bse_code": enr.get("bse_code", ""),
                "yahoo_symbol": enr.get("yahoo_symbol") or f"{sym}.NS",
                "company_name": enr["company_name"],
                "series": "SM" if enr.get("exchange") == "NSE-SME" else "EQ",
                "sector": enr.get("sector", "Indian Equities"),
                "industry": enr.get("industry", "Indian Listed Equity"),
                "exchange": enr.get("exchange", "NSE"),
                "market_cap_cr": enr.get("market_cap_cr"),
                "cap_tier": enr.get("cap_tier"),
                "trading_status": "ACTIVE",
                "screener_url": f"https://www.screener.in/company/{sym}/",
                "aliases_json": json.dumps(enr.get("aliases", [])),
                "updated_at": now,
            }

    tuples = [
        (
            v["stock_id"],
            v["isin"],
            v["nse_symbol"],
            v["bse_code"],
            v["yahoo_symbol"],
            v["company_name"],
            v["series"],
            v["sector"],
            v["industry"],
            v["exchange"],
            v["market_cap_cr"],
            v["cap_tier"],
            v["trading_status"],
            v["screener_url"],
            v["aliases_json"],
            v["updated_at"],
        )
        for v in records_by_id.values()
    ]
    if tuples:
        execute_many(
            """
            INSERT INTO stocks_master
            (stock_id, isin, nse_symbol, bse_code, yahoo_symbol, company_name, series, sector, industry, exchange,
             market_cap_cr, cap_tier, trading_status, screener_url, aliases_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_id) DO UPDATE SET
                nse_symbol = COALESCE(NULLIF(excluded.nse_symbol, ''), stocks_master.nse_symbol),
                bse_code = COALESCE(NULLIF(excluded.bse_code, ''), stocks_master.bse_code),
                yahoo_symbol = COALESCE(NULLIF(excluded.yahoo_symbol, ''), stocks_master.yahoo_symbol),
                company_name = excluded.company_name,
                sector = CASE WHEN stocks_master.sector = 'Indian Equities' THEN excluded.sector ELSE stocks_master.sector END,
                industry = CASE WHEN stocks_master.industry = 'Indian Listed Equity' THEN excluded.industry ELSE stocks_master.industry END,
                aliases_json = CASE WHEN excluded.aliases_json != '[]' THEN excluded.aliases_json ELSE stocks_master.aliases_json END,
                updated_at = excluded.updated_at
            """,
            tuples,
        )
        set_kv("stocks_master_synced_at", now, now)

    cnt = query_all("SELECT COUNT(*) AS cnt FROM stocks_master")[0]["cnt"]
    return {"synced": True, "count": cnt, "last_synced_at": now}


def upsert_stock_record(record: Dict[str, Any]) -> str:
    """Insert or update a stock in the central Stock Master DB and return its canonical stock_id."""
    now = datetime.now(tz=IST).isoformat()
    isin = (record.get("isin") or "").strip().upper() or None
    nse = normalize_symbol(record.get("nse_symbol") or "") if record.get("nse_symbol") else None
    bse = (record.get("bse_code") or "").strip() or None

    # Find existing by ISIN, NSE symbol, or BSE code
    existing: List[Dict[str, Any]] = []
    if isin:
        existing = query_all("SELECT * FROM stocks_master WHERE isin = ?", (isin,))
    if not existing and nse:
        existing = query_all("SELECT * FROM stocks_master WHERE UPPER(nse_symbol) = ?", (nse,))
    if not existing and bse:
        existing = query_all("SELECT * FROM stocks_master WHERE bse_code = ?", (bse,))

    if existing:
        cur = existing[0]
        stock_id = cur["stock_id"]
        mcap = record.get("market_cap_cr") if record.get("market_cap_cr") is not None else cur.get("market_cap_cr")
        cap_tier = record.get("cap_tier") or cur.get("cap_tier") or classify_cap_tier(mcap)
        execute_sql(
            """
            UPDATE stocks_master SET
                isin = COALESCE(?, isin),
                nse_symbol = COALESCE(NULLIF(?, ''), nse_symbol),
                bse_code = COALESCE(NULLIF(?, ''), bse_code),
                yahoo_symbol = COALESCE(NULLIF(?, ''), yahoo_symbol),
                company_name = COALESCE(NULLIF(?, ''), company_name),
                sector = COALESCE(NULLIF(?, ''), sector),
                industry = COALESCE(NULLIF(?, ''), industry),
                market_cap_cr = COALESCE(?, market_cap_cr),
                cap_tier = COALESCE(?, cap_tier),
                screener_url = COALESCE(NULLIF(?, ''), screener_url),
                updated_at = ?
            WHERE stock_id = ?
            """,
            (
                isin,
                nse,
                bse,
                record.get("yahoo_symbol"),
                record.get("company_name"),
                record.get("sector"),
                record.get("industry"),
                mcap,
                cap_tier,
                record.get("screener_url"),
                now,
                stock_id,
            ),
        )
        return stock_id

    stock_id = isin or (f"NSE:{nse}" if nse else f"BSE:{bse or record.get('company_name','UNKNOWN')[:20].upper()}")
    mcap = record.get("market_cap_cr")
    cap_tier = record.get("cap_tier") or classify_cap_tier(mcap)
    yahoo_sym = record.get("yahoo_symbol") or (f"{nse}.NS" if nse else (f"{bse}.BO" if bse else None))
    execute_sql(
        """
        INSERT INTO stocks_master
        (stock_id, isin, nse_symbol, bse_code, yahoo_symbol, company_name, series, sector, industry, exchange,
         market_cap_cr, cap_tier, trading_status, screener_url, aliases_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'EQ', ?, ?, ?, ?, ?, 'ACTIVE', ?, '[]', ?)
        """,
        (
            stock_id,
            isin,
            nse,
            bse or "",
            yahoo_sym,
            record.get("company_name") or nse or bse or stock_id,
            record.get("sector") or (get_symbol_sector(nse) if nse else "Indian Equities"),
            record.get("industry") or "Indian Listed Equity",
            record.get("exchange") or ("BSE" if bse and not nse else "NSE"),
            mcap,
            cap_tier,
            record.get("screener_url") or (f"https://www.screener.in/company/{nse or bse}/" if (nse or bse) else None),
            now,
        ),
    )
    return stock_id


def _discover_via_yahoo(query: str) -> Optional[Dict[str, Any]]:
    """Fallback discovery for unlisted/BSE/SME symbols via Yahoo Search (labeled unofficial)."""
    try:
        u = f"https://query1.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(query)}&quotesCount=6&newsCount=0"
        req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT})
        data = json.loads(urllib.request.urlopen(req, timeout=6).read().decode("utf-8"))
        for q in data.get("quotes", []):
            exch = q.get("exchange")
            ysym = q.get("symbol", "")
            if exch in {"NSI", "BSE", "BOM"} and (ysym.endswith(".NS") or ysym.endswith(".BO")):
                base = ysym.rsplit(".", 1)[0].replace("-SM", "")
                is_bse = ysym.endswith(".BO")
                record = {
                    "nse_symbol": None if is_bse else base,
                    "bse_code": base if is_bse and base.isdigit() else "",
                    "yahoo_symbol": ysym,
                    "company_name": q.get("longname") or q.get("shortname") or base,
                    "sector": q.get("sectorDisp") or "Indian Equities",
                    "industry": q.get("industryDisp") or "Indian Listed Equity",
                    "exchange": "BSE" if is_bse else ("NSE-SME" if "-SM.NS" in ysym else "NSE"),
                }
                sid = upsert_stock_record(record)
                rows = query_all("SELECT * FROM stocks_master WHERE stock_id = ?", (sid,))
                return rows[0] if rows else None
    except Exception:
        pass
    return None


def resolve_stock(identifier: str, exchange: Optional[str] = None) -> Dict[str, Any]:
    """
    Resolve ANY Indian stock identifier (ISIN, NSE symbol, BSE code, alias, or company name)
    to its canonical central database record.
    """
    sync_stock_master(force=False)
    raw = (identifier or "").strip()
    upper = raw.upper()
    clean = normalize_symbol(upper)

    # 1. Exact match on stock_id / ISIN / NSE symbol / BSE code
    rows = query_all(
        """
        SELECT * FROM stocks_master
        WHERE UPPER(stock_id) = ?
           OR UPPER(isin) = ?
           OR UPPER(nse_symbol) = ?
           OR UPPER(bse_code) = ?
        LIMIT 1
        """,
        (upper, upper, clean, clean),
    )
    if rows:
        rec = dict(rows[0])
        if exchange and exchange.upper() == "BSE" and rec.get("bse_code"):
            rec["effective_yahoo_symbol"] = f"{rec['bse_code']}.BO" if rec["bse_code"].isdigit() else f"{rec['nse_symbol']}.BO"
        else:
            rec["effective_yahoo_symbol"] = rec.get("yahoo_symbol") or f"{rec.get('nse_symbol') or clean}.NS"
        return rec

    # 2. Match in aliases_json (e.g., ORIANAPOWER -> ORIANA, HBLENGINEERING -> HBLENGINE, SHILCHAR -> SHILCTECH, GEVERNOVA -> GVT&D)
    alias_rows = query_all(
        """
        SELECT * FROM stocks_master
        WHERE UPPER(aliases_json) LIKE ?
           OR UPPER(company_name) LIKE ?
        ORDER BY CASE WHEN UPPER(aliases_json) LIKE ? THEN 0 ELSE 1 END, LENGTH(company_name) ASC
        LIMIT 1
        """,
        (f'%"{clean}"%', f"%{upper}%", f'%"{clean}"%'),
    )
    if alias_rows:
        rec = dict(alias_rows[0])
        rec["effective_yahoo_symbol"] = rec.get("yahoo_symbol") or f"{rec.get('nse_symbol') or clean}.NS"
        return rec

    # 3. Dynamic discovery via Yahoo Search
    discovered = _discover_via_yahoo(raw)
    if discovered:
        discovered["effective_yahoo_symbol"] = discovered.get("yahoo_symbol")
        return discovered

    # 4. Graceful fallback object (do not fail silently)
    fallback_sym = clean
    return {
        "stock_id": f"NSE:{fallback_sym}",
        "isin": None,
        "nse_symbol": fallback_sym,
        "bse_code": "",
        "yahoo_symbol": f"{fallback_sym}.BO" if (exchange or "").upper() == "BSE" else f"{fallback_sym}.NS",
        "effective_yahoo_symbol": f"{fallback_sym}.BO" if (exchange or "").upper() == "BSE" else f"{fallback_sym}.NS",
        "company_name": fallback_sym,
        "sector": get_symbol_sector(fallback_sym),
        "industry": "Indian Listed Equity",
        "exchange": (exchange or "NSE").upper(),
        "market_cap_cr": None,
        "cap_tier": None,
        "trading_status": "UNVERIFIED",
        "screener_url": f"https://www.screener.in/company/{fallback_sym}/",
    }


def search_stock_master(
    query: str = "",
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    cap_tier: Optional[str] = None,
    exchange: Optional[str] = None,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """Global search across Company Name, NSE Symbol, BSE Code, ISIN, Sector, Industry, and Aliases."""
    sync_stock_master(force=False)
    clauses: List[str] = []
    params: List[Any] = []

    q = (query or "").strip()
    if q:
        qu = q.upper()
        like = f"%{qu}%"
        clauses.append(
            "(UPPER(nse_symbol) LIKE ? OR UPPER(bse_code) LIKE ? OR UPPER(isin) LIKE ? "
            "OR UPPER(company_name) LIKE ? OR UPPER(sector) LIKE ? OR UPPER(industry) LIKE ? OR UPPER(aliases_json) LIKE ?)"
        )
        params.extend([like, like, like, like, like, like, like])

    if sector and sector != "ALL":
        clauses.append("LOWER(sector) = LOWER(?)")
        params.append(sector)
    if industry and industry != "ALL":
        clauses.append("LOWER(industry) = LOWER(?)")
        params.append(industry)
    if cap_tier and cap_tier != "ALL":
        clauses.append("LOWER(cap_tier) = LOWER(?)")
        params.append(cap_tier)
    if exchange and exchange != "ALL":
        clauses.append("UPPER(exchange) LIKE ?")
        params.append(f"{exchange.upper()}%")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    qu_exact = normalize_symbol(q) if q else ""
    sql = f"""
        SELECT * FROM stocks_master
        {where_sql}
        ORDER BY
            CASE
                WHEN UPPER(nse_symbol) = ? THEN 0
                WHEN UPPER(bse_code) = ? THEN 0
                WHEN UPPER(aliases_json) LIKE ? THEN 1
                WHEN UPPER(nse_symbol) LIKE ? THEN 2
                WHEN UPPER(company_name) LIKE ? THEN 3
                ELSE 4
            END,
            COALESCE(market_cap_cr, 0) DESC,
            company_name ASC
        LIMIT ?
    """
    params.extend([qu_exact, qu_exact, f'%"{qu_exact}"%', f"{qu_exact}%", f"{q.upper()}%", limit])
    return query_all(sql, tuple(params))


def get_master_stats() -> Dict[str, Any]:
    sync_stock_master(force=False)
    total = query_all("SELECT COUNT(*) AS c FROM stocks_master")[0]["c"]
    screener_linked = query_all("SELECT COUNT(DISTINCT stock_id) AS c FROM screener_company_data")[0]["c"]
    sectors = [r["sector"] for r in query_all("SELECT DISTINCT sector FROM stocks_master WHERE sector IS NOT NULL ORDER BY sector")]
    industries = [r["industry"] for r in query_all("SELECT DISTINCT industry FROM stocks_master WHERE industry IS NOT NULL ORDER BY industry")]
    return {
        "total_stocks": total,
        "screener_imported_stocks": screener_linked,
        "sectors": sectors,
        "industries": industries,
        "last_synced_at": get_kv("stocks_master_synced_at"),
    }
