"""Governed decision-accountability contract with an offline transactional adapter.

This module does not connect to Neo4j or infer decisions from agent traces. It models the
authority, preview, optimistic-concurrency, event/current-projection, retention, and bounded
query behavior that a future live adapter must preserve.
"""

from __future__ import annotations

import copy
import json
import os
import re
import stat
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .contract import canonical_json, sha256_value


DECISION_CONTRACT_VERSION = 1
MAX_PREVIEW_BYTES = 512 * 1024
MAX_EVENTS_PER_DECISION = 512
MAX_RELATIONSHIPS = 10_000
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
DECISION_CLASSES = {
    "promotion", "adoption", "policy_gate", "approval", "external_effect_routing",
    "release", "rollback", "provider_selection",
}
DECISION_STATUSES = {
    "accepted", "corrected", "invalidated", "superseded", "reversed", "purged",
}
CORRECTION_KINDS = {"corrected", "invalidated", "superseded", "reversed"}
RELATIONSHIP_TYPES = {"PRECEDENT_FOR", "INFLUENCED_BY", "CAUSED"}
FORBIDDEN_TEXT = (
    "chain of thought", "chain-of-thought", "system prompt", "ignore all previous",
    "-----begin", "sk-", "/users/", "\\users\\", "client content",
)
FORBIDDEN_SECRET_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"sntrys_[A-Za-z0-9._-]{20,})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
PROPOSAL_FIELDS = {
    "tenantRef", "projectRef", "domain", "decisionClass", "source", "workflow",
    "actorHash", "acl", "sensitivity", "rationaleSummaryHash", "evidenceSet",
    "policySnapshot", "policyEvaluation", "approval", "retentionUntil",
}


class DecisionError(ValueError):
    """Raised when decision data, authority, concurrency, or privacy fails closed."""


@dataclass(frozen=True)
class DecisionQueryBudget:
    depth: int = 1
    results: int = 20
    runtime_ms: int = 250
    max_bytes: int = 32_768


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_time(value: datetime) -> str:
    if value.utcoffset() is None:
        raise DecisionError("timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or "T" not in value or len(value) > 64:
        raise DecisionError(f"{field} must be a bounded ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionError(f"{field} must be a bounded ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise DecisionError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def decision_bindings(proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact canonical-source bindings revalidated when a preview is recorded."""

    return {
        "source": copy.deepcopy(proposal["source"]),
        "evidenceSetDigest": proposal["evidenceSet"]["digest"],
        "policyVersion": proposal["policySnapshot"]["version"],
        "policyDigest": proposal["policySnapshot"]["digest"],
        "policyEvaluationDigest": sha256_value(proposal["policyEvaluation"]),
        "approvalRevision": proposal["approval"]["revision"],
        "approvalDigest": proposal["approval"]["digest"],
    }


class DecisionPreviewStore:
    """Mode-0600, single-use preview artifacts under a caller-selected private root."""

    def __init__(self, root: Path | None = None) -> None:
        state_root = Path(os.environ.get("RHIZE_STATE_ROOT", Path.home() / ".rhize"))
        self.root = root or state_root / "decision-previews"
        if not self.root.is_absolute():
            raise DecisionError("preview root must be absolute")
        if self.root.is_symlink():
            raise DecisionError("preview root cannot be a symlink")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        root_stat = self.root.lstat()
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or stat.S_IMODE(root_stat.st_mode) != 0o700
            or root_stat.st_uid != os.getuid()
        ):
            raise DecisionError("preview root must be a private caller-owned directory")

    def write(self, preview: Mapping[str, Any]) -> Path:
        path = self._path(preview["previewId"], "json")
        if path.exists() or self._used(preview["previewId"]).exists():
            raise DecisionError("preview identifier already exists")
        payload = f"{canonical_json(preview)}\n"
        if len(payload.encode("utf-8")) > MAX_PREVIEW_BYTES:
            raise DecisionError("preview exceeds the private artifact size budget")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        os.chmod(path, 0o600)
        return path

    def load(self, preview_id: str) -> dict[str, Any]:
        _hash(preview_id, "previewId")
        if self._used(preview_id).exists() or self._claimed(preview_id).exists():
            raise DecisionError("preview_replayed")
        path = self._path(preview_id, "json")
        try:
            path_stat = path.lstat()
            if (
                not stat.S_ISREG(path_stat.st_mode)
                or stat.S_IMODE(path_stat.st_mode) != 0o600
                or path_stat.st_uid != os.getuid()
                or path_stat.st_size > MAX_PREVIEW_BYTES
            ):
                raise DecisionError("preview_unavailable")
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DecisionError("preview_unavailable") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise DecisionError("preview_unavailable") from exc
        if not isinstance(value, dict):
            raise DecisionError("preview_unavailable")
        return value

    def claim(self, preview_id: str) -> dict[str, Any]:
        preview = self.load(preview_id)
        try:
            os.replace(self._path(preview_id, "json"), self._claimed(preview_id))
        except FileNotFoundError as exc:
            raise DecisionError("preview_replayed") from exc
        return preview

    def finish(self, preview_id: str, *, consumed_at: str, outcome: str) -> None:
        marker = {
            "previewId": preview_id,
            "consumedAt": consumed_at,
            "outcome": outcome,
        }
        target = self._used(preview_id)
        temp = self._path(preview_id, "used.tmp")
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(canonical_json(marker))
            handle.write("\n")
        os.replace(temp, target)
        self._claimed(preview_id).unlink(missing_ok=True)

    def _path(self, preview_id: str, suffix: str) -> Path:
        return self.root / f"{preview_id}.{suffix}"

    def _claimed(self, preview_id: str) -> Path:
        return self._path(preview_id, "claimed")

    def _used(self, preview_id: str) -> Path:
        return self._path(preview_id, "used")


class InMemoryDecisionLedger:
    """Fake publication adapter with atomic append/current projection semantics."""

    RECORD_ROLE = "decision_record"
    REVIEW_ROLE = "decision_review"
    QUERY_ROLE = "decision_query"

    def __init__(
        self,
        preview_store: DecisionPreviewStore,
        *,
        causality_enabled: bool = False,
    ) -> None:
        self.preview_store = preview_store
        self.causality_enabled = causality_enabled
        self._lock = threading.RLock()
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._current: dict[str, dict[str, Any]] = {}
        self._decision_idempotency: dict[tuple[str, str], str] = {}
        self._record_results: dict[tuple[str, str], dict[str, Any]] = {}
        self._transition_idempotency: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        self._relationships: dict[str, dict[str, Any]] = {}

    def preview(
        self,
        proposal: Mapping[str, Any],
        *,
        principal_hash: str,
        principal_scopes: Sequence[str],
        idempotency_key: str,
        nonce: str,
        now: datetime | None = None,
        ttl_seconds: int = 600,
    ) -> dict[str, Any]:
        current_time = now or utc_now()
        _validate_proposal(proposal, current_time)
        _hash(principal_hash, "principalHash")
        scopes = _refs(principal_scopes, "principalScopes")
        if "decision:record" not in scopes or not set(scopes).intersection(proposal["acl"]):
            raise DecisionError("unauthorized")
        if not idempotency_key or len(idempotency_key) > 256:
            raise DecisionError("a bounded idempotency key is required")
        if not nonce or len(nonce) < 16 or len(nonce) > 256:
            raise DecisionError("a nonce of 16-256 characters is required")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 3600:
            raise DecisionError("preview TTL must be between 1 and 3600 seconds")
        created_at = iso_time(current_time)
        proposal_copy = copy.deepcopy(dict(proposal))
        unsigned = {
            "previewVersion": 1,
            "createdAt": created_at,
            "expiresAt": iso_time(current_time + timedelta(seconds=ttl_seconds)),
            "principalHash": principal_hash,
            "principalScopes": scopes,
            "nonceHash": sha256_value(nonce),
            "idempotencyKeyHash": sha256_value(idempotency_key),
            "bindingDigest": sha256_value(decision_bindings(proposal_copy)),
            "proposal": proposal_copy,
        }
        preview_id = sha256_value(unsigned)
        preview = {**unsigned, "previewId": preview_id}
        preview["previewDigest"] = sha256_value(preview)
        self.preview_store.write(preview)
        return copy.deepcopy(preview)

    def record(
        self,
        preview_id: str,
        *,
        tenant_ref: str,
        project_ref: str,
        actor_hash: str,
        workflow: Mapping[str, Any],
        principal_hash: str,
        principal_scopes: Sequence[str],
        nonce: str,
        current_bindings: Mapping[str, Any],
        role: str,
        expected_sequence: int = 0,
        expected_event_hash: str | None = None,
        failure_at: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_role(role, self.RECORD_ROLE)
        current_time = now or utc_now()
        _ref(tenant_ref, "tenantRef")
        _ref(project_ref, "projectRef")
        _hash(actor_hash, "actorHash")
        _validate_workflow(workflow)
        _hash(principal_hash, "principalHash")
        if not nonce or len(nonce) < 16 or len(nonce) > 256:
            raise DecisionError("a nonce of 16-256 characters is required")
        _validate_bindings(current_bindings)
        if isinstance(expected_sequence, bool) or not isinstance(expected_sequence, int):
            raise DecisionError("expected sequence must be an integer")
        if failure_at not in {None, "before_commit"}:
            raise DecisionError("unsupported failure injection point")
        with self._lock:
            preview = self.preview_store.load(preview_id)
            self._validate_preview(
                preview,
                tenant_ref=tenant_ref,
                project_ref=project_ref,
                actor_hash=actor_hash,
                workflow=workflow,
                principal_hash=principal_hash,
                principal_scopes=principal_scopes,
                nonce=nonce,
                current_bindings=current_bindings,
                now=current_time,
            )
            preview = self.preview_store.claim(preview_id)
            outcome = "failed"
            try:
                proposal = preview["proposal"]
                idempotency_hash = preview["idempotencyKeyHash"]
                decision_id = sha256_value(
                    [proposal["tenantRef"], proposal["source"]["idHash"], idempotency_hash]
                )
                prior_id = self._decision_idempotency.get(
                    (proposal["tenantRef"], idempotency_hash)
                )
                if prior_id is not None:
                    if prior_id != decision_id:
                        raise DecisionError("idempotency_conflict")
                    prior_result = self._record_results.get(
                        (proposal["tenantRef"], idempotency_hash)
                    )
                    if prior_result is None or prior_id not in self._current:
                        raise DecisionError("ledger_projection_divergence")
                    outcome = "replayed"
                    return copy.deepcopy(prior_result) | {"replayed": True}
                if expected_sequence != 0 or expected_event_hash is not None:
                    raise DecisionError("stale_writer")

                timestamp = iso_time(current_time)
                event = self._event(
                    decision_id=decision_id,
                    sequence=1,
                    event_type="accepted",
                    actor_hash=actor_hash,
                    previous_hash=None,
                    payload={
                        "sourceDigest": proposal["source"]["digest"],
                        "policyDigest": proposal["policySnapshot"]["digest"],
                        "approvalDigest": proposal["approval"]["digest"],
                    },
                    recorded_at=timestamp,
                )
                record = {
                    "recordVersion": 1,
                    "decisionId": decision_id,
                    "tenantRef": proposal["tenantRef"],
                    "projectRef": proposal["projectRef"],
                    "domain": proposal["domain"],
                    "decisionClass": proposal["decisionClass"],
                    "source": copy.deepcopy(proposal["source"]),
                    "workflow": copy.deepcopy(proposal["workflow"]),
                    "actorHash": proposal["actorHash"],
                    "acl": list(proposal["acl"]),
                    "sensitivity": proposal["sensitivity"],
                    "status": "accepted",
                    "sequence": 1,
                    "currentEventHash": event["eventHash"],
                    "idempotencyKeyHash": idempotency_hash,
                    "rationaleSummaryHash": proposal["rationaleSummaryHash"],
                    "evidenceSet": copy.deepcopy(proposal["evidenceSet"]),
                    "policySnapshot": copy.deepcopy(proposal["policySnapshot"]),
                    "policyEvaluation": copy.deepcopy(proposal["policyEvaluation"]),
                    "approval": copy.deepcopy(proposal["approval"]),
                    "effects": [],
                    "outcomes": [],
                    "corrections": [],
                    "staleReasons": [],
                    "createdAt": timestamp,
                    "updatedAt": timestamp,
                    "retentionUntil": proposal["retentionUntil"],
                }
                validate_decision_record(record)
                if failure_at == "before_commit":
                    raise DecisionError("injected_failure_before_commit")
                self._events[decision_id] = [event]
                self._current[decision_id] = record
                self._decision_idempotency[(proposal["tenantRef"], idempotency_hash)] = decision_id
                result = {"record": self._safe_record(record), "replayed": False}
                self._record_results[(proposal["tenantRef"], idempotency_hash)] = copy.deepcopy(result)
                outcome = "accepted"
                return result
            finally:
                self.preview_store.finish(
                    preview_id, consumed_at=iso_time(current_time), outcome=outcome
                )

    def correct(
        self,
        decision_id: str,
        *,
        kind: str,
        reason_code: str,
        correction_approval: Mapping[str, Any],
        tenant_ref: str,
        actor_hash: str,
        principal_scopes: Sequence[str],
        expected_sequence: int,
        expected_event_hash: str,
        idempotency_key: str,
        role: str,
        superseding_decision_id: str | None = None,
        failure_at: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if kind not in CORRECTION_KINDS:
            raise DecisionError("unsupported correction kind")
        _code(reason_code, "reasonCode")
        current_time = now or utc_now()
        _validate_approval(correction_approval, current_time)
        if not correction_approval["granted"] or correction_approval["actorHash"] != actor_hash:
            raise DecisionError("unauthorized")
        if superseding_decision_id is not None:
            _hash(superseding_decision_id, "supersedingDecisionId")
        correction = {
            "correctionId": sha256_value(
                [decision_id, kind, reason_code, correction_approval["approvalIdHash"]]
            ),
            "kind": kind,
            "reasonCode": reason_code,
            "approvalIdHash": correction_approval["approvalIdHash"],
            "recordedAt": iso_time(current_time),
            **(
                {"supersedingDecisionId": superseding_decision_id}
                if superseding_decision_id is not None else {}
            ),
        }

        def mutate(record: dict[str, Any]) -> None:
            if not set(record["acl"]).issubset(correction_approval["scopes"]):
                raise DecisionError("correction approval scope is insufficient")
            if kind == "superseded":
                target = self._current.get(superseding_decision_id or "")
                if (
                    target is None
                    or target["tenantRef"] != record["tenantRef"]
                    or target["projectRef"] != record["projectRef"]
                ):
                    raise DecisionError("superseding_decision_not_found")
            elif superseding_decision_id is not None:
                raise DecisionError("supersedingDecisionId is only valid for supersession")
            record["corrections"].append(correction)
            record["status"] = kind

        return self._transition(
            decision_id,
            event_type=kind,
            payload=correction,
            mutate=mutate,
            tenant_ref=tenant_ref,
            actor_hash=actor_hash,
            principal_scopes=principal_scopes,
            expected_sequence=expected_sequence,
            expected_event_hash=expected_event_hash,
            idempotency_key=idempotency_key,
            role=role,
            allowed_roles=(self.REVIEW_ROLE,),
            failure_at=failure_at,
            now=current_time,
        )

    def invalidate_evidence(
        self,
        decision_id: str,
        *,
        evidence_id: str,
        tenant_ref: str,
        actor_hash: str,
        principal_scopes: Sequence[str],
        expected_sequence: int,
        expected_event_hash: str,
        idempotency_key: str,
        role: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        _hash(evidence_id, "evidenceId")

        def mutate(record: dict[str, Any]) -> None:
            item = next(
                (entry for entry in record["evidenceSet"]["items"] if entry["evidenceId"] == evidence_id),
                None,
            )
            if item is None:
                raise DecisionError("evidence_not_found")
            if "evidence_invalidated" not in record["staleReasons"]:
                record["staleReasons"].append("evidence_invalidated")

        return self._transition(
            decision_id,
            event_type="evidence_invalidated",
            payload={"evidenceId": evidence_id},
            mutate=mutate,
            tenant_ref=tenant_ref,
            actor_hash=actor_hash,
            principal_scopes=principal_scopes,
            expected_sequence=expected_sequence,
            expected_event_hash=expected_event_hash,
            idempotency_key=idempotency_key,
            role=role,
            allowed_roles=(self.REVIEW_ROLE,),
            now=now or utc_now(),
        )

    def record_effect(
        self,
        decision_id: str,
        *,
        system: str,
        action: str,
        effect_idempotency_key: str,
        tenant_ref: str,
        actor_hash: str,
        principal_scopes: Sequence[str],
        expected_sequence: int,
        expected_event_hash: str,
        transition_idempotency_key: str,
        role: str,
        failure_at: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        _ref(system, "effect system")
        _ref(action, "effect action")
        if not effect_idempotency_key or len(effect_idempotency_key) > 256:
            raise DecisionError("a bounded effect idempotency key is required")
        current_time = now or utc_now()
        effect = {
            "effectId": sha256_value([decision_id, system, action, effect_idempotency_key]),
            "system": system,
            "action": action,
            "idempotencyKeyHash": sha256_value(effect_idempotency_key),
            "status": "attempted",
            "attemptedAt": iso_time(current_time),
        }

        def mutate(record: dict[str, Any]) -> None:
            if record["status"] not in {"accepted", "corrected"}:
                raise DecisionError("decision is not eligible for a new effect")
            if parse_time(record["approval"]["expiresAt"], "approval expiresAt") <= current_time:
                raise DecisionError("approval_expired")
            if any(item["effectId"] == effect["effectId"] for item in record["effects"]):
                raise DecisionError("effect_already_recorded")
            record["effects"].append(effect)

        return self._transition(
            decision_id,
            event_type="effect_attempted",
            payload=effect,
            mutate=mutate,
            tenant_ref=tenant_ref,
            actor_hash=actor_hash,
            principal_scopes=principal_scopes,
            expected_sequence=expected_sequence,
            expected_event_hash=expected_event_hash,
            idempotency_key=transition_idempotency_key,
            role=role,
            allowed_roles=(self.RECORD_ROLE,),
            failure_at=failure_at,
            now=current_time,
        )

    def observe_outcome(
        self,
        decision_id: str,
        *,
        effect_id: str,
        source_receipt_hash: str,
        source_revision: str,
        status: str,
        tenant_ref: str,
        actor_hash: str,
        principal_scopes: Sequence[str],
        expected_sequence: int,
        expected_event_hash: str,
        idempotency_key: str,
        role: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        _hash(effect_id, "effectId")
        _hash(source_receipt_hash, "sourceReceiptHash")
        _ref(source_revision, "sourceRevision")
        if status not in {"succeeded", "failed", "unknown", "reconciliation_required"}:
            raise DecisionError("invalid outcome status")
        current_time = now or utc_now()
        observation = {
            "observationId": sha256_value(
                [decision_id, effect_id, source_receipt_hash, source_revision]
            ),
            "effectId": effect_id,
            "sourceReceiptHash": source_receipt_hash,
            "sourceRevision": source_revision,
            "status": status,
            "observedAt": iso_time(current_time),
        }

        def mutate(record: dict[str, Any]) -> None:
            if not any(item["effectId"] == effect_id for item in record["effects"]):
                raise DecisionError("effect_not_found")
            record["outcomes"].append(observation)

        return self._transition(
            decision_id,
            event_type="outcome_observed",
            payload=observation,
            mutate=mutate,
            tenant_ref=tenant_ref,
            actor_hash=actor_hash,
            principal_scopes=principal_scopes,
            expected_sequence=expected_sequence,
            expected_event_hash=expected_event_hash,
            idempotency_key=idempotency_key,
            role=role,
            allowed_roles=(self.RECORD_ROLE, self.REVIEW_ROLE),
            now=current_time,
        )

    def link_decisions(
        self,
        source_decision_id: str,
        target_decision_id: str,
        *,
        relationship_type: str,
        tenant_ref: str,
        actor_hash: str,
        principal_scopes: Sequence[str],
        expected_sequence: int,
        expected_event_hash: str,
        idempotency_key: str,
        role: str,
        evidence_digest: str | None = None,
        mechanism: str | None = None,
        reviewed: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if relationship_type not in RELATIONSHIP_TYPES:
            raise DecisionError("unsupported decision relationship")
        if not isinstance(reviewed, bool):
            raise DecisionError("relationship reviewed must be boolean")
        if mechanism is not None:
            _ref(mechanism, "relationship mechanism")
        if source_decision_id == target_decision_id:
            raise DecisionError("a decision cannot relate to itself")
        _hash(target_decision_id, "targetDecisionId")
        if relationship_type == "CAUSED":
            if not self.causality_enabled:
                raise DecisionError("causality_disabled")
            if not reviewed or evidence_digest is None or mechanism != "deterministic":
                raise DecisionError("causality_requires_deterministic_reviewed_evidence")
            _hash(evidence_digest, "causality evidenceDigest")
        elif evidence_digest is not None:
            _hash(evidence_digest, "relationship evidenceDigest")
        relation_id = sha256_value(
            [source_decision_id, target_decision_id, relationship_type, evidence_digest]
        )
        relation = {
            "relationshipId": relation_id,
            "sourceDecisionId": source_decision_id,
            "targetDecisionId": target_decision_id,
            "relationshipType": relationship_type,
            "evidenceDigest": evidence_digest,
            "mechanism": mechanism,
            "reviewed": reviewed,
        }

        def mutate(record: dict[str, Any]) -> None:
            if len(self._relationships) >= MAX_RELATIONSHIPS:
                raise DecisionError("decision relationship backlog exceeds budget")
            target = self._current.get(target_decision_id)
            if (
                target is None
                or target["tenantRef"] != record["tenantRef"]
                or target["projectRef"] != record["projectRef"]
                or not set(principal_scopes).intersection(target["acl"])
            ):
                raise DecisionError("target_not_found")
            if relation_id in self._relationships:
                raise DecisionError("relationship_already_recorded")

        result = self._transition(
            source_decision_id,
            event_type="relationship_recorded",
            payload=relation,
            mutate=mutate,
            tenant_ref=tenant_ref,
            actor_hash=actor_hash,
            principal_scopes=principal_scopes,
            expected_sequence=expected_sequence,
            expected_event_hash=expected_event_hash,
            idempotency_key=idempotency_key,
            role=role,
            allowed_roles=(self.REVIEW_ROLE,),
            commit=lambda: self._relationships.__setitem__(relation_id, relation),
            now=now or utc_now(),
        )
        return result

    def purge(
        self,
        decision_id: str,
        *,
        tenant_ref: str,
        actor_hash: str,
        principal_scopes: Sequence[str],
        expected_sequence: int,
        expected_event_hash: str,
        idempotency_key: str,
        role: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current_time = now or utc_now()

        def mutate(record: dict[str, Any]) -> None:
            if parse_time(record["retentionUntil"], "retentionUntil") > current_time:
                raise DecisionError("retention_not_expired")
            record["status"] = "purged"
            record["purgedAt"] = iso_time(current_time)
            record["effects"] = []
            record["outcomes"] = []
            if "retention_purged" not in record["staleReasons"]:
                record["staleReasons"].append("retention_purged")

        return self._transition(
            decision_id,
            event_type="purged",
            payload={"reasonCode": "retention_expired"},
            mutate=mutate,
            tenant_ref=tenant_ref,
            actor_hash=actor_hash,
            principal_scopes=principal_scopes,
            expected_sequence=expected_sequence,
            expected_event_hash=expected_event_hash,
            idempotency_key=idempotency_key,
            role=role,
            allowed_roles=(self.REVIEW_ROLE,),
            now=current_time,
        )

    def explain(
        self,
        decision_id: str,
        *,
        tenant_ref: str,
        principal_hash: str,
        principal_scopes: Sequence[str],
        role: str,
        budget: DecisionQueryBudget = DecisionQueryBudget(),
        current_bindings: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_role(role, self.QUERY_ROLE, self.REVIEW_ROLE)
        started = time.monotonic()
        self._validate_query_context(principal_hash, principal_scopes, budget)
        with self._lock:
            record = self._visible_record(decision_id, tenant_ref, principal_scopes)
            events = copy.deepcopy(self._events.get(decision_id, [])) if record else []
        results = [] if record is None else [{"record": self._safe_record(record), "events": events}]
        warnings = self._record_warnings(record) if record else []
        if record is not None:
            warnings.extend(self._binding_warnings(record, current_bindings))
        return self._query_result(
            "explain", tenant_ref, principal_hash, results, budget, started,
            warnings=warnings,
            missing=record is None,
            query_scope={"decisionId": decision_id},
        )

    def impact(
        self,
        decision_id: str,
        *,
        tenant_ref: str,
        principal_hash: str,
        principal_scopes: Sequence[str],
        role: str,
        budget: DecisionQueryBudget = DecisionQueryBudget(depth=2),
    ) -> dict[str, Any]:
        self._require_role(role, self.QUERY_ROLE, self.REVIEW_ROLE)
        started = time.monotonic()
        self._validate_query_context(principal_hash, principal_scopes, budget)
        with self._lock:
            root = self._visible_record(decision_id, tenant_ref, principal_scopes)
            if root is None:
                relations: list[dict[str, Any]] = []
            else:
                visible = {
                    item_id for item_id in self._current
                    if self._visible_record(item_id, tenant_ref, principal_scopes) is not None
                }
                relations = self._walk_relationships(decision_id, visible, budget, started)
        warnings = sorted(
            {"candidate_not_authority"}
            | ({"causality_present"} if any(r["relationshipType"] == "CAUSED" for r in relations) else set())
        )
        return self._query_result(
            "impact", tenant_ref, principal_hash, relations, budget, started,
            warnings=warnings if root is not None else [], missing=root is None,
            query_scope={"decisionId": decision_id, "depth": budget.depth},
        )

    def precedents(
        self,
        *,
        tenant_ref: str,
        principal_hash: str,
        principal_scopes: Sequence[str],
        role: str,
        decision_class: str,
        domain: str,
        current_policy_digest: str,
        budget: DecisionQueryBudget = DecisionQueryBudget(),
    ) -> dict[str, Any]:
        self._require_role(role, self.QUERY_ROLE, self.REVIEW_ROLE)
        started = time.monotonic()
        self._validate_query_context(principal_hash, principal_scopes, budget)
        if decision_class not in DECISION_CLASSES:
            raise DecisionError("unsupported decision class")
        _ref(domain, "domain")
        _hash(current_policy_digest, "currentPolicyDigest")
        candidates: list[dict[str, Any]] = []
        with self._lock:
            for decision_id, record in self._current.items():
                if (
                    self._visible_record(decision_id, tenant_ref, principal_scopes) is None
                    or record["decisionClass"] != decision_class
                    or record["domain"] != domain
                    or record["status"] not in {"accepted", "corrected"}
                ):
                    continue
                candidates.append({
                    "decisionId": decision_id,
                    "status": record["status"],
                    "policyDigest": record["policySnapshot"]["digest"],
                    "policyMismatch": record["policySnapshot"]["digest"] != current_policy_digest,
                    "candidateOnly": True,
                })
        candidates.sort(key=lambda item: item["decisionId"])
        return self._query_result(
            "precedents", tenant_ref, principal_hash, candidates, budget, started,
            warnings=["candidate_not_authority"], missing=False,
            query_scope={
                "decisionClass": decision_class,
                "domain": domain,
                "currentPolicyDigest": current_policy_digest,
            },
        )

    def status(
        self,
        *,
        tenant_ref: str,
        principal_hash: str,
        principal_scopes: Sequence[str],
        role: str,
        budget: DecisionQueryBudget = DecisionQueryBudget(),
    ) -> dict[str, Any]:
        self._require_role(role, self.QUERY_ROLE, self.REVIEW_ROLE)
        started = time.monotonic()
        self._validate_query_context(principal_hash, principal_scopes, budget)
        counts: dict[str, int] = {}
        with self._lock:
            for decision_id, record in self._current.items():
                if self._visible_record(decision_id, tenant_ref, principal_scopes) is None:
                    continue
                counts[record["status"]] = counts.get(record["status"], 0) + 1
        return self._query_result(
            "status", tenant_ref, principal_hash,
            [{"liveNeo4jEnabled": False, "counts": dict(sorted(counts.items()))}],
            budget, started, warnings=["offline_contract_only"], missing=False,
            query_scope={"tenantHash": sha256_value(tenant_ref)},
        )

    def events(self, decision_id: str) -> list[dict[str, Any]]:
        """Test/adapter verification hook; callers must not expose this without ACL checks."""

        with self._lock:
            return copy.deepcopy(self._events.get(decision_id, []))

    def current(self, decision_id: str) -> dict[str, Any] | None:
        """Test/adapter verification hook; callers must not expose this without ACL checks."""

        with self._lock:
            value = self._current.get(decision_id)
            return copy.deepcopy(value) if value is not None else None

    def verify(self, decision_id: str) -> bool:
        with self._lock:
            record = self._current.get(decision_id)
            events = self._events.get(decision_id)
            if record is None or not events or len(events) != record["sequence"]:
                return False
            previous: str | None = None
            for sequence, event in enumerate(events, 1):
                if event["sequence"] != sequence or event["previousEventHash"] != previous:
                    return False
                unsigned = {key: value for key, value in event.items() if key != "eventHash"}
                if event["eventHash"] != sha256_value(unsigned):
                    return False
                previous = event["eventHash"]
            return previous == record["currentEventHash"]

    def _transition(
        self,
        decision_id: str,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        mutate: Callable[[dict[str, Any]], None],
        tenant_ref: str,
        actor_hash: str,
        principal_scopes: Sequence[str],
        expected_sequence: int,
        expected_event_hash: str,
        idempotency_key: str,
        role: str,
        allowed_roles: Sequence[str],
        commit: Callable[[], None] | None = None,
        failure_at: str | None = None,
        now: datetime,
    ) -> dict[str, Any]:
        self._require_role(role, *allowed_roles)
        _hash(decision_id, "decisionId")
        _hash(actor_hash, "actorHash")
        scopes = _refs(principal_scopes, "principalScopes")
        if not idempotency_key or len(idempotency_key) > 256:
            raise DecisionError("a bounded transition idempotency key is required")
        if (
            isinstance(expected_sequence, bool)
            or not isinstance(expected_sequence, int)
            or expected_sequence < 1
        ):
            raise DecisionError("expected sequence must be a positive integer")
        _hash(expected_event_hash, "expectedEventHash")
        if failure_at not in {None, "before_commit"}:
            raise DecisionError("unsupported failure injection point")
        _privacy_safe(payload)
        key_hash = sha256_value(idempotency_key)
        request_digest = sha256_value([event_type, payload, actor_hash])
        with self._lock:
            prior = self._transition_idempotency.get((decision_id, key_hash))
            if prior is not None:
                if prior[0] != request_digest:
                    raise DecisionError("idempotency_conflict")
                return copy.deepcopy(prior[1]) | {"replayed": True}
            record = self._current.get(decision_id)
            if (
                record is None
                or record["tenantRef"] != tenant_ref
                or not set(scopes).intersection(record["acl"])
            ):
                raise DecisionError("unauthorized_or_not_found")
            if actor_hash != record["actorHash"] and role != self.REVIEW_ROLE:
                raise DecisionError("unauthorized")
            if record["status"] == "purged":
                raise DecisionError("decision_purged")
            if event_type != "purged" and parse_time(
                record["retentionUntil"], "retentionUntil"
            ) <= now:
                raise DecisionError("decision_retention_expired")
            if record["sequence"] != expected_sequence or record["currentEventHash"] != expected_event_hash:
                raise DecisionError("stale_writer")
            if len(self._events[decision_id]) >= MAX_EVENTS_PER_DECISION:
                raise DecisionError("decision event backlog exceeds budget")
            updated = copy.deepcopy(record)
            mutate(updated)
            timestamp = iso_time(now)
            event = self._event(
                decision_id=decision_id,
                sequence=expected_sequence + 1,
                event_type=event_type,
                actor_hash=actor_hash,
                previous_hash=expected_event_hash,
                payload=payload,
                recorded_at=timestamp,
            )
            updated["sequence"] = event["sequence"]
            updated["currentEventHash"] = event["eventHash"]
            updated["updatedAt"] = timestamp
            validate_decision_record(updated)
            if failure_at == "before_commit":
                raise DecisionError("injected_failure_before_commit")
            result = {"record": self._safe_record(updated), "event": copy.deepcopy(event), "replayed": False}
            self._events[decision_id] = [*self._events[decision_id], event]
            self._current[decision_id] = updated
            if commit is not None:
                commit()
            self._transition_idempotency[(decision_id, key_hash)] = (request_digest, copy.deepcopy(result))
            return result

    def _validate_preview(
        self,
        preview: Mapping[str, Any],
        *,
        tenant_ref: str,
        project_ref: str,
        actor_hash: str,
        workflow: Mapping[str, Any],
        principal_hash: str,
        principal_scopes: Sequence[str],
        nonce: str,
        current_bindings: Mapping[str, Any],
        now: datetime,
    ) -> None:
        required = {
            "previewVersion", "createdAt", "expiresAt", "principalHash", "principalScopes",
            "nonceHash", "idempotencyKeyHash", "bindingDigest", "proposal", "previewId",
            "previewDigest",
        }
        if not isinstance(preview, dict) or set(preview) != required or preview["previewVersion"] != 1:
            raise DecisionError("preview_invalid")
        unsigned_digest = sha256_value({key: value for key, value in preview.items() if key != "previewDigest"})
        if unsigned_digest != preview["previewDigest"]:
            raise DecisionError("preview_invalid")
        without_ids = {
            key: value for key, value in preview.items() if key not in {"previewId", "previewDigest"}
        }
        if preview["previewId"] != sha256_value(without_ids):
            raise DecisionError("preview_invalid")
        if parse_time(preview["expiresAt"], "preview expiresAt") <= now:
            raise DecisionError("preview_expired")
        proposal = preview["proposal"]
        _validate_proposal(proposal, now)
        scopes = _refs(principal_scopes, "principalScopes")
        if (
            preview["principalHash"] != principal_hash
            or preview["principalScopes"] != scopes
            or preview["nonceHash"] != sha256_value(nonce)
            or proposal["tenantRef"] != tenant_ref
            or proposal["projectRef"] != project_ref
            or proposal["actorHash"] != actor_hash
            or proposal["workflow"] != workflow
            or not set(scopes).intersection(proposal["acl"])
        ):
            raise DecisionError("preview_binding_mismatch")
        if preview["bindingDigest"] != sha256_value(current_bindings):
            raise DecisionError("preview_stale")
        if current_bindings != decision_bindings(proposal):
            raise DecisionError("preview_stale")

    def _query_result(
        self,
        operation: str,
        tenant_ref: str,
        principal_hash: str,
        results: list[dict[str, Any]],
        budget: DecisionQueryBudget,
        started: float,
        *,
        warnings: Sequence[str],
        missing: bool,
        query_scope: Mapping[str, Any],
    ) -> dict[str, Any]:
        if (time.monotonic() - started) * 1000 > budget.runtime_ms:
            raise DecisionError("query_budget_exceeded")
        selected: list[dict[str, Any]] = []
        used_bytes = 0
        for result in results[: budget.results]:
            size = len(canonical_json(result).encode("utf-8"))
            if used_bytes + size > budget.max_bytes:
                break
            selected.append(copy.deepcopy(result))
            used_bytes += size
        truncated = len(selected) < len(results)
        query_hash = sha256_value(query_scope)
        receipt = {
            "receiptVersion": 1,
            "queryId": sha256_value(
                [operation, query_hash, sha256_value(tenant_ref), principal_hash, len(selected), sorted(set(warnings))]
            ),
            "queryHash": query_hash,
            "operation": operation,
            "status": "not_found" if missing else "ok",
            "tenantHash": sha256_value(tenant_ref),
            "principalHash": principal_hash,
            "resultCount": len(selected),
            "truncated": truncated,
            "warnings": sorted(set(warnings)),
            "contractVersion": DECISION_CONTRACT_VERSION,
        }
        validate_query_receipt(receipt)
        return {"receipt": receipt, "results": selected}

    def _walk_relationships(
        self,
        root_id: str,
        visible: set[str],
        budget: DecisionQueryBudget,
        started: float,
    ) -> list[dict[str, Any]]:
        visited = {root_id}
        frontier = {root_id}
        results: list[dict[str, Any]] = []
        for depth in range(1, budget.depth + 1):
            if (time.monotonic() - started) * 1000 > budget.runtime_ms:
                raise DecisionError("query_budget_exceeded")
            next_frontier: set[str] = set()
            for relation in sorted(self._relationships.values(), key=lambda item: item["relationshipId"]):
                if relation["sourceDecisionId"] not in frontier:
                    continue
                target = relation["targetDecisionId"]
                if target not in visible:
                    continue
                results.append({**copy.deepcopy(relation), "depth": depth, "candidateOnly": relation["relationshipType"] != "CAUSED"})
                if target not in visited:
                    next_frontier.add(target)
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        return results

    def _visible_record(
        self,
        decision_id: str,
        tenant_ref: str,
        principal_scopes: Sequence[str],
    ) -> dict[str, Any] | None:
        record = self._current.get(decision_id)
        if (
            record is None
            or record["tenantRef"] != tenant_ref
            or not set(principal_scopes).intersection(record["acl"])
        ):
            return None
        return copy.deepcopy(record)

    @staticmethod
    def _record_warnings(record: Mapping[str, Any] | None) -> list[str]:
        if record is None:
            return []
        warnings = list(record["staleReasons"])
        if record["policySnapshot"]["status"] != "current":
            warnings.append("policy_stale")
        if any(item["status"] != "available" for item in record["evidenceSet"]["items"]):
            warnings.append("evidence_stale")
        return sorted(set(warnings))

    @staticmethod
    def _binding_warnings(
        record: Mapping[str, Any],
        current_bindings: Mapping[str, Any] | None,
    ) -> list[str]:
        if current_bindings is None:
            return ["canonical_revalidation_unavailable"]
        expected = decision_bindings(record)
        warnings: list[str] = []
        if current_bindings.get("source") != expected["source"]:
            warnings.append("source_stale")
        if current_bindings.get("evidenceSetDigest") != expected["evidenceSetDigest"]:
            warnings.append("evidence_stale")
        if (
            current_bindings.get("policyVersion") != expected["policyVersion"]
            or current_bindings.get("policyDigest") != expected["policyDigest"]
            or current_bindings.get("policyEvaluationDigest") != expected["policyEvaluationDigest"]
        ):
            warnings.append("policy_stale")
        if (
            current_bindings.get("approvalRevision") != expected["approvalRevision"]
            or current_bindings.get("approvalDigest") != expected["approvalDigest"]
        ):
            warnings.append("approval_stale")
        return warnings

    @staticmethod
    def _safe_record(record: Mapping[str, Any]) -> dict[str, Any]:
        safe = copy.deepcopy(dict(record))
        for field in ("tenantRef", "projectRef", "actorHash", "acl"):
            safe.pop(field, None)
        if safe.get("status") == "purged":
            safe["source"] = {"system": "purged", "idHash": safe["source"]["idHash"], "revision": "purged", "digest": safe["source"]["digest"]}
            safe["evidenceSet"]["items"] = []
        return safe

    @staticmethod
    def _event(
        *,
        decision_id: str,
        sequence: int,
        event_type: str,
        actor_hash: str,
        previous_hash: str | None,
        payload: Mapping[str, Any],
        recorded_at: str,
    ) -> dict[str, Any]:
        unsigned = {
            "decisionId": decision_id,
            "sequence": sequence,
            "eventType": event_type,
            "actorHash": actor_hash,
            "recordedAt": recorded_at,
            "previousEventHash": previous_hash,
            "payload": copy.deepcopy(dict(payload)),
        }
        return {**unsigned, "eventHash": sha256_value(unsigned)}

    @staticmethod
    def _validate_query_context(
        principal_hash: str,
        principal_scopes: Sequence[str],
        budget: DecisionQueryBudget,
    ) -> None:
        _hash(principal_hash, "principalHash")
        _refs(principal_scopes, "principalScopes")
        if isinstance(budget.depth, bool) or not isinstance(budget.depth, int) or not 0 <= budget.depth <= 3:
            raise DecisionError("query depth exceeds budget")
        if isinstance(budget.results, bool) or not isinstance(budget.results, int) or not 1 <= budget.results <= 100:
            raise DecisionError("query result limit exceeds budget")
        if isinstance(budget.runtime_ms, bool) or not isinstance(budget.runtime_ms, int) or not 1 <= budget.runtime_ms <= 1000:
            raise DecisionError("query runtime exceeds budget")
        if isinstance(budget.max_bytes, bool) or not isinstance(budget.max_bytes, int) or not 512 <= budget.max_bytes <= 65_536:
            raise DecisionError("query byte budget is invalid")

    @staticmethod
    def _require_role(role: str, *allowed: str) -> None:
        if role not in allowed:
            raise DecisionError("role_not_authorized")


def validate_policy_evaluation(value: Mapping[str, Any]) -> None:
    required = {
        "evaluationVersion", "evaluationId", "policyIdHash", "policyVersion",
        "policyDigest", "inputRefs", "result", "status", "evaluatedAt",
        "evaluatorVersion", "deterministic", "outputDigest",
    }
    optional = {"errorCode"}
    _closed(value, required, optional, "policy evaluation")
    if value["evaluationVersion"] != 1 or value["deterministic"] is not True:
        raise DecisionError("policy evaluation must be deterministic v1")
    for field in ("evaluationId", "policyIdHash", "policyDigest", "outputDigest"):
        _hash(value[field], f"policy evaluation {field}")
    _ref(value["policyVersion"], "policyVersion")
    _ref(value["evaluatorVersion"], "evaluatorVersion")
    inputs = value["inputRefs"]
    if (
        not isinstance(inputs, list)
        or not 1 <= len(inputs) <= 128
        or not all(isinstance(item, str) for item in inputs)
        or len(inputs) != len(set(inputs))
    ):
        raise DecisionError("policy inputRefs must be a bounded unique array")
    for item in inputs:
        _hash(item, "policy inputRef")
    if value["result"] not in {"allow", "deny", "review"}:
        raise DecisionError("invalid policy result")
    if value["status"] not in {"reproduced", "failed", "stale"}:
        raise DecisionError("invalid policy status")
    parse_time(value["evaluatedAt"], "evaluatedAt")
    error_code = value.get("errorCode")
    if error_code is not None:
        _code(error_code, "policy errorCode")
    if value["status"] == "reproduced" and error_code is not None:
        raise DecisionError("a reproduced policy evaluation cannot have an errorCode")
    if value["status"] != "reproduced" and error_code is None:
        raise DecisionError("a non-reproduced policy evaluation requires an errorCode")
    expected_output = sha256_value({
        "policyIdHash": value["policyIdHash"],
        "policyVersion": value["policyVersion"],
        "policyDigest": value["policyDigest"],
        "inputRefs": sorted(value["inputRefs"]),
        "result": value["result"],
        "status": value["status"],
        "evaluatorVersion": value["evaluatorVersion"],
    })
    if value["inputRefs"] != sorted(value["inputRefs"]) or value["outputDigest"] != expected_output:
        raise DecisionError("policy evaluation output is not reproducible")
    expected_id = sha256_value([
        value["policyIdHash"], value["policyVersion"], expected_output, value["evaluatedAt"]
    ])
    if value["evaluationId"] != expected_id:
        raise DecisionError("policy evaluation identity is not reproducible")


def validate_decision_record(value: Mapping[str, Any]) -> None:
    required = {
        "recordVersion", "decisionId", "tenantRef", "projectRef", "domain", "decisionClass",
        "source", "workflow", "actorHash", "acl", "sensitivity", "status", "sequence",
        "currentEventHash", "idempotencyKeyHash", "rationaleSummaryHash", "evidenceSet",
        "policySnapshot", "policyEvaluation", "approval", "effects", "outcomes",
        "corrections", "staleReasons", "createdAt", "updatedAt", "retentionUntil",
    }
    _closed(value, required, {"purgedAt"}, "decision record")
    if value["recordVersion"] != 1:
        raise DecisionError("unsupported decision record version")
    for field in (
        "decisionId", "actorHash", "currentEventHash", "idempotencyKeyHash",
        "rationaleSummaryHash",
    ):
        _hash(value[field], field)
    for field in ("tenantRef", "projectRef", "domain"):
        _ref(value[field], field)
    if value["decisionClass"] not in DECISION_CLASSES or value["status"] not in DECISION_STATUSES:
        raise DecisionError("invalid decision class or status")
    if value["sensitivity"] not in {"internal", "confidential", "restricted"}:
        raise DecisionError("invalid decision sensitivity")
    if isinstance(value["sequence"], bool) or not isinstance(value["sequence"], int) or value["sequence"] < 1:
        raise DecisionError("decision sequence must be a positive integer")
    _validate_source(value["source"])
    _validate_workflow(value["workflow"])
    _refs(value["acl"], "acl")
    _validate_evidence_set(value["evidenceSet"])
    _validate_policy_snapshot(value["policySnapshot"])
    validate_policy_evaluation(value["policyEvaluation"])
    created_at = parse_time(value["createdAt"], "createdAt")
    updated_at = parse_time(value["updatedAt"], "updatedAt")
    retention_until = parse_time(value["retentionUntil"], "retentionUntil")
    _validate_approval(value["approval"], created_at)
    if updated_at < created_at or retention_until <= created_at:
        raise DecisionError("decision timestamps are out of order")
    if parse_time(value["policyEvaluation"]["evaluatedAt"], "evaluatedAt") > created_at:
        raise DecisionError("policy evaluation cannot postdate the decision")
    if value.get("purgedAt") is not None:
        if parse_time(value["purgedAt"], "purgedAt") < created_at:
            raise DecisionError("purgedAt cannot predate the decision")
    if value["status"] == "purged" and value.get("purgedAt") is None:
        raise DecisionError("a purged decision requires purgedAt")
    if value["status"] != "purged" and "purgedAt" in value:
        raise DecisionError("purgedAt is only valid for a purged decision")
    _validate_effects(value["effects"])
    _validate_outcomes(value["outcomes"], value["effects"])
    _validate_corrections(value["corrections"])
    if any(parse_time(item["attemptedAt"], "effect attemptedAt") < created_at for item in value["effects"]):
        raise DecisionError("an effect cannot predate the decision")
    effect_times = {
        item["effectId"]: parse_time(item["attemptedAt"], "effect attemptedAt")
        for item in value["effects"]
    }
    if any(
        parse_time(item["observedAt"], "outcome observedAt") < effect_times[item["effectId"]]
        for item in value["outcomes"]
    ):
        raise DecisionError("an outcome cannot predate its effect")
    if any(parse_time(item["recordedAt"], "correction recordedAt") < created_at for item in value["corrections"]):
        raise DecisionError("a correction cannot predate the decision")
    reasons = value["staleReasons"]
    if (
        not isinstance(reasons, list)
        or len(reasons) > 128
        or not all(isinstance(reason, str) for reason in reasons)
        or len(reasons) != len(set(reasons))
    ):
        raise DecisionError("staleReasons must be a bounded unique array")
    for reason in reasons:
        _code(reason, "stale reason")
    _privacy_safe(value)


def validate_query_receipt(value: Mapping[str, Any]) -> None:
    required = {
        "receiptVersion", "queryId", "queryHash", "operation", "status", "tenantHash", "principalHash",
        "resultCount", "truncated", "warnings", "contractVersion",
    }
    _closed(value, required, set(), "decision query receipt")
    if value["receiptVersion"] != 1 or value["contractVersion"] != 1:
        raise DecisionError("unsupported query receipt version")
    for field in ("queryId", "queryHash", "tenantHash", "principalHash"):
        _hash(value[field], field)
    if value["operation"] not in {"explain", "impact", "precedents", "status"}:
        raise DecisionError("unsupported query receipt operation")
    if value["status"] not in {"ok", "not_found", "unavailable", "unauthorized", "budget_exceeded"}:
        raise DecisionError("unsupported query receipt status")
    if isinstance(value["resultCount"], bool) or not isinstance(value["resultCount"], int) or value["resultCount"] < 0:
        raise DecisionError("query resultCount must be non-negative")
    if not isinstance(value["truncated"], bool):
        raise DecisionError("query truncated must be boolean")
    warnings = value["warnings"]
    if (
        not isinstance(warnings, list)
        or len(warnings) > 64
        or not all(isinstance(warning, str) for warning in warnings)
        or len(warnings) != len(set(warnings))
    ):
        raise DecisionError("query warnings must be a bounded unique array")
    for warning in warnings:
        _code(warning, "query warning")


def _validate_proposal(value: Mapping[str, Any], now: datetime) -> None:
    _closed(value, PROPOSAL_FIELDS, set(), "decision proposal")
    for field in ("tenantRef", "projectRef", "domain"):
        _ref(value[field], field)
    if value["decisionClass"] not in DECISION_CLASSES:
        raise DecisionError("unsupported decision class")
    _validate_source(value["source"])
    _validate_workflow(value["workflow"])
    _hash(value["actorHash"], "actorHash")
    _refs(value["acl"], "acl")
    if value["sensitivity"] not in {"internal", "confidential", "restricted"}:
        raise DecisionError("invalid sensitivity")
    _hash(value["rationaleSummaryHash"], "rationaleSummaryHash")
    _validate_evidence_set(value["evidenceSet"])
    _validate_policy_snapshot(value["policySnapshot"])
    validate_policy_evaluation(value["policyEvaluation"])
    _validate_approval(value["approval"], now)
    if value["approval"]["actorHash"] != value["actorHash"]:
        raise DecisionError("approval actor does not match decision actor")
    if not set(value["acl"]).issubset(value["approval"]["scopes"]):
        raise DecisionError("approval scope does not cover the decision ACL")
    if not value["approval"]["granted"]:
        raise DecisionError("approval was denied")
    if value["policySnapshot"]["status"] != "current":
        raise DecisionError("policy snapshot is not current")
    evaluation = value["policyEvaluation"]
    if evaluation["status"] != "reproduced" or evaluation["result"] == "deny":
        raise DecisionError("policy evaluation does not permit recording")
    if parse_time(evaluation["evaluatedAt"], "evaluatedAt") > now:
        raise DecisionError("policy evaluation cannot postdate recording")
    if evaluation["policyIdHash"] != value["policySnapshot"]["policyIdHash"]:
        raise DecisionError("policy evaluation is bound to another policy")
    if evaluation["policyVersion"] != value["policySnapshot"]["version"]:
        raise DecisionError("policy evaluation version mismatch")
    if evaluation["policyDigest"] != value["policySnapshot"]["digest"]:
        raise DecisionError("policy evaluation digest mismatch")
    if any(item["status"] != "available" for item in value["evidenceSet"]["items"]):
        raise DecisionError("decision evidence is stale or unavailable")
    if parse_time(value["retentionUntil"], "retentionUntil") <= now:
        raise DecisionError("decision retention must extend beyond recording")
    _privacy_safe(value)


def _validate_source(value: Any) -> None:
    _closed(value, {"system", "idHash", "revision", "digest"}, set(), "source binding")
    _ref(value["system"], "source system")
    if value["system"].casefold() in {"prompt", "transcript", "chain_of_thought"}:
        raise DecisionError("private agent traces are not canonical sources")
    _hash(value["idHash"], "source idHash")
    _ref(value["revision"], "source revision")
    _hash(value["digest"], "source digest")


def _validate_workflow(value: Any) -> None:
    _closed(value, {"id", "revision"}, set(), "workflow binding")
    _ref(value["id"], "workflow id")
    _ref(value["revision"], "workflow revision")


def _validate_bindings(value: Any) -> None:
    _closed(
        value,
        {
            "source", "evidenceSetDigest", "policyVersion", "policyDigest",
            "policyEvaluationDigest", "approvalRevision", "approvalDigest",
        },
        set(),
        "current decision bindings",
    )
    _validate_source(value["source"])
    for field in (
        "evidenceSetDigest", "policyDigest", "policyEvaluationDigest", "approvalDigest",
    ):
        _hash(value[field], f"current bindings {field}")
    _ref(value["policyVersion"], "current bindings policyVersion")
    _ref(value["approvalRevision"], "current bindings approvalRevision")


def _validate_evidence_set(value: Any) -> None:
    _closed(value, {"evidenceSetId", "digest", "items"}, set(), "evidence set")
    _hash(value["evidenceSetId"], "evidenceSetId")
    _hash(value["digest"], "evidenceSet digest")
    items = value["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 128:
        raise DecisionError("evidence set items must be a bounded non-empty array")
    identifiers: set[str] = set()
    for item in items:
        _closed(
            item, {"evidenceId", "system", "idHash", "revision", "digest", "status"},
            set(), "evidence item",
        )
        for field in ("evidenceId", "idHash", "digest"):
            _hash(item[field], f"evidence {field}")
        _ref(item["system"], "evidence system")
        _ref(item["revision"], "evidence revision")
        if item["status"] not in {"available", "stale", "unavailable", "invalidated"}:
            raise DecisionError("invalid evidence status")
        if item["evidenceId"] in identifiers:
            raise DecisionError("duplicate evidence identifier")
        identifiers.add(item["evidenceId"])
    expected_digest = sha256_value(items)
    if value["digest"] != expected_digest:
        raise DecisionError("evidence set digest mismatch")


def _validate_policy_snapshot(value: Any) -> None:
    _closed(value, {"policyIdHash", "version", "digest", "status"}, set(), "policy snapshot")
    _hash(value["policyIdHash"], "policyIdHash")
    _ref(value["version"], "policy version")
    _hash(value["digest"], "policy digest")
    if value["status"] not in {"current", "stale", "unavailable"}:
        raise DecisionError("invalid policy snapshot status")


def _validate_approval(value: Any, now: datetime) -> None:
    _closed(
        value,
        {"approvalIdHash", "source", "revision", "digest", "actorHash", "scopes", "granted", "expiresAt"},
        set(), "approval",
    )
    for field in ("approvalIdHash", "digest", "actorHash"):
        _hash(value[field], f"approval {field}")
    _ref(value["source"], "approval source")
    _ref(value["revision"], "approval revision")
    _refs(value["scopes"], "approval scopes")
    if not isinstance(value["granted"], bool):
        raise DecisionError("approval granted must be boolean")
    if parse_time(value["expiresAt"], "approval expiresAt") <= now:
        raise DecisionError("approval_expired")


def _validate_effects(values: Any) -> None:
    if not isinstance(values, list) or len(values) > 128:
        raise DecisionError("effects must be a bounded array")
    identifiers: set[str] = set()
    for value in values:
        _closed(
            value, {"effectId", "system", "action", "idempotencyKeyHash", "status", "attemptedAt"},
            set(), "effect",
        )
        _hash(value["effectId"], "effectId")
        _hash(value["idempotencyKeyHash"], "effect idempotencyKeyHash")
        _ref(value["system"], "effect system")
        _ref(value["action"], "effect action")
        if value["status"] not in {"attempted", "unknown", "reconciliation_required"}:
            raise DecisionError("an effect attempt cannot assert success or failure")
        parse_time(value["attemptedAt"], "effect attemptedAt")
        if value["effectId"] in identifiers:
            raise DecisionError("duplicate effect identifier")
        identifiers.add(value["effectId"])


def _validate_outcomes(values: Any, effects: Sequence[Mapping[str, Any]]) -> None:
    if not isinstance(values, list) or len(values) > 128:
        raise DecisionError("outcomes must be a bounded array")
    effect_ids = {item["effectId"] for item in effects}
    identifiers: set[str] = set()
    for value in values:
        _closed(
            value,
            {"observationId", "effectId", "sourceReceiptHash", "sourceRevision", "status", "observedAt"},
            set(), "outcome observation",
        )
        for field in ("observationId", "effectId", "sourceReceiptHash"):
            _hash(value[field], f"outcome {field}")
        _ref(value["sourceRevision"], "outcome sourceRevision")
        if value["effectId"] not in effect_ids:
            raise DecisionError("outcome does not resolve to an effect")
        if value["status"] not in {"succeeded", "failed", "unknown", "reconciliation_required"}:
            raise DecisionError("invalid outcome status")
        parse_time(value["observedAt"], "outcome observedAt")
        if value["observationId"] in identifiers:
            raise DecisionError("duplicate outcome identifier")
        identifiers.add(value["observationId"])


def _validate_corrections(values: Any) -> None:
    if not isinstance(values, list) or len(values) > 128:
        raise DecisionError("corrections must be a bounded array")
    identifiers: set[str] = set()
    for value in values:
        _closed(
            value,
            {"correctionId", "kind", "reasonCode", "approvalIdHash", "recordedAt"},
            {"supersedingDecisionId"}, "correction",
        )
        _hash(value["correctionId"], "correctionId")
        _hash(value["approvalIdHash"], "correction approvalIdHash")
        if value["kind"] not in CORRECTION_KINDS:
            raise DecisionError("invalid correction kind")
        _code(value["reasonCode"], "correction reasonCode")
        parse_time(value["recordedAt"], "correction recordedAt")
        if value.get("supersedingDecisionId") is not None:
            _hash(value["supersedingDecisionId"], "supersedingDecisionId")
        if value["correctionId"] in identifiers:
            raise DecisionError("duplicate correction identifier")
        identifiers.add(value["correctionId"])


def _privacy_safe(value: Any) -> None:
    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                lowered = str(key).casefold().replace("_", "")
                if lowered in {
                    "prompt", "systemprompt", "transcript", "chainofthought", "secret",
                    "credential", "clientcontent", "rawcontent", "absolutepath",
                }:
                    raise DecisionError(f"forbidden protected field: {key}")
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, str):
            lowered = item.casefold()
            if any(marker in lowered for marker in FORBIDDEN_TEXT):
                raise DecisionError("protected or prompt-like content is forbidden")
            if FORBIDDEN_SECRET_PATTERN.search(item):
                raise DecisionError("secret-shaped content is forbidden")

    walk(value)


def _closed(value: Any, required: set[str], optional: set[str], name: str) -> None:
    if not isinstance(value, Mapping):
        raise DecisionError(f"{name} must be an object")
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing or unknown:
        raise DecisionError(f"{name} fields missing={sorted(missing)} unknown={sorted(unknown)}")


def _hash(value: Any, name: str) -> None:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise DecisionError(f"{name} must be a sha256 hash")


def _ref(value: Any, name: str) -> None:
    if not isinstance(value, str) or not REF_PATTERN.fullmatch(value):
        raise DecisionError(f"{name} must be a bounded opaque reference")


def _refs(values: Sequence[Any], name: str) -> list[str]:
    if (
        isinstance(values, (str, bytes))
        or not isinstance(values, Sequence)
        or not 1 <= len(values) <= 64
        or not all(isinstance(value, str) for value in values)
        or len(values) != len(set(values))
    ):
        raise DecisionError(f"{name} must be a bounded unique reference array")
    for value in values:
        _ref(value, name)
    return sorted(values)


def _code(value: Any, name: str) -> None:
    if not isinstance(value, str) or not CODE_PATTERN.fullmatch(value):
        raise DecisionError(f"{name} must be a bounded machine-readable code")


__all__ = [
    "DECISION_CONTRACT_VERSION",
    "DecisionError",
    "DecisionPreviewStore",
    "DecisionQueryBudget",
    "InMemoryDecisionLedger",
    "decision_bindings",
    "validate_decision_record",
    "validate_policy_evaluation",
    "validate_query_receipt",
]
