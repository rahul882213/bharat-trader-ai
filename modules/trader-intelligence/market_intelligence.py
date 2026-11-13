"""Module 11: Indian Market Intelligence (Indices, VIX, Breadth, Sector Rotation, Macro & Briefing)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import NIFTY_50_SECTORS, get_symbol_sector
from backend.data_providers.provider_manager import get_provider_manager
from backend.services.market_calendar import get_market_status, next_trading_day

IST = ZoneInfo("Asia/Kolkata")

CORE_INDICES = [
    {"id": "NIFTY_50", "name": "NIFTY 50", "symbol": "^NSEI"},
    {"id": "BANK_NIFTY", "name": "BANK NIFTY", "symbol": "^NSEBANK"},
    {"id": "FIN_NIFTY", "name": "FIN NIFTY", "symbol": "^CNXFIN"},
    {"id": "SENSEX", "name": "BSE SENSEX", "symbol": "^BSESN"},
    {"id": "INDIA_VIX", "name": "INDIA VIX", "symbol": "^INDIAVIX"},
]

SECTOR_INDICES = [
    {"id": "NIFTY_IT", "name": "IT", "symbol": "^CNXIT"},
    {"id": "NIFTY_BANK", "name": "Banking", "symbol": "^NSEBANK"},
    {"id": "NIFTY_AUTO", "name": "Auto", "symbol": "^CNXAUTO"},
    {"id": "NIFTY_PHARMA", "name": "Pharma", "symbol": "^CNXPHARMA"},
    {"id": "NIFTY_METAL", "name": "Metals", "symbol": "^CNXMETAL"},
    {"id": "NIFTY_FMCG", "name": "FMCG", "symbol": "^CNXFMCG"},
    {"id": "NIFTY_ENERGY", "name": "Energy", "symbol": "^CNXENERGY"},
    {"id": "NIFTY_REALTY", "name": "Realty", "symbol": "^CNXREALTY"},
]

GLOBAL_MACRO = [
    {"id": "USD_INR", "name": "USD / INR", "symbol": "INR=X", "unit": "₹"},
    {"id": "CRUDE_OIL", "name": "Crude Oil (WTI)", "symbol": "CL=F", "unit": "$"},
    {"id": "GOLD", "name": "Gold Futures", "symbol": "GC=F", "unit": "$"},
    {"id": "SP500", "name": "S&P 500 (Global Cue)", "symbol": "^GSPC", "unit": "pts"},
]


def _fetch_quote_safe(item: Dict[str, str]) -> Dict[str, Any]:
    pm = get_provider_manager()
    q = pm.get_quote(item["symbol"], exchange="NSE")
    return {
        "id": item["id"],
        "name": item["name"],
        "symbol": item["symbol"],
        "unit": item.get("unit", ""),
        "available": q.get("available", False),
        "price": q.get("price"),
        "change": q.get("change"),
        "change_pct": q.get("change_pct"),
        "day_high": q.get("day_high"),
        "day_low": q.get("day_low"),
        "source": q.get("source", "Yahoo Finance (Unofficial)"),
        "last_bar_ist": q.get("last_bar_ist"),
    }


def get_market_overview(breadth_sample_size: int = 30) -> Dict[str, Any]:
    """Fetch live NIFTY/BankNifty/Sensex/VIX, Sector Rotation, Macro, Breadth, and Top Gainers/Losers."""
    pm = get_provider_manager()
    cal_status = get_market_status()

    indices: List[Dict[str, Any]] = []
    sectors: List[Dict[str, Any]] = []
    macros: List[Dict[str, Any]] = []
    constituents: List[Dict[str, Any]] = []

    sample_syms = list(NIFTY_50_SECTORS.keys())[:breadth_sample_size]

    with ThreadPoolExecutor(max_workers=10) as pool:
        idx_futs = [pool.submit(_fetch_quote_safe, x) for x in CORE_INDICES]
        sec_futs = [pool.submit(_fetch_quote_safe, x) for x in SECTOR_INDICES]
        mac_futs = [pool.submit(_fetch_quote_safe, x) for x in GLOBAL_MACRO]
        eq_futs = {pool.submit(pm.get_quote, sym, "NSE"): sym for sym in sample_syms}

        for f in idx_futs:
            indices.append(f.result())
        for f in sec_futs:
            sectors.append(f.result())
        for f in mac_futs:
            macros.append(f.result())
        for f, sym in eq_futs.items():
            q = f.result()
            if q.get("available"):
                constituents.append({
                    "symbol": sym,
                    "sector": get_symbol_sector(sym),
                    "price": q["price"],
                    "change": q["change"],
                    "change_pct": q["change_pct"],
                    "volume": q["volume"],
                    "source": q["source"],
                })

    sectors_sorted = sorted(
        [s for s in sectors if s.get("available") and s.get("change_pct") is not None],
        key=lambda x: x["change_pct"],
        reverse=True,
    )
    advances = sum(1 for c in constituents if (c.get("change_pct") or 0) > 0)
    declines = sum(1 for c in constituents if (c.get("change_pct") or 0) < 0)
    unchanged = len(constituents) - advances - declines
    ad_ratio = round(advances / max(declines, 1), 2) if constituents else None

    gainers = sorted(constituents, key=lambda x: x.get("change_pct") or -999, reverse=True)[:8]
    losers = sorted(constituents, key=lambda x: x.get("change_pct") or 999)[:8]

    nifty = next((x for x in indices if x["id"] == "NIFTY_50"), {})
    bank_nifty = next((x for x in indices if x["id"] == "BANK_NIFTY"), {})
    vix = next((x for x in indices if x["id"] == "INDIA_VIX"), {})

    nifty_chg = nifty.get("change_pct") or 0.0
    vix_val = vix.get("price")
    trend_label = "BULLISH" if nifty_chg > 0.35 else ("BEARISH" if nifty_chg < -0.35 else "SIDEWAYS / CONSOLIDATION")
    volatility_regime = (
        "LOW VOLATILITY" if (vix_val and vix_val < 13.5)
        else ("ELEVATED VOLATILITY" if (vix_val and vix_val > 18.5) else "NORMAL VOLATILITY")
    )

    return {
        "generated_at_ist": datetime.now(tz=IST).isoformat(),
        "market_calendar": {
            **cal_status,
            "next_trading_day": next_trading_day(),
        },
        "indices": indices,
        "sector_rotation": sectors_sorted,
        "global_macro": macros,
        "market_breadth": {
            "sample_universe": f"NIFTY 50 ({len(constituents)} active quotes)",
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "advance_decline_ratio": ad_ratio,
        },
        "nifty_trend": trend_label,
        "bank_nifty_trend": "BULLISH" if (bank_nifty.get("change_pct") or 0) > 0.35 else ("BEARISH" if (bank_nifty.get("change_pct") or 0) < -0.35 else "SIDEWAYS"),
        "volatility_regime": volatility_regime,
        "top_gainers": gainers,
        "top_losers": losers,
        "heatmap": constituents,
        "institutional_flow_note": (
            "FII/DII daily net cash figures are published post-market by NSE/NSDL (~18:30 IST). "
            "Refer to News & Filings for live bulk/block/promoter disclosures; no synthetic FII/DII figures are generated."
        ),
        "data_source": "Yahoo Finance (Unofficial)",
    }


def get_daily_briefing() -> Dict[str, Any]:
    overview = get_market_overview(breadth_sample_size=25)
    nifty = next((x for x in overview["indices"] if x["id"] == "NIFTY_50"), {})
    bank = next((x for x in overview["indices"] if x["id"] == "BANK_NIFTY"), {})
    vix = next((x for x in overview["indices"] if x["id"] == "INDIA_VIX"), {})
    top_sec = overview["sector_rotation"][0] if overview["sector_rotation"] else None
    weak_sec = overview["sector_rotation"][-1] if overview["sector_rotation"] else None
    usdinr = next((x for x in overview["global_macro"] if x["id"] == "USD_INR"), {})
    crude = next((x for x in overview["global_macro"] if x["id"] == "CRUDE_OIL"), {})

    lines = [
        f"Market Session: {overview['market_calendar']['session_label']} ({overview['market_calendar']['date']}).",
        f"NIFTY 50 at {nifty.get('price', 'N/A')} ({nifty.get('change_pct', 0):+.2f}%) — Trend: {overview['nifty_trend']}.",
        f"BANK NIFTY at {bank.get('price', 'N/A')} ({bank.get('change_pct', 0):+.2f}%) — Trend: {overview['bank_nifty_trend']}.",
        f"India VIX at {vix.get('price', 'N/A')} ({overview['volatility_regime']}).",
        f"Breadth: {overview['market_breadth']['advances']} Advances vs {overview['market_breadth']['declines']} Declines (A/D {overview['market_breadth']['advance_decline_ratio']}).",
    ]
    if top_sec and weak_sec:
        lines.append(f"Sector Rotation: Leading {top_sec['name']} ({top_sec['change_pct']:+.2f}%) | Lagging {weak_sec['name']} ({weak_sec['change_pct']:+.2f}%).")
    if usdinr.get("price") or crude.get("price"):
        lines.append(f"Macro Cues: USD/INR ₹{usdinr.get('price', 'N/A')} · Crude Oil ${crude.get('price', 'N/A')}.")

    return {
        "generated_at_ist": overview["generated_at_ist"],
        "headline": f"Bharat Trader Daily Briefing — NIFTY {overview['nifty_trend']}",
        "bullet_summary": lines,
        "overview": overview,
    }
