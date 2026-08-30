"""Authorized identity-review state, append-only decisions, and logical projection."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .contract import sha256_value
from .dedup import candidate_revision_hash, identity_pair_key
from .resolution import canonical_pair, parse_timestamp, validate_entity_type, validate_hash


REVIEW_STATES = {
    "pending", "leased", "accepted", "rejected", "deferred", "superseded", "reversed",
}
DECISION_ACTIONS = {"accept_same_as", "reject_same_as", "defer"}
RATIONALES = {
    "accept_same_as": {
        "same_authoritative_identity", "same_source_record", "verified_alias",
    },
    "reject_same_as": {
        "insufficient_evidence", "distinct_entities", "type_collision", "scope_collision",
        "stale_evidence",
    },
    "defer": {"insufficient_evidence", "stale_evidence", "dependency_blocked"},
    "reverse_same_as": {"distinct_entities", "stale_evidence", "dependency_blocked"},
}
MAX_REVIEWS = 100_000
MAX_LEDGER_EVENTS = 500_000
MAX_IDEMPOTENCY_RECEIPTS = 1_000_000
MAX_DEPENDENCIES = 256
MAX_PREVIEWS = 200_000


class ReviewError(RuntimeError):
    """Raised when review authority, state, or optimistic concurrency is invalid."""


@dataclass(frozen=True)
class AuthenticatedActor:
    """Hashed identity supplied by a verified host boundary, never by graph text."""

    actor_hash: str
    session_hash: str
    roles: frozenset[str]
    authentication_context_hash: str
    authorized_partitions: frozenset[tuple[str, str]]
    authorized_acl_scope_hashes: frozenset[str]

    def validate(self) -> None:
        validate_hash(self.actor_hash, "actor_hash")
        validate_hash(self.session_hash, "session_hash")
        validate_hash(self.authentication_context_hash, "authentication_context_hash")
        allowed = {"identity_reviewer", "identity_ingest", "identity_auditor"}
        if not isinstance(self.roles, frozenset) or not self.roles or not self.roles.issubset(allowed):
            raise ReviewError("authenticated actor roles are invalid")
        if (
            not isinstance(self.authorized_partitions, frozenset)
            or not self.authorized_partitions
            or len(self.authorized_partitions) > 64
        ):
            raise ReviewError("authenticated actor partitions are invalid")
        for partition in self.authorized_partitions:
            if not isinstance(partition, tuple) or len(partition) != 2:
                raise ReviewError("authenticated actor partition entry is invalid")
            tenant_hash, namespace_hash = partition
            validate_hash(tenant_hash, "authorized tenant hash")
            validate_hash(namespace_hash, "authorized namespace hash")
        if (
            not isinstance(self.authorized_acl_scope_hashes, frozenset)
            or not self.authorized_acl_scope_hashes
            or len(self.authorized_acl_scope_hashes) > 256
        ):
            raise ReviewError("authenticated actor ACL scopes are invalid")
        for scope_hash in self.authorized_acl_scope_hashes:
            validate_hash(scope_hash, "authorized ACL scope hash")


class IdentityReviewStore:
    """In-memory transactional model for a future Neo4j review adapter."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._reviews: dict[str, dict[str, Any]] = {}
        self._pair_reviews: dict[str, str] = {}
        self._sequences: dict[str, int] = {}
        self._ledger: list[dict[str, Any]] = []
        self._same_as: dict[str, tuple[str, str]] = {}
        self._decision_partitions: dict[str, tuple[str, str]] = {}
        self._decision_acl_scopes: dict[str, tuple[str, ...]] = {}
        self._idempotency: dict[str, tuple[str, dict[str, Any]]] = {}
        self._previews: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def enqueue_candidates(
        self,
        candidates: Iterable[Mapping[str, Any]],
        *,
        actor: AuthenticatedActor,
        occurred_at: str,
        failure_at: str | None = None,
    ) -> dict[str, int]:
        incoming = []
        for index, candidate in enumerate(candidates):
            if index >= MAX_REVIEWS:
                raise ReviewError("candidate enqueue exceeds the review budget")
            incoming.append(copy.deepcopy(dict(candidate)))
        for candidate in incoming:
            _validate_review(candidate, initial=True)
            if candidate["poisonFlags"]:
                raise ReviewError("poisoned candidates cannot enter identity review")
        actor.validate()
        parse_timestamp(occurred_at, "occurred_at")
        for candidate in incoming:
            self._require_partition(actor, candidate["tenantHash"], candidate["namespaceHash"])
            self._require_acl(actor, candidate)
            role = "identity_reviewer" if candidate["origin"] == "manual" else "identity_ingest"
            self._require_role(actor, role)

        with self._lock:
            reviews = copy.deepcopy(self._reviews)
            pair_reviews = dict(self._pair_reviews)
            sequences = dict(self._sequences)
            ledger = copy.deepcopy(self._ledger)
            same_as = dict(self._same_as)
            decision_partitions = dict(self._decision_partitions)
            decision_acl_scopes = dict(self._decision_acl_scopes)
            stale_preview_ids: set[str] = set()
            queued = replayed = suppressed = superseded = 0
            for candidate in incoming:
                existing_id = pair_reviews.get(candidate["pairKey"])
                if existing_id is None:
                    reviews[candidate["reviewId"]] = candidate
                    pair_reviews[candidate["pairKey"]] = candidate["reviewId"]
                    sequences[candidate["reviewId"]] = 0
                    queued += 1
                    continue
                existing = reviews[existing_id]
                self._require_acl(actor, existing)
                if existing["candidateRevision"] == candidate["candidateRevision"]:
                    if existing["state"] in {"rejected", "accepted", "reversed", "superseded"}:
                        suppressed += 1
                    else:
                        replayed += 1
                    continue
                if existing["state"] in {"pending", "leased", "deferred", "accepted"}:
                    if "identity_ingest" not in actor.roles:
                        raise ReviewError("stale candidate supersession requires identity_ingest authority")
                    before_edges = self._partition_edges_from_state(
                        same_as,
                        decision_partitions,
                        decision_acl_scopes,
                        existing["tenantHash"],
                        existing["namespaceHash"],
                        actor.authorized_acl_scope_hashes,
                    )
                    after_edges = dict(before_edges)
                    reversal_of = None
                    if existing["state"] == "accepted":
                        reversal_of = existing["decisionId"]
                        has_active_dependency = any(
                            reversal_of in event["dependsOnDecisionIds"]
                            and event["decisionId"] in same_as
                            and self._can_access_acl(actor, event)
                            for event in ledger
                        )
                        if has_active_dependency:
                            raise ReviewError("stale accepted identity decision has active dependencies")
                        del after_edges[reversal_of]
                        del same_as[reversal_of]
                        del decision_partitions[reversal_of]
                        del decision_acl_scopes[reversal_of]
                    event, updated = self._stage_supersession(
                        existing,
                        sequences[existing_id],
                        actor,
                        occurred_at,
                        before_edges=before_edges,
                        after_edges=after_edges,
                        reversal_of=reversal_of,
                    )
                    reviews[existing_id] = updated
                    sequences[existing_id] += 1
                    ledger.append(event)
                    stale_preview_ids.add(existing_id)
                    superseded += 1
                reviews[candidate["reviewId"]] = candidate
                pair_reviews[candidate["pairKey"]] = candidate["reviewId"]
                sequences[candidate["reviewId"]] = 0
                queued += 1
            if failure_at == "after_transition_staged":
                raise ReviewError("injected failure after enqueue transition staging")
            if len(reviews) > MAX_REVIEWS or len(ledger) > MAX_LEDGER_EVENTS:
                raise ReviewError("identity review or ledger capacity is exhausted")
            self._reviews = reviews
            self._pair_reviews = pair_reviews
            self._sequences = sequences
            self._ledger = ledger
            self._same_as = same_as
            self._decision_partitions = decision_partitions
            self._decision_acl_scopes = decision_acl_scopes
            for review_id in stale_preview_ids:
                self._discard_previews(review_id)
            return {
                "queued": queued,
                "replayed": replayed,
                "suppressed": suppressed,
                "superseded": superseded,
            }

    def lease(
        self,
        review_id: str,
        *,
        expected_revision: str,
        actor: AuthenticatedActor,
        now: str,
        lease_expires_at: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        actor.validate()
        self._require_role(actor, "identity_reviewer")
        now_time = parse_timestamp(now, "now")
        expiry = parse_timestamp(lease_expires_at, "lease_expires_at")
        if expiry <= now_time:
            raise ReviewError("lease expiry must be after the lease time")
        fingerprint = sha256_value(
            {
                "operation": "lease", "reviewId": review_id, "actor": _actor_binding(actor),
                "expectedRevision": expected_revision, "leaseExpiresAt": lease_expires_at,
            }
        )
        with self._lock:
            authorized_review = self._authorized_review(review_id, actor)
            idempotency_hash, replay = self._idempotency_lookup(
                idempotency_key,
                fingerprint,
                operation="lease",
                review=authorized_review,
                actor_hash=actor.actor_hash,
            )
            if replay is not None:
                return replay
            lease_token = sha256_value(
                {
                    "reviewId": review_id,
                    "actor": actor.actor_hash,
                    "session": actor.session_hash,
                    "key": idempotency_hash,
                }
            )
            review = self._current(review_id, expected_revision)
            if parse_timestamp(review["expiresAt"], "candidate expiresAt") <= now_time:
                raise ReviewError("identity candidate has expired")
            if review["state"] not in {"pending", "deferred", "leased", "accepted"}:
                raise ReviewError("identity review cannot be leased from its current state")
            current_lease = review["lease"]
            if current_lease is not None and parse_timestamp(current_lease["expiresAt"], "lease expiresAt") > now_time:
                raise ReviewError("identity review already has an active lease")
            updated = copy.deepcopy(review)
            if review["state"] != "accepted":
                updated["state"] = "leased"
            updated["lease"] = {
                "tokenHash": lease_token,
                "actorHash": actor.actor_hash,
                "expiresAt": lease_expires_at,
            }
            updated["updatedAt"] = now
            updated["reviewRevision"] = self._next_revision(updated, self._sequences[review_id] + 1)
            self._reviews[review_id] = updated
            self._sequences[review_id] += 1
            self._discard_previews(review_id)
            receipt = self._receipt(
                "lease", "leased", updated, actor, now, idempotency_hash,
                leaseTokenHash=lease_token,
            )
            self._idempotency[idempotency_hash] = (fingerprint, receipt)
            return copy.deepcopy(receipt)

    def preview(
        self,
        review_id: str,
        *,
        operation: str,
        expected_revision: str,
        lease_token_hash: str,
        actor: AuthenticatedActor,
        now: str,
        current_state: Mapping[str, Any],
        dependency_snapshot: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        actor.validate()
        self._require_role(actor, "identity_reviewer")
        now_time = parse_timestamp(now, "now")
        if operation not in {*DECISION_ACTIONS, "reverse_same_as"}:
            raise ReviewError("unsupported identity impact preview operation")
        dependencies = _validate_dependencies(dependency_snapshot)
        with self._lock:
            review = self._current(review_id, expected_revision)
            self._require_partition(actor, review["tenantHash"], review["namespaceHash"])
            self._require_acl(actor, review)
            self._validate_lease(review, actor, lease_token_hash, now_time)
            self._validate_current_state(review, current_state)
            if operation == "reverse_same_as" and review["state"] != "accepted":
                raise ReviewError("only an accepted identity decision can be reversed")
            if operation != "reverse_same_as" and review["state"] != "leased":
                raise ReviewError("identity decision requires a leased review")
            blocked_decisions: list[str] = []
            blocked_dependencies: list[str] = []
            if operation == "reverse_same_as":
                target = review["decisionId"]
                # Hidden ACL lanes cannot affect an actor-bound preview: even a
                # blocked status would disclose the existence of restricted state.
                blocked_decisions = sorted(
                    event["decisionId"]
                    for event in self._ledger
                    if target in event["dependsOnDecisionIds"]
                    and event["decisionId"] in self._same_as
                    and event["tenantHash"] == review["tenantHash"]
                    and event["namespaceHash"] == review["namespaceHash"]
                    and self._can_access_acl(actor, event)
                )
                blocked_dependencies = sorted(
                    item["dependencyHash"]
                    for item in dependencies
                    if not item["immutableSourceBound"]
                )
            partition_edges = self._actor_visible_edges(review, actor)
            projection_before = self._projection_hash(partition_edges)
            preview = {
                "previewVersion": 1,
                "reviewId": review_id,
                "operation": operation,
                "candidateRevision": review["candidateRevision"],
                "reviewRevision": review["reviewRevision"],
                "tenantHash": review["tenantHash"],
                "namespaceHash": review["namespaceHash"],
                "candidateIds": list(review["candidateIds"]),
                "projectionHash": projection_before,
                "currentClusterMemberIds": _members_for_pair(review["candidateIds"], partition_edges),
                "dependencySnapshotHash": sha256_value(dependencies),
                "dependencyCount": len(dependencies),
                "blockedByDecisionIds": blocked_decisions,
                "blockedByDependencyHashes": blocked_dependencies,
                "canApply": not blocked_decisions and not blocked_dependencies,
                "previewedAt": now,
                "actorHash": actor.actor_hash,
            }
            preview["previewHash"] = sha256_value(preview)
            key = (review_id, actor.actor_hash, review["reviewRevision"], operation)
            if key not in self._previews and len(self._previews) >= MAX_PREVIEWS:
                raise ReviewError("identity impact preview budget is exhausted")
            self._previews[key] = copy.deepcopy(preview)
            return copy.deepcopy(preview)

    def decide(
        self,
        review_id: str,
        *,
        action: str,
        rationale_code: str,
        expected_revision: str,
        lease_token_hash: str,
        preview_hash: str,
        actor: AuthenticatedActor,
        occurred_at: str,
        idempotency_key: str,
        current_state: Mapping[str, Any],
        dependency_snapshot: Sequence[Mapping[str, Any]] = (),
        failure_at: str | None = None,
    ) -> dict[str, Any]:
        if action not in DECISION_ACTIONS or rationale_code not in RATIONALES[action]:
            raise ReviewError("identity decision action or rationale is invalid")
        actor.validate()
        self._require_role(actor, "identity_reviewer")
        now_time = parse_timestamp(occurred_at, "occurred_at")
        dependencies = _validate_dependencies(dependency_snapshot)
        validated_current_state = _validate_current_state_input(current_state)
        fingerprint = sha256_value(
            {
                "operation": action, "reviewId": review_id, "actor": _actor_binding(actor),
                "rationaleCode": rationale_code, "expectedRevision": expected_revision,
                "leaseTokenHash": lease_token_hash, "previewHash": preview_hash,
                "currentStateHash": sha256_value(validated_current_state),
                "dependencySnapshotHash": sha256_value(dependencies),
            }
        )
        with self._lock:
            authorized_review = self._authorized_review(review_id, actor)
            idempotency_hash, replay = self._idempotency_lookup(
                idempotency_key,
                fingerprint,
                operation=action,
                review=authorized_review,
                actor_hash=actor.actor_hash,
            )
            if replay is not None:
                return replay
            review = self._current(review_id, expected_revision)
            if review["state"] != "leased":
                raise ReviewError("identity decision requires a leased review")
            self._validate_lease(review, actor, lease_token_hash, now_time)
            self._validate_current_state(review, validated_current_state)
            preview = self._require_preview(review, actor, action, preview_hash, dependencies)
            if not preview["canApply"]:
                raise ReviewError("identity decision impact preview is blocked")
            if failure_at == "after_validation":
                raise ReviewError("injected failure after identity decision validation")

            before_edges = self._actor_visible_edges(review, actor)
            after_edges = dict(before_edges)
            all_after_edges = dict(self._same_as)
            all_after_partitions = dict(self._decision_partitions)
            all_after_acl_scopes = dict(self._decision_acl_scopes)
            decision_id = sha256_value(
                {"reviewId": review_id, "candidateRevision": review["candidateRevision"], "action": action}
            )
            depends_on: list[str] = []
            if action == "accept_same_as":
                depends_on = self._active_dependencies(review["candidateIds"], before_edges)
                after_edges[decision_id] = tuple(review["candidateIds"])
                all_after_edges[decision_id] = tuple(review["candidateIds"])
                all_after_partitions[decision_id] = (
                    review["tenantHash"], review["namespaceHash"]
                )
                all_after_acl_scopes[decision_id] = tuple(review["aclScopeHashes"])
                next_state, event_type = "accepted", "ACCEPT_SAME_AS"
            elif action == "reject_same_as":
                next_state, event_type = "rejected", "REJECT_SAME_AS"
            else:
                next_state, event_type = "deferred", "DEFER"
            updated = copy.deepcopy(review)
            updated.update(
                {
                    "state": next_state,
                    "lease": None,
                    "decisionId": decision_id,
                    "rationaleCode": rationale_code,
                    "updatedAt": occurred_at,
                }
            )
            updated["reviewRevision"] = self._next_revision(
                updated, self._sequences[review_id] + 1
            )
            event = self._ledger_event(
                review,
                updated,
                actor=actor,
                occurred_at=occurred_at,
                rationale_code=rationale_code,
                event_type=event_type,
                decision_id=decision_id,
                before_edges=before_edges,
                after_edges=after_edges,
                dependencies=dependencies,
                depends_on=depends_on,
                reversal_of=None,
                idempotency_hash=idempotency_hash,
            )
            if failure_at == "after_transition_staged":
                raise ReviewError("injected failure after identity transition staging")
            if len(self._ledger) >= MAX_LEDGER_EVENTS:
                raise ReviewError("identity decision ledger capacity is exhausted")
            self._reviews[review_id] = updated
            self._sequences[review_id] += 1
            self._same_as = all_after_edges
            self._decision_partitions = all_after_partitions
            self._decision_acl_scopes = all_after_acl_scopes
            self._ledger.append(event)
            self._discard_previews(review_id)
            receipt = self._receipt(
                action, next_state, updated, actor, occurred_at, idempotency_hash,
                eventId=event["eventId"], projectionHash=event["projectionAfterHash"],
            )
            self._idempotency[idempotency_hash] = (fingerprint, receipt)
            return copy.deepcopy(receipt)

    def reverse(
        self,
        review_id: str,
        *,
        rationale_code: str,
        expected_revision: str,
        lease_token_hash: str,
        preview_hash: str,
        actor: AuthenticatedActor,
        occurred_at: str,
        idempotency_key: str,
        current_state: Mapping[str, Any],
        dependency_snapshot: Sequence[Mapping[str, Any]] = (),
        failure_at: str | None = None,
    ) -> dict[str, Any]:
        if rationale_code not in RATIONALES["reverse_same_as"]:
            raise ReviewError("identity reversal rationale is invalid")
        actor.validate()
        self._require_role(actor, "identity_reviewer")
        now_time = parse_timestamp(occurred_at, "occurred_at")
        dependencies = _validate_dependencies(dependency_snapshot)
        validated_current_state = _validate_current_state_input(current_state)
        fingerprint = sha256_value(
            {
                "operation": "reverse_same_as", "reviewId": review_id,
                "actor": _actor_binding(actor), "rationaleCode": rationale_code,
                "expectedRevision": expected_revision, "leaseTokenHash": lease_token_hash,
                "previewHash": preview_hash,
                "currentStateHash": sha256_value(validated_current_state),
                "dependencySnapshotHash": sha256_value(dependencies),
            }
        )
        with self._lock:
            authorized_review = self._authorized_review(review_id, actor)
            idempotency_hash, replay = self._idempotency_lookup(
                idempotency_key,
                fingerprint,
                operation="reverse_same_as",
                review=authorized_review,
                actor_hash=actor.actor_hash,
            )
            if replay is not None:
                return replay
            review = self._current(review_id, expected_revision)
            if review["state"] != "accepted" or review["decisionId"] not in self._same_as:
                raise ReviewError("only an active SAME_AS decision can be reversed")
            self._validate_lease(review, actor, lease_token_hash, now_time)
            self._validate_current_state(review, validated_current_state)
            preview = self._require_preview(
                review, actor, "reverse_same_as", preview_hash, dependencies
            )
            blockers = [
                *preview["blockedByDecisionIds"], *preview["blockedByDependencyHashes"]
            ]
            if blockers:
                raise ReviewError(f"reversal blocked by dependency {blockers[0]}")
            if failure_at == "after_validation":
                raise ReviewError("injected failure after reversal validation")

            before_edges = self._actor_visible_edges(review, actor)
            after_edges = dict(before_edges)
            all_after_edges = dict(self._same_as)
            all_after_partitions = dict(self._decision_partitions)
            all_after_acl_scopes = dict(self._decision_acl_scopes)
            reversed_decision = review["decisionId"]
            del after_edges[reversed_decision]
            del all_after_edges[reversed_decision]
            del all_after_partitions[reversed_decision]
            del all_after_acl_scopes[reversed_decision]
            reversal_id = sha256_value(
                {"reviewId": review_id, "reversalOf": reversed_decision, "candidateRevision": review["candidateRevision"]}
            )
            updated = copy.deepcopy(review)
            updated.update(
                {
                    "state": "reversed",
                    "lease": None,
                    "decisionId": reversal_id,
                    "rationaleCode": rationale_code,
                    "updatedAt": occurred_at,
                }
            )
            updated["reviewRevision"] = self._next_revision(
                updated, self._sequences[review_id] + 1
            )
            event = self._ledger_event(
                review,
                updated,
                actor=actor,
                occurred_at=occurred_at,
                rationale_code=rationale_code,
                event_type="REVERSE_SAME_AS",
                decision_id=reversal_id,
                before_edges=before_edges,
                after_edges=after_edges,
                dependencies=dependencies,
                depends_on=[],
                reversal_of=reversed_decision,
                idempotency_hash=idempotency_hash,
            )
            if failure_at == "after_transition_staged":
                raise ReviewError("injected failure after reversal transition staging")
            if len(self._ledger) >= MAX_LEDGER_EVENTS:
                raise ReviewError("identity decision ledger capacity is exhausted")
            self._reviews[review_id] = updated
            self._sequences[review_id] += 1
            self._same_as = all_after_edges
            self._decision_partitions = all_after_partitions
            self._decision_acl_scopes = all_after_acl_scopes
            self._ledger.append(event)
            self._discard_previews(review_id)
            receipt = self._receipt(
                "reverse_same_as", "reversed", updated, actor, occurred_at, idempotency_hash,
                eventId=event["eventId"], projectionHash=event["projectionAfterHash"],
                reversalOfDecisionId=reversed_decision,
            )
            self._idempotency[idempotency_hash] = (fingerprint, receipt)
            return copy.deepcopy(receipt)

    def list_reviews(
        self,
        *,
        tenant_hash: str,
        namespace_hash: str,
        actor: AuthenticatedActor,
        states: Iterable[str] = (),
        entity_type: str | None = None,
        risk: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        actor.validate()
        self._require_any_role(actor, "identity_reviewer", "identity_auditor")
        validate_hash(tenant_hash, "tenant_hash")
        validate_hash(namespace_hash, "namespace_hash")
        self._require_partition(actor, tenant_hash, namespace_hash)
        requested_states = set(states)
        if not requested_states.issubset(REVIEW_STATES):
            raise ReviewError("review state filter is invalid")
        if risk not in {None, "standard", "protected"}:
            raise ReviewError("review risk filter is invalid")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ReviewError("review page limit is invalid")
        with self._lock:
            rows = [
                review for review in self._reviews.values()
                if review["tenantHash"] == tenant_hash
                and review["namespaceHash"] == namespace_hash
                and self._can_access_acl(actor, review)
                and (not requested_states or review["state"] in requested_states)
                and (entity_type is None or review["entityType"] == entity_type)
                and (risk is None or review["risk"] == risk)
            ]
            rows.sort(key=lambda item: item["reviewId"])
            if cursor is not None:
                validate_hash(cursor, "cursor")
                rows = [row for row in rows if row["reviewId"] > cursor]
            selected = rows[:limit]
            return {
                "status": "ok",
                "results": [self._review_summary(row) for row in selected],
                "nextCursor": selected[-1]["reviewId"] if len(rows) > limit else None,
                "truncated": len(rows) > limit,
            }

    def show_review(
        self, review_id: str, *, actor: AuthenticatedActor
    ) -> dict[str, Any]:
        actor.validate()
        self._require_any_role(actor, "identity_reviewer", "identity_auditor")
        with self._lock:
            return copy.deepcopy(self._authorized_review(review_id, actor))

    def ledger(
        self, *, tenant_hash: str, namespace_hash: str, actor: AuthenticatedActor
    ) -> list[dict[str, Any]]:
        actor.validate()
        self._require_any_role(actor, "identity_reviewer", "identity_auditor")
        validate_hash(tenant_hash, "tenant_hash")
        validate_hash(namespace_hash, "namespace_hash")
        self._require_partition(actor, tenant_hash, namespace_hash)
        with self._lock:
            return copy.deepcopy(
                [
                    event for event in self._ledger
                    if event["tenantHash"] == tenant_hash
                    and event["namespaceHash"] == namespace_hash
                    and bool(actor.authorized_acl_scope_hashes.intersection(event["aclScopeHashes"]))
                ]
            )

    def projection(
        self, *, tenant_hash: str, namespace_hash: str, actor: AuthenticatedActor
    ) -> dict[str, list[str]]:
        actor.validate()
        self._require_any_role(actor, "identity_reviewer", "identity_auditor")
        validate_hash(tenant_hash, "tenant_hash")
        validate_hash(namespace_hash, "namespace_hash")
        self._require_partition(actor, tenant_hash, namespace_hash)
        with self._lock:
            return _projection_components(
                self._partition_edges(
                    tenant_hash, namespace_hash, actor.authorized_acl_scope_hashes
                )
            )

    def suppressed_candidate_revisions(
        self,
        *,
        tenant_hash: str,
        namespace_hash: str,
        acl_scope_hashes: Iterable[str] | None = None,
    ) -> set[str]:
        validate_hash(tenant_hash, "tenant_hash")
        validate_hash(namespace_hash, "namespace_hash")
        allowed = _validated_acl_filter(acl_scope_hashes)
        with self._lock:
            return {
                review["candidateRevision"]
                for review in self._reviews.values()
                if review["state"] in {"rejected", "accepted", "reversed", "superseded"}
                and review["tenantHash"] == tenant_hash
                and review["namespaceHash"] == namespace_hash
                and (allowed is None or bool(allowed.intersection(review["aclScopeHashes"])))
            }

    def counts(
        self,
        *,
        tenant_hash: str | None = None,
        namespace_hash: str | None = None,
        acl_scope_hashes: Iterable[str] | None = None,
    ) -> dict[str, int]:
        if (tenant_hash is None) != (namespace_hash is None):
            raise ReviewError("review counts require both tenant and namespace or neither")
        if acl_scope_hashes is not None and tenant_hash is None:
            raise ReviewError("ACL-scoped review counts require a tenant and namespace")
        if tenant_hash is not None and namespace_hash is not None:
            validate_hash(tenant_hash, "tenant_hash")
            validate_hash(namespace_hash, "namespace_hash")
        allowed = _validated_acl_filter(acl_scope_hashes)
        with self._lock:
            counts = {state: 0 for state in sorted(REVIEW_STATES)}
            for review in self._reviews.values():
                if tenant_hash is not None and (
                    review["tenantHash"] != tenant_hash
                    or review["namespaceHash"] != namespace_hash
                ):
                    continue
                if allowed is not None and not allowed.intersection(review["aclScopeHashes"]):
                    continue
                counts[review["state"]] += 1
            return counts

    def _stage_supersession(
        self,
        review: Mapping[str, Any],
        sequence: int,
        actor: AuthenticatedActor,
        occurred_at: str,
        *,
        before_edges: Mapping[str, tuple[str, str]],
        after_edges: Mapping[str, tuple[str, str]],
        reversal_of: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        updated = copy.deepcopy(dict(review))
        updated.update(
            {
                "state": "superseded",
                "lease": None,
                "rationaleCode": "stale_evidence",
                "updatedAt": occurred_at,
            }
        )
        decision_id = sha256_value(
            {"reviewId": review["reviewId"], "candidateRevision": review["candidateRevision"], "action": "supersede"}
        )
        updated["decisionId"] = decision_id
        updated["reviewRevision"] = self._next_revision(updated, sequence + 1)
        event = self._ledger_event(
            review,
            updated,
            actor=actor,
            occurred_at=occurred_at,
            rationale_code="stale_evidence",
            event_type="SUPERSEDE",
            decision_id=decision_id,
            before_edges=before_edges,
            after_edges=after_edges,
            dependencies=[],
            depends_on=[],
            reversal_of=reversal_of,
            idempotency_hash=sha256_value(f"supersede:{decision_id}"),
        )
        return event, updated

    def _ledger_event(
        self,
        prior: Mapping[str, Any],
        updated: Mapping[str, Any],
        *,
        actor: AuthenticatedActor,
        occurred_at: str,
        rationale_code: str,
        event_type: str,
        decision_id: str,
        before_edges: Mapping[str, tuple[str, str]],
        after_edges: Mapping[str, tuple[str, str]],
        dependencies: Sequence[Mapping[str, Any]],
        depends_on: Sequence[str],
        reversal_of: str | None,
        idempotency_hash: str,
    ) -> dict[str, Any]:
        members = _members_for_pair(updated["candidateIds"], after_edges)
        event = {
            "ledgerVersion": 1,
            "eventId": sha256_value(
                {"decisionId": decision_id, "eventType": event_type, "idempotency": idempotency_hash}
            ),
            "decisionId": decision_id,
            "reviewId": updated["reviewId"],
            "pairKey": updated["pairKey"],
            "eventType": event_type,
            "status": updated["state"],
            "tenantHash": updated["tenantHash"],
            "namespaceHash": updated["namespaceHash"],
            "aclScopeHashes": list(updated["aclScopeHashes"]),
            "entityType": updated["entityType"],
            "actorHash": actor.actor_hash,
            "occurredAt": occurred_at,
            "rationaleCode": rationale_code,
            "candidateRevision": updated["candidateRevision"],
            "priorReviewRevision": prior["reviewRevision"],
            "newReviewRevision": updated["reviewRevision"],
            "sourceRevisionHashes": list(updated["sourceRevisionHashes"]),
            "projectionBeforeHash": self._projection_hash(before_edges),
            "projectionAfterHash": self._projection_hash(after_edges),
            "projectionMemberIds": members,
            "dependsOnDecisionIds": sorted(depends_on),
            "reversalOfDecisionId": reversal_of,
            "dependencySnapshotHash": sha256_value(dependencies),
            "idempotencyKeyHash": idempotency_hash,
        }
        _validate_ledger_event(event)
        return event

    def _current(self, review_id: str, expected_revision: str) -> dict[str, Any]:
        validate_hash(review_id, "review_id")
        validate_hash(expected_revision, "expected_revision")
        review = self._reviews.get(review_id)
        if review is None:
            raise ReviewError("identity review is unavailable")
        if review["reviewRevision"] != expected_revision:
            raise ReviewError("identity review changed; compare-and-swap rejected")
        return copy.deepcopy(review)

    @staticmethod
    def _validate_lease(
        review: Mapping[str, Any],
        actor: AuthenticatedActor,
        lease_token_hash: str,
        now: Any,
    ) -> None:
        validate_hash(lease_token_hash, "lease_token_hash")
        lease = review["lease"]
        if (
            lease is None
            or lease["actorHash"] != actor.actor_hash
            or lease["tokenHash"] != lease_token_hash
        ):
            raise ReviewError("identity review lease is not owned by this actor")
        if parse_timestamp(lease["expiresAt"], "lease expiresAt") <= now:
            raise ReviewError("identity review lease has expired")
        if parse_timestamp(review["updatedAt"], "lease issuedAt") > now:
            raise ReviewError("identity review lease is not yet valid")

    @staticmethod
    def _validate_current_state(
        review: Mapping[str, Any], current_state: Mapping[str, Any]
    ) -> None:
        validated = _validate_current_state_input(current_state)
        if (
            validated["candidateRevision"] != review["candidateRevision"]
            or sorted(validated["sourceRevisionHashes"]) != review["sourceRevisionHashes"]
            or validated["versions"] != review["versions"]
        ):
            raise ReviewError("candidate source, schema, model, or evidence state is stale")

    def _require_preview(
        self,
        review: Mapping[str, Any],
        actor: AuthenticatedActor,
        operation: str,
        preview_hash: str,
        dependencies: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        validate_hash(preview_hash, "preview_hash")
        key = (review["reviewId"], actor.actor_hash, review["reviewRevision"], operation)
        preview = self._previews.get(key)
        if (
            preview is None
            or preview["previewHash"] != preview_hash
            or preview["dependencySnapshotHash"] != sha256_value(dependencies)
        ):
            raise ReviewError("a current bounded impact preview is required")
        return preview

    @staticmethod
    def _next_revision(review: Mapping[str, Any], sequence: int) -> str:
        return sha256_value(
            {
                "candidateRevision": review["candidateRevision"],
                "state": review["state"],
                "lease": review["lease"],
                "decisionId": review["decisionId"],
                "rationaleCode": review["rationaleCode"],
                "updatedAt": review["updatedAt"],
                "sequence": sequence,
            }
        )

    def _active_dependencies(
        self, candidate_ids: Sequence[str], edges: Mapping[str, tuple[str, str]]
    ) -> list[str]:
        members = set(_members_for_pair(candidate_ids, edges))
        return sorted(
            decision_id for decision_id, pair in edges.items()
            if members.intersection(pair)
        )

    def _actor_visible_edges(
        self, review: Mapping[str, Any], actor: AuthenticatedActor
    ) -> dict[str, tuple[str, str]]:
        """Return only partition edges the authenticated actor may observe."""

        return self._partition_edges(
            review["tenantHash"],
            review["namespaceHash"],
            actor.authorized_acl_scope_hashes,
        )

    def _partition_edges(
        self,
        tenant_hash: str,
        namespace_hash: str,
        acl_scope_hashes: Iterable[str] | None = None,
    ) -> dict[str, tuple[str, str]]:
        return self._partition_edges_from_state(
            self._same_as,
            self._decision_partitions,
            self._decision_acl_scopes,
            tenant_hash,
            namespace_hash,
            acl_scope_hashes,
        )

    @staticmethod
    def _partition_edges_from_state(
        same_as: Mapping[str, tuple[str, str]],
        decision_partitions: Mapping[str, tuple[str, str]],
        decision_acl_scopes: Mapping[str, tuple[str, ...]],
        tenant_hash: str,
        namespace_hash: str,
        acl_scope_hashes: Iterable[str] | None = None,
    ) -> dict[str, tuple[str, str]]:
        allowed = set(acl_scope_hashes) if acl_scope_hashes is not None else None
        return {
            decision_id: pair
            for decision_id, pair in same_as.items()
            if decision_partitions[decision_id] == (tenant_hash, namespace_hash)
            and (
                allowed is None
                or bool(allowed.intersection(decision_acl_scopes[decision_id]))
            )
        }

    @staticmethod
    def _projection_hash(edges: Mapping[str, tuple[str, str]]) -> str:
        return sha256_value(
            {decision_id: list(pair) for decision_id, pair in sorted(edges.items())}
        )

    def _idempotency_lookup(
        self,
        idempotency_key: str,
        fingerprint: str,
        *,
        operation: str,
        review: Mapping[str, Any],
        actor_hash: str,
    ) -> tuple[str, dict[str, Any] | None]:
        if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 256:
            raise ReviewError("bounded idempotency key is required")
        key_hash = sha256_value(
            {
                "domain": "identity-review",
                "operation": operation,
                "tenantHash": review["tenantHash"],
                "namespaceHash": review["namespaceHash"],
                "aclScopeHashes": sorted(review["aclScopeHashes"]),
                "actorHash": actor_hash,
                "idempotencyKey": idempotency_key,
            }
        )
        with self._lock:
            existing = self._idempotency.get(key_hash)
            if existing is None:
                if len(self._idempotency) >= MAX_IDEMPOTENCY_RECEIPTS:
                    raise ReviewError("identity idempotency receipt capacity is exhausted")
                return key_hash, None
            if existing[0] != fingerprint:
                raise ReviewError("idempotency key is already bound to another operation")
            return key_hash, copy.deepcopy(existing[1])

    def _authorized_review(
        self, review_id: str, actor: AuthenticatedActor
    ) -> Mapping[str, Any]:
        validate_hash(review_id, "review_id")
        review = self._reviews.get(review_id)
        if review is None:
            raise ReviewError("identity review is unavailable")
        self._require_partition(actor, review["tenantHash"], review["namespaceHash"])
        self._require_acl(actor, review)
        return review

    def _discard_previews(self, review_id: str) -> None:
        for key in [key for key in self._previews if key[0] == review_id]:
            del self._previews[key]

    @staticmethod
    def _receipt(
        operation: str,
        status: str,
        review: Mapping[str, Any],
        actor: AuthenticatedActor,
        occurred_at: str,
        idempotency_hash: str,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "receiptVersion": 1,
            "operation": operation,
            "status": status,
            "reviewId": review["reviewId"],
            "pairKey": review["pairKey"],
            "candidateRevision": review["candidateRevision"],
            "reviewRevision": review["reviewRevision"],
            "decisionId": review["decisionId"],
            "actorHash": actor.actor_hash,
            "occurredAt": occurred_at,
            "idempotencyKeyHash": idempotency_hash,
            **extra,
        }

    @staticmethod
    def _review_summary(review: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "reviewId": review["reviewId"],
            "candidateRevision": review["candidateRevision"],
            "reviewRevision": review["reviewRevision"],
            "entityType": review["entityType"],
            "state": review["state"],
            "risk": review["risk"],
            "weightedScore": review["scoreComponents"]["weightedScore"],
            "createdAt": review["createdAt"],
            "expiresAt": review["expiresAt"],
        }

    @staticmethod
    def _require_role(actor: AuthenticatedActor, role: str) -> None:
        if role not in actor.roles:
            raise ReviewError("authenticated actor is not authorized for this operation")

    @staticmethod
    def _require_any_role(actor: AuthenticatedActor, *roles: str) -> None:
        if not actor.roles.intersection(roles):
            raise ReviewError("authenticated actor is not authorized for this operation")

    @staticmethod
    def _require_partition(
        actor: AuthenticatedActor, tenant_hash: str, namespace_hash: str
    ) -> None:
        if (tenant_hash, namespace_hash) not in actor.authorized_partitions:
            raise ReviewError("authenticated actor is not authorized for this partition")

    @staticmethod
    def _can_access_acl(actor: AuthenticatedActor, review: Mapping[str, Any]) -> bool:
        return bool(actor.authorized_acl_scope_hashes.intersection(review["aclScopeHashes"]))

    @classmethod
    def _require_acl(cls, actor: AuthenticatedActor, review: Mapping[str, Any]) -> None:
        if not cls._can_access_acl(actor, review):
            raise ReviewError("authenticated actor is not authorized for this ACL scope")


def current_candidate_state(review: Mapping[str, Any]) -> dict[str, Any]:
    """Build the explicit state precondition required by preview and transition calls."""

    return {
        "candidateRevision": review["candidateRevision"],
        "sourceRevisionHashes": list(review["sourceRevisionHashes"]),
        "versions": copy.deepcopy(review["versions"]),
    }


def _actor_binding(actor: AuthenticatedActor) -> dict[str, Any]:
    return {
        "actorHash": actor.actor_hash,
        "authenticationContextHash": actor.authentication_context_hash,
        "authorizedPartitions": sorted([tenant, namespace] for tenant, namespace in actor.authorized_partitions),
        "authorizedAclScopeHashes": sorted(actor.authorized_acl_scope_hashes),
    }


def _validated_acl_filter(values: Iterable[str] | None) -> set[str] | None:
    if values is None:
        return None
    allowed: set[str] = set()
    for index, value in enumerate(values):
        if index >= 256:
            raise ReviewError("review ACL filter must be a bounded non-empty set")
        validate_hash(value, "review ACL filter hash")
        allowed.add(value)
    if not allowed:
        raise ReviewError("review ACL filter must be a bounded non-empty set")
    return allowed


def _validate_current_state_input(current_state: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(current_state, dict) or set(current_state) != {
        "candidateRevision", "sourceRevisionHashes", "versions"
    }:
        raise ReviewError("current candidate state has missing or unknown fields")
    validate_hash(current_state["candidateRevision"], "current candidate revision")
    source_revisions = current_state["sourceRevisionHashes"]
    if not isinstance(source_revisions, list) or not 1 <= len(source_revisions) <= 2:
        raise ReviewError("current candidate source revisions must be a bounded array")
    for revision in source_revisions:
        validate_hash(revision, "current source revision")
    versions = current_state["versions"]
    if not isinstance(versions, dict) or set(versions) != {
        "normalizationVersion", "scoringModelVersion", "schemaVersion", "evidenceVersion"
    }:
        raise ReviewError("current candidate versions are invalid")
    return copy.deepcopy(current_state)


def _projection_components(edges: Mapping[str, tuple[str, str]]) -> dict[str, list[str]]:
    parents: dict[str, str] = {}

    def find(node: str) -> str:
        parents.setdefault(node, node)
        if parents[node] != node:
            parents[node] = find(parents[node])
        return parents[node]

    def union(first: str, second: str) -> None:
        first_root, second_root = find(first), find(second)
        if first_root == second_root:
            return
        low, high = sorted((first_root, second_root))
        parents[high] = low

    for pair in edges.values():
        union(*pair)
    groups: dict[str, list[str]] = {}
    for node in sorted(parents):
        groups.setdefault(find(node), []).append(node)
    return {root: members for root, members in sorted(groups.items())}


def _members_for_pair(
    candidate_ids: Sequence[str], edges: Mapping[str, tuple[str, str]]
) -> list[str]:
    components = _projection_components(edges)
    members = set(candidate_ids)
    for component in components.values():
        if members.intersection(component):
            members.update(component)
    return sorted(members)


def _validate_dependencies(
    dependencies: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(dependencies, Sequence) or isinstance(dependencies, (str, bytes)):
        raise ReviewError("dependency snapshot must be an array")
    if len(dependencies) > MAX_DEPENDENCIES:
        raise ReviewError("dependency snapshot exceeds the review budget")
    validated: list[dict[str, Any]] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict) or set(dependency) != {
            "dependencyHash", "kind", "immutableSourceBound", "sourceRevisionHash"
        }:
            raise ReviewError("dependency snapshot entry has missing or unknown fields")
        validate_hash(dependency["dependencyHash"], "dependencyHash")
        validate_hash(dependency["sourceRevisionHash"], "dependency sourceRevisionHash")
        if dependency["kind"] not in {"decision", "relationship", "claim"}:
            raise ReviewError("dependency kind is invalid")
        if not isinstance(dependency["immutableSourceBound"], bool):
            raise ReviewError("dependency source binding must be boolean")
        validated.append(dict(dependency))
    return sorted(validated, key=lambda item: item["dependencyHash"])


def _validate_review(review: Mapping[str, Any], *, initial: bool) -> None:
    required = {
        "reviewVersion", "reviewId", "pairKey", "candidateRevision", "reviewRevision",
        "tenantHash", "namespaceHash", "entityType", "candidateIds", "sourceRevisionHashes",
        "aclSummaryHash", "aclScopeHashes", "trustSummary", "scoreComponents", "versions", "createdAt",
        "updatedAt", "expiresAt", "state", "risk", "poisonFlags", "idempotencyKeyHash",
        "origin", "lease", "decisionId", "rationaleCode",
    }
    if not isinstance(review, dict) or set(review) != required:
        raise ReviewError("identity review has missing or unknown fields")
    if review["reviewVersion"] != 1:
        raise ReviewError("unsupported identity review version")
    for field in (
        "reviewId", "pairKey", "candidateRevision", "reviewRevision", "tenantHash",
        "namespaceHash", "aclSummaryHash", "idempotencyKeyHash",
    ):
        validate_hash(review[field], field)
    if not isinstance(review["candidateIds"], list) or len(review["candidateIds"]) != 2:
        raise ReviewError("identity review requires exactly two candidate ids")
    pair = canonical_pair(*review["candidateIds"])
    if list(pair) != review["candidateIds"]:
        raise ReviewError("identity review candidate ids must be canonically ordered")
    if (
        not isinstance(review["sourceRevisionHashes"], list)
        or not 1 <= len(review["sourceRevisionHashes"]) <= 2
        or len(review["sourceRevisionHashes"]) != len(set(review["sourceRevisionHashes"]))
        or review["sourceRevisionHashes"] != sorted(review["sourceRevisionHashes"])
    ):
        raise ReviewError("identity review source revisions are invalid")
    for revision in review["sourceRevisionHashes"]:
        validate_hash(revision, "sourceRevisionHash")
    if (
        not isinstance(review["aclScopeHashes"], list)
        or not review["aclScopeHashes"]
        or len(review["aclScopeHashes"]) > 256
        or review["aclScopeHashes"] != sorted(set(review["aclScopeHashes"]))
    ):
        raise ReviewError("identity review ACL scope hashes are invalid")
    for scope_hash in review["aclScopeHashes"]:
        validate_hash(scope_hash, "identity review ACL scope hash")
    expected_pair_key = identity_pair_key(
        review["tenantHash"],
        review["namespaceHash"],
        pair,
        review["aclScopeHashes"],
    )
    if review["pairKey"] != expected_pair_key:
        raise ReviewError(
            "identity review pair key is not governed by its partition, ACL lane, and ids"
        )
    if review["state"] not in REVIEW_STATES or review["risk"] not in {"standard", "protected"}:
        raise ReviewError("identity review state or risk is invalid")
    if initial and (review["state"] != "pending" or review["lease"] is not None or review["decisionId"] is not None):
        raise ReviewError("new identity reviews must start pending and undecided")
    if initial:
        expected_review_id = sha256_value(
            f"identity-review:{review['pairKey']}:{review['candidateRevision']}"
        )
        expected_revision = sha256_value(
            {"candidateRevision": review["candidateRevision"], "state": "pending", "sequence": 0}
        )
        if (
            review["reviewId"] != expected_review_id
            or review["reviewRevision"] != expected_revision
            or review["idempotencyKeyHash"] != sha256_value(
                f"candidate:{review['candidateRevision']}"
            )
        ):
            raise ReviewError("new identity review governed ids are inconsistent")
    if review["origin"] not in {"manual", "ingest", "consolidation"}:
        raise ReviewError("identity review origin is invalid")
    validate_entity_type(review["entityType"])
    created = parse_timestamp(review["createdAt"], "createdAt")
    updated = parse_timestamp(review["updatedAt"], "updatedAt")
    expires = parse_timestamp(review["expiresAt"], "expiresAt")
    if updated < created or expires <= created:
        raise ReviewError("identity review timestamps are invalid")
    if review["trustSummary"] not in {"high", "medium", "low", "unverified"}:
        raise ReviewError("identity review trust summary is invalid")
    if (
        not isinstance(review["poisonFlags"], list)
        or len(review["poisonFlags"]) > 16
        or len(review["poisonFlags"]) != len(set(review["poisonFlags"]))
        or not all(isinstance(flag, str) and 2 <= len(flag) <= 64 for flag in review["poisonFlags"])
    ):
        raise ReviewError("identity review poison flags are invalid")
    if review["lease"] is not None:
        if not isinstance(review["lease"], dict) or set(review["lease"]) != {
            "tokenHash", "actorHash", "expiresAt"
        }:
            raise ReviewError("identity review lease is invalid")
        validate_hash(review["lease"]["tokenHash"], "lease tokenHash")
        validate_hash(review["lease"]["actorHash"], "lease actorHash")
        parse_timestamp(review["lease"]["expiresAt"], "lease expiresAt")
    if review["decisionId"] is not None:
        validate_hash(review["decisionId"], "decisionId")
    if review["rationaleCode"] is not None and review["rationaleCode"] not in set().union(*RATIONALES.values()):
        raise ReviewError("identity review rationaleCode is invalid")
    components = review["scoreComponents"]
    if not isinstance(components, dict) or set(components) != {
        "exactAlias", "nameSimilarity", "contextSimilarity", "semanticSimilarity",
        "weightedScore",
    }:
        raise ReviewError("identity review score components are invalid")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1
        for value in components.values()
    ):
        raise ReviewError("identity review scores must be between zero and one")
    versions = review["versions"]
    if not isinstance(versions, dict) or set(versions) != {
        "normalizationVersion", "scoringModelVersion", "schemaVersion", "evidenceVersion"
    }:
        raise ReviewError("identity review versions are invalid")
    if any(not isinstance(value, str) or not value or len(value) > 128 for value in versions.values()):
        raise ReviewError("identity review versions must be bounded text")
    expected_candidate_revision = candidate_revision_hash(review)
    if review["candidateRevision"] != expected_candidate_revision:
        raise ReviewError("identity candidate revision does not bind its governed evidence")


def _validate_ledger_event(event: Mapping[str, Any]) -> None:
    required = {
        "ledgerVersion", "eventId", "decisionId", "reviewId", "pairKey", "eventType",
        "status", "tenantHash", "namespaceHash", "entityType", "actorHash", "occurredAt",
        "aclScopeHashes",
        "rationaleCode", "candidateRevision", "priorReviewRevision", "newReviewRevision",
        "sourceRevisionHashes", "projectionBeforeHash", "projectionAfterHash",
        "projectionMemberIds", "dependsOnDecisionIds", "reversalOfDecisionId",
        "dependencySnapshotHash", "idempotencyKeyHash",
    }
    if not isinstance(event, dict) or set(event) != required or event["ledgerVersion"] != 1:
        raise ReviewError("identity ledger event has missing or unknown fields")
    for field in (
        "eventId", "decisionId", "reviewId", "pairKey", "actorHash", "candidateRevision",
        "priorReviewRevision", "newReviewRevision", "projectionBeforeHash",
        "projectionAfterHash", "dependencySnapshotHash", "idempotencyKeyHash",
    ):
        validate_hash(event[field], field)
    for field in ("sourceRevisionHashes", "projectionMemberIds", "dependsOnDecisionIds"):
        if not isinstance(event[field], list) or len(event[field]) > MAX_DEPENDENCIES:
            raise ReviewError(f"ledger {field} is invalid")
        for value in event[field]:
            validate_hash(value, f"ledger {field}")
    if (
        not isinstance(event["aclScopeHashes"], list)
        or not event["aclScopeHashes"]
        or event["aclScopeHashes"] != sorted(set(event["aclScopeHashes"]))
    ):
        raise ReviewError("ledger ACL scope hashes are invalid")
    for scope_hash in event["aclScopeHashes"]:
        validate_hash(scope_hash, "ledger ACL scope hash")
    if not 1 <= len(event["sourceRevisionHashes"]) <= 2:
        raise ReviewError("ledger source revisions are invalid")
    if event["reversalOfDecisionId"] is not None:
        validate_hash(event["reversalOfDecisionId"], "reversalOfDecisionId")
    expected_status = {
        "ACCEPT_SAME_AS": "accepted",
        "REJECT_SAME_AS": "rejected",
        "DEFER": "deferred",
        "SUPERSEDE": "superseded",
        "REVERSE_SAME_AS": "reversed",
    }
    if event["eventType"] not in expected_status or event["status"] != expected_status[event["eventType"]]:
        raise ReviewError("identity ledger event type and status are inconsistent")
    if event["rationaleCode"] not in set().union(*RATIONALES.values()):
        raise ReviewError("identity ledger rationale is invalid")
    parse_timestamp(event["occurredAt"], "ledger occurredAt")
