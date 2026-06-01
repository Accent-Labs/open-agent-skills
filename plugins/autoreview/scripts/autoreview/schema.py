from __future__ import annotations
import json
from typing import Dict, Iterable, List

OUTCOMES = ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "NEEDS_CONTEXT")
AUTHORIZING_OUTCOMES = ("APPROVED", "COMMENTED")
SEVERITIES = ("critical", "high", "medium", "low", "info")
COUNT_KEYS = SEVERITIES


class SchemaError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SchemaError(message)


def _is_int_or_none(value) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)


def validate_feedback_item(item: dict) -> dict:
    _require(isinstance(item, dict), "feedback item must be an object")
    for key in ("severity", "path", "line", "title", "impact", "evidence", "recommendation", "blocking"):
        _require(key in item, "feedback item missing %s" % key)
    _require(item["severity"] in SEVERITIES, "unknown severity")
    _require(isinstance(item["path"], str), "path must be a string")
    _require(_is_int_or_none(item["line"]), "line must be a non-negative integer or null")
    for key in ("title", "impact", "evidence", "recommendation"):
        _require(isinstance(item[key], str) and item[key].strip(), "%s must be a non-empty string" % key)
    _require(isinstance(item["blocking"], bool), "blocking must be a boolean")
    return item


def validate_reviewer_result(data: dict) -> dict:
    _require(isinstance(data, dict), "reviewer result must be an object")
    for key in ("reviewer", "outcome", "feedback"):
        _require(key in data, "reviewer result missing %s" % key)
    _require(isinstance(data["reviewer"], str) and data["reviewer"].strip(), "reviewer must be a non-empty string")
    _require(data["outcome"] in OUTCOMES, "unknown outcome")
    _require(isinstance(data["feedback"], list), "feedback must be an array")
    for item in data["feedback"]:
        validate_feedback_item(item)
    if "summary" in data:
        _require(isinstance(data["summary"], str), "summary must be a string")

    outcome = data["outcome"]
    feedback = data["feedback"]
    if outcome == "APPROVED":
        _require(feedback == [], "APPROVED requires empty feedback")
    elif outcome == "COMMENTED":
        _require(all((not f["blocking"]) and f["severity"] in ("low", "info") for f in feedback),
                 "COMMENTED permits only non-blocking low/info feedback")
    elif outcome == "CHANGES_REQUESTED":
        _require(any(f["blocking"] for f in feedback), "CHANGES_REQUESTED requires blocking feedback")
    return data


def _needs_context_result(reviewer: str, reason: str) -> dict:
    return {
        "reviewer": reviewer,
        "outcome": "NEEDS_CONTEXT",
        "summary": reason,
        "feedback": [{
            "severity": "high",
            "path": "",
            "line": None,
            "title": "Reviewer output could not be used",
            "impact": reason,
            "evidence": "The reviewer did not return valid autoreview JSON.",
            "recommendation": "Refresh staged context and rerun this reviewer.",
            "blocking": True,
        }],
    }


def coerce_reviewer_result(reviewer: str, raw: str) -> dict:
    try:
        data = json.loads(raw)
        return validate_reviewer_result(data)
    except Exception as exc:
        return _needs_context_result(reviewer, str(exc))


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
        feedback.extend(result["feedback"])
        reviewers.append({"reviewer": result["reviewer"], "outcome": result["outcome"]})

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
    for key in ("reviewer", "outcome"):
        _require(key in data, "reviewer summary missing %s" % key)
    _require(isinstance(data["reviewer"], str) and data["reviewer"].strip(),
             "reviewer summary reviewer must be a non-empty string")
    _require(data["outcome"] in AUTHORIZING_OUTCOMES, "reviewer summary outcome does not authorize commit")
    if final_outcome == "APPROVED":
        _require(data["outcome"] == "APPROVED", "APPROVED marker cannot include commented reviewers")
    return data


def validate_marker_payload(data: dict) -> dict:
    _require(isinstance(data, dict), "marker payload must be an object")
    payload = dict(data)
    payload.pop("version", None)
    payload.pop("created", None)
    for key in ("outcome", "counts", "feedback", "reviewers"):
        _require(key in payload, "marker payload missing %s" % key)
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
        _require(all((not f["blocking"]) and f["severity"] in ("low", "info") for f in payload["feedback"]),
                 "COMMENTED marker permits only non-blocking low/info feedback")
        _require(any(r["outcome"] == "COMMENTED" for r in payload["reviewers"]),
                 "COMMENTED marker requires at least one commented reviewer")
    return payload
