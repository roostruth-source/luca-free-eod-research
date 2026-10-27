"""Offline full-path data access safety tests."""
import datetime as dt
import unittest
from full_path_access_probe import evaluate

NOW=dt.datetime(2026,10,27,11,0,tzinfo=dt.timezone.utc)
def result():
    return {"status":"COLLECTED_UNVERIFIED","validation_status":"NOT_VALIDATED",
            "real_trades_allowed":False,"discovered_count":3,
            "batches":[{"size":2,"status":"OK","returned":2},
                       {"size":1,"status":"OK","returned":1}],
            "snapshots_present":3,"priced_count":2,"price_band_count":1,
            "rows":[{"symbol":"A"},{"symbol":"B"},{"symbol":"C"}]}

class FullPathTests(unittest.TestCase):
    def test_complete_all_batches_not_live(self):
        x=evaluate(result(),NOW)
        self.assertEqual(x["snapshot_batch_count"],2)
        self.assertEqual(x["full_path_access"],"ALL_BATCH_GET_OK_SCHEMA_ONLY")
        self.assertFalse(x["not_prospective_t0"] is False)
        self.assertFalse(x["live_signals_confirmed"])
        self.assertFalse(x["real_trades_allowed"])
    def test_batch_403_does_not_approve(self):
        x=result();x["status"]="SNAPSHOTS_UNAVAILABLE";x["batches"][1]["status"]="HTTP_403"
        self.assertEqual(evaluate(x,NOW)["full_path_access"],"NOT_VERIFIED")
    def test_missing_batch_fails(self):
        x=result();x["batches"].pop()
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_SNAPSHOT_BATCHES"):
            evaluate(x,NOW)
    def test_short_rows_fails(self):
        x=result();x["rows"].pop()
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_SNAPSHOT_BATCHES"):
            evaluate(x,NOW)
    def test_batch_429_fails(self):
        x=result();x["batches"][0]["status"]="HTTP_429"
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_SNAPSHOT_BATCHES"):
            evaluate(x,NOW)
    def test_false_trading_claim_fails(self):
        x=result();x["real_trades_allowed"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_ENRICHMENT"):
            evaluate(x,NOW)
    def test_no_validation_claim_fails(self):
        x=result();x["validation_status"]="VALIDATED"
        with self.assertRaisesRegex(ValueError,"UNSAFE_ENRICHMENT"):
            evaluate(x,NOW)
    def test_naive_clock_fails(self):
        with self.assertRaisesRegex(ValueError,"AWARE_CLOCK_REQUIRED"):
            evaluate(result(),dt.datetime(2026,10,27,11,0))
    def test_empty_rows_fails(self):
        x=result();x["rows"]=[]
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_SNAPSHOT_BATCHES"):
            evaluate(x,NOW)

if __name__=="__main__":
    unittest.main()
