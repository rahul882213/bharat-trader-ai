import unittest
from backend.services.indicators import compute_all_indicators


class TestScannerIndicators(unittest.TestCase):
    def test_compute_indicators_on_synthetic_fixture(self):
        # Deterministic synthetic OHLCV fixture for offline indicator unit validation
        candles = []
        price = 1000.0
        for i in range(60):
            price += 4.0 if i < 55 else 15.0
            candles.append({
                "date": f"2026-01-{(i % 28) + 1:02d}",
                "open": price - 3.0,
                "high": price + 5.0,
                "low": price - 5.0,
                "close": price,
                "volume": 100000 if i < 58 else 350000,
            })
        res = compute_all_indicators(candles)
        self.assertIn("latest", res)
        self.assertGreater(res["latest"]["ema9"], res["latest"]["ema21"])
        self.assertGreater(res["latest"]["volume_ratio"], 2.0)


if __name__ == "__main__":
    unittest.main()
