"""Module 10: AI Fundamental Analyst (Screener.in + Market Data Integration)."""
from __future__ import annotations

import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import get_symbol_sector, normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager
from backend.database.db import execute_sql, query_all
from backend.database.stock_master_db import resolve_stock

IST = ZoneInfo("Asia/Kolkata")
CRORE = 1e7
ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_screener_mod():
    p = ROOT_DIR / "modules" / "trader-screener" / "screener_importer.py"
    spec = importlib.util.spec_from_file_location("trader_screener_importer", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _raw(obj: Any) -> Optional[float]:
    if isinstance(obj, dict):
        v = obj.get("raw")
        return float(v) if isinstance(v, (int, float)) else None
    if isinstance(obj, (int, float)):
        return float(obj)
    return None


def _to_cr(val: Optional[float]) -> Optional[float]:
    return round(val / CRORE, 2) if val is not None else None


def _pct(val: Optional[float]) -> Optional[float]:
    return round(val * 100.0, 2) if val is not None else None


def _growth(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev is None or prev == 0:
        return None
    return round(((cur - prev) / abs(prev)) * 100.0, 2)


SECTOR_PEERS: Dict[str, List[str]] = {
    "Energy": ["RELIANCE", "ONGC", "BPCL", "COALINDIA"],
    "IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM"],
    "Technology": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM"],
    "Banking": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"],
    "Auto": ["TATAMOTORS", "MARUTI", "M&M", "BAJAJ-AUTO"],
    "Consumer Cyclical": ["TATAMOTORS", "MARUTI", "M&M", "TITAN"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB"],
    "Healthcare": ["SUNPHARMA", "DRREDDY", "CIPLA", "APOLLOHOSP"],
    "Defence": ["HAL", "BEL", "MAZDOCK"],
    "Industrials": ["HAL", "MAZDOCK", "LT", "SIEMENS", "ABB"],
    "Capital Goods": ["HBLENGINE", "KIRLOSBROS", "SHILCTECH", "SIEMENS", "ABB"],
    "Renewables": ["ORIANA", "SUZLON", "NTPC", "TATAPOWER"],
    "Power": ["GVT&D", "NTPC", "POWERGRID", "TATAPOWER"],
    "Metals": ["HINDCOPPER", "TATASTEEL", "JSWSTEEL", "HINDALCO"],
    "Basic Materials": ["HINDCOPPER", "TATASTEEL", "JSWSTEEL", "HINDALCO"],
    "Financial Services": ["BAJFINANCE", "BAJAJFINSV", "JIOFIN", "SHRIRAMFIN"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "TATACONSUM"],
}


def parse_yahoo_fundamentals(symbol: str, raw: Dict[str, Any], source: str = "Yahoo Finance (Unofficial)") -> Dict[str, Any]:
    clean = normalize_symbol(symbol)
    profile = raw.get("assetProfile") or {}
    summary = raw.get("summaryDetail") or {}
    fin = raw.get("financialData") or {}
    stats = raw.get("defaultKeyStatistics") or {}
    holders = raw.get("majorHoldersBreakdown") or {}

    inc_hist = (raw.get("incomeStatementHistory") or {}).get("incomeStatementHistory") or []
    inc_qtr = (raw.get("incomeStatementHistoryQuarterly") or {}).get("incomeStatementHistory") or []
    bal_hist = (raw.get("balanceSheetHistory") or {}).get("balanceSheetStatements") or []
    cf_hist = (raw.get("cashflowStatementHistory") or {}).get("cashflowStatements") or []

    annual_series: List[Dict[str, Any]] = []
    for stmt in inc_hist[:5]:
        end_dt = ((stmt.get("endDate") or {}).get("fmt")) or "N/A"
        rev = _raw(stmt.get("totalRevenue"))
        ebit = _raw(stmt.get("ebit"))
        pat = _raw(stmt.get("netIncome"))
        opm = round((ebit / rev) * 100.0, 2) if (ebit is not None and rev) else None
        annual_series.append({
            "period": end_dt,
            "revenue_cr": _to_cr(rev),
            "ebit_cr": _to_cr(ebit),
            "opm_pct": opm,
            "pat_cr": _to_cr(pat),
        })

    quarterly_series: List[Dict[str, Any]] = []
    for stmt in inc_qtr[:4]:
        end_dt = ((stmt.get("endDate") or {}).get("fmt")) or "N/A"
        rev = _raw(stmt.get("totalRevenue"))
        ebit = _raw(stmt.get("ebit"))
        pat = _raw(stmt.get("netIncome"))
        opm = round((ebit / rev) * 100.0, 2) if (ebit is not None and rev) else None
        quarterly_series.append({
            "period": end_dt,
            "revenue_cr": _to_cr(rev),
            "ebit_cr": _to_cr(ebit),
            "opm_pct": opm,
            "pat_cr": _to_cr(pat),
        })

    rev_growth = _pct(_raw(fin.get("revenueGrowth")))
    if rev_growth is None and len(inc_hist) >= 2:
        rev_growth = _growth(_raw(inc_hist[0].get("totalRevenue")), _raw(inc_hist[1].get("totalRevenue")))

    ebitda_growth = None
    if len(inc_hist) >= 2:
        ebitda_growth = _growth(_raw(inc_hist[0].get("ebit")), _raw(inc_hist[1].get("ebit")))

    pat_growth = _pct(_raw(fin.get("earningsGrowth")))
    if pat_growth is None and len(inc_hist) >= 2:
        pat_growth = _growth(_raw(inc_hist[0].get("netIncome")), _raw(inc_hist[1].get("netIncome")))

    eps_trailing = _raw(stats.get("trailingEps"))
    eps_forward = _raw(stats.get("forwardEps"))
    eps_growth = _growth(eps_forward, eps_trailing) if (eps_forward and eps_trailing) else pat_growth

    working_capital = None
    roce_pct = None
    if bal_hist:
        bs0 = bal_hist[0]
        cur_assets = _raw(bs0.get("totalCurrentAssets"))
        cur_liab = _raw(bs0.get("totalCurrentLiabilities"))
        tot_assets = _raw(bs0.get("totalAssets"))
        if cur_assets is not None and cur_liab is not None:
            working_capital = cur_assets - cur_liab
        if tot_assets is not None and cur_liab is not None and inc_hist:
            cap_employed = tot_assets - cur_liab
            ebit0 = _raw(inc_hist[0].get("ebit"))
            if cap_employed > 0 and ebit0 is not None:
                roce_pct = round((ebit0 / cap_employed) * 100.0, 2)

    fcf = _raw(fin.get("freeCashflow"))
    ocf = _raw(fin.get("operatingCashflow"))
    if ocf is None and cf_hist:
        ocf = _raw(cf_hist[0].get("totalCashFromOperatingActivities"))

    debt_to_equity = _raw(fin.get("debtToEquity"))
    if debt_to_equity is not None and debt_to_equity > 10:
        debt_to_equity = round(debt_to_equity / 100.0, 2)

    roe_pct = _pct(_raw(fin.get("returnOnEquity")))
    op_margin_pct = _pct(_raw(fin.get("operatingMargins")))
    ebitda_margin_pct = _pct(_raw(fin.get("ebitdaMargins")))
    promoter_holding_pct = _pct(_raw(holders.get("insidersPercentHeld")))
    inst_holding_pct = _pct(_raw(holders.get("institutionsPercentHeld")))

    cur_price = _raw(fin.get("currentPrice")) or _raw(summary.get("previousClose"))
    shares_out = _raw(stats.get("sharesOutstanding"))
    market_cap = _raw(summary.get("marketCap"))
    pe_trailing = _raw(summary.get("trailingPE"))
    pe_forward = _raw(summary.get("forwardPE")) or _raw(stats.get("forwardPE"))
    pb_ratio = _raw(stats.get("priceToBook"))
    ev_ebitda = _raw(stats.get("enterpriseToEbitda"))
    peg_ratio = _raw(stats.get("pegRatio"))
    ps_ratio = _raw(summary.get("priceToSalesTrailing12Months"))

    dcf_estimate = None
    if fcf and fcf > 0 and shares_out and shares_out > 0:
        wacc = 0.12
        terminal_g = 0.045
        g_rate = min(max((rev_growth or 10.0) / 100.0, 0.06), 0.18)
        pv_fcfs = 0.0
        proj_fcf = fcf
        for yr in range(1, 6):
            proj_fcf *= (1.0 + g_rate)
            pv_fcfs += proj_fcf / ((1.0 + wacc) ** yr)
        term_val = (proj_fcf * (1.0 + terminal_g)) / (wacc - terminal_g)
        pv_term = term_val / ((1.0 + wacc) ** 5)
        total_debt = _raw(fin.get("totalDebt")) or 0.0
        total_cash = _raw(fin.get("totalCash")) or 0.0
        equity_val = pv_fcfs + pv_term + total_cash - total_debt
        per_share = round(equity_val / shares_out, 2)
        if per_share > 0:
            upside = round(((per_share - cur_price) / cur_price) * 100.0, 2) if cur_price else None
            dcf_estimate = {
                "intrinsic_value_per_share_inr": per_share,
                "upside_downside_pct": upside,
                "classification_tag": "Model Estimate — Disclosed Assumptions",
                "assumptions": {
                    "discount_rate_wacc_pct": 12.0,
                    "5y_fcf_growth_pct": round(g_rate * 100.0, 2),
                    "terminal_growth_pct": 4.5,
                    "base_fcf_cr": _to_cr(fcf),
                },
            }

    classifications: List[str] = []
    if dcf_estimate and dcf_estimate.get("upside_downside_pct") is not None:
        if dcf_estimate["upside_downside_pct"] >= 15.0 or (pe_trailing and pe_trailing < 18.0 and (roe_pct or 0) >= 14.0):
            classifications.append("Undervalued")
        elif dcf_estimate["upside_downside_pct"] <= -20.0 or (pe_trailing and pe_trailing > 55.0 and (rev_growth or 0) < 12.0):
            classifications.append("Overvalued")
    elif pe_trailing is not None:
        if pe_trailing < 18.0 and (roe_pct or 0) >= 14.0:
            classifications.append("Undervalued")
        elif pe_trailing > 60.0 and (rev_growth or 0) < 12.0:
            classifications.append("Overvalued")
    if (rev_growth or 0) >= 15.0 and (pat_growth or 0) >= 15.0:
        classifications.append("High-Growth")
    if (pat_growth or 0) > 10.0 and (op_margin_pct or 0) > 12.0:
        classifications.append("Improving Fundamentals")
    if (rev_growth is not None and rev_growth < 0) or (pat_growth is not None and pat_growth < -10.0):
        classifications.append("Deteriorating Fundamentals")

    return {
        "available": True,
        "symbol": clean,
        "sector": profile.get("sector") or get_symbol_sector(clean),
        "industry": profile.get("industry") or "Indian Equities",
        "business_summary": profile.get("longBusinessSummary") or "Business summary not reported in feed.",
        "website": profile.get("website"),
        "currency": "INR",
        "current_price_inr": round(cur_price, 2) if cur_price else None,
        "market_cap_cr": _to_cr(market_cap),
        "reported_financial_metrics": {
            "data_type": "Reported Historical Financials",
            "revenue_growth_yoy_pct": rev_growth,
            "ebitda_growth_yoy_pct": ebitda_growth,
            "pat_growth_yoy_pct": pat_growth,
            "eps_trailing_inr": round(eps_trailing, 2) if eps_trailing is not None else None,
            "eps_growth_pct": eps_growth,
            "operating_margin_pct": op_margin_pct,
            "ebitda_margin_pct": ebitda_margin_pct,
            "roe_pct": roe_pct,
            "roce_pct": roce_pct,
            "debt_to_equity": debt_to_equity,
            "free_cash_flow_cr": _to_cr(fcf),
            "operating_cash_flow_cr": _to_cr(ocf),
            "working_capital_cr": _to_cr(working_capital),
            "promoter_insider_holding_pct": promoter_holding_pct,
            "institutional_holding_pct": inst_holding_pct,
            "pledged_shares_pct": None,
            "pledged_shares_note": "Verify exact promoter pledge % on Screener.in export or NSE/BSE Shareholding filings.",
        },
        "valuation": {
            "pe_trailing": round(pe_trailing, 2) if pe_trailing is not None else None,
            "forward_pe": round(pe_forward, 2) if pe_forward is not None else None,
            "forward_pe_note": "Analyst Consensus Estimate" if pe_forward is not None else "Analyst forward P/E estimate unavailable",
            "pb_ratio": round(pb_ratio, 2) if pb_ratio is not None else None,
            "ev_ebitda": round(ev_ebitda, 2) if ev_ebitda is not None else None,
            "peg_ratio": round(peg_ratio, 2) if peg_ratio is not None else None,
            "price_to_sales": round(ps_ratio, 2) if ps_ratio is not None else None,
        },
        "analyst_estimates_and_models": {
            "data_type": "Analyst Estimates & Disclosed DCF Model (Distinct from Reported Financials)",
            "forward_eps_estimate_inr": round(eps_forward, 2) if eps_forward is not None else None,
            "dcf_intrinsic_valuation": dcf_estimate,
        },
        "annual_results_cr": annual_series,
        "quarterly_results_cr": quarterly_series,
        "classifications": classifications or ["Fairly Valued / Neutral"],
        "source": source,
        "is_unofficial": True,
        "fetched_at_ist": datetime.now(tz=IST).isoformat(),
    }


def _compute_evidenced_scores_and_thesis(
    company_name: str,
    symbol: str,
    fm: Dict[str, Any],
    val: Dict[str, Any],
    dcf: Optional[Dict[str, Any]],
    biz_notes: Dict[str, Any],
    has_screener: bool,
    missing_fields: List[str],
) -> Dict[str, Any]:
    """Compute transparent 0-100 fundamental scores strictly anchored to reported figures."""
    roce = fm.get("roce_pct")
    roe = fm.get("roe_pct")
    opm = fm.get("operating_margin_pct") or fm.get("ebitda_margin_pct")
    de = fm.get("debt_to_equity")
    ocf = fm.get("operating_cash_flow_cr")
    fcf = fm.get("free_cash_flow_cr")
    rev_g = fm.get("sales_growth_5y_pct") if fm.get("sales_growth_5y_pct") is not None else fm.get("revenue_growth_yoy_pct")
    pat_g = fm.get("profit_growth_5y_pct") if fm.get("profit_growth_5y_pct") is not None else fm.get("pat_growth_yoy_pct")
    pe = val.get("pe_trailing")
    pb = val.get("pb_ratio")
    ev_eb = val.get("ev_ebitda")
    prom = fm.get("promoter_insider_holding_pct")

    bullish: List[str] = []
    bearish: List[str] = []
    risks: List[str] = []

    # 1. Business Quality Score
    bq_pts = 45.0
    bq_ev: List[str] = []
    if roce is not None:
        bq_ev.append(f"ROCE {roce:.1f}%")
        if roce >= 25:
            bq_pts += 22
            bullish.append(f"Superior capital efficiency with ROCE of {roce:.1f}%.")
        elif roce >= 15:
            bq_pts += 14
        elif roce < 10:
            bq_pts -= 12
            bearish.append(f"Sub-hurdle ROCE at {roce:.1f}% indicates weak capital returns.")
    if roe is not None:
        bq_ev.append(f"ROE {roe:.1f}%")
        if roe >= 20:
            bq_pts += 15
        elif roe >= 14:
            bq_pts += 8
        elif roe < 10:
            bq_pts -= 8
    if opm is not None:
        bq_ev.append(f"Operating Margin {opm:.1f}%")
        if opm >= 20:
            bq_pts += 14
            bullish.append(f"Healthy operating margin profile ({opm:.1f}%).")
        elif opm >= 12:
            bq_pts += 7
        elif opm < 7:
            bq_pts -= 10
            bearish.append(f"Thin operating margins ({opm:.1f}%) leave limited shock cushion.")
    if biz_notes.get("order_book_cr"):
        bq_pts += 5
        bq_ev.append(f"Order book ₹{biz_notes['order_book_cr']} Cr")
        bullish.append(f"Disclosed order book visibility of ₹{biz_notes['order_book_cr']} Cr.")

    # 2. Financial Strength Score
    fs_pts = 50.0
    fs_ev: List[str] = []
    if de is not None:
        fs_ev.append(f"Debt/Equity {de:.2f}x")
        if de <= 0.25:
            fs_pts += 24
            bullish.append(f"Virtually debt-free / conservative balance sheet (D/E {de:.2f}x).")
        elif de <= 0.7:
            fs_pts += 12
        elif de > 1.2:
            fs_pts -= 20
            bearish.append(f"Elevated leverage (Debt/Equity {de:.2f}x) increases interest burden.")
            risks.append(f"Balance sheet leverage risk with Debt/Equity at {de:.2f}x.")
    if ocf is not None:
        fs_ev.append(f"Operating Cash Flow ₹{ocf:,.1f} Cr")
        if ocf > 0:
            fs_pts += 14
        else:
            fs_pts -= 18
            bearish.append(f"Negative Operating Cash Flow (₹{ocf:,.1f} Cr).")
            risks.append("Negative operating cash generation requires monitoring working capital cycle.")
    if fcf is not None:
        fs_ev.append(f"Free Cash Flow ₹{fcf:,.1f} Cr")
        if fcf > 0:
            fs_pts += 10

    # 3. Growth Score
    gr_pts = 45.0
    gr_ev: List[str] = []
    if fm.get("sales_growth_5y_pct") is not None:
        gr_ev.append(f"5Y Sales CAGR {fm['sales_growth_5y_pct']:.1f}%")
    elif fm.get("revenue_growth_yoy_pct") is not None:
        gr_ev.append(f"YoY Revenue Growth {fm['revenue_growth_yoy_pct']:.1f}%")
    if fm.get("profit_growth_5y_pct") is not None:
        gr_ev.append(f"5Y Profit CAGR {fm['profit_growth_5y_pct']:.1f}%")
    elif fm.get("pat_growth_yoy_pct") is not None:
        gr_ev.append(f"YoY PAT Growth {fm['pat_growth_yoy_pct']:.1f}%")

    if rev_g is not None:
        if rev_g >= 20:
            gr_pts += 24
            bullish.append(f"Strong top-line compounding at {rev_g:.1f}%.")
        elif rev_g >= 12:
            gr_pts += 14
        elif rev_g < 5:
            gr_pts -= 10
            bearish.append(f"Modest revenue growth ({rev_g:.1f}%).")
    if pat_g is not None:
        if pat_g >= 25:
            gr_pts += 22
            bullish.append(f"Robust earnings expansion at {pat_g:.1f}%.")
        elif pat_g >= 12:
            gr_pts += 12
        elif pat_g < 0:
            gr_pts -= 16
            bearish.append(f"Earnings contraction ({pat_g:.1f}%).")

    # 4. Valuation Score
    val_pts = 50.0
    val_ev: List[str] = []
    if pe is not None:
        val_ev.append(f"P/E {pe:.1f}x")
        if pe <= 18:
            val_pts += 22
            bullish.append(f"Reasonable earnings multiple (P/E {pe:.1f}x).")
        elif pe <= 30:
            val_pts += 10
        elif pe > 55:
            val_pts -= 22
            bearish.append(f"Expensive valuation multiple (P/E {pe:.1f}x) prices in high future execution.")
            risks.append(f"Valuation compression risk if growth slows from current P/E {pe:.1f}x.")
    if pb is not None:
        val_ev.append(f"P/B {pb:.2f}x")
    if ev_eb is not None:
        val_ev.append(f"EV/EBITDA {ev_eb:.1f}x")
    if dcf and dcf.get("upside_downside_pct") is not None:
        up = dcf["upside_downside_pct"]
        val_ev.append(f"DCF Implied {up:+.1f}%")
        if up >= 15:
            val_pts += 15
        elif up <= -20:
            val_pts -= 12

    bq_score = round(max(10.0, min(98.0, bq_pts)), 1)
    fs_score = round(max(10.0, min(98.0, fs_pts)), 1)
    gr_score = round(max(10.0, min(98.0, gr_pts)), 1)
    val_score = round(max(10.0, min(98.0, val_pts)), 1)
    composite = round((bq_score + fs_score + gr_score + val_score) / 4.0, 1)

    if prom is not None:
        if prom >= 50:
            gov_obs = f"High promoter/insider alignment at {prom:.1f}% holding."
        elif prom >= 25:
            gov_obs = f"Moderate promoter/insider ownership at {prom:.1f}%."
        else:
            gov_obs = f"Low promoter/insider stake ({prom:.1f}%); monitor institutional stewardship."
            risks.append(f"Low insider stake ({prom:.1f}%) increases reliance on institutional governance.")
    else:
        gov_obs = "Promoter holding % not yet reported in current feed; upload Screener.in Shareholding export for exact breakdown."

    if missing_fields:
        risks.append(f"Incomplete financial disclosure in current sources ({', '.join(missing_fields[:4])}).")
    if biz_notes.get("customer_concentration"):
        risks.append(f"Customer concentration note: {biz_notes['customer_concentration']}")
    if not risks:
        risks.append("Monitor quarterly margin trajectory, working-capital receivables, and sector cyclicality.")

    if not bullish:
        bullish.append(f"Tracked in central Bharat Trader AI registry ({symbol}); import full Screener.in Excel export for deeper historical catalysts.")
    if not bearish:
        bearish.append("Limited downside flags in currently reported metrics; watch macro & execution risks.")

    # Classifications
    classifications: List[str] = []
    if val_score >= 68:
        classifications.append("Undervalued")
    elif val_score <= 35:
        classifications.append("Overvalued")
    if gr_score >= 68:
        classifications.append("High-Growth")
    if bq_score >= 70 and fs_score >= 65:
        classifications.append("High Quality Compounder")
    if pat_g is not None and pat_g < -10:
        classifications.append("Deteriorating Fundamentals")
    if not classifications:
        classifications.append("Fairly Valued / Neutral")

    if not has_screener:
        data_completeness_note = "Partial market feed only (import Screener.in .xlsx/.csv in Screener.in Data Center for 5-10Y multi-statement depth)."
    else:
        data_completeness_note = "Screener.in financial statements integrated with live market pricing."

    ev_parts = bq_ev + fs_ev + gr_ev + val_ev
    final_assessment = (
        f"{company_name} ({symbol}) scores {composite}/100 composite fundamental strength "
        f"(Quality {bq_score}, Strength {fs_score}, Growth {gr_score}, Valuation {val_score}). "
        + (f"Key reported anchors: {', '.join(ev_parts[:6])}. " if ev_parts else "Quantitative financial statements are currently incomplete; verify missing lines before capital allocation. ")
        + data_completeness_note
    )

    return {
        "scores": {
            "composite_score": composite,
            "business_quality": {"score": bq_score, "evidence": bq_ev or ["Insufficient quality metrics imported"]},
            "financial_strength": {"score": fs_score, "evidence": fs_ev or ["Insufficient balance sheet/cash flow metrics"]},
            "growth": {"score": gr_score, "evidence": gr_ev or ["Insufficient multi-year growth history"]},
            "valuation": {"score": val_score, "evidence": val_ev or ["Valuation multiples unavailable"]},
        },
        "classifications": classifications,
        "management_and_governance": gov_obs,
        "major_risks": risks,
        "bullish_factors": bullish,
        "bearish_factors": bearish,
        "final_assessment": final_assessment,
    }


def analyze_fundamentals(symbol: str, exchange: str = "NSE", include_peers: bool = True) -> Dict[str, Any]:
    """
    Analyze fundamentals for ANY Indian listed stock by combining Screener.in central DB records
    with Yahoo Finance Unofficial market data. Never returns another stock's data.
    """
    stock_meta = resolve_stock(symbol, exchange=exchange)
    canonical_sym = stock_meta.get("nse_symbol") or stock_meta.get("bse_code") or normalize_symbol(symbol)
    company_name = stock_meta.get("company_name") or canonical_sym

    # 1. Load Screener.in imported data if present in central DB
    screener_mod = _load_screener_mod()
    sc_data = screener_mod.get_screener_company(stock_meta["stock_id"])
    has_screener = bool(sc_data.get("available"))

    # 2. Fetch live Yahoo market & fundamental feed (non-fatal if Screener exists or if Yahoo quote succeeds)
    pm = get_provider_manager()
    y_fund = pm.get_fundamentals(canonical_sym, exchange=exchange)
    y_quote = pm.get_quote(canonical_sym, exchange=exchange) if not y_fund.get("available") else None

    if not y_fund.get("available") and not has_screener and not (y_quote and y_quote.get("available")):
        return {
            "available": False,
            "symbol": canonical_sym,
            "company_name": company_name,
            "stock_meta": stock_meta,
            "error": y_fund.get("error") or f"No market or Screener.in data found for {canonical_sym}.",
        }

    # Base parsed structure from Yahoo if available, otherwise clean empty scaffold
    if y_fund.get("available"):
        base = parse_yahoo_fundamentals(canonical_sym, y_fund["raw"], source=y_fund.get("source", "Yahoo Finance (Unofficial)"))
    else:
        cmp_val = (y_quote or {}).get("price") if (y_quote and y_quote.get("available")) else None
        base = {
            "available": True,
            "symbol": canonical_sym,
            "sector": stock_meta.get("sector") or "Indian Equities",
            "industry": stock_meta.get("industry") or "Indian Listed Equity",
            "business_summary": "Market summary unavailable from Yahoo feed; refer to Screener.in statements & company filings.",
            "currency": "INR",
            "current_price_inr": cmp_val,
            "market_cap_cr": stock_meta.get("market_cap_cr"),
            "reported_financial_metrics": {
                "data_type": "Reported Historical Financials",
                "revenue_growth_yoy_pct": None,
                "ebitda_growth_yoy_pct": None,
                "pat_growth_yoy_pct": None,
                "eps_trailing_inr": None,
                "eps_growth_pct": None,
                "operating_margin_pct": None,
                "ebitda_margin_pct": None,
                "roe_pct": None,
                "roce_pct": None,
                "debt_to_equity": None,
                "free_cash_flow_cr": None,
                "operating_cash_flow_cr": None,
                "working_capital_cr": None,
                "promoter_insider_holding_pct": None,
                "institutional_holding_pct": None,
                "pledged_shares_pct": None,
                "pledged_shares_note": "Verify exact promoter pledge % on Screener.in or NSE/BSE filings.",
            },
            "valuation": {
                "pe_trailing": None,
                "forward_pe": None,
                "forward_pe_note": "Analyst forward P/E estimate unavailable",
                "pb_ratio": None,
                "ev_ebitda": None,
                "peg_ratio": None,
                "price_to_sales": None,
            },
            "analyst_estimates_and_models": {
                "data_type": "Analyst Estimates & Disclosed DCF Model",
                "forward_eps_estimate_inr": None,
                "dcf_intrinsic_valuation": None,
            },
            "annual_results_cr": [],
            "quarterly_results_cr": [],
            "source": "Screener.in Export + Market Quote" if has_screener else "Yahoo Finance Quote (Limited Fundamentals)",
            "is_unofficial": not has_screener,
            "fetched_at_ist": datetime.now(tz=IST).isoformat(),
        }

    # Refresh stock_meta after Yahoo possibly enriched market_cap_cr / sector / industry
    stock_meta = resolve_stock(stock_meta["stock_id"], exchange=exchange)
    base["stock_meta"] = stock_meta
    base["company_name"] = stock_meta.get("company_name") or company_name
    base["sector"] = stock_meta.get("sector") or base.get("sector")
    base["industry"] = stock_meta.get("industry") or base.get("industry")
    if base.get("market_cap_cr") is None:
        base["market_cap_cr"] = stock_meta.get("market_cap_cr")

    fm = base["reported_financial_metrics"]
    val = base["valuation"]
    biz_notes: Dict[str, Any] = {}
    balance_sheet: List[Dict[str, Any]] = []
    cash_flow: List[Dict[str, Any]] = []
    shareholding: List[Dict[str, Any]] = []
    missing_fields: List[str] = []

    # 3. Overlay authoritative Screener.in data when imported
    sources_used: List[str] = []
    if has_screener:
        sources_used.append(sc_data.get("source") or "Screener.in Import")
        sr = sc_data.get("ratios") or {}
        if sr.get("cmp_inr") and base.get("current_price_inr") is None:
            base["current_price_inr"] = sr["cmp_inr"]
        if sr.get("market_cap_cr"):
            base["market_cap_cr"] = sr["market_cap_cr"]
        if sr.get("pe") is not None:
            val["pe_trailing"] = sr["pe"]
        if sr.get("pb_ratio") is not None:
            val["pb_ratio"] = sr["pb_ratio"]
        if sr.get("ev_ebitda") is not None:
            val["ev_ebitda"] = sr["ev_ebitda"]
        if sr.get("peg_ratio") is not None:
            val["peg_ratio"] = sr["peg_ratio"]
        if sr.get("roce_pct") is not None:
            fm["roce_pct"] = sr["roce_pct"]
        if sr.get("roe_pct") is not None:
            fm["roe_pct"] = sr["roe_pct"]
        if sr.get("opm_pct") is not None:
            fm["operating_margin_pct"] = sr["opm_pct"]
        if sr.get("debt_to_equity") is not None:
            fm["debt_to_equity"] = sr["debt_to_equity"]
        if sr.get("sales_growth_5y_pct") is not None:
            fm["sales_growth_5y_pct"] = sr["sales_growth_5y_pct"]
        if sr.get("profit_growth_5y_pct") is not None:
            fm["profit_growth_5y_pct"] = sr["profit_growth_5y_pct"]
        if sr.get("sales_growth_3y_pct") is not None:
            fm["sales_growth_3y_pct"] = sr["sales_growth_3y_pct"]
        if sr.get("profit_growth_3y_pct") is not None:
            fm["profit_growth_3y_pct"] = sr["profit_growth_3y_pct"]
        if sr.get("qtr_sales_var_pct") is not None:
            fm["revenue_growth_yoy_pct"] = sr["qtr_sales_var_pct"]
        if sr.get("qtr_profit_var_pct") is not None:
            fm["pat_growth_yoy_pct"] = sr["qtr_profit_var_pct"]
        if sr.get("promoter_holding_pct") is not None:
            fm["promoter_insider_holding_pct"] = sr["promoter_holding_pct"]
        if sr.get("pledged_pct") is not None:
            fm["pledged_shares_pct"] = sr["pledged_pct"]

        if sc_data.get("pnl_annual"):
            base["annual_results_cr"] = [
                {
                    "period": r.get("period"),
                    "revenue_cr": r.get("sales"),
                    "ebit_cr": r.get("operating_profit"),
                    "opm_pct": r.get("opm") or r.get("opm_"),
                    "pat_cr": r.get("net_profit"),
                    "eps_inr": r.get("eps_in_rs"),
                }
                for r in sc_data["pnl_annual"]
            ]
        if sc_data.get("quarters"):
            base["quarterly_results_cr"] = [
                {
                    "period": r.get("period"),
                    "revenue_cr": r.get("sales"),
                    "ebit_cr": r.get("operating_profit"),
                    "opm_pct": r.get("opm") or r.get("opm_"),
                    "pat_cr": r.get("net_profit"),
                    "eps_inr": r.get("eps_in_rs"),
                }
                for r in sc_data["quarters"]
            ]
        balance_sheet = sc_data.get("balance_sheet") or []
        cash_flow = sc_data.get("cash_flow") or []
        shareholding = sc_data.get("shareholding") or []
        biz_notes = sc_data.get("business_notes") or {}
        missing_fields = sc_data.get("missing_fields") or []

    if y_fund.get("available"):
        sources_used.append(y_fund.get("source", "Yahoo Finance (Unofficial)"))
    elif y_quote and y_quote.get("available"):
        sources_used.append(y_quote.get("source", "Yahoo Finance Quote (Unofficial)"))

    if not has_screener:
        if not base.get("annual_results_cr"):
            missing_fields.append("Multi-Year Annual P&L")
        if fm.get("roce_pct") is None:
            missing_fields.append("ROCE %")
        if not balance_sheet:
            missing_fields.append("Detailed Screener Balance Sheet")

    base["source"] = " + ".join(sources_used) if sources_used else base.get("source")
    base["provenance"] = {
        "data_source": base["source"],
        "reporting_period": (sc_data.get("reporting_period") if has_screener else (base["annual_results_cr"][0]["period"] if base.get("annual_results_cr") else "Latest TTM / Market Quote")),
        "last_updated": sc_data.get("imported_at") if has_screener else base["fetched_at_ist"],
        "statement_scope": sc_data.get("statement_scope") if has_screener else "Consolidated / Market Default",
        "actual_vs_estimated": "Actual Reported Financials (Model DCF & Forward P/E Separated)" if (has_screener or base.get("annual_results_cr")) else "Limited Market Quote Only",
        "screener_imported": has_screener,
        "screener_url": sc_data.get("screener_url") or stock_meta.get("screener_url"),
    }

    # 4. Evidenced Scores, Risks & Thesis
    dcf = base["analyst_estimates_and_models"].get("dcf_intrinsic_valuation")
    ai_eval = _compute_evidenced_scores_and_thesis(
        company_name=base["company_name"],
        symbol=canonical_sym,
        fm=fm,
        val=val,
        dcf=dcf,
        biz_notes=biz_notes,
        has_screener=has_screener,
        missing_fields=missing_fields,
    )
    base["scores"] = ai_eval["scores"]
    base["classifications"] = ai_eval["classifications"]
    base["management_and_governance"] = ai_eval["management_and_governance"]
    base["major_risks"] = ai_eval["major_risks"]
    base["bullish_factors"] = ai_eval["bullish_factors"]
    base["bearish_factors"] = ai_eval["bearish_factors"]
    base["final_assessment"] = ai_eval["final_assessment"]
    base["missing_fields"] = missing_fields
    base["balance_sheet"] = balance_sheet
    base["cash_flow"] = cash_flow
    base["shareholding"] = shareholding
    base["business_notes"] = biz_notes
    base["business_analysis"] = {
        "business_model": base.get("business_summary") or "Refer to Screener.in & company investor filings.",
        "governance_and_ownership": ai_eval["management_and_governance"],
        "capital_allocation": (
            f"ROCE {fm.get('roce_pct') if fm.get('roce_pct') is not None else 'N/A'}% · "
            f"ROE {fm.get('roe_pct') if fm.get('roe_pct') is not None else 'N/A'}% · "
            f"Debt/Equity {fm.get('debt_to_equity') if fm.get('debt_to_equity') is not None else 'N/A'}x"
        ),
        "order_book_and_execution_note": (
            f"Order Book: ₹{biz_notes['order_book_cr']} Cr · Execution: {biz_notes.get('order_execution_timeline', 'Specified in notes')}"
            if biz_notes.get("order_book_cr")
            else "Import Screener.in notes or add Order Book / Execution notes in Screener.in Data Center."
        ),
    }

    # 5. Dynamic Sector Peer Comparison
    if include_peers:
        sec = base.get("sector") or "Indian Equities"
        cand_syms = list(SECTOR_PEERS.get(sec, []))
        # Add stocks from central DB matching sector
        try:
            db_peers = query_all(
                "SELECT nse_symbol FROM stocks_master WHERE sector = ? AND nse_symbol IS NOT NULL AND nse_symbol != ? ORDER BY COALESCE(market_cap_cr, 0) DESC LIMIT 4",
                (sec, canonical_sym),
            )
            for dp in db_peers:
                if dp["nse_symbol"] not in cand_syms:
                    cand_syms.append(dp["nse_symbol"])
        except Exception:
            pass
        candidates = [p for p in cand_syms if p and p != canonical_sym][:3]
        peers: List[Dict[str, Any]] = []

        def _fetch_peer(psym: str) -> Optional[Dict[str, Any]]:
            pr = pm.get_fundamentals(psym, exchange=exchange)
            if not pr.get("available"):
                return None
            pp = parse_yahoo_fundamentals(psym, pr["raw"])
            return {
                "symbol": psym,
                "price_inr": pp["current_price_inr"],
                "market_cap_cr": pp["market_cap_cr"],
                "pe": pp["valuation"]["pe_trailing"],
                "pb": pp["valuation"]["pb_ratio"],
                "roe_pct": pp["reported_financial_metrics"]["roe_pct"],
                "op_margin_pct": pp["reported_financial_metrics"]["operating_margin_pct"],
                "debt_to_equity": pp["reported_financial_metrics"]["debt_to_equity"],
            }

        if candidates:
            with ThreadPoolExecutor(max_workers=3) as pool:
                futs = [pool.submit(_fetch_peer, c) for c in candidates]
                for f in as_completed(futs):
                    item = f.result()
                    if item:
                        peers.append(item)
        base["peer_comparison"] = peers
    else:
        base["peer_comparison"] = []

    # 6. Persist to ai_fundamental_analyses linked by stock_id
    try:
        sc = ai_eval["scores"]
        execute_sql(
            """
            INSERT OR REPLACE INTO ai_fundamental_analyses
            (stock_id, symbol, business_quality_score, financial_strength_score, growth_score,
             valuation_score, overall_assessment, analysis_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stock_meta["stock_id"],
                canonical_sym,
                sc["business_quality"]["score"],
                sc["financial_strength"]["score"],
                sc["growth"]["score"],
                sc["valuation"]["score"],
                ai_eval["final_assessment"],
                json.dumps(base),
                datetime.now(tz=IST).isoformat(),
            ),
        )
    except Exception:
        pass

    return base
