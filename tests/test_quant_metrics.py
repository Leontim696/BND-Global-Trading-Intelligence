"""Regression tests for annualized performance metrics."""
import unittest
from src.bnd.quant_metrics import performance_metrics, compare_to_benchmark


class PerformanceMetricTests(unittest.TestCase):
    def test_flat_curve(self):
        result = performance_metrics([100, 100, 100], 252)
        self.assertEqual(result["net_return_pct"], 0)
        self.assertEqual(result["max_drawdown_pct"], 0)
        self.assertIsNone(result["annualized_sharpe"])

    def test_drawdown_and_return(self):
        result = performance_metrics([100, 120, 90, 110], 252)
        self.assertAlmostEqual(result["max_drawdown_pct"], 25)
        self.assertAlmostEqual(result["net_return_pct"], 10)

    def test_sharpe_requires_nonzero_variance(self):
        result = performance_metrics([100, 110, 110, 121], 252)
        self.assertIsNotNone(result["annualized_sharpe"])

    def test_benchmark_difference(self):
        result = compare_to_benchmark([100, 110, 120], [100, 105, 110], 252)
        self.assertAlmostEqual(result["excess_net_return_pct"], 10)

    def test_mismatched_curve_rejected(self):
        with self.assertRaises(ValueError):
            compare_to_benchmark([100, 110], [100, 110, 120], 252)

    def test_invalid_equity_rejected(self):
        for curve in ([100], [100, 0], [100, float("nan")]):
            with self.subTest(curve=curve):
                with self.assertRaises(ValueError):
                    performance_metrics(curve, 252)

    def test_invalid_frequency_rejected(self):
        with self.assertRaises(ValueError):
            performance_metrics([100, 101], 0)

if __name__ == "__main__":
    unittest.main()
