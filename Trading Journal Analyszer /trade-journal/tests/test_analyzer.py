import io
import unittest
from pathlib import Path

import pandas as pd

from analyzer import full_report, load_journal, overall_stats, winrate_by_setup


ROOT = Path(__file__).resolve().parents[1]


class NamedBuffer(io.StringIO):
    def __init__(self, value, name):
        super().__init__(value)
        self.name = name


class AnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_journal(ROOT / "template.csv")
        cls.report = full_report(cls.df)

    def test_template_loads_and_preserves_pl_r(self):
        self.assertEqual(len(self.df), 10)
        self.assertIn("PL_R", self.df.columns)
        self.assertAlmostEqual(self.df["PL_R"].sum(), 11.75)
        self.assertEqual(self.df.attrs["rows_dropped"], 0)

    def test_overall_statistics(self):
        stats = overall_stats(self.df)
        self.assertEqual(stats["Total Trades"], 10)
        self.assertEqual(stats["Wins"], 6)
        self.assertEqual(stats["Losses"], 4)
        self.assertEqual(stats["Win Rate"], "60.0%")
        self.assertEqual(stats["Total R"], "11.75R")

    def test_setup_results_match_sample(self):
        setups = winrate_by_setup(self.df)
        self.assertEqual(setups.index[0], "Fvg")
        self.assertAlmostEqual(setups.loc["Fvg", "TotalR"], 5.95)
        self.assertAlmostEqual(setups.loc["Breakout", "TotalR"], 3.80)
        self.assertAlmostEqual(setups.loc["Orderblock", "TotalR"], 2.00)

    def test_column_aliases_and_missing_optional_columns(self):
        csv = "date,pair,direction,setup,entry,exit,r multiple\n2025-01-01,EURUSD,long,Breakout,1,2,1.5\n"
        df = load_journal(NamedBuffer(csv, "journal.csv"))
        self.assertEqual(len(df), 1)
        self.assertIn("PL_R", df.columns)
        self.assertTrue(full_report(df)["by_session"].empty)

    def test_missing_required_column_is_actionable(self):
        csv = "Date,Pair,Direction,Setup,Entry,Exit\n2025-01-01,EURUSD,LONG,Breakout,1,2\n"
        with self.assertRaisesRegex(ValueError, "PL_R"):
            load_journal(NamedBuffer(csv, "bad.csv"))

    def test_invalid_rows_are_removed(self):
        csv = (
            "Date,Pair,Direction,Setup,Entry,Exit,PL_R\n"
            "not-a-date,EURUSD,LONG,Breakout,1,2,1\n"
            "2025-01-01,EURUSD,LONG,Breakout,1,2,2\n"
        )
        df = load_journal(NamedBuffer(csv, "journal.csv"))
        self.assertEqual(len(df), 1)
        self.assertEqual(df.attrs["rows_dropped"], 1)

    def test_all_positive_setups_are_not_called_losers(self):
        draft = self.report["system_draft"]
        self.assertIn("lowest-R setup, but still net positive", draft)
        self.assertIn("SAMPLE-SIZE WARNING", draft)


if __name__ == "__main__":
    unittest.main()
