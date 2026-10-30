"""Offline walk-forward boundary regression tests."""
import unittest
from src.bnd.quant_backtest import Bar, BacktestConfig
from src.bnd.quant_evaluation import evaluate_sma_walk_forward

class BoundaryTests(unittest.TestCase):
    def test_first_trade_uses_first_test_open(self):
        bars = [Bar(100+i, 100+i) for i in range(12)]
        config = BacktestConfig(fee_bps=0, slippage_bps=0)
        result = evaluate_sma_walk_forward(bars, 3, 6, 3, config)[0]
        self.assertAlmostEqual(result["strategy"]["final_equity"], 10000 * 108 / 106)
        self.assertEqual(result["strategy"]["execution_count"], 1)

    def test_reject_invalid_windows(self):
        bars = [Bar(100, 100)] * 12
        for window in (True, 0, -1, 1, 7):
            with self.subTest(window=window):
                with self.assertRaises(ValueError):
                    evaluate_sma_walk_forward(bars, window, 6, 3)

if __name__ == "__main__":
    unittest.main()
