"""Offline validation of the NasdaqTrader listing importer."""
import unittest
from nasdaq_symbol_universe import parse_directory

def directory(rows):
    header = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
    return (header + "\n" + "\n".join(rows) + "\nFile Creation Time: 20261117\n").encode()

class UniverseTests(unittest.TestCase):
    def test_reject_unexpected_header(self):
        with self.assertRaises(ValueError):
            parse_directory(b"bad input")

    def test_reject_suspiciously_small_listing(self):
        with self.assertRaises(ValueError):
            parse_directory(directory(["TEST|Test Common Stock|S|N|N|100|N|N"]))

    def test_filters_etf_test_issue_and_warrants(self):
        rows = [f"X{i:03d}|Example {i} Common Stock|S|N|N|100|N|N"
                for i in range(120)]
        rows += ["ZZZZ|Example ETF|S|N|N|100|Y|N",
                 "YYYY|Example warrant|S|N|N|100|N|N",
                 "QQQQ|Test security|S|Y|N|100|N|N"]
        symbols = parse_directory(directory(rows))
        self.assertEqual(len(symbols), 120)
        self.assertNotIn("ZZZZ", symbols)
        self.assertNotIn("YYYY", symbols)
        self.assertNotIn("QQQQ", symbols)

if __name__ == "__main__":
    unittest.main()
