from io import BytesIO
import json
import unittest
from zipfile import ZipFile

from restore_previous_ledger import restore


class Response:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, *_):
        return self.body


class RestoreTests(unittest.TestCase):
    def test_uses_previous_successful_run_only(self):
        ledger = {"schema_version": "LUCA_V10_PROSPECTIVE_LEDGER_1", "event_count": 2}
        data = BytesIO()
        with ZipFile(data, "w") as archive:
            archive.writestr("prospective_ledger.json", json.dumps(ledger))
        seen = []
        def opener(request, timeout):
            url = request.full_url
            seen.append(url)
            if "/runs?" in url:
                return Response(json.dumps({"workflow_runs": [{"id": 9}, {"id": 8}]}).encode())
            if "/runs/8/artifacts" in url:
                return Response(json.dumps({"artifacts": [
                    {"id": 77, "name": "luca-v10-executable-research-build", "expired": False}
                ]}).encode())
            if "/artifacts/77/zip" in url:
                return Response(data.getvalue())
            raise AssertionError(url)
        result = restore("owner/repo", 9, "token", opener)
        self.assertEqual(result["event_count"], 2)
        self.assertFalse(any("/runs/9/artifacts" in url for url in seen))

    def test_custom_scheduler_workflow_and_branch(self):
        seen = []
        def opener(request, timeout):
            seen.append(request.full_url)
            return Response(json.dumps({"workflow_runs": []}).encode())
        self.assertIsNone(restore("owner/repo", 1, "token", opener,
                                  workflow="luca-v10-daily-observation.yml", branch="main"))
        self.assertIn("luca-v10-daily-observation.yml", seen[0])
        self.assertIn("branch=main", seen[0])

    def test_repo_path_must_be_safe(self):
        with self.assertRaisesRegex(ValueError, "github_repo_and_token_required"):
            restore("owner/../other", 1, "token")


if __name__ == "__main__":
    unittest.main()
