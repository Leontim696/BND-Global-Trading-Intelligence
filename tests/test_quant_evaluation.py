"""Offline tests for deterministic market-data and walk-forward evaluation."""
import tempfile
import unittest
from pathlib import Path

from src.bnd.quant_backtest import Bar, BacktestConfig
from src.bnd.quant_evaluation import load_ohlc_csv, sma_signals, buy_and_hold, evaluate_sma_walk_forward


class QuantEvaluationTests(unittest.TestCase):
    def test_csv_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bars.csv"
            p.write_text("timestamp,open,close\\n2026-01-01,100,101\\n2026-01-02,102,103\\n".replace("\\n", "\n"))
            self.assertEqual(len(load_ohlc_csv(p)), 2)

    def test_duplicate_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bars.csv"
            p.write_text("timestamp,open,close\na,1,1\na,2,2\n")
            with self.assertRaises(ValueError):
                load_ohlc_csv(p)

    def test_sma_has_warmup(self):
        bars = [Bar(x, x) for x in (1, 2, 3, 4)]
        self.assertEqual(sma_signals(bars, 3), [False, False, True, True])

    def test_benchmark_uses_next_bar_open(self):
        bars = [Bar(100, 100), Bar(200, 220)]
        result = buy_and_hold(bars, BacktestConfig(fee_bps=0, slippage_bps=0))
        self.assertAlmostEqual(result["final_equity"], 11000)

    def test_walk_forward_folds_are_independent(self):
        bars = [Bar(100+i, 100+i) for i in range(12)]
        folds = evaluate_sma_walk_forward(bars, 3, 6, 3,
                                           BacktestConfig(fee_bps=0, slippage_bps=0))
        self.assertEqual(len(folds), 2)
        self.assertEqual(folds[0]["test_start"], 6)
        self.assertEqual(folds[1]["test_start"], 9)
        self.assertAlmostEqual(folds[0]["strategy"]["starting_cash"], 10000)
        self.assertAlmostEqual(folds[1]["strategy"]["starting_cash"], 10000)

    def test_invalid_window_rejected(self):
        bars = [Bar(100, 100)] * 10
        with self.assertRaises(ValueError):
            evaluate_sma_walk_forward(bars, 7, 6, 2)


if __name__ == "__main__":
    unittest.main()
