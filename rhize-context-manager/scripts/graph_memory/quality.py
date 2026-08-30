"""Privacy-safe identity quality metrics composed with Graphify health."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Any, Iterable, Mapping

from .contract import sha256_value
from .resolution import parse_timestamp, validate_entity_type, validate_hash


MAX_METRIC_ROWS = 100_000


class QualityError(ValueError):
    """Raised when quality evidence is malformed, sensitive, or unbounded."""


def build_quality_report(
    reviews: Iterable[Mapping[str, Any]],
    ledger: Iterable[Mapping[str, Any]],
    *,
    measured_at: str,
    graphify_integrity: Mapping[str, Any],
    consolidation_status: Mapping[str, Any],
    labeled_outcomes: Iterable[Mapping[str, Any]] = (),
    operational_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Aggregate bounded counts only; raw candidate and reviewer data never leave."""

    measured_time = parse_timestamp(measured_at, "measured_at")
    review_rows = _bounded_rows(reviews, "review")
    ledger_rows = _bounded_rows(ledger, "ledger")
    outcome_rows = _bounded_rows(labeled_outcomes, "labeled outcome")
    graphify = _graphify_summary(graphify_integrity)
    consolidation = _consolidation_summary(consolidation_status)
    operations = _operational_counts(operational_counts or {})

    state_counts: Counter[str] = Counter()
    type_counts: dict[str, Counter[str]] = defaultdict(Counter)
    backlog_ages: dict[str, list[float]] = defaultdict(list)
    pair_counts: Counter[str] = Counter()
    rejected_pairs: set[str] = set()
    review_created: dict[str, datetime] = {}
    for review in review_rows:
        _validate_review_metric_row(review)
        state_counts[review["state"]] += 1
        type_counts[review["entityType"]][review["state"]] += 1
        pair_counts[review["pairKey"]] += 1
        if review["state"] == "rejected":
            rejected_pairs.add(review["pairKey"])
        created = parse_timestamp(review["createdAt"], "review createdAt")
        review_created[review["reviewId"]] = created
        if review["state"] in {"pending", "leased", "deferred"}:
            backlog_ages[review["entityType"]].append(
                max(0.0, (measured_time - created).total_seconds())
            )

    decision_latencies: dict[str, list[float]] = defaultdict(list)
    event_counts: Counter[str] = Counter()
    for event in ledger_rows:
        _validate_ledger_metric_row(event)
        event_counts[event["eventType"]] += 1
        created = review_created.get(event["reviewId"])
        if created is not None and event["eventType"] in {
            "ACCEPT_SAME_AS", "REJECT_SAME_AS", "DEFER"
        }:
            occurred = parse_timestamp(event["occurredAt"], "ledger occurredAt")
            decision_latencies[event["entityType"]].append(
                max(0.0, (occurred - created).total_seconds())
            )

    outcomes_by_type: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: {"tuning": Counter(), "held_out": Counter()}
    )
    for outcome in outcome_rows:
        _validate_outcome(outcome)
        actual = outcome["actualDisposition"]
        expected = outcome["expectedDisposition"]
        bucket = outcomes_by_type[outcome["entityType"]][outcome["cohort"]]
        bucket["labeled"] += 1
        bucket[f"expected_{expected}"] += 1
        bucket[f"actual_{actual}"] += 1
        if outcome["reviewerDisagreement"]:
            bucket["reviewerDisagreement"] += 1
        if actual == "same" and expected == "different":
            bucket["falseAcceptance"] += 1
            if outcome["protected"]:
                bucket["protectedFalseAcceptance"] += 1
        if actual == "different" and expected == "same":
            bucket["falseSplit"] += 1
        if actual == expected:
            bucket["correct"] += 1

    per_type = {
        entity_type: _type_report(
            type_counts[entity_type],
            backlog_ages[entity_type],
            decision_latencies[entity_type],
            outcomes_by_type[entity_type],
        )
        for entity_type in sorted(
            set(type_counts) | set(backlog_ages) | set(decision_latencies) | set(outcomes_by_type)
        )
    }
    protected_incidents = sum(
        sum(
            cohort["protectedFalseAcceptanceCount"]
            for cohort in result["labeledEvaluation"].values()
        )
        for result in per_type.values()
    )
    accepted = event_counts["ACCEPT_SAME_AS"]
    reversed_count = event_counts["REVERSE_SAME_AS"]
    blockers = []
    if graphify["status"] != "ok":
        blockers.append("graphify_integrity")
    if consolidation["status"] in {"degraded", "paused_backlog", "failed"}:
        blockers.append("consolidation_health")
    if protected_incidents:
        blockers.append("protected_false_acceptance")

    report = {
        "qualityVersion": 1,
        "measuredAt": measured_at,
        "status": "blocked" if blockers else "ok",
        "automationEligible": False,
        "automationBlockers": blockers,
        "graphifyIntegrity": graphify,
        "consolidation": consolidation,
        "totals": {
            "reviews": sum(state_counts.values()),
            "byState": dict(sorted(state_counts.items())),
            "ledgerEvents": sum(event_counts.values()),
            "byEventType": dict(sorted(event_counts.items())),
            "reversalRate": _ratio(reversed_count, accepted),
            "rejectionRecurrenceCount": sum(
                pair_counts[pair_key] - 1
                for pair_key in rejected_pairs
                if pair_counts[pair_key] > 1
            ),
            "reviewerDisagreementCount": sum(
                sum(
                    cohort["reviewerDisagreementCount"]
                    for cohort in result["labeledEvaluation"].values()
                )
                for result in per_type.values()
            ),
            "protectedIncidentCount": protected_incidents,
        },
        "byEntityType": per_type,
        "operations": operations,
        "privacy": {
            "aggregateOnly": True,
            "containsCandidateContent": False,
            "containsReviewerIdentity": False,
            "containsTenantIdentifier": False,
        },
    }
    report["reportHash"] = sha256_value(report)
    return report


def _type_report(
    states: Counter[str],
    backlog_ages: list[float],
    decision_latencies: list[float],
    outcomes: Mapping[str, Counter[str]],
) -> dict[str, Any]:
    return {
        "byState": dict(sorted(states.items())),
        "backlogAgeSeconds": _distribution(backlog_ages),
        "decisionLatencySeconds": _distribution(decision_latencies),
        "labeledEvaluation": {
            "tuning": _evaluation(outcomes["tuning"]),
            "heldOut": _evaluation(outcomes["held_out"]),
        },
    }


def _evaluation(outcomes: Counter[str]) -> dict[str, Any]:
    expected_different = outcomes["expected_different"]
    expected_same = outcomes["expected_same"]
    actual_same = outcomes["actual_same"]
    return {
        "labeledCount": outcomes["labeled"],
        "correctCount": outcomes["correct"],
        "falseAcceptanceCount": outcomes["falseAcceptance"],
        "falseAcceptanceDenominator": expected_different,
        "falseAcceptanceRate": _ratio(outcomes["falseAcceptance"], expected_different),
        "falseSplitCount": outcomes["falseSplit"],
        "falseSplitDenominator": expected_same,
        "falseSplitRate": _ratio(outcomes["falseSplit"], expected_same),
        "reviewPrecisionDenominator": actual_same,
        "reviewPrecision": _ratio(
            outcomes["actual_same"] - outcomes["falseAcceptance"], actual_same
        ),
        "reviewerDisagreementCount": outcomes["reviewerDisagreement"],
        "reviewerDisagreementDenominator": outcomes["labeled"],
        "reviewerDisagreementRate": _ratio(
            outcomes["reviewerDisagreement"], outcomes["labeled"]
        ),
        "protectedFalseAcceptanceCount": outcomes["protectedFalseAcceptance"],
    }


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "median": None, "p95": None}
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "count": len(ordered),
        "median": round(median(ordered), 6),
        "p95": round(ordered[index], 6),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _bounded_rows(
    rows: Iterable[Mapping[str, Any]], name: str
) -> list[dict[str, Any]]:
    bounded = []
    for index, row in enumerate(rows):
        if index >= MAX_METRIC_ROWS:
            raise QualityError(f"{name} input exceeds the governed row budget")
        bounded.append(dict(row))
    return bounded


def _graphify_summary(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {
        "status", "reportHash", "extractionVersion"
    }:
        raise QualityError("Graphify integrity summary has missing or unknown fields")
    if value["status"] not in {"ok", "degraded", "failed"}:
        raise QualityError("Graphify integrity status is invalid")
    validate_hash(value["reportHash"], "Graphify reportHash")
    if (
        not isinstance(value["extractionVersion"], str)
        or not value["extractionVersion"]
        or len(value["extractionVersion"]) > 128
    ):
        raise QualityError("Graphify extractionVersion is invalid")
    return dict(value)


def _consolidation_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"status", "watermarkLagSeconds", "pendingBacklog"}
    if not isinstance(value, dict) or set(value) != required:
        raise QualityError("consolidation summary has missing or unknown fields")
    if value["status"] not in {
        "ok", "proposed", "advanced_no_proposals", "no_change", "degraded",
        "paused_backlog", "failed",
    }:
        raise QualityError("consolidation summary status is invalid")
    for field in ("watermarkLagSeconds", "pendingBacklog"):
        if (
            isinstance(value[field], bool)
            or not isinstance(value[field], (int, float))
            or not math.isfinite(value[field])
            or value[field] < 0
        ):
            raise QualityError(f"consolidation {field} is invalid")
    return dict(value)


def _operational_counts(value: Mapping[str, int]) -> dict[str, int]:
    allowed = {
        "poisonEvents", "rateLimitEvents", "leaseExpiries", "staleCandidates",
        "blockedReversals", "incompleteTrials",
    }
    if not isinstance(value, Mapping) or not set(value).issubset(allowed):
        raise QualityError("operational counts contain unknown fields")
    result = {field: 0 for field in sorted(allowed)}
    for field, count in value.items():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise QualityError(f"operational count {field} is invalid")
        result[field] = count
    return result


def _validate_review_metric_row(review: Mapping[str, Any]) -> None:
    required = {
        "reviewId", "pairKey", "candidateRevision", "entityType", "state", "risk", "createdAt"
    }
    if not required.issubset(review):
        raise QualityError("review metric row is incomplete")
    validate_hash(review["reviewId"], "review metric reviewId")
    validate_hash(review["pairKey"], "review metric pairKey")
    validate_hash(review["candidateRevision"], "review metric candidateRevision")
    validate_entity_type(review["entityType"])
    if review["state"] not in {
        "pending", "leased", "accepted", "rejected", "deferred", "superseded", "reversed"
    }:
        raise QualityError("review metric state is invalid")
    if review["risk"] not in {"standard", "protected"}:
        raise QualityError("review metric risk is invalid")


def _validate_ledger_metric_row(event: Mapping[str, Any]) -> None:
    required = {"reviewId", "eventType", "entityType", "actorHash", "occurredAt"}
    if not required.issubset(event):
        raise QualityError("ledger metric row is incomplete")
    validate_hash(event["reviewId"], "ledger metric reviewId")
    validate_hash(event["actorHash"], "ledger metric actorHash")
    if event["eventType"] not in {
        "ACCEPT_SAME_AS", "REJECT_SAME_AS", "DEFER", "SUPERSEDE", "REVERSE_SAME_AS"
    }:
        raise QualityError("ledger metric eventType is invalid")
    validate_entity_type(event["entityType"])


def _validate_outcome(outcome: Mapping[str, Any]) -> None:
    required = {
        "entityType", "expectedDisposition", "actualDisposition", "protected", "cohort",
        "reviewerDisagreement",
    }
    if not isinstance(outcome, dict) or set(outcome) != required:
        raise QualityError("labeled outcome has missing or unknown fields")
    validate_entity_type(outcome["entityType"])
    if outcome["expectedDisposition"] not in {"same", "different", "uncertain"}:
        raise QualityError("labeled expectedDisposition is invalid")
    if outcome["actualDisposition"] not in {"same", "different", "deferred"}:
        raise QualityError("labeled actualDisposition is invalid")
    if not isinstance(outcome["protected"], bool):
        raise QualityError("labeled protected flag is invalid")
    if not isinstance(outcome["reviewerDisagreement"], bool):
        raise QualityError("labeled reviewerDisagreement flag is invalid")
    if outcome["cohort"] not in {"tuning", "held_out"}:
        raise QualityError("labeled cohort is invalid")
