from __future__ import annotations
import unittest

from autoreview import schema


def result(outcome, feedback=None, reviewer="correctness"):
    return {
        "reviewer": reviewer,
        "outcome": outcome,
        "summary": "Reviewer summary.",
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
    def test_summary_is_required(self):
        missing_summary = {
            "reviewer": "correctness",
            "outcome": "APPROVED",
            "feedback": [],
        }
        with self.assertRaises(schema.SchemaError):
            schema.validate_reviewer_result(missing_summary)

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
        self.assertEqual(coerced["feedback"], [])
        self.assertEqual(coerced["review_error"]["kind"], "invalid_json")

    def test_feedback_line_must_be_positive_when_present(self):
        schema.validate_feedback_item(item())
        file_level = item()
        file_level["line"] = None
        schema.validate_feedback_item(file_level)

        zero_line = item()
        zero_line["line"] = 0
        with self.assertRaises(schema.SchemaError):
            schema.validate_feedback_item(zero_line)


class TestAggregation(unittest.TestCase):
    def test_aggregate_outcomes(self):
        self.assertEqual(schema.aggregate_results([result("APPROVED"), result("APPROVED", reviewer="security")])["outcome"],
                         "APPROVED")
        self.assertEqual(schema.aggregate_results([result("APPROVED"), result("COMMENTED", [item("low")])])["outcome"],
                         "COMMENTED")
        self.assertEqual(schema.aggregate_results([result("NEEDS_CONTEXT")])["outcome"], "NEEDS_CONTEXT")
        self.assertEqual(schema.aggregate_results([result("CHANGES_REQUESTED", [item("high", True)])])["outcome"],
                         "CHANGES_REQUESTED")

    def test_aggregate_injects_reviewer_into_feedback_items(self):
        aggregated = schema.aggregate_results([result("CHANGES_REQUESTED", [item("high", True)], reviewer="security")])
        self.assertEqual(aggregated["feedback"][0]["reviewer"], "security")

    def test_needs_context_does_not_count_as_real_feedback(self):
        aggregated = schema.aggregate_results([schema.coerce_reviewer_result("security", "{not json")])
        self.assertEqual(aggregated["outcome"], "NEEDS_CONTEXT")
        self.assertEqual(aggregated["feedback"], [])
        self.assertEqual(aggregated["counts"], schema._empty_counts())
        self.assertEqual(aggregated["reviewers"][0]["reviewer"], "security")
        self.assertEqual(aggregated["reviewers"][0]["outcome"], "NEEDS_CONTEXT")
        self.assertEqual(aggregated["reviewers"][0]["status"], "invalid_json")
        self.assertIn("error", aggregated["reviewers"][0])

    def test_changes_requested_survives_incomplete_reviewer_metadata(self):
        aggregated = schema.aggregate_results([
            result("CHANGES_REQUESTED", [item("high", True)], reviewer="correctness"),
            schema.coerce_reviewer_result("security", "{not json"),
        ])
        self.assertEqual(aggregated["outcome"], "CHANGES_REQUESTED")
        self.assertEqual(aggregated["counts"]["high"], 1)
        self.assertEqual(len(aggregated["feedback"]), 1)
        self.assertEqual(aggregated["feedback"][0]["reviewer"], "correctness")
        self.assertEqual(
            [(r["reviewer"], r["outcome"], r["status"]) for r in aggregated["reviewers"]],
            [("correctness", "CHANGES_REQUESTED", "completed"), ("security", "NEEDS_CONTEXT", "invalid_json")],
        )


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
