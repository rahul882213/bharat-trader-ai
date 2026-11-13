"""Module 2: Indian Market News & Regulatory Filing Analyst."""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import normalize_symbol

IST = ZoneInfo("Asia/Kolkata")
USER_AGENT = "Mozilla/5.0 (compatible; BharatTraderAI/1.0)"

RSS_FEEDS = [
    {"source": "Economic Times Markets", "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "category_hint": "Market News"},
    {"source": "Moneycontrol Market Reports", "url": "https://www.moneycontrol.com/rss/marketreports.xml", "category_hint": "Market News"},
    {"source": "Business Standard Markets", "url": "https://www.business-standard.com/rss/markets-106.rss", "category_hint": "Market News"},
    {"source": "CNBC-TV18 Markets", "url": "https://www.cnbctv18.com/commonfeeds/v1/cne/rss/market.xml", "category_hint": "Market News"},
    {"source": "RBI Press Releases", "url": "https://rbi.org.in/pressreleases_rss.xml", "category_hint": "RBI Announcement"},
    {"source": "SEBI Regulatory Filings", "url": "https://www.sebi.gov.in/sebirss.xml", "category_hint": "SEBI Announcement"},
]

EVENT_CATEGORIES = [
    ("Order Wins", ["order win", "contract", "bagged", "awarded", "l1 bidder", "work order", "defence order", "epc"]),
    ("Bulk & Block Deals", ["bulk deal", "block deal", "institutional trade"]),
    ("Promoter & Insider Activity", ["promoter", "insider", "sast", "pledge", "stake buy", "stake sale", "shareholding"]),
    ("Mergers & Acquisitions", ["merger", "acquisition", "acquire", "demerger", "amalgamation", "buyout"]),
    ("Fundraising & Capital", ["qip", "ipo", "rights issue", "ncd", "bond", "fundrais", "preferential", "fpo", "dividend", "buyback"]),
    ("Regulatory & Policy", ["sebi", "rbi", "policy", "circular", "penalty", "tariff", "gst", "ministry", "budget", "repo rate"]),
    ("Quarterly Results", ["q1", "q2", "q3", "q4", "quarter", "results", "net profit", "ebitda", "pat ", "earnings", "revenue"]),
]

BULLISH_KW = [
    "surge", "jump", "gain", "rally", "order win", "bagged", "profit rises", "beats estimate",
    "upgrade", "buyback", "dividend", "expansion", "approval", "promoter buys", "stake hike",
    "breakout", "record high", "outperform", "strong demand", "margin expansion",
]
BEARISH_KW = [
    "fall", "drop", "slump", "plunge", "loss", "profit falls", "misses estimate", "downgrade",
    "sebi notice", "penalty", "probe", "fraud", "default", "promoter sells", "pledge increase",
    "resignation", "weak demand", "margin pressure", "block deal discount", "sell-off",
]


def _clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    stripped = re.sub(r"<[^>]+>", " ", html.unescape(text))
    return re.sub(r"\s+", " ", stripped).strip()


def classify_news_item(title: str, summary: str = "", default_cat: str = "Corporate Announcement") -> Dict[str, str]:
    blob = f"{title} {summary}".lower()
    category = default_cat
    for cat_name, keywords in EVENT_CATEGORIES:
        if any(kw in blob for kw in keywords):
            category = cat_name
            break

    bull_hits = [kw for kw in BULLISH_KW if kw in blob]
    bear_hits = [kw for kw in BEARISH_KW if kw in blob]

    if len(bull_hits) > len(bear_hits):
        sentiment = "BULLISH"
        impact = f"Positive catalyst ({', '.join(bull_hits[:2])}); may support buying interest or upward re-rating if confirmed by volume."
    elif len(bear_hits) > len(bull_hits):
        sentiment = "BEARISH"
        impact = f"Negative risk factor ({', '.join(bear_hits[:2])}); could trigger supply pressure or near-term volatility."
    else:
        sentiment = "NEUTRAL"
        impact = f"Informational {category.lower()} update; monitor price reaction at key support/resistance before acting."

    return {
        "event_category": category,
        "sentiment": sentiment,
        "impact_explanation": impact,
    }


def _fetch_rss(feed: Dict[str, str], max_items: int = 8) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    try:
        req = urllib.request.Request(feed["url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=7) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        for item_el in root.findall(".//item")[:max_items]:
            title = _clean_text(item_el.findtext("title"))
            link = (item_el.findtext("link") or "").strip()
            pub_date = (item_el.findtext("pubDate") or "").strip()
            desc = _clean_text(item_el.findtext("description"))[:240]
            if not title:
                continue
            cls = classify_news_item(title, desc, feed.get("category_hint", "Corporate Announcement"))
            items.append({
                "title": title,
                "summary": desc,
                "source": feed["source"],
                "published_at": pub_date or "Recent",
                "url": link,
                **cls,
            })
    except Exception:
        pass
    return items


def _fetch_yahoo_symbol_news(symbol: str, exchange: str = "NSE") -> List[Dict[str, Any]]:
    clean = normalize_symbol(symbol)
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    q = urllib.parse.quote(f"{clean}{suffix}")
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={q}&newsCount=8&quotesCount=1"
    items: List[Dict[str, Any]] = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for n in data.get("news", []):
            title = _clean_text(n.get("title"))
            if not title:
                continue
            ts = n.get("providerPublishTime")
            pub_ist = (
                datetime.fromtimestamp(ts, tz=IST).strftime("%Y-%m-%d %H:%M IST")
                if isinstance(ts, (int, float))
                else "Recent"
            )
            cls = classify_news_item(title, "", "Corporate Announcement")
            items.append({
                "title": title,
                "summary": "",
                "source": f"{n.get('publisher', 'Market Wire')} (via Yahoo Search)",
                "published_at": pub_ist,
                "url": n.get("link", ""),
                "symbol": clean,
                **cls,
            })
    except Exception:
        pass
    return items


def _fetch_google_news_india_symbol(symbol: str) -> List[Dict[str, Any]]:
    clean = normalize_symbol(symbol)
    q = urllib.parse.quote(f"{clean} NSE stock India")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    items: List[Dict[str, Any]] = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=7) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        for item_el in root.findall(".//item")[:8]:
            title = _clean_text(item_el.findtext("title"))
            link = (item_el.findtext("link") or "").strip()
            pub_date = (item_el.findtext("pubDate") or "").strip()
            source_el = item_el.find("source")
            src_name = source_el.text.strip() if source_el is not None and source_el.text else "Indian Financial Media"
            if not title:
                continue
            cls = classify_news_item(title, "", "Corporate Announcement")
            items.append({
                "title": title,
                "summary": "",
                "source": src_name,
                "published_at": pub_date or "Recent",
                "url": link,
                "symbol": clean,
                **cls,
            })
    except Exception:
        pass
    return items


def fetch_market_news(symbol: Optional[str] = None, limit: int = 30) -> Dict[str, Any]:
    """Aggregate live Indian financial news, RBI/SEBI updates, and symbol-specific stories."""
    all_items: List[Dict[str, Any]] = []

    if symbol:
        clean = normalize_symbol(symbol)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = [
                pool.submit(_fetch_yahoo_symbol_news, clean),
                pool.submit(_fetch_google_news_india_symbol, clean),
            ]
            for f in as_completed(futs):
                all_items.extend(f.result())

    # Always include broad Indian feeds (filtered if symbol specified, or full market stream)
    feed_items: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(_fetch_rss, feed, 6) for feed in RSS_FEEDS]
        for f in as_completed(futs):
            feed_items.extend(f.result())

    if symbol:
        clean = normalize_symbol(symbol).lower()
        matching = [
            it for it in feed_items
            if clean in it["title"].lower() or clean in it.get("summary", "").lower()
        ]
        all_items.extend(matching)
    else:
        all_items.extend(feed_items)

    # Deduplicate by title
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for it in all_items:
        key = it["title"].lower()[:75]
        if key not in seen:
            seen.add(key)
            deduped.append(it)

    bullish_count = sum(1 for x in deduped if x["sentiment"] == "BULLISH")
    bearish_count = sum(1 for x in deduped if x["sentiment"] == "BEARISH")
    neutral_count = sum(1 for x in deduped if x["sentiment"] == "NEUTRAL")
    overall = "BULLISH" if bullish_count > bearish_count else ("BEARISH" if bearish_count > bullish_count else "NEUTRAL")

    return {
        "generated_at_ist": datetime.now(tz=IST).isoformat(),
        "symbol": normalize_symbol(symbol) if symbol else "INDIA_MARKET",
        "overall_sentiment": overall,
        "counts": {
            "total": len(deduped[:limit]),
            "bullish": bullish_count,
            "bearish": bearish_count,
            "neutral": neutral_count,
        },
        "sources_monitored": [f["source"] for f in RSS_FEEDS] + ["Google News India (NSE/BSE)", "Yahoo Finance Search"],
        "articles": deduped[:limit],
    }
