import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("position_sizer", Path(__file__).resolve().parents[1] / "position_sizer.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestPositionSizer(unittest.TestCase):
    def test_exact_prompt_example(self):
        # Capital: ₹10,00,000, Risk: 1%, Entry: ₹500, Stop-loss: ₹480
        res = mod.calculate_position_size(1000000.0, 1.0, 500.0, 480.0)
        self.assertTrue(res["allowed"])
        self.assertLessEqual(res["total_monetary_risk_inr"], 10000.0)
        self.assertGreaterEqual(res["quantity"], 490)
        self.assertLessEqual(res["quantity"], 500)

    def test_fno_blocked_by_default(self):
        res = mod.calculate_position_size(1000000.0, 1.0, 500.0, 480.0, segment="fno", lot_size=25, fno_enabled=False)
        self.assertFalse(res["allowed"])


if __name__ == "__main__":
    unittest.main()
