"""Offline quant foundation regression tests."""
import unittest
from src.bnd.quant_backtest import Bar, BacktestConfig, backtest, walk_forward_splits


class QuantBacktestTests(unittest.TestCase):
    def test_no_lookahead_first_signal_fills_second_open(self):
        result = backtest([Bar(100, 100), Bar(200, 210)], [True, True],
                          BacktestConfig(fee_bps=0, slippage_bps=0))
        self.assertAlmostEqual(result["final_equity"], 10500)
        self.assertEqual(result["execution_count"], 1)

    def test_no_trades_if_signals_false(self):
        result = backtest([Bar(100, 100), Bar(200, 210)], [False, False])
        self.assertEqual(result["final_equity"], 10000)

    def test_costs_reduce_returns(self):
        bars = [Bar(100, 100), Bar(100, 100), Bar(100, 100)]
        signals = [True, False, False]
        free = backtest(bars, signals, BacktestConfig(fee_bps=0, slippage_bps=0))
        costly = backtest(bars, signals, BacktestConfig(fee_bps=10, slippage_bps=5))
        self.assertLess(costly["final_equity"], free["final_equity"])
        self.assertEqual(costly["execution_count"], 2)

    def test_final_open_position_marked_not_forced_liquidated(self):
        result = backtest([Bar(100, 100), Bar(100, 90)], [True, False],
                          BacktestConfig(fee_bps=0, slippage_bps=0))
        self.assertAlmostEqual(result["final_equity"], 9000)
        self.assertGreater(result["open_units"], 0)

    def test_reject_invalid_inputs(self):
        with self.assertRaises(ValueError):
            Bar(float("nan"), 100)
        with self.assertRaises(ValueError):
            backtest([Bar(1, 1)], [True])
        with self.assertRaises(ValueError):
            backtest([Bar(1, 1), Bar(1, 1)], [1, False])

    def test_walk_forward_has_no_train_test_overlap(self):
        folds = walk_forward_splits(100, 40, 20)
        self.assertEqual(len(folds), 3)
        for train, test in folds:
            self.assertLess(max(train), min(test))
            self.assertEqual(len(train), 40)
            self.assertEqual(len(test), 20)

    def test_drawdown(self):
        result = backtest([Bar(100, 100), Bar(100, 80), Bar(80, 90)],
                          [True, True, True], BacktestConfig(fee_bps=0, slippage_bps=0))
        self.assertGreater(result["max_drawdown_pct"], 0)


if __name__ == "__main__":
    unittest.main()
