import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("entry_engine", Path(__file__).resolve().parents[1] / "entry_engine.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestEntryEngine(unittest.TestCase):
    def test_completed_candle_ignores_forming_bar(self):
        candles = []
        price = 500.0
        for i in range(35):
            price += 1.2
            candles.append({
                "date": f"2026-02-01 09:{15 + i:02d}:00",
                "open": price - 1.0,
                "high": price + 1.5,
                "low": price - 1.5,
                "close": price,
                "volume": 50000 if i < 33 else 120000,
            })
        # Append an incomplete bearish drop as forming bar; completed bar should still evaluate cleanly
        candles.append({
            "date": "2026-02-01 09:50:00",
            "open": price,
            "high": price + 0.5,
            "low": price - 25.0,
            "close": price - 20.0,
            "volume": 1000,
        })
        res = mod.evaluate_entry_from_candles("RELIANCE", candles, timeframe="15m", is_live_session=True)
        self.assertTrue(res["forming_candle_ignored_for_breakout"])
        self.assertIn(res["status"], {"ENTRY TRIGGERED", "WATCH", "WAIT"})


if __name__ == "__main__":
    unittest.main()
