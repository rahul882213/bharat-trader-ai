"""Module 10: Indian Company Fundamental & Valuation Analyst."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import NIFTY_50_SECTORS, get_symbol_sector, normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager

IST = ZoneInfo("Asia/Kolkata")
CRORE = 1e7  # 1 Crore INR = 10,000,000


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
    "Banking": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"],
    "Auto": ["TATAMOTORS", "MARUTI", "M&M", "BAJAJ-AUTO"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB"],
    "Defence": ["HAL", "BEL", "MAZDOCK"],
    "Financial Services": ["BAJFINANCE", "BAJAJFINSV", "JIOFIN", "SHRIRAMFIN"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "TATACONSUM"],
    "Metals": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL"],
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

    # Reported Annual Statements
    annual_series: List[Dict[str, Any]] = []
    for stmt in inc_hist[:4]:
        end_dt = ((stmt.get("endDate") or {}).get("fmt")) or "N/A"
        rev = _raw(stmt.get("totalRevenue"))
        ebit = _raw(stmt.get("ebit"))
        pat = _raw(stmt.get("netIncome"))
        annual_series.append({
            "period": end_dt,
            "revenue_cr": _to_cr(rev),
            "ebit_cr": _to_cr(ebit),
            "pat_cr": _to_cr(pat),
        })

    quarterly_series: List[Dict[str, Any]] = []
    for stmt in inc_qtr[:4]:
        end_dt = ((stmt.get("endDate") or {}).get("fmt")) or "N/A"
        rev = _raw(stmt.get("totalRevenue"))
        ebit = _raw(stmt.get("ebit"))
        pat = _raw(stmt.get("netIncome"))
        quarterly_series.append({
            "period": end_dt,
            "revenue_cr": _to_cr(rev),
            "ebit_cr": _to_cr(ebit),
            "pat_cr": _to_cr(pat),
        })

    # Growth from reported annual statements when available
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

    # Balance sheet & ROCE & Working Capital
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
        # Yahoo reports D/E in percentage (e.g. 42.5 means 0.425x)
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

    # Intrinsic DCF estimate with disclosed assumptions (ONLY if positive FCF and shares outstanding exist)
    dcf_estimate = None
    if fcf and fcf > 0 and shares_out and shares_out > 0:
        wacc = 0.12  # 12% INR Equity Hurdle Rate
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

    # Classifications derived strictly from reported ratios
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
    if len(inc_hist) >= 2:
        p0 = _raw(inc_hist[0].get("netIncome"))
        p1 = _raw(inc_hist[1].get("netIncome"))
        if p0 is not None and p1 is not None and p1 < 0 and p0 > 0:
            classifications.append("Potential Turnaround")

    return {
        "available": True,
        "symbol": clean,
        "company_name": profile.get("longBusinessSummary", "")[:0] or clean,
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
            "pledged_shares_note": "Verify exact promoter pledge % on NSE/BSE Shareholding Pattern filings (not exposed via Yahoo Finance API).",
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
        "business_analysis": {
            "business_model": profile.get("longBusinessSummary") or "Unavailable",
            "governance_and_ownership": (
                f"Insider/Promoter holding ~{promoter_holding_pct:.1f}%, Institutional holding ~{inst_holding_pct:.1f}%. "
                if promoter_holding_pct is not None and inst_holding_pct is not None
                else "Shareholding breakdown partially unavailable; cross-check NSE quarterly shareholding filing."
            ),
            "capital_allocation": (
                f"ROE {roe_pct:.1f}% · Debt/Equity {debt_to_equity:.2f}x · FCF ₹{_to_cr(fcf):,.1f} Cr"
                if roe_pct is not None and debt_to_equity is not None and fcf is not None
                else "Partial capital allocation metrics available from reported statements."
            ),
            "order_book_and_execution_note": "Qualitative order book, customer concentration & management commentary require quarterly investor presentation / BSE corporate filings (use Gemini AI Research Synthesis for live commentary).",
        },
        "annual_results_cr": annual_series,
        "quarterly_results_cr": quarterly_series,
        "classifications": classifications or ["Fairly Valued / Neutral"],
        "source": source,
        "is_unofficial": True,
        "fetched_at_ist": datetime.now(tz=IST).isoformat(),
    }


def analyze_fundamentals(symbol: str, exchange: str = "NSE", include_peers: bool = True) -> Dict[str, Any]:
    pm = get_provider_manager()
    res = pm.get_fundamentals(symbol, exchange=exchange)
    if not res.get("available"):
        return res
    parsed = parse_yahoo_fundamentals(symbol, res["raw"], source=res.get("source", "Yahoo Finance (Unofficial)"))

    if include_peers:
        clean = normalize_symbol(symbol)
        sec = get_symbol_sector(clean)
        candidates = [p for p in SECTOR_PEERS.get(sec, ["RELIANCE", "TCS", "HDFCBANK"]) if p != clean][:3]
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

        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = [pool.submit(_fetch_peer, c) for c in candidates]
            for f in as_completed(futs):
                item = f.result()
                if item:
                    peers.append(item)
        parsed["peer_comparison"] = peers
    else:
        parsed["peer_comparison"] = []

    return parsed
