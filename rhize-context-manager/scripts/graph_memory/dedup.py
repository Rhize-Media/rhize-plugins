"""Tenant-safe, candidate-only identity scoring with no acceptance path."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any, Iterable, Mapping

from .contract import sha256_value
from .resolution import (
    NORMALIZATION_VERSION,
    HygieneError,
    canonical_pair,
    normalize_entity,
    parse_timestamp,
    trust_rank,
    validate_hash,
)


IDENTITY_REVIEW_SCHEMA_VERSION = "1.0.0"
MAX_INPUT_ENTITIES = 100_000


@dataclass(frozen=True)
class CandidateRule:
    """A review floor and reproducible component weights for one entity type."""

    review_floor: float
    exact_alias_weight: float
    name_weight: float
    context_weight: float
    semantic_weight: float

    def validate(self) -> None:
        values = (
            self.review_floor,
            self.exact_alias_weight,
            self.name_weight,
            self.context_weight,
            self.semantic_weight,
        )
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise HygieneError("candidate rule values must be numeric")
        if not 0 <= self.review_floor <= 1:
            raise HygieneError("candidate review floor must be between zero and one")
        weights = values[1:]
        if any(value < 0 or value > 1 for value in weights) or not math.isclose(sum(weights), 1.0):
            raise HygieneError("candidate component weights must sum to one")


@dataclass(frozen=True)
class CandidatePolicy:
    """Caller-approved candidate policy; no threshold grants identity authority."""

    scoring_model_version: str
    evidence_version: str
    schema_version: str
    rules: Mapping[str, CandidateRule]
    max_entities_per_source: int = 100
    max_entities_per_type: int = 1000
    max_pair_comparisons: int = 10_000
    max_candidates: int = 1000
    candidate_ttl_seconds: int = 86_400

    def validate(self) -> None:
        for value, name in (
            (self.scoring_model_version, "scoring_model_version"),
            (self.evidence_version, "evidence_version"),
            (self.schema_version, "schema_version"),
        ):
            if not isinstance(value, str) or not value or len(value) > 128:
                raise HygieneError(f"{name} must be bounded text")
        if not isinstance(self.rules, Mapping) or not self.rules:
            raise HygieneError("candidate policy requires entity-type rules")
        for entity_type, rule in self.rules.items():
            if not isinstance(entity_type, str) or not entity_type or len(entity_type) > 128:
                raise HygieneError("candidate policy entity type is invalid")
            if not isinstance(rule, CandidateRule):
                raise HygieneError("candidate policy rules must be CandidateRule values")
            rule.validate()
        limits = (
            self.max_entities_per_source,
            self.max_entities_per_type,
            self.max_pair_comparisons,
            self.max_candidates,
            self.candidate_ttl_seconds,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in limits):
            raise HygieneError("candidate policy limits must be positive integers")
        if (
            self.max_entities_per_source > 10_000
            or self.max_entities_per_type > 50_000
            or self.max_pair_comparisons > 1_000_000
            or self.max_candidates > 100_000
            or self.candidate_ttl_seconds > 31_536_000
        ):
            raise HygieneError("candidate policy limits exceed the governed maximum")


def generate_candidates(
    entities: Iterable[Mapping[str, Any]],
    *,
    policy: CandidatePolicy,
    tenant_hash: str,
    namespace_hash: str,
    created_at: str,
    suppressed_candidate_revisions: Iterable[str] = (),
    origin: str = "ingest",
) -> dict[str, Any]:
    """Generate pending reviews inside one explicit partition; never accept SAME_AS."""

    policy.validate()
    validate_hash(tenant_hash, "tenant_hash")
    validate_hash(namespace_hash, "namespace_hash")
    created_time = parse_timestamp(created_at, "created_at")
    if origin not in {"manual", "ingest", "consolidation"}:
        raise HygieneError("candidate origin is invalid")
    suppressed: set[str] = set()
    for index, value in enumerate(suppressed_candidate_revisions):
        if index >= MAX_INPUT_ENTITIES:
            raise HygieneError("suppressed revision input exceeds the governed budget")
        validate_hash(value, "suppressed candidate revision")
        suppressed.add(value)

    normalized = []
    for index, entity in enumerate(entities):
        if index >= MAX_INPUT_ENTITIES:
            raise HygieneError("candidate input exceeds the governed entity budget")
        normalized.append(normalize_entity(entity))
    if any(
        entity["tenantHash"] != tenant_hash or entity["namespaceHash"] != namespace_hash
        for entity in normalized
    ):
        raise HygieneError("candidate input crosses the requested partition")
    entity_ids = [entity["entityId"] for entity in normalized]
    if len(entity_ids) != len(set(entity_ids)):
        raise HygieneError("candidate input contains duplicate entity ids")

    source_counts = Counter(
        (entity["sourceRefHash"], entity["entityType"]) for entity in normalized
    )
    type_counts = Counter(entity["entityType"] for entity in normalized)
    paused_source_types = {
        (source_ref, entity_type)
        for (source_ref, entity_type), count in source_counts.items()
        if count > policy.max_entities_per_source
    }
    paused_types = {
        entity_type for entity_type, count in type_counts.items()
        if count > policy.max_entities_per_type
    }
    unconfigured_types = {
        entity["entityType"] for entity in normalized
        if entity["entityType"] not in policy.rules
    }
    comparable = [
        entity for entity in normalized
        if entity["eligibleForComparison"]
        and (entity["sourceRefHash"], entity["entityType"]) not in paused_source_types
        and entity["entityType"] not in paused_types
    ]

    candidates: list[dict[str, Any]] = []
    deterministic_matches: list[dict[str, Any]] = []
    matched_entity_ids: set[str] = set()
    comparisons = 0
    rejected_comparisons = 0
    suppressed_count = 0
    pair_budget_exceeded = False

    for first, second in combinations(comparable, 2):
        if comparisons >= policy.max_pair_comparisons:
            pair_budget_exceeded = True
            break
        comparisons += 1
        if first["entityType"] != second["entityType"]:
            rejected_comparisons += 1
            continue
        if not set(first["acl"]).intersection(second["acl"]):
            rejected_comparisons += 1
            continue
        pair = canonical_pair(first["entityId"], second["entityId"])
        pair_key = sha256_value({"tenant": tenant_hash, "namespace": namespace_hash, "pair": pair})
        deterministic = _deterministic_disposition(first, second)
        if deterministic is not None:
            if deterministic == "match":
                deterministic_matches.append({"pairKey": pair_key, "candidateIds": list(pair)})
                matched_entity_ids.update(pair)
            else:
                rejected_comparisons += 1
            continue
        if first["protectedType"] or second["protectedType"]:
            rejected_comparisons += 1
            continue
        if first["entityType"] in unconfigured_types:
            rejected_comparisons += 1
            continue

        rule = policy.rules[first["entityType"]]
        components = _score_components(first, second, rule)
        if components["weightedScore"] < rule.review_floor:
            rejected_comparisons += 1
            continue
        source_revisions = sorted(
            {first["sourceRevisionHash"], second["sourceRevisionHash"]}
        )
        shared_acl_scopes = sorted(set(first["acl"]).intersection(second["acl"]))
        acl_scope_hashes = [sha256_value(scope) for scope in shared_acl_scopes]
        acl_summary_hash = sha256_value(shared_acl_scopes)
        trust_summary = min((first["trust"], second["trust"]), key=trust_rank)
        versions = {
            "normalizationVersion": NORMALIZATION_VERSION,
            "scoringModelVersion": policy.scoring_model_version,
            "schemaVersion": policy.schema_version,
            "evidenceVersion": policy.evidence_version,
        }
        candidate_evidence = {
            "pairKey": pair_key,
            "entityType": first["entityType"],
            "sourceRevisionHashes": source_revisions,
            "aclSummaryHash": acl_summary_hash,
            "aclScopeHashes": acl_scope_hashes,
            "trustSummary": trust_summary,
            "risk": "standard",
            "scoreComponents": components,
            "versions": versions,
        }
        candidate_revision = candidate_revision_hash(candidate_evidence)
        matched_entity_ids.update(pair)
        if candidate_revision in suppressed:
            suppressed_count += 1
            continue
        if len(candidates) >= policy.max_candidates:
            pair_budget_exceeded = True
            break
        expires_at = (created_time + timedelta(seconds=policy.candidate_ttl_seconds)).isoformat()
        review_id = sha256_value(f"identity-review:{pair_key}:{candidate_revision}")
        candidates.append(
            {
                "reviewVersion": 1,
                "reviewId": review_id,
                "pairKey": pair_key,
                "candidateRevision": candidate_revision,
                "reviewRevision": sha256_value(
                    {"candidateRevision": candidate_revision, "state": "pending", "sequence": 0}
                ),
                "tenantHash": tenant_hash,
                "namespaceHash": namespace_hash,
                "entityType": first["entityType"],
                "candidateIds": list(pair),
                "sourceRevisionHashes": source_revisions,
                "aclSummaryHash": acl_summary_hash,
                "aclScopeHashes": acl_scope_hashes,
                "trustSummary": trust_summary,
                "scoreComponents": components,
                "versions": versions,
                "createdAt": created_at,
                "updatedAt": created_at,
                "expiresAt": expires_at,
                "state": "pending",
                "risk": "standard",
                "poisonFlags": [],
                "idempotencyKeyHash": sha256_value(f"candidate:{candidate_revision}"),
                "origin": origin,
                "lease": None,
                "decisionId": None,
                "rationaleCode": None,
            }
        )

    candidates.sort(key=lambda item: item["reviewId"])
    deterministic_matches.sort(key=lambda item: item["pairKey"])
    return {
        "generationVersion": 1,
        "status": "degraded" if paused_source_types or paused_types or pair_budget_exceeded else "ok",
        "tenantHash": tenant_hash,
        "namespaceHash": namespace_hash,
        "candidates": candidates,
        "deterministicMatches": deterministic_matches,
        "counts": {
            "input": len(normalized),
            "eligible": len(comparable),
            "comparisons": comparisons,
            "candidates": len(candidates),
            "deterministicMatches": len(deterministic_matches),
            "noCandidate": len(normalized) - len(matched_entity_ids),
            "rejectedComparisons": rejected_comparisons,
            "suppressed": suppressed_count,
            "poisoned": sum(bool(entity["poisonFlags"]) for entity in normalized),
        },
        "pausedSourceTypeHashes": sorted(
            sha256_value({"source": source_ref, "type": entity_type})
            for source_ref, entity_type in paused_source_types
        ),
        "pausedTypes": sorted(paused_types),
        "unconfiguredTypes": sorted(unconfigured_types),
        "pairBudgetExceeded": pair_budget_exceeded,
        "policyHash": candidate_policy_hash(policy),
    }


def _deterministic_disposition(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> str | None:
    first_identity = first["deterministicIdentity"]
    second_identity = second["deterministicIdentity"]
    if first_identity is None and second_identity is None:
        return None
    if not first["deterministicEligible"] or not second["deterministicEligible"]:
        return "different"
    return "match" if first_identity == second_identity else "different"


def _score_components(
    first: Mapping[str, Any], second: Mapping[str, Any], rule: CandidateRule
) -> dict[str, float]:
    first_names = {first["canonicalName"], *first["canonicalAliases"]}
    second_names = {second["canonicalName"], *second["canonicalAliases"]}
    exact_alias = 1.0 if first_names.intersection(second_names) else 0.0
    name_similarity = SequenceMatcher(
        None, first["canonicalName"], second["canonicalName"], autojunk=False
    ).ratio()
    context_similarity = _jaccard(first["comparisonTokens"], second["comparisonTokens"])
    semantic_similarity = _cosine(first["semanticVector"], second["semanticVector"])
    weighted = (
        exact_alias * rule.exact_alias_weight
        + name_similarity * rule.name_weight
        + context_similarity * rule.context_weight
        + semantic_similarity * rule.semantic_weight
    )
    return {
        "exactAlias": round(exact_alias, 6),
        "nameSimilarity": round(name_similarity, 6),
        "contextSimilarity": round(context_similarity, 6),
        "semanticSimilarity": round(semantic_similarity, 6),
        "weightedScore": round(weighted, 6),
    }


def _jaccard(first: Iterable[str], second: Iterable[str]) -> float:
    first_set, second_set = set(first), set(second)
    union = first_set | second_set
    return len(first_set & second_set) / len(union) if union else 0.0


def _cosine(first: Any, second: Any) -> float:
    if first is None or second is None or len(first) != len(second):
        return 0.0
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if first_norm == 0 or second_norm == 0:
        return 0.0
    cosine = sum(left * right for left, right in zip(first, second)) / (
        first_norm * second_norm
    )
    return max(0.0, min(1.0, (cosine + 1) / 2))


def candidate_policy_hash(policy: CandidatePolicy) -> str:
    """Return the one canonical fingerprint used by generation and consolidation."""

    policy.validate()
    return sha256_value({
        "scoringModelVersion": policy.scoring_model_version,
        "evidenceVersion": policy.evidence_version,
        "schemaVersion": policy.schema_version,
        "rules": {
            entity_type: {
                "reviewFloor": rule.review_floor,
                "weights": [
                    rule.exact_alias_weight,
                    rule.name_weight,
                    rule.context_weight,
                    rule.semantic_weight,
                ],
            }
            for entity_type, rule in sorted(policy.rules.items())
        },
        "limits": [
            policy.max_entities_per_source,
            policy.max_entities_per_type,
            policy.max_pair_comparisons,
            policy.max_candidates,
            policy.candidate_ttl_seconds,
        ],
    })


def candidate_revision_hash(candidate: Mapping[str, Any]) -> str:
    """Bind identity evidence, policy versions, tenancy-safe pair, trust, and ACL."""

    return sha256_value(
        {
            "pairKey": candidate["pairKey"],
            "entityType": candidate["entityType"],
            "sourceRevisions": candidate["sourceRevisionHashes"],
            "aclSummaryHash": candidate["aclSummaryHash"],
            "aclScopeHashes": candidate["aclScopeHashes"],
            "trustSummary": candidate["trustSummary"],
            "risk": candidate["risk"],
            "components": candidate["scoreComponents"],
            "versions": candidate["versions"],
        }
    )
