import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("alert_engine", Path(__file__).resolve().parents[1] / "alert_engine.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestAlertEngine(unittest.TestCase):
    def test_price_above_alert_triggers(self):
        candles = [
            {"date": f"2026-01-{i+1:02d}", "open": 490 + i, "high": 500 + i, "low": 485 + i, "close": 495 + i, "volume": 10000}
            for i in range(25)
        ]
        res = mod.evaluate_alert_rule({"symbol": "SBIN", "condition": "price_above", "threshold": 510.0}, candles)
        self.assertTrue(res["triggered"])


if __name__ == "__main__":
    unittest.main()
