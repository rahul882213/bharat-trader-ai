import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("exit_planner", Path(__file__).resolve().parents[1] / "exit_planner.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestExitPlanner(unittest.TestCase):
    def test_buy_exit_levels_order(self):
        candles = [
            {"date": f"2026-01-{i+1:02d}", "open": 990 + i, "high": 1000 + i, "low": 985 + i, "close": 995 + i, "volume": 100000}
            for i in range(30)
        ]
        res = mod.plan_exit_from_candles("TCS", candles, entry_price=1025.0, side="BUY", product="MIS")
        self.assertTrue(res["available"])
        self.assertLess(res["initial_stop_loss"], res["entry_price"])
        self.assertGreater(res["target_1"], res["entry_price"])
        self.assertGreater(res["target_2"], res["target_1"])
        self.assertGreater(res["target_3"], res["target_2"])
        self.assertGreaterEqual(res["risk_reward"]["target_2_rr"], 2.0)


if __name__ == "__main__":
    unittest.main()
