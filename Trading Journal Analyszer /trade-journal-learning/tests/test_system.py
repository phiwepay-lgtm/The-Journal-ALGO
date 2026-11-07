import json
import sqlite3
import unittest

from analyser import (
    DB_PATH,
    LEARNED_PATH,
    continuous_learning,
    load_journal,
    read_learned_system,
    read_trades_select_only,
)
from app import calculate_heikin_ashi, generate_ohlc
from security import ReadOnlyViolation, enforce_read_only_request


class LearningSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = continuous_learning()

    def test_journal_loads_ten_template_rows(self):
        journal = load_journal()
        self.assertEqual(len(journal), 10)
        self.assertAlmostEqual(journal["PL_R"].sum(), 11.75)
        self.assertEqual(self.report["overall"]["win_rate"], 60.0)

    def test_report_contains_required_pattern_sections(self):
        self.assertIn("win_rate_by_setup", self.report)
        self.assertIn("win_rate_by_time", self.report)
        self.assertIn("common_mistakes", self.report)
        self.assertIn("loss_reasons", self.report)

    def test_sqlite_reader_returns_rows_and_database_is_query_only(self):
        rows = read_trades_select_only()
        self.assertEqual(len(rows), 10)
        connection = sqlite3.connect(f"{DB_PATH.resolve().as_uri()}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only = ON")
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("INSERT INTO trades (source_row, date, pair, direction, setup, pl_r) VALUES (99, 'x', 'x', 'x', 'x', 1)")
        connection.close()

    def test_learned_system_is_encrypted_and_decryptable(self):
        token = LEARNED_PATH.read_bytes()
        self.assertNotIn(b"Pattern_A", token)
        self.assertNotIn(b"HA uptrend", token)
        learned = read_learned_system()
        self.assertEqual(learned["system_status"], "Pattern A found")
        self.assertEqual(learned["execution_learning"]["confirmation"], "HA reversal candle + volume spike")

    def test_heikin_ashi_formula_and_seeding(self):
        candles = [
            {"time": 1, "open": 10, "high": 15, "low": 8, "close": 12, "volume": 100},
            {"time": 2, "open": 12, "high": 16, "low": 10, "close": 14, "volume": 200},
        ]
        ha = calculate_heikin_ashi(candles)
        self.assertAlmostEqual(ha[0]["open"], 11.0)
        self.assertAlmostEqual(ha[0]["close"], 11.25)
        self.assertAlmostEqual(ha[1]["open"], 11.125)
        self.assertAlmostEqual(ha[1]["close"], 13.0)
        self.assertAlmostEqual(ha[1]["high"], 16.0)
        self.assertAlmostEqual(ha[1]["low"], 10.0)

    def test_generated_ohlc_is_deterministic_and_valid(self):
        first = generate_ohlc("XAUUSD", "M5", 20)
        second = generate_ohlc("XAUUSD", "M5", 20)
        self.assertEqual(first, second)
        for candle in first:
            self.assertGreaterEqual(candle["high"], max(candle["open"], candle["close"]))
            self.assertLessEqual(candle["low"], min(candle["open"], candle["close"]))

    def test_vercel_post_is_blocked_but_read_may_pass_guard(self):
        url = "https://example-journal.vercel.app/api/trades"
        with self.assertRaisesRegex(ReadOnlyViolation, "READ-ONLY VIOLATION BLOCKED"):
            enforce_read_only_request("POST", url)
        self.assertTrue(enforce_read_only_request("GET", url))


if __name__ == "__main__":
    unittest.main()
