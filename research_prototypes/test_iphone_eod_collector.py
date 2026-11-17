"""Offline regression tests for the public LUCA iPhone EOD collector."""
import importlib.util, io, unittest
from unittest.mock import patch
from pathlib import Path
SPEC=importlib.util.spec_from_file_location("collector",Path(__file__).with_name("iphone_eod_collector.py"))
mod=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(mod)
class FakeResponse:
 def __init__(self, data): self.f=io.BytesIO(data)
 def __enter__(self): return self.f
 def __exit__(self,*args): return False
def bars(rows=25):
 import datetime as dt
 out=["Date,Open,High,Low,Close,Volume"]
 start=dt.date(2026,9,1)
 for i in range(rows):
  d=start+dt.timedelta(days=i)
  out.append(f"{d},1,1.2,0.9,1.1,{1000+i}")
 return ("\n".join(out)+"\n").encode()
class CollectorTests(unittest.TestCase):
 def test_good_rows_are_unverified(self):
  with patch.object(mod.urllib.request,"urlopen",return_value=FakeResponse(bars())):
   row=mod.fetch("AAPL")
  self.assertFalse(row["sec_verified"])
  self.assertIsNone(row["float_shares"])
  self.assertFalse(row["contract_terms_verified"])
  self.assertEqual(row["ticker"],"AAPL")
 def test_short_history_rejected(self):
  with patch.object(mod.urllib.request,"urlopen",return_value=FakeResponse(bars(3))):
   with self.assertRaises(ValueError): mod.fetch("AAPL")
 def test_future_date_rejected(self):
  bad=bars().decode().replace("2026-09-25","2099-09-25").encode()
  with patch.object(mod.urllib.request,"urlopen",return_value=FakeResponse(bad)):
   with self.assertRaises(ValueError): mod.fetch("AAPL")
 def test_zero_price_rejected(self):
  bad=bars().decode().replace("1,1.2,0.9,1.1,1024","1,1.2,0.9,0,1024").encode()
  with patch.object(mod.urllib.request,"urlopen",return_value=FakeResponse(bad)):
   with self.assertRaises(ValueError): mod.fetch("AAPL")
 def test_curated_watchlist_validation_and_rotation(self):
  import tempfile
  import datetime as dt
  with tempfile.TemporaryDirectory() as temp:
   file=Path(temp)/"symbols.txt"
   file.write_text("# curated only\nABCD\nEFGH\nABCD\nIJKL\n")
   symbols, label=mod.load_symbols(file)
   self.assertEqual(symbols, ["ABCD","EFGH","IJKL"])
   self.assertEqual(label, "CURATED_WATCHLIST_NOT_MARKET_WIDE")
   self.assertEqual(mod.select_batch(symbols,dt.date(2026,11,17),limit=2),
                    mod.select_batch(symbols,dt.date(2026,11,17),limit=2))
   file.write_text("ABC/../../BAD\nDEF\nGHI\n")
   with self.assertRaises(ValueError): mod.load_symbols(file)
if __name__=="__main__":unittest.main()
