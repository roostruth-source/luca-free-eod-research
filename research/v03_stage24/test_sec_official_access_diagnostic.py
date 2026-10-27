"""No-network SEC official access diagnostic tests."""
import io
import urllib.error
import unittest
from sec_official_access_diagnostic import ENDPOINTS, diagnose


class Response:
    status=200
    def __init__(self, content=b'{"ok":true}'):self.content=content
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.content[:n]


class Tests(unittest.TestCase):
    def test_all_official_and_get_only(self):
        calls=[]
        def opener(req,timeout):
            calls.append(req.full_url)
            self.assertEqual(req.get_method(),"GET")
            self.assertIn("LUCA-Research",req.get_header("User-agent"))
            self.assertIn(timeout,(15,))
            return Response()
        result=diagnose(opener)
        self.assertEqual(len(calls),3)
        self.assertEqual(set(calls),set(ENDPOINTS.values()))
        self.assertTrue(all(x["status"]=="REACHABLE_PARTIAL_NOT_PARSED" for x in result["endpoints"].values()))
        self.assertFalse(result["sec_risk_cleared"])
        self.assertFalse(result["real_trades_allowed"])

    def test_403_kept_as_failure(self):
        def opener(req,timeout):
            raise urllib.error.HTTPError(req.full_url,403,"Forbidden",{},None)
        result=diagnose(opener)
        self.assertTrue(all(x["status"]=="HTTP_403" for x in result["endpoints"].values()))
        self.assertFalse(result["sec_filing_verified"])

    def test_partial_outage_does_not_cause_false_success(self):
        def opener(req,timeout):
            if "company_tickers" in req.full_url:
                raise urllib.error.HTTPError(req.full_url,403,"Forbidden",{},None)
            return Response()
        result=diagnose(opener)
        self.assertEqual(result["endpoints"]["official_ticker_map"]["status"],"HTTP_403")
        self.assertEqual(result["endpoints"]["official_data_submissions_GPUS"]["status"],
                         "REACHABLE_PARTIAL_NOT_PARSED")
        self.assertFalse(result["sec_risk_cleared"])

    def test_network_exception_not_swallowed_as_success(self):
        def opener(req,timeout):
            raise TimeoutError("timeout")
        result=diagnose(opener)
        self.assertTrue(all(x["status"]=="ERROR_TimeoutError" for x in result["endpoints"].values()))


if __name__=="__main__":
    unittest.main()
