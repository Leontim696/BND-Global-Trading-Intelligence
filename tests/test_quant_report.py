"""Offline integration regression tests for SMA walk-forward reporting."""
import unittest

from src.bnd.quant_backtest import Bar, BacktestConfig
from src.bnd.quant_report import evaluate_sma_report


class WalkForwardReportTests(unittest.TestCase):
    def setUp(self):
        self.bars = [Bar(100 + i, 100 + i) for i in range(18)]
        self.config = BacktestConfig(fee_bps=0, slippage_bps=0)

    def test_three_forward_folds_and_aligned_metrics(self):
        report = evaluate_sma_report(self.bars, 3, 6, 4, 252, self.config)
        self.assertEqual(report["summary"]["fold_count"], 3)
        self.assertEqual([f["test_start"] for f in report["folds"]], [6, 10, 14])
        for fold in report["folds"]:
            self.assertEqual(fold["strategy"]["period_count"], 4)
            self.assertEqual(fold["benchmark"]["period_count"], 4)
            self.assertEqual(fold["strategy_execution_count"], 1)
            self.assertAlmostEqual(fold["excess_net_return_pct"], 0)

    def test_flat_prices_have_no_trade_or_profit(self):
        bars = [Bar(100, 100)] * 12
        report = evaluate_sma_report(bars, 3, 6, 3, 252, self.config)
        for fold in report["folds"]:
            self.assertEqual(fold["strategy_execution_count"], 0)
            self.assertEqual(fold["strategy"]["net_return_pct"], 0)
            self.assertEqual(fold["excess_net_return_pct"], 0)
            self.assertIsNone(fold["strategy"]["annualized_sharpe"])

    def test_fees_appear_in_forward_report(self):
        config = BacktestConfig(fee_bps=10, slippage_bps=5)
        report = evaluate_sma_report(self.bars, 3, 6, 4, 252, config)
        self.assertGreater(report["folds"][0]["strategy_fees_paid"], 0)
        self.assertLess(report["folds"][0]["strategy"]["net_return_pct"],
                        evaluate_sma_report(self.bars, 3, 6, 4, 252,
                                            self.config)["folds"][0]["strategy"]["net_return_pct"])

    def test_no_complete_fold_is_error(self):
        with self.assertRaises(ValueError):
            evaluate_sma_report(self.bars[:7], 3, 6, 4, 252, self.config)

    def test_invalid_frequency_is_error(self):
        for frequency in (0, -1, True, 252.0):
            with self.subTest(frequency=frequency):
                with self.assertRaises(ValueError):
                    evaluate_sma_report(self.bars, 3, 6, 4, frequency, self.config)

    def test_summary_is_arithmetic_not_compounded(self):
        report = evaluate_sma_report(self.bars, 3, 6, 4, 252, self.config)
        excess = [f["excess_net_return_pct"] for f in report["folds"]]
        self.assertAlmostEqual(report["summary"]["mean_excess_net_return_pct"],
                               sum(excess) / len(excess))
        self.assertIn("not compounded", report["summary"]["note"])


if __name__ == "__main__":
    unittest.main()
