from __future__ import annotations

import json
from typing import Dict, Iterable, List

OUTCOMES = ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "NEEDS_CONTEXT")
AUTHORIZING_OUTCOMES = ("APPROVED", "COMMENTED")
SEVERITIES = ("critical", "high", "medium", "low", "info")
COUNT_KEYS = SEVERITIES
FEEDBACK_KEYS = ("severity", "path", "line", "title", "impact", "evidence", "recommendation", "blocking")
REVIEWER_RESULT_KEYS = ("reviewer", "outcome", "summary", "feedback")
MARKER_PAYLOAD_KEYS = ("outcome", "counts", "feedback", "reviewers")


class SchemaError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SchemaError(message)


def _require_keys(data: dict, keys: Iterable[str], label: str) -> None:
    for key in keys:
        _require(key in data, "%s missing %s" % (label, key))


def _is_non_empty_string(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_positive_int_or_none(value) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value > 0)


def _is_nonblocking_low_or_info(item: dict) -> bool:
    return (not item["blocking"]) and item["severity"] in ("low", "info")


def validate_feedback_item(item: dict) -> dict:
    _require(isinstance(item, dict), "feedback item must be an object")
    _require_keys(item, FEEDBACK_KEYS, "feedback item")
    _require(item["severity"] in SEVERITIES, "unknown severity")
    _require(isinstance(item["path"], str), "path must be a string")
    _require(_is_positive_int_or_none(item["line"]), "line must be a positive integer or null")
    for key in ("title", "impact", "evidence", "recommendation"):
        _require(_is_non_empty_string(item[key]), "%s must be a non-empty string" % key)
    _require(isinstance(item["blocking"], bool), "blocking must be a boolean")
    return item


def validate_reviewer_result(data: dict) -> dict:
    _require(isinstance(data, dict), "reviewer result must be an object")
    _require_keys(data, REVIEWER_RESULT_KEYS, "reviewer result")
    _require(_is_non_empty_string(data["reviewer"]), "reviewer must be a non-empty string")
    _require(data["outcome"] in OUTCOMES, "unknown outcome")
    _require(_is_non_empty_string(data["summary"]), "summary must be a non-empty string")
    _require(isinstance(data["feedback"], list), "feedback must be an array")
    for item in data["feedback"]:
        validate_feedback_item(item)

    outcome = data["outcome"]
    feedback = data["feedback"]
    if outcome == "APPROVED":
        _require(feedback == [], "APPROVED requires empty feedback")
    elif outcome == "COMMENTED":
        _require(all(_is_nonblocking_low_or_info(f) for f in feedback),
                 "COMMENTED permits only non-blocking low/info feedback")
    elif outcome == "CHANGES_REQUESTED":
        _require(any(f["blocking"] for f in feedback), "CHANGES_REQUESTED requires blocking feedback")
    elif outcome == "NEEDS_CONTEXT":
        _require(feedback == [], "NEEDS_CONTEXT requires empty feedback")
    return data


def needs_context_result(reviewer: str, reason: str, kind: str) -> dict:
    return {
        "reviewer": reviewer,
        "outcome": "NEEDS_CONTEXT",
        "summary": reason,
        "feedback": [],
        "review_error": {
            "kind": kind,
            "message": reason,
        },
    }


def coerce_reviewer_result(reviewer: str, raw: str) -> dict:
    try:
        data = json.loads(raw)
        validated = validate_reviewer_result(data)
        if validated["reviewer"] != reviewer:
            raise SchemaError("reviewer mismatch: expected %s, got %s" % (reviewer, validated["reviewer"]))
        return validated
    except json.JSONDecodeError as exc:
        return needs_context_result(reviewer, str(exc), "invalid_json")
    except Exception as exc:
        return needs_context_result(reviewer, str(exc), "invalid_schema")


def _empty_counts() -> Dict[str, int]:
    return {k: 0 for k in COUNT_KEYS}


def _counts(feedback: Iterable[dict]) -> Dict[str, int]:
    counts = _empty_counts()
    for item in feedback:
        counts[item["severity"]] += 1
    return counts


def aggregate_results(results: List[dict]) -> dict:
    validated = [validate_reviewer_result(r) for r in results]
    feedback: List[dict] = []
    reviewers: List[dict] = []
    for result in validated:
        reviewer = result["reviewer"]
        feedback.extend(dict(item, reviewer=reviewer) for item in result["feedback"])
        reviewer_summary = {
            "reviewer": reviewer,
            "outcome": result["outcome"],
            "summary": result["summary"],
            "status": "completed",
        }
        if result["outcome"] == "NEEDS_CONTEXT":
            reviewer_summary["status"] = "needs_context"
        if "review_error" in result:
            reviewer_summary["status"] = result["review_error"]["kind"]
            reviewer_summary["error"] = result["review_error"]["message"]
        reviewers.append(reviewer_summary)

    outcomes = [r["outcome"] for r in validated]
    if any(o == "CHANGES_REQUESTED" for o in outcomes):
        outcome = "CHANGES_REQUESTED"
    elif any(o == "NEEDS_CONTEXT" for o in outcomes):
        outcome = "NEEDS_CONTEXT"
    elif any(o == "COMMENTED" for o in outcomes):
        outcome = "COMMENTED"
    else:
        outcome = "APPROVED"

    return {
        "outcome": outcome,
        "counts": _counts(feedback),
        "feedback": feedback,
        "reviewers": reviewers,
    }


def validate_counts(counts: dict) -> dict:
    _require(isinstance(counts, dict), "counts must be an object")
    _require(set(counts.keys()) == set(COUNT_KEYS), "counts must contain exactly severity keys")
    for key in COUNT_KEYS:
        value = counts[key]
        _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0,
                 "count %s must be a non-negative integer" % key)
    return counts


def validate_reviewer_summary(data: dict, final_outcome: str) -> dict:
    _require(isinstance(data, dict), "reviewer summary must be an object")
    _require_keys(data, ("reviewer", "outcome"), "reviewer summary")
    _require(_is_non_empty_string(data["reviewer"]), "reviewer summary reviewer must be a non-empty string")
    _require(data["outcome"] in AUTHORIZING_OUTCOMES, "reviewer summary outcome does not authorize commit")
    if final_outcome == "APPROVED":
        _require(data["outcome"] == "APPROVED", "APPROVED marker cannot include commented reviewers")
    return data


def validate_marker_payload(data: dict) -> dict:
    _require(isinstance(data, dict), "marker payload must be an object")
    payload = dict(data)
    payload.pop("version", None)
    payload.pop("created", None)
    _require_keys(payload, MARKER_PAYLOAD_KEYS, "marker payload")
    _require(payload["outcome"] in AUTHORIZING_OUTCOMES, "marker outcome does not authorize commit")
    _require(isinstance(payload["feedback"], list), "feedback must be an array")
    for item in payload["feedback"]:
        validate_feedback_item(item)
    validate_counts(payload["counts"])
    _require(payload["counts"] == _counts(payload["feedback"]), "counts do not match feedback")
    _require(isinstance(payload["reviewers"], list), "reviewers must be an array")
    _require(payload["reviewers"], "reviewers must not be empty")
    for reviewer in payload["reviewers"]:
        validate_reviewer_summary(reviewer, payload["outcome"])
    if payload["outcome"] == "APPROVED":
        _require(payload["feedback"] == [], "APPROVED marker requires empty feedback")
    if payload["outcome"] == "COMMENTED":
        _require(all(_is_nonblocking_low_or_info(f) for f in payload["feedback"]),
                 "COMMENTED marker permits only non-blocking low/info feedback")
        _require(any(r["outcome"] == "COMMENTED" for r in payload["reviewers"]),
                 "COMMENTED marker requires at least one commented reviewer")
    return payload
