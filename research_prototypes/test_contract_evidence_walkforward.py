import datetime as dt,unittest
from contract_evidence_walkforward import evidence,walkforward
URL="https://www.sec.gov/Archives/edgar/data/123/000000012326000001/x.htm"
class ResearchTests(unittest.TestCase):
 def test_sec_keywords_not_certification(self):
  r=evidence(b"convertible notes and warrants",URL)
  self.assertFalse(r["sec_contract_terms_verified"])
  self.assertIn("CB",[x["category"] for x in r["evidence_flags"]])
 def test_reject_fake_sec(self):
  with self.assertRaises(ValueError):evidence(b"x","https://www.sec.gov.evil.test/Archives/edgar/data/x")
 def test_reject_large(self):
  with self.assertRaises(ValueError):evidence(b"x"*3000001,URL)
 def test_walkforward(self):
  rows=[{"ticker":"ABCD","date":str(dt.date(2026,1,1)+dt.timedelta(days=i)),"close":1+i*.02,"score":45} for i in range(40)]
  r=walkforward(rows);self.assertFalse(r["validated"]);self.assertFalse(r["orders_enabled"]);self.assertGreater(r["test"]["observations"],0)
 def test_insufficient(self):self.assertEqual(walkforward([])["status"],"INSUFFICIENT_HISTORY")
if __name__=="__main__":unittest.main()
