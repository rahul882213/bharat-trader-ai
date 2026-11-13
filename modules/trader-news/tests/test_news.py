import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("news_analyst", Path(__file__).resolve().parents[1] / "news_analyst.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestNewsAnalyst(unittest.TestCase):
    def test_order_win_bullish_classification(self):
        res = mod.classify_news_item(
            "HAL bagged defence order win worth Rs 2400 crore from Ministry of Defence",
            "Revenue visibility improves."
        )
        self.assertEqual(res["event_category"], "Order Wins")
        self.assertEqual(res["sentiment"], "BULLISH")

    def test_regulatory_bearish_classification(self):
        res = mod.classify_news_item(
            "SEBI notice issued for penalty and probe after profit falls in Q2",
            "Shares slump 5%."
        )
        self.assertEqual(res["sentiment"], "BEARISH")


if __name__ == "__main__":
    unittest.main()
