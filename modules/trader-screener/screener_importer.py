"""Module 12: Screener.in CSV & Excel (.xlsx) Importer, Deduplication & Data Center Storage."""
from __future__ import annotations

import csv
import io
import json
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import normalize_symbol
from backend.database.db import execute_sql, query_all
from backend.database.stock_master_db import classify_cap_tier, resolve_stock, upsert_stock_record

IST = ZoneInfo("Asia/Kolkata")
EXCEL_EPOCH = datetime(1899, 12, 30)


def _to_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s in {"-", "--", "NA", "N/A", "None", "null"}:
        return None
    s = s.replace(",", "").replace("₹", "").replace("%", "").replace("Cr.", "").replace("Cr", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _col_letter_to_idx(col_ref: str) -> int:
    idx = 0
    for ch in col_ref:
        if ch.isalpha():
            idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return max(idx - 1, 0)


def _format_excel_period(val: Any) -> str:
    if isinstance(val, (int, float)) and 20000 < val < 80000:
        dt = EXCEL_EPOCH + timedelta(days=int(round(val)))
        return dt.strftime("%b %Y")
    s = str(val or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
            return dt.strftime("%b %Y")
        except Exception:
            pass
    return s


def parse_xlsx_sheets(xlsx_bytes: bytes) -> Dict[str, List[List[Any]]]:
    """Pure Python standard-library .xlsx parser (no openpyxl/pandas dependency required)."""
    sheets_out: Dict[str, List[List[Any]]] = {}
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes), "r") as zf:
        names = set(zf.namelist())
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in names:
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                texts = [t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")]
                shared_strings.append("".join(texts))

        rels: Dict[str, str] = {}
        if "xl/_rels/workbook.xml.rels" in names:
            rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            for rel in rel_root:
                rid = rel.attrib.get("Id")
                target = rel.attrib.get("Target", "").lstrip("/")
                if rid and target:
                    rels[rid] = target if target.startswith("xl/") else f"xl/{target}"

        wb_sheets: List[Tuple[str, str]] = []
        if "xl/workbook.xml" in names:
            wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
            for sh in wb_root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"):
                sh_name = sh.attrib.get("name", "Sheet")
                rid = sh.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                target = rels.get(rid or "", "")
                if target in names:
                    wb_sheets.append((sh_name, target))

        if not wb_sheets:
            for nm in sorted(names):
                if nm.startswith("xl/worksheets/sheet") and nm.endswith(".xml"):
                    wb_sheets.append((nm.rsplit("/", 1)[-1], nm))

        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        for sh_name, target in wb_sheets:
            sh_root = ET.fromstring(zf.read(target))
            rows_data: List[List[Any]] = []
            for row_el in sh_root.iter(f"{ns}row"):
                row_map: Dict[int, Any] = {}
                max_col = -1
                for c_el in row_el.findall(f"{ns}c"):
                    ref = c_el.attrib.get("r", "")
                    col_idx = _col_letter_to_idx(ref) if ref else (max_col + 1)
                    max_col = max(max_col, col_idx)
                    c_type = c_el.attrib.get("t", "")
                    val: Any = None
                    if c_type == "inlineStr":
                        texts = [t.text or "" for t in c_el.iter(f"{ns}t")]
                        val = "".join(texts)
                    else:
                        v_el = c_el.find(f"{ns}v")
                        if v_el is not None and v_el.text is not None:
                            raw_v = v_el.text
                            if c_type == "s":
                                try:
                                    val = shared_strings[int(raw_v)]
                                except Exception:
                                    val = raw_v
                            elif c_type in {"str", "e"}:
                                val = raw_v
                            elif c_type == "b":
                                val = raw_v == "1"
                            else:
                                try:
                                    num = float(raw_v)
                                    val = int(num) if num.is_integer() else num
                                except ValueError:
                                    val = raw_v
                    row_map[col_idx] = val
                if max_col >= 0:
                    rows_data.append([row_map.get(i) for i in range(max_col + 1)])
            sheets_out[sh_name] = rows_data
    return sheets_out


def _extract_screener_horizontal_table(rows: List[List[Any]]) -> List[Dict[str, Any]]:
    """Convert Screener horizontal Excel table (Col A = Metric Name, Row Header = Periods) into period records."""
    if not rows:
        return []
    header_idx = -1
    periods: List[str] = []
    for i, r in enumerate(rows[:15]):
        non_empty = [x for x in r[1:] if x not in (None, "")]
        if len(non_empty) >= 2:
            # Look for date/month/year headers like Mar 2021, 2024-03-31, or Excel serials
            sample = _format_excel_period(non_empty[0])
            if re.search(r"(20\d{2}|19\d{2}|TTM|Mar|Jun|Sep|Dec|FY)", sample, re.I):
                header_idx = i
                periods = [_format_excel_period(c) for c in r[1:]]
                break
    if header_idx < 0:
        return []

    period_records: List[Dict[str, Any]] = [{"period": p} for p in periods if p]
    for r in rows[header_idx + 1 :]:
        if not r or r[0] in (None, ""):
            continue
        label = str(r[0]).strip()
        if not label:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        for idx, p_name in enumerate(periods):
            if not p_name or idx >= len(period_records):
                continue
            val = _to_float(r[idx + 1]) if (idx + 1) < len(r) else None
            if val is not None:
                period_records[idx][key] = val
    return [p for p in period_records if len(p) > 1]


def _extract_symbol_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"screener\.in/company/([^/]+)/", url, re.I)
    return m.group(1).strip().upper() if m else None


def _audit_missing_fields(
    ratios: Dict[str, Any],
    pnl: List[Dict[str, Any]],
    quarters: List[Dict[str, Any]],
    balance_sheet: List[Dict[str, Any]],
    cash_flow: List[Dict[str, Any]],
    shareholding: List[Dict[str, Any]],
) -> List[str]:
    missing: List[str] = []
    if not ratios.get("market_cap_cr"):
        missing.append("Market Cap (₹ Cr)")
    if not ratios.get("pe"):
        missing.append("Stock P/E")
    if not ratios.get("roce_pct"):
        missing.append("ROCE %")
    if not ratios.get("roe_pct"):
        missing.append("ROE %")
    if not pnl:
        missing.append("Multi-Year Profit & Loss Statement")
    if not quarters:
        missing.append("Quarterly Results")
    if not balance_sheet:
        missing.append("Balance Sheet")
    if not cash_flow:
        missing.append("Cash Flow Statement")
    if not shareholding:
        missing.append("Shareholding Pattern")
    return missing


def _save_screener_company_record(
    stock_meta: Dict[str, Any],
    source: str,
    statement_scope: str,
    reporting_period: Optional[str],
    is_estimated: bool,
    ratios: Dict[str, Any],
    pnl: List[Dict[str, Any]],
    quarters: List[Dict[str, Any]],
    balance_sheet: List[Dict[str, Any]],
    cash_flow: List[Dict[str, Any]],
    shareholding: List[Dict[str, Any]],
    business_notes: Optional[Dict[str, Any]] = None,
    screener_url: Optional[str] = None,
    update_existing: bool = True,
) -> Dict[str, Any]:
    now = datetime.now(tz=IST).isoformat()
    stock_id = stock_meta["stock_id"]

    existing = query_all(
        "SELECT * FROM screener_company_data WHERE stock_id = ? ORDER BY imported_at DESC LIMIT 1",
        (stock_id,),
    )
    duplicate_detected = len(existing) > 0
    if duplicate_detected and not update_existing:
        return {
            "stock_id": stock_id,
            "symbol": stock_meta.get("nse_symbol") or stock_meta.get("bse_code") or stock_id,
            "company_name": stock_meta.get("company_name"),
            "action": "SKIPPED_DUPLICATE",
            "duplicate_detected": True,
        }

    # Preserve previously imported tables/notes if new upload only updates ratios (e.g. Stock Screen CSV)
    prev = existing[0] if existing else {}
    merged_ratios = {**(json.loads(prev.get("ratios_json") or "{}")), **{k: v for k, v in ratios.items() if v is not None}}
    final_pnl = pnl if pnl else json.loads(prev.get("pnl_annual_json") or "[]")
    final_qtr = quarters if quarters else json.loads(prev.get("quarters_json") or "[]")
    final_bs = balance_sheet if balance_sheet else json.loads(prev.get("balance_sheet_json") or "[]")
    final_cf = cash_flow if cash_flow else json.loads(prev.get("cash_flow_json") or "[]")
    final_sh = shareholding if shareholding else json.loads(prev.get("shareholding_json") or "[]")
    merged_notes = {**(json.loads(prev.get("business_notes_json") or "{}")), **(business_notes or {})}
    final_url = screener_url or prev.get("screener_url") or stock_meta.get("screener_url")

    missing = _audit_missing_fields(merged_ratios, final_pnl, final_qtr, final_bs, final_cf, final_sh)
    final_period = reporting_period or (final_qtr[-1]["period"] if final_qtr else (final_pnl[-1]["period"] if final_pnl else "Latest Available"))

    execute_sql(
        """
        INSERT INTO screener_company_data
        (stock_id, company_name, nse_symbol, bse_code, isin, screener_url, source, statement_scope,
         reporting_period, is_estimated, ratios_json, pnl_annual_json, quarters_json, balance_sheet_json,
         cash_flow_json, shareholding_json, business_notes_json, peers_json, missing_fields_json, imported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)
        ON CONFLICT(stock_id, source, statement_scope) DO UPDATE SET
            company_name = excluded.company_name,
            nse_symbol = COALESCE(NULLIF(excluded.nse_symbol, ''), screener_company_data.nse_symbol),
            bse_code = COALESCE(NULLIF(excluded.bse_code, ''), screener_company_data.bse_code),
            isin = COALESCE(NULLIF(excluded.isin, ''), screener_company_data.isin),
            screener_url = COALESCE(NULLIF(excluded.screener_url, ''), screener_company_data.screener_url),
            reporting_period = excluded.reporting_period,
            ratios_json = excluded.ratios_json,
            pnl_annual_json = excluded.pnl_annual_json,
            quarters_json = excluded.quarters_json,
            balance_sheet_json = excluded.balance_sheet_json,
            cash_flow_json = excluded.cash_flow_json,
            shareholding_json = excluded.shareholding_json,
            business_notes_json = excluded.business_notes_json,
            missing_fields_json = excluded.missing_fields_json,
            imported_at = excluded.imported_at
        """,
        (
            stock_id,
            stock_meta.get("company_name"),
            stock_meta.get("nse_symbol"),
            stock_meta.get("bse_code"),
            stock_meta.get("isin"),
            final_url,
            source,
            statement_scope,
            final_period,
            1 if is_estimated else 0,
            json.dumps(merged_ratios),
            json.dumps(final_pnl),
            json.dumps(final_qtr),
            json.dumps(final_bs),
            json.dumps(final_cf),
            json.dumps(final_sh),
            json.dumps(merged_notes),
            json.dumps(missing),
            now,
        ),
    )

    if merged_ratios.get("market_cap_cr") or final_url:
        mcap = merged_ratios.get("market_cap_cr")
        upsert_stock_record({
            "isin": stock_meta.get("isin"),
            "nse_symbol": stock_meta.get("nse_symbol"),
            "bse_code": stock_meta.get("bse_code"),
            "company_name": stock_meta.get("company_name"),
            "market_cap_cr": mcap,
            "cap_tier": classify_cap_tier(mcap) if mcap else None,
            "screener_url": final_url,
        })

    return {
        "stock_id": stock_id,
        "symbol": stock_meta.get("nse_symbol") or stock_meta.get("bse_code") or stock_id,
        "company_name": stock_meta.get("company_name"),
        "isin": stock_meta.get("isin"),
        "action": "UPDATED_EXISTING" if duplicate_detected else "INSERTED_NEW",
        "duplicate_detected": duplicate_detected,
        "missing_fields": missing,
        "reporting_period": final_period,
    }


def import_screener_xlsx(
    xlsx_bytes: bytes,
    filename: str = "screener_company.xlsx",
    symbol_hint: Optional[str] = None,
    screener_url: Optional[str] = None,
    statement_scope: str = "Consolidated",
    update_existing: bool = True,
) -> Dict[str, Any]:
    """Import a Screener.in exported company Excel (.xlsx) workbook."""
    sheets = parse_xlsx_sheets(xlsx_bytes)
    if not sheets:
        return {"success": False, "error": "Invalid or empty .xlsx file."}

    ratios: Dict[str, Any] = {}
    company_name = None

    # Parse 'Data Sheet' key-value metadata & ratios if present
    data_sheet_name = next((s for s in sheets if "data" in s.lower()), None)
    if data_sheet_name:
        for r in sheets[data_sheet_name]:
            if not r or len(r) < 2 or r[0] is None:
                continue
            k = str(r[0]).strip()
            v = r[1]
            kl = k.lower()
            if kl in {"company name", "name"} and v:
                company_name = str(v).strip()
            elif "market cap" in kl:
                ratios["market_cap_cr"] = _to_float(v)
            elif "current price" in kl or kl == "cmp":
                ratios["cmp_inr"] = _to_float(v)
            elif "stock p/e" in kl or kl == "p/e":
                ratios["pe"] = _to_float(v)
            elif "book value" in kl:
                ratios["book_value_inr"] = _to_float(v)
            elif "dividend yield" in kl:
                ratios["dividend_yield_pct"] = _to_float(v)
            elif "roce" in kl:
                ratios["roce_pct"] = _to_float(v)
            elif "roe" in kl:
                ratios["roe_pct"] = _to_float(v)
            elif "face value" in kl:
                ratios["face_value_inr"] = _to_float(v)
            elif "number of shares" in kl:
                ratios["shares_cr"] = _to_float(v)
            elif "bse" in kl and "code" in kl and v:
                ratios["bse_code"] = str(v).strip().split(".")[0]
            elif "nse" in kl and "code" in kl and v:
                ratios["nse_symbol"] = str(v).strip().upper()
            elif "isin" in kl and v:
                ratios["isin"] = str(v).strip().upper()

    # Fallback: scan Profit & Loss / Quarters / Balance Sheet / Cash Flow / Shareholding
    pnl = []
    quarters = []
    balance_sheet = []
    cash_flow = []
    shareholding = []

    for sname, srows in sheets.items():
        sl = sname.lower()
        if "profit" in sl or "p&l" in sl:
            pnl = _extract_screener_horizontal_table(srows)
        elif "quarter" in sl:
            quarters = _extract_screener_horizontal_table(srows)
        elif "balance" in sl:
            balance_sheet = _extract_screener_horizontal_table(srows)
        elif "cash" in sl:
            cash_flow = _extract_screener_horizontal_table(srows)
        elif "shareholding" in sl:
            shareholding = _extract_screener_horizontal_table(srows)

    # Also support Screener single 'Data Sheet' multi-section dump (where Quarters / Balance Sheet / Cash Flow appear as sub-headers inside Data Sheet)
    if data_sheet_name and not (pnl and quarters):
        ds_rows = sheets[data_sheet_name]
        section_starts: List[Tuple[str, int]] = []
        for idx, r in enumerate(ds_rows):
            if r and isinstance(r[0], str):
                lbl = r[0].strip().upper()
                if lbl in {"PROFIT & LOSS", "QUARTERS", "BALANCE SHEET", "CASH FLOW:", "CASH FLOW", "SHAREHOLDING PATTERN"}:
                    section_starts.append((lbl, idx))
        for i, (lbl, st) in enumerate(section_starts):
            end = section_starts[i + 1][1] if (i + 1) < len(section_starts) else len(ds_rows)
            tbl = _extract_screener_horizontal_table(ds_rows[st + 1 : end])
            if "PROFIT" in lbl and not pnl:
                pnl = tbl
            elif "QUARTER" in lbl and not quarters:
                quarters = tbl
            elif "BALANCE" in lbl and not balance_sheet:
                balance_sheet = tbl
            elif "CASH" in lbl and not cash_flow:
                cash_flow = tbl
            elif "SHAREHOLDING" in lbl and not shareholding:
                shareholding = tbl

    # Derive 5Y / 3Y sales & profit CAGR and margins if P&L exists
    if len(pnl) >= 2:
        sales_vals = [r.get("sales") for r in pnl if r.get("sales") is not None]
        np_vals = [r.get("net_profit") for r in pnl if r.get("net_profit") is not None]
        if len(sales_vals) >= 6 and sales_vals[-6] > 0 and sales_vals[-1] > 0:
            ratios["sales_growth_5y_pct"] = round((((sales_vals[-1] / sales_vals[-6]) ** (1 / 5)) - 1) * 100.0, 2)
        elif len(sales_vals) >= 4 and sales_vals[-4] > 0 and sales_vals[-1] > 0:
            ratios["sales_growth_3y_pct"] = round((((sales_vals[-1] / sales_vals[-4]) ** (1 / 3)) - 1) * 100.0, 2)
        if len(np_vals) >= 6 and np_vals[-6] > 0 and np_vals[-1] > 0:
            ratios["profit_growth_5y_pct"] = round((((np_vals[-1] / np_vals[-6]) ** (1 / 5)) - 1) * 100.0, 2)
        elif len(np_vals) >= 4 and np_vals[-4] > 0 and np_vals[-1] > 0:
            ratios["profit_growth_3y_pct"] = round((((np_vals[-1] / np_vals[-4]) ** (1 / 3)) - 1) * 100.0, 2)
        latest_p = pnl[-1]
        if latest_p.get("opm") is not None:
            ratios.setdefault("opm_pct", latest_p.get("opm"))
        elif latest_p.get("operating_profit") is not None and latest_p.get("sales"):
            ratios.setdefault("opm_pct", round((latest_p["operating_profit"] / latest_p["sales"]) * 100.0, 2))

    # Derive Debt / Equity if Balance Sheet exists
    if balance_sheet:
        bs_last = balance_sheet[-1]
        debt = bs_last.get("borrowings")
        eq_cap = bs_last.get("equity_share_capital") or bs_last.get("share_capital") or 0.0
        reserves = bs_last.get("reserves") or 0.0
        net_worth = eq_cap + reserves
        if debt is not None and net_worth > 0:
            ratios.setdefault("debt_to_equity", round(debt / net_worth, 2))
            ratios.setdefault("total_debt_cr", round(debt, 2))
            ratios.setdefault("net_worth_cr", round(net_worth, 2))

    url_sym = _extract_symbol_from_url(screener_url)
    lookup = ratios.get("isin") or ratios.get("nse_symbol") or symbol_hint or url_sym or ratios.get("bse_code") or company_name or filename.rsplit(".", 1)[0]
    stock_meta = resolve_stock(str(lookup))
    if company_name and stock_meta.get("trading_status") == "UNVERIFIED":
        sid = upsert_stock_record({
            "isin": ratios.get("isin"),
            "nse_symbol": ratios.get("nse_symbol") or symbol_hint or url_sym,
            "bse_code": ratios.get("bse_code"),
            "company_name": company_name,
            "market_cap_cr": ratios.get("market_cap_cr"),
            "screener_url": screener_url,
        })
        stock_meta = resolve_stock(sid)

    saved = _save_screener_company_record(
        stock_meta=stock_meta,
        source=f"Screener.in Excel Import ({filename})",
        statement_scope=statement_scope,
        reporting_period=quarters[-1]["period"] if quarters else (pnl[-1]["period"] if pnl else "Latest Available"),
        is_estimated=False,
        ratios=ratios,
        pnl=pnl,
        quarters=quarters,
        balance_sheet=balance_sheet,
        cash_flow=cash_flow,
        shareholding=shareholding,
        screener_url=screener_url,
        update_existing=update_existing,
    )

    return {
        "success": True,
        "import_type": "excel_company_export",
        "filename": filename,
        "sheets_parsed": list(sheets.keys()),
        "company": saved,
        "pnl_periods": len(pnl),
        "quarterly_periods": len(quarters),
        "balance_sheet_periods": len(balance_sheet),
        "cash_flow_periods": len(cash_flow),
    }


def import_screener_csv(
    csv_text: str,
    filename: str = "screener_screen.csv",
    screen_name: Optional[str] = None,
    screener_url: Optional[str] = None,
    statement_scope: str = "Consolidated",
    update_existing: bool = True,
) -> Dict[str, Any]:
    """
    Import Screener.in exported CSV (multi-company stock screen export OR company summary CSV).
    Detects duplicates, auto-maps NSE/BSE/ISIN/Company Name, updates previously imported records,
    and reports missing financial data.
    """
    clean_text = csv_text.lstrip("\ufeff").strip()
    if not clean_text:
        return {"success": False, "error": "Uploaded CSV file is empty."}

    reader = csv.DictReader(io.StringIO(clean_text))
    headers = reader.fieldnames or []
    rows = [dict(r) for r in reader if any(str(v or "").strip() for v in r.values())]
    if not rows:
        return {"success": False, "error": "No data rows found in Screener CSV."}

    def _pick(row: Dict[str, Any], candidates: List[str]) -> Optional[str]:
        lower_map = {str(k).strip().lower(): v for k, v in row.items() if k}
        for c in candidates:
            for k_low, val in lower_map.items():
                if c in k_low and str(val or "").strip():
                    return str(val).strip()
        return None

    imported_items: List[Dict[str, Any]] = []
    screen_rows: List[Dict[str, Any]] = []
    seen_stock_ids = set()
    duplicates_in_file = 0
    updated_count = 0
    inserted_count = 0

    for row in rows:
        comp_name = _pick(row, ["name", "company"])
        nse_code = _pick(row, ["nse code", "nse symbol", "symbol"])
        bse_code = _pick(row, ["bse code", "bse"])
        isin = _pick(row, ["isin"])

        if bse_code and "." in bse_code:
            bse_code = bse_code.split(".")[0]

        lookup = isin or nse_code or bse_code or comp_name
        if not lookup:
            continue

        stock_meta = resolve_stock(lookup)
        if stock_meta.get("trading_status") == "UNVERIFIED" or (nse_code or bse_code or isin):
            # Ensure stock master captures new identifiers from Screener export
            mcap = _to_float(_pick(row, ["mar cap", "market cap"]))
            sid = upsert_stock_record({
                "isin": isin or stock_meta.get("isin"),
                "nse_symbol": (nse_code or stock_meta.get("nse_symbol") or "").upper() or None,
                "bse_code": bse_code or stock_meta.get("bse_code"),
                "company_name": comp_name or stock_meta.get("company_name"),
                "market_cap_cr": mcap,
                "cap_tier": classify_cap_tier(mcap) if mcap else None,
            })
            stock_meta = resolve_stock(sid)

        sid = stock_meta["stock_id"]
        if sid in seen_stock_ids:
            duplicates_in_file += 1
            if not update_existing:
                continue
        seen_stock_ids.add(sid)

        ratios = {
            "cmp_inr": _to_float(_pick(row, ["cmp", "current price"])),
            "pe": _to_float(_pick(row, ["p/e", "stock p/e", "pe"])),
            "market_cap_cr": _to_float(_pick(row, ["mar cap", "market cap"])),
            "dividend_yield_pct": _to_float(_pick(row, ["div yld", "dividend yield"])),
            "np_qtr_cr": _to_float(_pick(row, ["np qtr"])),
            "qtr_profit_var_pct": _to_float(_pick(row, ["qtr profit var", "profit var"])),
            "sales_qtr_cr": _to_float(_pick(row, ["sales qtr"])),
            "qtr_sales_var_pct": _to_float(_pick(row, ["qtr sales var", "sales var"])),
            "roce_pct": _to_float(_pick(row, ["roce"])),
            "roe_pct": _to_float(_pick(row, ["roe"])),
            "opm_pct": _to_float(_pick(row, ["opm"])),
            "debt_to_equity": _to_float(_pick(row, ["debt to equity", "debt / equity", "d/e"])),
            "sales_growth_3y_pct": _to_float(_pick(row, ["sales growth 3years", "sales 3yr"])),
            "sales_growth_5y_pct": _to_float(_pick(row, ["sales growth 5years", "sales 5yr"])),
            "profit_growth_3y_pct": _to_float(_pick(row, ["profit growth 3years", "profit 3yr"])),
            "profit_growth_5y_pct": _to_float(_pick(row, ["profit growth 5years", "profit 5yr"])),
            "promoter_holding_pct": _to_float(_pick(row, ["promoter holding"])),
            "pledged_pct": _to_float(_pick(row, ["pledged"])),
            "peg_ratio": _to_float(_pick(row, ["peg"])),
            "pb_ratio": _to_float(_pick(row, ["price to book", "p/b"])),
            "ev_ebitda": _to_float(_pick(row, ["ev / ebitda", "evebitda"])),
        }
        ratios = {k: v for k, v in ratios.items() if v is not None}

        saved = _save_screener_company_record(
            stock_meta=stock_meta,
            source=f"Screener.in CSV Import ({filename})",
            statement_scope=statement_scope,
            reporting_period="Latest Screener Export",
            is_estimated=False,
            ratios=ratios,
            pnl=[],
            quarters=[],
            balance_sheet=[],
            cash_flow=[],
            shareholding=[],
            screener_url=screener_url if len(rows) == 1 else stock_meta.get("screener_url"),
            update_existing=update_existing,
        )
        if saved["action"] == "UPDATED_EXISTING":
            updated_count += 1
        elif saved["action"] == "INSERTED_NEW":
            inserted_count += 1

        imported_items.append(saved)
        screen_rows.append({
            "stock_id": sid,
            "symbol": saved["symbol"],
            "company_name": saved["company_name"],
            "sector": stock_meta.get("sector"),
            "cap_tier": stock_meta.get("cap_tier") or classify_cap_tier(ratios.get("market_cap_cr")),
            **ratios,
        })

    # Store imported stock screen table
    now = datetime.now(tz=IST).isoformat()
    scr_id = f"SCR-{uuid.uuid4().hex[:8].upper()}"
    execute_sql(
        """
        INSERT INTO screener_screens (screen_id, screen_name, source_filename, columns_json, rows_json, row_count, imported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scr_id,
            screen_name or filename.rsplit(".", 1)[0],
            filename,
            json.dumps(headers),
            json.dumps(screen_rows),
            len(screen_rows),
            now,
        ),
    )

    return {
        "success": True,
        "import_type": "csv_stock_screen" if len(screen_rows) > 1 else "csv_company",
        "screen_id": scr_id,
        "screen_name": screen_name or filename.rsplit(".", 1)[0],
        "filename": filename,
        "total_rows": len(rows),
        "processed_companies": len(imported_items),
        "inserted_new": inserted_count,
        "updated_existing": updated_count,
        "duplicates_in_file": duplicates_in_file,
        "companies": imported_items,
    }


def associate_screener_url(symbol: str, screener_url: str, statement_scope: Optional[str] = None) -> Dict[str, Any]:
    stock_meta = resolve_stock(symbol)
    now = datetime.now(tz=IST).isoformat()
    execute_sql(
        "UPDATE stocks_master SET screener_url = ?, updated_at = ? WHERE stock_id = ?",
        (screener_url.strip(), now, stock_meta["stock_id"]),
    )
    execute_sql(
        "UPDATE screener_company_data SET screener_url = ? WHERE stock_id = ?",
        (screener_url.strip(), stock_meta["stock_id"]),
    )
    if statement_scope:
        execute_sql(
            "UPDATE screener_company_data SET statement_scope = ? WHERE stock_id = ?",
            (statement_scope, stock_meta["stock_id"]),
        )
    return {
        "updated": True,
        "stock_id": stock_meta["stock_id"],
        "symbol": stock_meta.get("nse_symbol") or stock_meta.get("bse_code"),
        "screener_url": screener_url.strip(),
    }


def update_business_notes(symbol: str, notes: Dict[str, Any]) -> Dict[str, Any]:
    """Attach order book, order inflow, execution, customer concentration & industry outlook notes."""
    stock_meta = resolve_stock(symbol)
    stock_id = stock_meta["stock_id"]
    now = datetime.now(tz=IST).isoformat()
    existing = query_all(
        "SELECT * FROM screener_company_data WHERE stock_id = ? ORDER BY imported_at DESC LIMIT 1",
        (stock_id,),
    )
    allowed_keys = [
        "order_book_cr",
        "order_inflow_cr",
        "order_execution_timeline",
        "customer_concentration",
        "industry_outlook",
        "competitive_position",
        "management_notes",
    ]
    cleaned_notes = {k: notes[k] for k in allowed_keys if k in notes and notes[k] not in (None, "")}
    cleaned_notes["updated_at"] = now

    if existing:
        cur = existing[0]
        merged = {**(json.loads(cur.get("business_notes_json") or "{}")), **cleaned_notes}
        execute_sql(
            "UPDATE screener_company_data SET business_notes_json = ?, imported_at = ? WHERE id = ?",
            (json.dumps(merged), now, cur["id"]),
        )
    else:
        _save_screener_company_record(
            stock_meta=stock_meta,
            source="Manual Research & Order Book Notes",
            statement_scope="Unspecified",
            reporting_period="User Notes",
            is_estimated=False,
            ratios={},
            pnl=[],
            quarters=[],
            balance_sheet=[],
            cash_flow=[],
            shareholding=[],
            business_notes=cleaned_notes,
            update_existing=True,
        )
    return {"updated": True, "stock_id": stock_id, "symbol": stock_meta.get("nse_symbol") or symbol, "business_notes": cleaned_notes}


def get_screener_company(symbol: str) -> Dict[str, Any]:
    """Retrieve full Screener.in imported data, statements, ratios, peers & missing fields for a company."""
    stock_meta = resolve_stock(symbol)
    stock_id = stock_meta["stock_id"]
    rows = query_all(
        "SELECT * FROM screener_company_data WHERE stock_id = ? ORDER BY imported_at DESC LIMIT 1",
        (stock_id,),
    )
    if not rows:
        return {
            "available": False,
            "stock_meta": stock_meta,
            "symbol": stock_meta.get("nse_symbol") or stock_meta.get("bse_code") or normalize_symbol(symbol),
            "screener_url": stock_meta.get("screener_url"),
            "missing_fields": ["No Screener.in CSV or Excel export imported yet for this company."],
        }

    r = rows[0]
    ratios = json.loads(r.get("ratios_json") or "{}")
    pnl = json.loads(r.get("pnl_annual_json") or "[]")
    quarters = json.loads(r.get("quarters_json") or "[]")
    bs = json.loads(r.get("balance_sheet_json") or "[]")
    cf = json.loads(r.get("cash_flow_json") or "[]")
    sh = json.loads(r.get("shareholding_json") or "[]")
    notes = json.loads(r.get("business_notes_json") or "{}")
    missing = json.loads(r.get("missing_fields_json") or "[]")

    # Peer comparison from Screener-imported companies in same sector
    peer_rows = query_all(
        """
        SELECT s.nse_symbol, s.company_name, s.sector, s.market_cap_cr, sc.ratios_json, sc.imported_at
        FROM screener_company_data sc
        JOIN stocks_master s ON s.stock_id = sc.stock_id
        WHERE s.sector = ? AND sc.stock_id != ?
        ORDER BY COALESCE(s.market_cap_cr, 0) DESC
        LIMIT 6
        """,
        (stock_meta.get("sector"), stock_id),
    )
    peers = []
    for p in peer_rows:
        pr = json.loads(p.get("ratios_json") or "{}")
        peers.append({
            "symbol": p["nse_symbol"],
            "company_name": p["company_name"],
            "sector": p["sector"],
            "market_cap_cr": pr.get("market_cap_cr") or p.get("market_cap_cr"),
            "pe": pr.get("pe"),
            "roce_pct": pr.get("roce_pct"),
            "roe_pct": pr.get("roe_pct"),
            "opm_pct": pr.get("opm_pct"),
        })

    return {
        "available": True,
        "stock_meta": stock_meta,
        "stock_id": stock_id,
        "symbol": r.get("nse_symbol") or r.get("bse_code") or normalize_symbol(symbol),
        "company_name": r.get("company_name") or stock_meta.get("company_name"),
        "isin": r.get("isin") or stock_meta.get("isin"),
        "bse_code": r.get("bse_code") or stock_meta.get("bse_code"),
        "screener_url": r.get("screener_url") or stock_meta.get("screener_url"),
        "source": r.get("source"),
        "statement_scope": r.get("statement_scope"),
        "reporting_period": r.get("reporting_period"),
        "is_estimated": bool(r.get("is_estimated")),
        "imported_at": r.get("imported_at"),
        "ratios": ratios,
        "pnl_annual": pnl,
        "quarters": quarters,
        "balance_sheet": bs,
        "cash_flow": cf,
        "shareholding": sh,
        "business_notes": notes,
        "peers": peers,
        "missing_fields": missing,
    }


def list_screener_companies(limit: int = 100) -> List[Dict[str, Any]]:
    rows = query_all(
        """
        SELECT sc.stock_id, sc.company_name, sc.nse_symbol, sc.bse_code, sc.isin, sc.source,
               sc.statement_scope, sc.reporting_period, sc.ratios_json, sc.missing_fields_json, sc.imported_at,
               s.sector, s.industry, s.cap_tier
        FROM screener_company_data sc
        LEFT JOIN stocks_master s ON s.stock_id = sc.stock_id
        ORDER BY sc.imported_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    out = []
    for r in rows:
        ratios = json.loads(r.get("ratios_json") or "{}")
        missing = json.loads(r.get("missing_fields_json") or "[]")
        out.append({
            "stock_id": r["stock_id"],
            "symbol": r["nse_symbol"] or r["bse_code"] or r["stock_id"],
            "company_name": r["company_name"],
            "isin": r["isin"],
            "sector": r["sector"] or "Indian Equities",
            "industry": r["industry"] or "Indian Listed Equity",
            "cap_tier": r["cap_tier"] or classify_cap_tier(ratios.get("market_cap_cr")),
            "source": r["source"],
            "statement_scope": r["statement_scope"],
            "reporting_period": r["reporting_period"],
            "market_cap_cr": ratios.get("market_cap_cr"),
            "pe": ratios.get("pe"),
            "roce_pct": ratios.get("roce_pct"),
            "roe_pct": ratios.get("roe_pct"),
            "missing_count": len(missing),
            "imported_at": r["imported_at"],
        })
    return out


def list_screener_screens(limit: int = 20) -> List[Dict[str, Any]]:
    rows = query_all(
        "SELECT * FROM screener_screens ORDER BY imported_at DESC LIMIT ?",
        (limit,),
    )
    return [
        {
            "screen_id": r["screen_id"],
            "screen_name": r["screen_name"],
            "source_filename": r["source_filename"],
            "columns": json.loads(r.get("columns_json") or "[]"),
            "rows": json.loads(r.get("rows_json") or "[]"),
            "row_count": r["row_count"],
            "imported_at": r["imported_at"],
        }
        for r in rows
    ]


def get_sample_csv_template() -> str:
    """Return a clean header-accurate Screener.in stock screen CSV template for users to populate with their exports."""
    return (
        "S.No.,Name,BSE Code,NSE Code,ISIN,CMP Rs.,P/E,Mar Cap Rs.Cr.,Div Yld %,NP Qtr Rs.Cr.,Qtr Profit Var %,Sales Qtr Rs.Cr.,Qtr Sales Var %,ROCE %,ROE %,OPM %,Debt to equity,Sales growth 5Years %,Profit growth 5Years %,Promoter holding %\n"
        "1,Company Name Here,500325,RELIANCE,INE002A01018,,,,,,,,,,,,,,,\n"
    )
