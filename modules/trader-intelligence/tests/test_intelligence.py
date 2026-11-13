import unittest
from backend.services.market_calendar import is_trading_day, get_market_status
from datetime import date, datetime
from zoneinfo import ZoneInfo


class TestMarketIntelligenceCalendar(unittest.TestCase):
    def test_republic_day_holiday_2026(self):
        self.assertFalse(is_trading_day(date(2026, 1, 26)))

    def test_regular_session_open_ist(self):
        ist = ZoneInfo("Asia/Kolkata")
        dt = datetime(2026, 11, 12, 11, 0, tzinfo=ist)  # Thursday 11:00 IST
        st = get_market_status(dt)
        self.assertTrue(st["is_market_open"])
        self.assertEqual(st["session"], "REGULAR_OPEN")


if __name__ == "__main__":
    unittest.main()
