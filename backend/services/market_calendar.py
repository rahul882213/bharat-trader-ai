"""Indian Stock Market Trading Calendar (NSE / BSE, IST Asia/Kolkata)."""
from __future__ import annotations

import json
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "market_calendar.json"


def load_calendar_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "timezone": "Asia/Kolkata",
        "regular_session": {
            "pre_open_start": "09:00",
            "pre_open_end": "09:15",
            "market_open": "09:15",
            "market_close": "15:30",
            "intraday_mis_squareoff": "15:15",
        },
        "holidays": {},
        "special_sessions": [],
    }


def _parse_hhmm(hhmm: str) -> time:
    parts = hhmm.split(":")
    return time(int(parts[0]), int(parts[1]))


def now_ist() -> datetime:
    return datetime.now(tz=IST)


def get_holiday_info(target_date: date, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
    cfg = config or load_calendar_config()
    year_str = str(target_date.year)
    date_iso = target_date.isoformat()
    for item in cfg.get("holidays", {}).get(year_str, []):
        if item.get("date") == date_iso:
            return item
    return None


def get_special_session(target_date: date, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
    cfg = config or load_calendar_config()
    date_iso = target_date.isoformat()
    for item in cfg.get("special_sessions", []):
        if item.get("date") == date_iso:
            return item
    return None


def is_trading_day(target_date: date, config: Optional[Dict[str, Any]] = None) -> bool:
    cfg = config or load_calendar_config()
    if get_special_session(target_date, cfg):
        return True
    if target_date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if get_holiday_info(target_date, cfg):
        return False
    return True


def get_market_status(dt: Optional[datetime] = None) -> Dict[str, Any]:
    cfg = load_calendar_config()
    current = dt.astimezone(IST) if dt else now_ist()
    today = current.date()
    cur_time = current.time().replace(tzinfo=None)

    special = get_special_session(today, cfg)
    holiday = get_holiday_info(today, cfg)

    if special:
        s_open = _parse_hhmm(special["open"])
        s_close = _parse_hhmm(special["close"])
        is_open = s_open <= cur_time <= s_close
        return {
            "timestamp_ist": current.isoformat(),
            "date": today.isoformat(),
            "day": current.strftime("%A"),
            "session": "SPECIAL_OPEN" if is_open else "SPECIAL_CLOSED",
            "session_label": special["name"],
            "is_market_open": is_open,
            "is_pre_open": False,
            "is_trading_day": True,
            "timings": {"open": special["open"], "close": special["close"]},
            "holiday": holiday["name"] if holiday else None,
        }

    if holiday:
        return {
            "timestamp_ist": current.isoformat(),
            "date": today.isoformat(),
            "day": current.strftime("%A"),
            "session": "HOLIDAY",
            "session_label": f"Exchange Holiday ({holiday['name']})",
            "is_market_open": False,
            "is_pre_open": False,
            "is_trading_day": False,
            "timings": cfg.get("regular_session", {}),
            "holiday": holiday["name"],
        }

    if today.weekday() >= 5:
        return {
            "timestamp_ist": current.isoformat(),
            "date": today.isoformat(),
            "day": current.strftime("%A"),
            "session": "WEEKEND",
            "session_label": "Weekend Closed",
            "is_market_open": False,
            "is_pre_open": False,
            "is_trading_day": False,
            "timings": cfg.get("regular_session", {}),
            "holiday": None,
        }

    reg = cfg.get("regular_session", {})
    pre_start = _parse_hhmm(reg.get("pre_open_start", "09:00"))
    pre_end = _parse_hhmm(reg.get("pre_open_end", "09:15"))
    mkt_open = _parse_hhmm(reg.get("market_open", "09:15"))
    mkt_close = _parse_hhmm(reg.get("market_close", "15:30"))
    mis_sq = _parse_hhmm(reg.get("intraday_mis_squareoff", "15:15"))

    if pre_start <= cur_time < pre_end:
        session = "PRE_OPEN"
        label = "Pre-Open Session (09:00 - 09:15 IST)"
        is_open = False
        is_pre = True
    elif mkt_open <= cur_time <= mkt_close:
        session = "REGULAR_OPEN"
        label = "Regular Trading Session (09:15 - 15:30 IST)"
        is_open = True
        is_pre = False
    elif cur_time < pre_start:
        session = "PRE_MARKET_CLOSED"
        label = "Before Market Hours"
        is_open = False
        is_pre = False
    else:
        session = "POST_MARKET_CLOSED"
        label = "After Market Close"
        is_open = False
        is_pre = False

    return {
        "timestamp_ist": current.isoformat(),
        "date": today.isoformat(),
        "day": current.strftime("%A"),
        "session": session,
        "session_label": label,
        "is_market_open": is_open,
        "is_pre_open": is_pre,
        "is_trading_day": True,
        "past_intraday_squareoff": cur_time >= mis_sq,
        "timings": reg,
        "holiday": None,
    }


def next_trading_day(from_date: Optional[date] = None) -> str:
    d = (from_date or now_ist().date()) + timedelta(days=1)
    for _ in range(30):
        if is_trading_day(d):
            return d.isoformat()
        d += timedelta(days=1)
    return d.isoformat()
