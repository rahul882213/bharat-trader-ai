import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("risk_engine", Path(__file__).resolve().parents[1] / "risk_engine.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestRiskEngine(unittest.TestCase):
    def test_blocks_excessive_trade_risk(self):
        res = mod.evaluate_trade_risk(
            symbol="RELIANCE",
            entry_price=1000.0,
            stop_loss=900.0,
            target_price=1250.0,
            quantity=500,  # 500 * 100 = ₹50,000 risk > ₹10,000 (1% of 10L)
        )
        self.assertEqual(res["verdict"], "BLOCK")
        self.assertGreater(len(res["violations"]), 0)

    def test_passes_compliant_trade(self):
        res = mod.evaluate_trade_risk(
            symbol="TCS",
            entry_price=500.0,
            stop_loss=480.0,
            target_price=550.0,
            quantity=250,  # 250 * 20 = ₹5,000 risk <= ₹10,000, R:R 1:2.5
        )
        self.assertEqual(res["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
