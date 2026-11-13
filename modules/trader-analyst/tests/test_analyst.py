import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("fundamental_analyst", Path(__file__).resolve().parents[1] / "fundamental_analyst.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestFundamentalAnalyst(unittest.TestCase):
    def test_parse_reported_financials_no_invented_pledge(self):
        sample_raw = {
            "assetProfile": {"sector": "Energy", "industry": "Oil & Gas", "longBusinessSummary": "Diversified Indian conglomerate."},
            "summaryDetail": {"trailingPE": {"raw": 22.1}, "marketCap": {"raw": 1800000 * 1e7}, "previousClose": {"raw": 1340.0}},
            "financialData": {
                "currentPrice": {"raw": 1344.6},
                "returnOnEquity": {"raw": 0.095},
                "operatingMargins": {"raw": 0.14},
                "debtToEquity": {"raw": 42.0},
                "freeCashflow": {"raw": 45000 * 1e7},
                "operatingCashflow": {"raw": 120000 * 1e7},
                "revenueGrowth": {"raw": 0.16},
                "earningsGrowth": {"raw": 0.18},
            },
            "defaultKeyStatistics": {"priceToBook": {"raw": 2.1}, "trailingEps": {"raw": 60.8}, "sharesOutstanding": {"raw": 1350 * 1e7}},
            "majorHoldersBreakdown": {"insidersPercentHeld": {"raw": 0.503}, "institutionsPercentHeld": {"raw": 0.34}},
            "incomeStatementHistory": {"incomeStatementHistory": [{"endDate": {"fmt": "2026-03-31"}, "totalRevenue": {"raw": 900000 * 1e7}, "ebit": {"raw": 130000 * 1e7}, "netIncome": {"raw": 75000 * 1e7}}]},
            "balanceSheetHistory": {"balanceSheetStatements": [{"totalAssets": {"raw": 1500000 * 1e7}, "totalCurrentAssets": {"raw": 400000 * 1e7}, "totalCurrentLiabilities": {"raw": 250000 * 1e7}}]},
        }
        res = mod.parse_yahoo_fundamentals("RELIANCE", sample_raw)
        self.assertTrue(res["available"])
        self.assertIsNone(res["reported_financial_metrics"]["pledged_shares_pct"])
        self.assertEqual(res["reported_financial_metrics"]["debt_to_equity"], 0.42)
        self.assertGreater(res["reported_financial_metrics"]["roce_pct"], 0)
        self.assertIn("High-Growth", res["classifications"])


if __name__ == "__main__":
    unittest.main()
