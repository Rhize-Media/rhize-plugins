"""Proposal-only, watermarked identity recheck for recent graph entities."""

from __future__ import annotations

import copy
import threading
from typing import Any, Iterable, Mapping

from .contract import sha256_value
from .dedup import MAX_INPUT_ENTITIES, CandidatePolicy, candidate_policy_hash, generate_candidates
from .resolution import normalize_entity, parse_timestamp, validate_hash
from .review import AuthenticatedActor, IdentityReviewStore


MAX_BATCH_SIZE = 1_000
MAX_BACKLOG = 100_000
INITIAL_WATERMARK_REVISION = sha256_value("identity-consolidation:initial")


class ConsolidationError(RuntimeError):
    """Raised when a consolidation precondition or safety bound is invalid."""


class ProposalConsolidator:
    """Advance a CAS watermark only after bounded proposals are durably enqueued."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._watermarks: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._idempotency: dict[str, tuple[str, dict[str, Any]]] = {}

    def status(
        self,
        *,
        tenant_hash: str,
        namespace_hash: str,
        acl_scope_hash: str,
        actor: AuthenticatedActor,
    ) -> dict[str, Any]:
        actor.validate()
        validate_hash(tenant_hash, "tenant_hash")
        validate_hash(namespace_hash, "namespace_hash")
        _require_acl_lane(actor, acl_scope_hash)
        if not actor.roles.intersection({"identity_ingest", "identity_auditor"}):
            raise ConsolidationError("consolidation status requires ingest or audit authority")
        _require_partition(actor, tenant_hash, namespace_hash)
        with self._lock:
            watermark = self._watermarks.get((tenant_hash, namespace_hash, acl_scope_hash))
            return copy.deepcopy(
                watermark or _initial_watermark(tenant_hash, namespace_hash, acl_scope_hash)
            )

    def run(
        self,
        entities: Iterable[Mapping[str, Any]],
        *,
        policy: CandidatePolicy,
        tenant_hash: str,
        namespace_hash: str,
        acl_scope_hash: str,
        expected_watermark_revision: str,
        actor: AuthenticatedActor,
        review_store: IdentityReviewStore,
        run_at: str,
        idempotency_key: str,
        batch_size: int = 100,
        backlog_limit: int = 10_000,
        failure_at: str | None = None,
    ) -> dict[str, Any]:
        """Recheck one bounded batch and enqueue candidates; never decide identity."""

        actor.validate()
        if "identity_ingest" not in actor.roles:
            raise ConsolidationError("consolidation requires identity_ingest authority")
        validate_hash(tenant_hash, "tenant_hash")
        validate_hash(namespace_hash, "namespace_hash")
        _require_partition(actor, tenant_hash, namespace_hash)
        _require_acl_lane(actor, acl_scope_hash)
        validate_hash(expected_watermark_revision, "expected_watermark_revision")
        parse_timestamp(run_at, "run_at")
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= MAX_BATCH_SIZE
        ):
            raise ConsolidationError("consolidation batch size is outside the governed bound")
        if (
            isinstance(backlog_limit, bool)
            or not isinstance(backlog_limit, int)
            or not 1 <= backlog_limit <= MAX_BACKLOG
        ):
            raise ConsolidationError("consolidation backlog limit is outside the governed bound")

        source_entities = []
        for index, entity in enumerate(entities):
            if index >= MAX_INPUT_ENTITIES:
                raise ConsolidationError("consolidation input exceeds the governed entity budget")
            source_entities.append(copy.deepcopy(dict(entity)))
        normalized = [normalize_entity(entity) for entity in source_entities]
        if any(
            entity["tenantHash"] != tenant_hash
            or entity["namespaceHash"] != namespace_hash
            for entity in normalized
        ):
            raise ConsolidationError("consolidation input crosses the requested partition")
        if any(
            acl_scope_hash not in {sha256_value(scope) for scope in entity["acl"]}
            for entity in normalized
        ):
            raise ConsolidationError("consolidation input crosses the requested ACL lane")
        normalized.sort(key=lambda item: (item["recordedAt"], item["entityId"]))

        key_hash = _idempotency_hash(idempotency_key)
        fingerprint = sha256_value(
            {
                "tenantHash": tenant_hash,
                "namespaceHash": namespace_hash,
                "aclScopeHash": acl_scope_hash,
                "expectedWatermarkRevision": expected_watermark_revision,
                "batchSize": batch_size,
                "backlogLimit": backlog_limit,
                "runAt": run_at,
                "policy": candidate_policy_hash(policy),
                "inputRevisions": [
                    [entity["entityId"], entity["sourceRevisionHash"], entity["recordedAt"]]
                    for entity in normalized
                ],
            }
        )
        replay = self._idempotency_receipt(key_hash, fingerprint)
        if replay is not None:
            return replay

        with self._lock:
            watermark = copy.deepcopy(
                self._watermarks.get(
                    (tenant_hash, namespace_hash, acl_scope_hash),
                    _initial_watermark(tenant_hash, namespace_hash, acl_scope_hash),
                )
            )
            if watermark["watermarkRevision"] != expected_watermark_revision:
                raise ConsolidationError("consolidation watermark compare-and-swap rejected")

        review_counts = review_store.counts(
            tenant_hash=tenant_hash,
            namespace_hash=namespace_hash,
            acl_scope_hashes={acl_scope_hash},
        )
        pending = review_counts["pending"] + review_counts["leased"]
        if pending >= backlog_limit:
            receipt = _receipt(
                status="paused_backlog",
                watermark=watermark,
                run_at=run_at,
                idempotency_hash=key_hash,
                input_count=len(normalized),
                processed_count=0,
                proposal_count=0,
                pending_backlog=pending,
            )
            self._record_idempotency(key_hash, fingerprint, receipt)
            return receipt

        recent = [
            entity
            for entity in normalized
            if (entity["recordedAt"], entity["entityId"])
            > (watermark["recordedAt"], watermark["entityId"])
        ]
        batch = recent[:batch_size]
        if not batch:
            receipt = _receipt(
                status="no_change",
                watermark=watermark,
                run_at=run_at,
                idempotency_hash=key_hash,
                input_count=len(normalized),
                processed_count=0,
                proposal_count=0,
                pending_backlog=pending,
            )
            self._record_idempotency(key_hash, fingerprint, receipt)
            return receipt

        batch_ids = {entity["entityId"] for entity in batch}
        generation = generate_candidates(
            source_entities,
            policy=policy,
            tenant_hash=tenant_hash,
            namespace_hash=namespace_hash,
            created_at=run_at,
            suppressed_candidate_revisions=review_store.suppressed_candidate_revisions(
                tenant_hash=tenant_hash,
                namespace_hash=namespace_hash,
                acl_scope_hashes={acl_scope_hash},
            ),
            origin="consolidation",
        )
        proposals = [
            candidate
            for candidate in generation["candidates"]
            if batch_ids.intersection(candidate["candidateIds"])
        ]
        if failure_at == "after_generation":
            raise ConsolidationError("injected failure after consolidation generation")

        enqueue = review_store.enqueue_candidates(
            proposals, actor=actor, occurred_at=run_at
        )
        if failure_at == "after_enqueue":
            raise ConsolidationError("injected failure after consolidation enqueue")

        last = batch[-1]
        next_watermark = {
            "watermarkVersion": 1,
            "tenantHash": tenant_hash,
            "namespaceHash": namespace_hash,
            "aclScopeHash": acl_scope_hash,
            "recordedAt": last["recordedAt"],
            "entityId": last["entityId"],
            "watermarkRevision": sha256_value(
                {
                    "prior": watermark["watermarkRevision"],
                    "recordedAt": last["recordedAt"],
                    "entityId": last["entityId"],
                    "runAt": run_at,
                }
            ),
        }
        receipt = _receipt(
            status="proposed" if proposals else "advanced_no_proposals",
            watermark=next_watermark,
            prior_watermark_revision=watermark["watermarkRevision"],
            run_at=run_at,
            idempotency_hash=key_hash,
            input_count=len(normalized),
            processed_count=len(batch),
            proposal_count=len(proposals),
            pending_backlog=pending,
            generation_status=generation["status"],
            enqueue_counts=enqueue,
        )
        with self._lock:
            current = self._watermarks.get(
                (tenant_hash, namespace_hash, acl_scope_hash),
                _initial_watermark(tenant_hash, namespace_hash, acl_scope_hash),
            )
            if current["watermarkRevision"] != expected_watermark_revision:
                existing = self._idempotency.get(key_hash)
                if existing is not None and existing[0] == fingerprint:
                    return copy.deepcopy(existing[1])
                raise ConsolidationError("consolidation watermark changed during enqueue")
            if failure_at == "before_watermark":
                raise ConsolidationError("injected failure before watermark commit")
            self._watermarks[(tenant_hash, namespace_hash, acl_scope_hash)] = next_watermark
            self._idempotency[key_hash] = (fingerprint, copy.deepcopy(receipt))
        return copy.deepcopy(receipt)

    def _idempotency_receipt(
        self, key_hash: str, fingerprint: str
    ) -> dict[str, Any] | None:
        with self._lock:
            existing = self._idempotency.get(key_hash)
            if existing is None:
                return None
            if existing[0] != fingerprint:
                raise ConsolidationError("idempotency key is bound to another consolidation run")
            return copy.deepcopy(existing[1])

    def _record_idempotency(
        self, key_hash: str, fingerprint: str, receipt: Mapping[str, Any]
    ) -> None:
        with self._lock:
            self._idempotency[key_hash] = (fingerprint, copy.deepcopy(dict(receipt)))


def _initial_watermark(
    tenant_hash: str, namespace_hash: str, acl_scope_hash: str
) -> dict[str, Any]:
    return {
        "watermarkVersion": 1,
        "tenantHash": tenant_hash,
        "namespaceHash": namespace_hash,
        "aclScopeHash": acl_scope_hash,
        "recordedAt": "1970-01-01T00:00:00+00:00",
        "entityId": "0" * 64,
        "watermarkRevision": INITIAL_WATERMARK_REVISION,
    }


def _idempotency_hash(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ConsolidationError("bounded idempotency key is required")
    return sha256_value(f"identity-consolidation:{value}")


def _require_partition(
    actor: AuthenticatedActor, tenant_hash: str, namespace_hash: str
) -> None:
    if (tenant_hash, namespace_hash) not in actor.authorized_partitions:
        raise ConsolidationError("authenticated actor is not authorized for this partition")


def _require_acl_lane(actor: AuthenticatedActor, acl_scope_hash: str) -> None:
    validate_hash(acl_scope_hash, "acl_scope_hash")
    if acl_scope_hash not in actor.authorized_acl_scope_hashes:
        raise ConsolidationError("authenticated actor is not authorized for this ACL lane")


def _receipt(
    *,
    status: str,
    watermark: Mapping[str, Any],
    run_at: str,
    idempotency_hash: str,
    input_count: int,
    processed_count: int,
    proposal_count: int,
    pending_backlog: int,
    prior_watermark_revision: str | None = None,
    generation_status: str | None = None,
    enqueue_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "receiptVersion": 1,
        "operation": "propose_consolidation_candidates",
        "status": status,
        "tenantHash": watermark["tenantHash"],
        "namespaceHash": watermark["namespaceHash"],
        "aclScopeHash": watermark["aclScopeHash"],
        "watermarkRevision": watermark["watermarkRevision"],
        "priorWatermarkRevision": prior_watermark_revision,
        "watermarkRecordedAt": watermark["recordedAt"],
        "watermarkEntityIdHash": sha256_value(watermark["entityId"]),
        "runAt": run_at,
        "idempotencyKeyHash": idempotency_hash,
        "inputCount": input_count,
        "processedCount": processed_count,
        "proposalCount": proposal_count,
        "pendingBacklog": pending_backlog,
        "generationStatus": generation_status,
        "enqueueCounts": dict(enqueue_counts or {}),
        "identityAuthority": "proposal_only",
    }
