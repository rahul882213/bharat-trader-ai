"""Screener.in & Authorized Fundamental Data Provider Adapters."""
from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
USER_AGENT = "Mozilla/5.0 (compatible; BharatTraderAI/1.0)"


class FundamentalExternalAdapter(ABC):
    """Pluggable provider contract for future authorized Indian fundamental data APIs."""

    provider_id: str = "base_fundamental"
    provider_label: str = "Base Fundamental Provider"
    is_unofficial: bool = False

    @abstractmethod
    def fetch_company(self, identifier: str, statement_scope: str = "Consolidated") -> Dict[str, Any]:
        """Fetch company fundamentals with strict provenance metadata."""


class ScreenerPublicPageAdapter(FundamentalExternalAdapter):
    """
    OPTIONAL, rate-limited adapter for public Screener.in company pages.
    Strictly public HTML only — never bypasses login, paywalls, or private screens.
    Explicitly labeled 'Screener.in Public Page (Unofficial)'.
    Disabled by default unless explicitly requested by user action.
    """

    provider_id = "screener_public_unofficial"
    provider_label = "Screener.in Public Page (Unofficial)"
    is_unofficial = True

    def __init__(self, min_delay_sec: float = 1.5):
        self._min_delay = min_delay_sec
        self._last_req = 0.0

    def fetch_company(self, identifier: str, statement_scope: str = "Consolidated") -> Dict[str, Any]:
        now = time.time()
        wait = self._min_delay - (now - self._last_req)
        if wait > 0:
            time.sleep(wait)
        self._last_req = time.time()

        slug = identifier.strip().upper()
        scope_path = "consolidated/" if statement_scope.lower() == "consolidated" else ""
        url = f"https://www.screener.in/company/{urllib.parse.quote(slug)}/{scope_path}"
        fetched_at = datetime.now(tz=IST).isoformat()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            if "Sign in" in html and "top-ratios" not in html:
                return {
                    "available": False,
                    "source": self.provider_label,
                    "is_unofficial": True,
                    "screener_url": url,
                    "error": "Screener.in public page did not expose ratios without login; import Excel/CSV export instead.",
                }

            ratios: Dict[str, Optional[float]] = {}
            # Extract public top-ratios list items cleanly
            ratio_blocks = re.findall(
                r'<li[^>]*>\s*<span class="name"[^>]*>(.*?)</span>.*?<span class="number"[^>]*>(.*?)</span>',
                html,
                flags=re.S | re.I,
            )
            for raw_name, raw_val in ratio_blocks:
                name = re.sub(r"<[^>]+>", "", raw_name).strip()
                val_txt = re.sub(r"<[^>]+>|,", "", raw_val).strip()
                try:
                    num = float(val_txt) if val_txt else None
                except ValueError:
                    num = None
                if name:
                    ratios[name] = num

            title_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.S | re.I)
            comp_name = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else slug

            return {
                "available": len(ratios) > 0,
                "symbol": slug,
                "company_name": comp_name,
                "screener_url": url,
                "statement_scope": statement_scope,
                "source": self.provider_label,
                "is_unofficial": True,
                "is_estimated": False,
                "fetched_at_ist": fetched_at,
                "ratios": ratios,
            }
        except Exception as exc:
            return {
                "available": False,
                "symbol": slug,
                "screener_url": url,
                "source": self.provider_label,
                "is_unofficial": True,
                "fetched_at_ist": fetched_at,
                "error": f"Public fetch unavailable ({exc}). Upload Screener.in Excel/CSV export for full multi-year statements.",
            }
