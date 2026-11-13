"""Integration Tests for Bharat Trader AI Core Pipeline."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.indian_charges import calculate_indian_charges
from backend.services.workflow import load_module_fn


class TestBharatTraderIntegration(unittest.TestCase):
    def test_indian_charges_intraday_vs_delivery(self):
        intraday = calculate_indian_charges(1000.0, 1020.0, 100, trade_type="equity_intraday", broker="zerodha")
        delivery = calculate_indian_charges(1000.0, 1020.0, 100, trade_type="equity_delivery", broker="zerodha")
        self.assertGreater(intraday["stt"], 0)
        self.assertGreater(delivery["stt"], intraday["stt"])
        self.assertGreater(intraday["gst"], 0)
        self.assertEqual(delivery["brokerage"], 0.0)

    def test_end_to_end_offline_fixture_pipeline(self):
        # Generate deterministic offline OHLCV fixture with realistic volatility (~3.5% stop distance)
        candles = []
        p = 1000.0
        for i in range(80):
            p += 5.0 if (i % 12) < 9 else -4.0
            candles.append({
                "date": f"2026-02-{(i % 28) + 1:02d}",
                "open": p - 12.0,
                "high": p + 22.0,
                "low": p - 24.0,
                "close": p,
                "volume": 120000 if i < 78 else 260000,
            })

        entry_mod = load_module_fn("trader-entry", "entry_engine.py")
        exit_mod = load_module_fn("trader-exit", "exit_planner.py")
        bt_mod = load_module_fn("trader-backtest", "backtester.py")
        budget_mod = load_module_fn("trader-budget", "position_sizer.py")
        risk_mod = load_module_fn("trader-risk", "risk_engine.py")

        entry = entry_mod.evaluate_entry_from_candles("RELIANCE", candles, timeframe="1d", is_live_session=False)
        exit_p = exit_mod.plan_exit_from_candles("RELIANCE", candles, entry_price=entry["ideal_entry_price"] or candles[-1]["close"])
        sizing = budget_mod.calculate_position_size(
            capital_inr=1000000.0,
            risk_pct=1.0,
            entry_price=exit_p["entry_price"],
            stop_loss=exit_p["initial_stop_loss"],
        )
        # Ensure risk check evaluates properly (exposure-capped vs compliant)
        compliant_qty = min(sizing["quantity"], int((1000000.0 * 0.25) // exit_p["entry_price"]))
        risk_compliant = risk_mod.evaluate_trade_risk(
            symbol="RELIANCE",
            entry_price=exit_p["entry_price"],
            stop_loss=exit_p["initial_stop_loss"],
            target_price=exit_p["target_2"],
            quantity=compliant_qty,
            charges_inr=sizing["estimated_charges_inr"],
        )
        bt = bt_mod.run_backtest_on_candles("RELIANCE", candles, strategy="ema_crossover", monte_carlo_runs=500)

        self.assertTrue(entry["available"])
        self.assertTrue(exit_p["available"])
        self.assertTrue(sizing["allowed"])
        self.assertEqual(risk_compliant["verdict"], "PASS")
        self.assertTrue(bt["available"])


if __name__ == "__main__":
    unittest.main()
