"""UTC chronology regression tests for offline OHLC CSV input."""
import tempfile
import unittest
from pathlib import Path

from src.bnd.quant_evaluation import load_ohlc_csv


class ChronologyTests(unittest.TestCase):
    def read_rows(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candles.csv"
            path.write_text("timestamp,open,close\n" + "\n".join(rows) + "\n",
                            encoding="utf-8")
            return load_ohlc_csv(path)

    def test_offsets_are_compared_by_instant_not_text(self):
        bars = self.read_rows([
            "2026-01-01T00:00:00+02:00,100,101",
            "2025-12-31T23:00:00Z,102,103",
        ])
        self.assertEqual(len(bars), 2)

    def test_equal_instant_different_offsets_is_duplicate(self):
        with self.assertRaises(ValueError):
            self.read_rows([
                "2026-01-01T00:00:00+02:00,100,101",
                "2025-12-31T22:00:00Z,102,103",
            ])

    def test_reverse_utc_order_rejected(self):
        with self.assertRaises(ValueError):
            self.read_rows([
                "2026-01-01T00:00:00+00:00,100,101",
                "2026-01-01T00:30:00+02:00,102,103",
            ])

    def test_invalid_iso_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            self.read_rows(["not-a-date,100,101", "also-not-a-date,102,103"])

    def test_date_only_timestamps_interpreted_utc(self):
        self.assertEqual(len(self.read_rows([
            "2026-01-01,100,101", "2026-01-02,102,103"
        ])), 2)

    def test_empty_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            self.read_rows([",100,101", "2026-01-02,102,103"])


if __name__ == "__main__":
    unittest.main()
