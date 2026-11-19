from datetime import datetime, timezone
import unittest

from nasdaq_symbol_scope import (NASDAQ_URL, OTHER_URL, collect,
                                 parse_directory)

ASOF = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
NASDAQ = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
ABC|ABC Inc. - Common Stock|S|N|N|100|N|N
FUND|Example Daily ETF|G|N|N|100|Y|N
WRTW|Example Inc. - Warrants|S|N|N|100|N|N
TEST|Nasdaq Test Issue|Q|Y|N|100|N|N
File Creation Time: 1119202612:00||||||||
"""
OTHER = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
XYZ|XYZ Corp. Common Stock|N|XYZ|N|100|N|XYZ
ABR$D|Arbor Realty Trust Preferred Stock|N|ABRpD|N|100|N|ABR-D
File Creation Time: 1119202612:00||||||||
"""


class Response:
    headers = {"Date": "Thu, 19 Nov 2026 12:00:00 GMT"}
    def __init__(self, text):
        self.raw = text.encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size=-1):
        return self.raw[:size]


def opener(request, timeout):
    return Response(NASDAQ if "nasdaqlisted" in request.full_url else OTHER)


class NasdaqSymbolScopeTests(unittest.TestCase):
    def test_parser_separates_common_etf_warrant_and_test_issue(self):
        records, creation = parse_directory(NASDAQ, NASDAQ_URL)
        self.assertEqual(records["ABC"]["status"], "COMMON_EQUITY_CANDIDATE_SCOPE")
        self.assertEqual(records["FUND"]["status"], "EXCLUDED_ETF_OR_ETP")
        self.assertEqual(records["WRTW"]["status"], "EXCLUDED_NON_COMMON_NAME")
        self.assertEqual(records["TEST"]["status"], "EXCLUDED_TEST_ISSUE")
        self.assertTrue(creation.startswith("File Creation Time:"))

    def test_collect_joins_both_official_directories_and_keeps_missing_unknown(self):
        result = collect(["ABC", "XYZ", "NONE"], ASOF, opener)
        by = {row["symbol"]: row for row in result["rows"]}
        self.assertEqual(result["status"], "OFFICIAL_NASDAQ_DIRECTORY_COLLECTED")
        self.assertEqual(by["ABC"]["status"], "COMMON_EQUITY_CANDIDATE_SCOPE")
        self.assertEqual(by["XYZ"]["exchange_code"], "N")
        self.assertEqual(by["NONE"]["status"], "SYMBOL_DIRECTORY_NOT_MAPPED")
        self.assertTrue(result["NO_ORDERS"])

    def test_official_exchange_native_symbols_outside_scanner_grammar_are_skipped(self):
        records, _ = parse_directory(OTHER, OTHER_URL)
        self.assertIn("XYZ", records)
        self.assertNotIn("ABR$D", records)

    def test_get_only_official_urls(self):
        seen = []
        def checking(request, timeout):
            seen.append(request.full_url)
            self.assertEqual(request.get_method(), "GET")
            return opener(request, timeout)
        collect(["ABC"], ASOF, checking)
        self.assertEqual(seen, [NASDAQ_URL, OTHER_URL])

    def test_malformed_directory_fails_closed(self):
        def bad(request, timeout):
            return Response("not a directory")
        result = collect(["ABC"], ASOF, bad)
        self.assertTrue(result["status"].startswith("SYMBOL_DIRECTORY_"))
        self.assertEqual(result["rows"], [])


if __name__ == "__main__":
    unittest.main()
