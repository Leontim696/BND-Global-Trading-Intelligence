"""Offline regression tests for opt-in continuous crypto bar intervals."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.bnd.quant_evaluation import load_ohlc_csv


class CryptoIntervalTests(unittest.TestCase):
    def _read(self, rows, interval):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "candles.csv"
            path.write_text("timestamp,open,close\n" + "\n".join(rows) + "\n",
                            encoding="utf-8")
            return load_ohlc_csv(path, expected_interval_seconds=interval)

    def test_hourly_contiguous_bars_accepted(self):
        rows = [
            "2026-01-01T00:00:00Z,100,101",
            "2026-01-01T01:00:00Z,101,102",
            "2026-01-01T02:00:00Z,102,103",
        ]
        self.assertEqual(len(self._read(rows, 3600)), 3)

    def test_timezone_offsets_compare_actual_instants(self):
        rows = [
            "2026-01-01T00:00:00+00:00,100,101",
            "2026-01-01T02:00:00+01:00,101,102",
        ]
        self.assertEqual(len(self._read(rows, 3600)), 2)

    def test_missing_crypto_candle_rejected(self):
        rows = [
            "2026-01-01T00:00:00Z,100,101",
            "2026-01-01T02:00:00Z,101,102",
        ]
        with self.assertRaisesRegex(ValueError, "Missing or irregular"):
            self._read(rows, 3600)

    def test_short_irregular_interval_rejected(self):
        rows = [
            "2026-01-01T00:00:00Z,100,101",
            "2026-01-01T00:30:00Z,101,102",
        ]
        with self.assertRaisesRegex(ValueError, "Missing or irregular"):
            self._read(rows, 3600)

    def test_interval_is_optional_for_session_markets(self):
        rows = [
            "2026-01-02T16:00:00Z,100,101",
            "2026-01-05T16:00:00Z,101,102",
        ]
        self.assertEqual(len(self._read(rows, None)), 2)

    def test_invalid_interval_rejected(self):
        rows = [
            "2026-01-01T00:00:00Z,100,101",
            "2026-01-01T01:00:00Z,101,102",
        ]
        for value in (True, 0, -3600, 3600.0, "3600"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Expected interval"):
                    self._read(rows, value)


if __name__ == "__main__":
    unittest.main()
