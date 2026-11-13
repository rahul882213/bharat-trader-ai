import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("broker_executor", Path(__file__).resolve().parents[1] / "broker_executor.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestBrokerExecutor(unittest.TestCase):
    def test_live_order_blocked_without_explicit_approval(self):
        res = mod.execute_order(
            {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "side": "BUY",
                "quantity": 10,
                "price": 1350.0,
                "stop_loss": 1320.0,
                "target": 1410.0,
                "product": "MIS",
            },
            mode="live",
            broker="zerodha",
            explicit_user_approval=False,
        )
        self.assertFalse(res["executed"])
        self.assertIn("approval_preview", res)
        self.assertEqual(res["approval_preview"]["quantity"], 10)


if __name__ == "__main__":
    unittest.main()
