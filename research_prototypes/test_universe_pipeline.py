import datetime as dt,unittest
from universe_pipeline import parse_symbols,ticker_map,parse_recent,sample
class Tests(unittest.TestCase):
 def test_filters(self):
  raw=b'Symbol|Security Name|ETF|Test Issue|NextShares\nABCD|Common|N|N|N\nWXYZ|Warrants|N|N|N\nQQQ|ETF|Y|N|N\n'
  self.assertEqual(parse_symbols(raw),['ABCD'])
 def test_sample_unique(self):
  x=sample(['A','B','C','D'],dt.date(2026,11,17),3);self.assertEqual(len(x),len(set(x)))
 def test_map(self):
  self.assertEqual(ticker_map(b'{"0":{"ticker":"abc","cik_str":123}}'),{'ABC':123})
 def test_recent(self):
  raw=b'{"filings":{"recent":{"form":["8-K"],"filingDate":["2026-11-15"],"accessionNumber":["0000000123-26-000001"],"primaryDocument":["x.htm"]}}}'
  self.assertEqual(len(parse_recent(raw,123,dt.date(2026,11,17))),1)
 def test_future_rejected(self):
  raw=b'{"filings":{"recent":{"form":["8-K"],"filingDate":["2027-01-01"],"accessionNumber":["0000000123-27-000001"],"primaryDocument":["x.htm"]}}}'
  self.assertEqual(parse_recent(raw,123,dt.date(2026,11,17)),[])
if __name__=="__main__":unittest.main()
