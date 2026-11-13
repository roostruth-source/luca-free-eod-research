import copy
import unittest

from resolve_reset_session_anchor import resolve_reset_session_anchor


def payload():
    return {
        "evaluation_asof": "2026-07-16T21:00:00-04:00",
        "reference_at": "2026-07-16T21:00:00-04:00",
        "ticker": "YYGH",
        "share_combination_event_date": "2026-06-23",
        "reset_after_trading_sessions": 16,
        "trading_sessions_after_event": [
            "2026-06-24", "2026-06-25", "2026-06-26", "2026-06-29",
            "2026-06-30", "2026-07-01", "2026-07-02", "2026-07-06",
            "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10",
            "2026-07-13", "2026-07-14", "2026-07-15", "2026-07-16",
        ],
        "anchor_evidence": {
            "anchor_policy": "AFTER_EVENT_DATE",
            "contract_quote": "the sixteenth Trading Day after such Share Combination Event Date",
            "evidence_available_at": "2026-03-23T16:00:00-04:00",
            "source_url": "https://www.sec.gov/Archives/edgar/data/1985337/note.htm",
        },
    }


class ResetSessionAnchorTests(unittest.TestCase):
    def test_explicit_after_excludes_event_date(self):
        result = resolve_reset_session_anchor(payload())
        self.assertEqual(result["including_event_date_candidate"], "2026-07-15")
        self.assertEqual(result["after_event_date_candidate"], "2026-07-16")
        self.assertEqual(result["selected_reset_date"], "2026-07-16")
        self.assertTrue(result["eligible_for_return_evaluation"])

    def test_explicit_including_selects_other_candidate(self):
        data = payload()
        data["anchor_evidence"]["anchor_policy"] = "INCLUDING_EVENT_DATE"
        data["anchor_evidence"]["contract_quote"] = "including the Share Combination Event Date"
        result = resolve_reset_session_anchor(data)
        self.assertEqual(result["selected_reset_date"], "2026-07-15")

    def test_ambiguous_text_keeps_both_and_blocks(self):
        data = payload()
        data["anchor_evidence"]["anchor_policy"] = "AMBIGUOUS"
        data["anchor_evidence"]["contract_quote"] = "the sixteenth Trading Day"
        result = resolve_reset_session_anchor(data)
        self.assertIsNone(result["selected_reset_date"])
        self.assertFalse(result["eligible_for_return_evaluation"])
        self.assertIn("RESET_DATE_ANCHOR_AMBIGUOUS", result["block_reasons"])

    def test_future_anchor_evidence_is_rejected(self):
        data = copy.deepcopy(payload())
        data["anchor_evidence"]["evidence_available_at"] = "2026-07-17T09:00:00-04:00"
        with self.assertRaisesRegex(ValueError, "future_anchor_evidence_not_allowed"):
            resolve_reset_session_anchor(data)

    def test_after_policy_requires_matching_contract_language(self):
        data = payload()
        data["anchor_evidence"]["contract_quote"] = "the sixteenth Trading Day"
        with self.assertRaisesRegex(ValueError, "after_event_date_language_required"):
            resolve_reset_session_anchor(data)


if __name__ == "__main__":
    unittest.main()
