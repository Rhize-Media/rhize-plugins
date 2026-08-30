from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "rhize-context-manager" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from graph_memory.contract import sha256_value  # noqa: E402
from graph_memory.dedup import CandidatePolicy, CandidateRule, generate_candidates  # noqa: E402
from graph_memory.review import AuthenticatedActor, IdentityReviewStore, current_candidate_state  # noqa: E402


TENANT = sha256_value("tenant-a")
NAMESPACE = sha256_value("namespace-a")
ACL = ["rhize:internal"]
NOW = "2026-08-30T14:00:00+00:00"


def h(value: str) -> str:
    return sha256_value(value)


def entity(
    key: str,
    label: str,
    *,
    entity_type: str = "Topic",
    tenant_hash: str = TENANT,
    namespace_hash: str = NAMESPACE,
    acl: list[str] | None = None,
    trust: str = "high",
    confidence: str = "EXTRACTED",
    quarantined: bool = False,
    aliases: list[str] | None = None,
    deterministic_identity: dict[str, str] | None = None,
    tokens: list[str] | None = None,
    vector: list[float] | None = None,
    recorded_at: str = "2026-08-30T13:00:00+00:00",
    source_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "entityId": h(f"entity:{key}"),
        "tenantHash": tenant_hash,
        "namespaceHash": namespace_hash,
        "entityType": entity_type,
        "acl": copy.deepcopy(acl or ACL),
        "trust": trust,
        "confidenceClass": confidence,
        "quarantined": quarantined,
        "sourceRevisionHash": h(f"revision:{key}"),
        "sourceRefHash": h(source_ref or f"source:{key}"),
        "label": label,
        "aliases": copy.deepcopy(aliases or []),
        "deterministicIdentity": copy.deepcopy(deterministic_identity),
        "comparisonTokens": copy.deepcopy(tokens or ["rhize", "graph"]),
        "semanticVector": copy.deepcopy(vector),
        "recordedAt": recorded_at,
        "schemaVersion": "1.0.0",
        "evidenceVersion": "fixture-v1",
    }


def deterministic(value: str, authority: str = "rhize") -> dict[str, str]:
    return {"kind": "source_id", "valueHash": h(value), "authorityHash": h(authority)}


def policy(**limits: int) -> CandidatePolicy:
    return CandidatePolicy(
        scoring_model_version="identity-score-v1",
        evidence_version="fixture-v1",
        schema_version="1.0.0",
        rules={
            "Topic": CandidateRule(0.65, 0.4, 0.4, 0.2, 0.0),
            "Organization": CandidateRule(0.7, 0.4, 0.4, 0.2, 0.0),
        },
        **limits,
    )


def actor(role: str, key: str = "one") -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_hash=h(f"actor:{key}"),
        session_hash=h(f"session:{key}"),
        roles=frozenset({role}),
        authentication_context_hash=h(f"auth:{key}"),
        authorized_partitions=frozenset({(TENANT, NAMESPACE)}),
    )


def candidate(
    first: dict[str, Any] | None = None,
    second: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generation = generate_candidates(
        [first or entity("a", "Context Compiler"), second or entity("b", "Context Compiler")],
        policy=policy(),
        tenant_hash=TENANT,
        namespace_hash=NAMESPACE,
        created_at=NOW,
        origin="manual",
    )
    assert len(generation["candidates"]) == 1
    return generation["candidates"][0]


def leased_review(
    store: IdentityReviewStore,
    review: dict[str, Any],
    reviewer: AuthenticatedActor,
    *,
    now: str = "2026-08-30T14:01:00+00:00",
    expires: str = "2026-08-30T14:31:00+00:00",
    key: str = "lease-one",
) -> tuple[dict[str, Any], dict[str, Any]]:
    store.enqueue_candidates([review], actor=reviewer, occurred_at=now)
    lease = store.lease(
        review["reviewId"],
        expected_revision=review["reviewRevision"],
        actor=reviewer,
        now=now,
        lease_expires_at=expires,
        idempotency_key=key,
    )
    current = store.show_review(review["reviewId"], actor=reviewer)
    return lease, current


def preview(
    store: IdentityReviewStore,
    review: dict[str, Any],
    reviewer: AuthenticatedActor,
    lease: dict[str, Any],
    operation: str,
    *,
    now: str = "2026-08-30T14:02:00+00:00",
    dependencies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return store.preview(
        review["reviewId"],
        operation=operation,
        expected_revision=review["reviewRevision"],
        lease_token_hash=lease["leaseTokenHash"],
        actor=reviewer,
        now=now,
        current_state=current_candidate_state(review),
        dependency_snapshot=dependencies or [],
    )
