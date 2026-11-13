import importlib.util
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("backtester", Path(__file__).resolve().parents[1] / "backtester.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestBacktester(unittest.TestCase):
    def test_backtest_with_indian_charges_and_monte_carlo(self):
        candles = []
        for i in range(140):
            # Sine wave + slight drift so EMA(9)/EMA(21) crosses multiple times cleanly
            p = 1000.0 + 90.0 * math.sin(i / 6.0) + i * 0.5
            candles.append({
                "date": f"2026-01-{(i % 28) + 1:02d}",
                "open": round(p - 3.0, 2),
                "high": round(p + 18.0, 2),
                "low": round(p - 18.0, 2),
                "close": round(p, 2),
                "volume": 200000,
            })
        res = mod.run_backtest_on_candles("INFY", candles, strategy="ema_crossover", monte_carlo_runs=1000)
        self.assertTrue(res["available"])
        self.assertTrue(res["bias_controls"]["look_ahead_bias_prevented"])
        self.assertGreater(res["metrics"]["total_trades"], 0)
        self.assertIn("NOT guaranteed future predictions", res["monte_carlo"]["disclaimer"])


if __name__ == "__main__":
    unittest.main()
