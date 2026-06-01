from __future__ import annotations
import unittest

from autoreview import schema


def result(outcome, feedback=None, reviewer="correctness"):
    return {
        "reviewer": reviewer,
        "outcome": outcome,
        "summary": "",
        "feedback": feedback or [],
    }


def item(severity="low", blocking=False):
    return {
        "severity": severity,
        "path": "src/app.py",
        "line": 12,
        "title": "Concrete issue",
        "impact": "Explains the user-visible failure.",
        "evidence": "Diff line or staged context proving the issue.",
        "recommendation": "Minimal fix.",
        "blocking": blocking,
    }


class TestReviewerSchema(unittest.TestCase):
    def test_approved_requires_no_feedback(self):
        self.assertEqual(schema.validate_reviewer_result(result("APPROVED"))["outcome"], "APPROVED")
        with self.assertRaises(schema.SchemaError):
            schema.validate_reviewer_result(result("APPROVED", [item()]))

    def test_commented_is_nonblocking_low_or_info_only(self):
        schema.validate_reviewer_result(result("COMMENTED", [item("low", False), item("info", False)]))
        with self.assertRaises(schema.SchemaError):
            schema.validate_reviewer_result(result("COMMENTED", [item("medium", False)]))
        with self.assertRaises(schema.SchemaError):
            schema.validate_reviewer_result(result("COMMENTED", [item("low", True)]))

    def test_changes_requested_requires_blocking_feedback(self):
        schema.validate_reviewer_result(result("CHANGES_REQUESTED", [item("high", True)]))
        with self.assertRaises(schema.SchemaError):
            schema.validate_reviewer_result(result("CHANGES_REQUESTED", [item("low", False)]))

    def test_invalid_json_coerces_to_needs_context_for_aggregation(self):
        coerced = schema.coerce_reviewer_result("security", "{not json")
        self.assertEqual(coerced["reviewer"], "security")
        self.assertEqual(coerced["outcome"], "NEEDS_CONTEXT")
        self.assertTrue(coerced["feedback"][0]["blocking"])


class TestAggregation(unittest.TestCase):
    def test_aggregate_outcomes(self):
        self.assertEqual(schema.aggregate_results([result("APPROVED"), result("APPROVED", reviewer="security")])["outcome"],
                         "APPROVED")
        self.assertEqual(schema.aggregate_results([result("APPROVED"), result("COMMENTED", [item("low")])])["outcome"],
                         "COMMENTED")
        self.assertEqual(schema.aggregate_results([result("NEEDS_CONTEXT")])["outcome"], "NEEDS_CONTEXT")
        self.assertEqual(schema.aggregate_results([result("CHANGES_REQUESTED", [item("high", True)])])["outcome"],
                         "CHANGES_REQUESTED")


class TestMarkerSchema(unittest.TestCase):
    def test_authorizing_marker_payloads(self):
        approved = schema.aggregate_results([result("APPROVED")])
        commented = schema.aggregate_results([result("COMMENTED", [item("low")])])
        self.assertEqual(schema.validate_marker_payload(approved)["outcome"], "APPROVED")
        self.assertEqual(schema.validate_marker_payload(commented)["outcome"], "COMMENTED")

    def test_non_authorizing_marker_payloads_rejected(self):
        approved_with_empty_reviewers = schema.aggregate_results([result("APPROVED")])
        approved_with_empty_reviewers["reviewers"] = []
        approved_with_commented_reviewer = schema.aggregate_results([result("APPROVED")])
        approved_with_commented_reviewer["reviewers"] = [{"reviewer": "correctness", "outcome": "COMMENTED"}]
        commented_without_commented_reviewer = schema.aggregate_results([result("COMMENTED", [item("low")])])
        commented_without_commented_reviewer["reviewers"] = [{"reviewer": "correctness", "outcome": "APPROVED"}]
        for payload in (
            {},
            {"verdict": "PASS"},
            {"verdict": "PASS_WITH_ISSUES"},
            {"verdict": "FAIL"},
            approved_with_empty_reviewers,
            approved_with_commented_reviewer,
            commented_without_commented_reviewer,
            schema.aggregate_results([result("NEEDS_CONTEXT")]),
            schema.aggregate_results([result("CHANGES_REQUESTED", [item("high", True)])]),
        ):
            with self.assertRaises(schema.SchemaError, msg=payload):
                schema.validate_marker_payload(payload)


if __name__ == "__main__":
    unittest.main()
