"""Strict memory envelopes, deterministic ranking, private packs, TTL, and purge."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


MEMORY_TYPES = ("working", "episodic", "semantic", "procedural")
CONTENT_ROLES = {
    "data", "evidence", "decision-summary", "policy-reference", "procedure-reference",
}
ADAPTER_STATUSES = {
    "available", "empty", "unavailable", "unauthorized", "timeout",
    "stale", "partial", "error",
}
SENSITIVITY_ORDER = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
AUTHORITY_ORDER = {
    "canonical-policy": 0,
    "human-decision": 1,
    "verified-fact": 2,
    "current-session": 3,
    "derived": 4,
    "untrusted": 5,
}
TRUST_ORDER = {"operator-approved": 0, "verified": 1, "observed": 2, "unverified": 3}
DEFAULT_LANE_BUDGETS = {
    memory_type: {"maxItems": 5, "maxTokens": 1_500} for memory_type in MEMORY_TYPES
}


def sha256(value: str | bytes) -> str:
    payload = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _strict_keys(document: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(document) - allowed
    if unknown:
        raise ValueError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise ValueError(f"{label} must be a safe identifier")
    return value


def _scope_hash(value: str | None) -> str | None:
    return sha256(value) if value else None


@dataclass(frozen=True)
class Candidate:
    envelope: dict[str, Any]
    content: str
    token_count: int


class MemoryContextAssembler:
    """Normalize explicit adapter results and assemble a bounded preview."""

    def assemble(self, document: dict[str, Any], now: datetime | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        _strict_keys(document, {"schemaVersion", "request", "adapters"}, "memory request")
        if document.get("schemaVersion") != 1:
            raise ValueError("memory request schemaVersion must be 1")
        request = self._validate_request(document.get("request"))
        adapters = document.get("adapters")
        if not isinstance(adapters, list):
            raise ValueError("adapters must be an array")
        build_time = now or utc_now()
        statuses: list[dict[str, Any]] = []
        candidates: list[Candidate] = []
        seen_adapters: set[str] = set()
        exclusions: dict[str, int] = {}

        for adapter in adapters:
            status, normalized, rejected = self._normalize_adapter(adapter, request, build_time)
            if status["name"] in seen_adapters:
                raise ValueError(f"duplicate adapter: {status['name']}")
            seen_adapters.add(status["name"])
            statuses.append(status)
            candidates.extend(normalized)
            for reason, count in rejected.items():
                exclusions[reason] = exclusions.get(reason, 0) + count

        defaults = {
            "host-episodic": ("episodic", "supported_api_not_supplied"),
            "procedural-memory": ("procedural", "machine_readable_recall_not_implemented"),
        }
        for name, (memory_type, reason) in defaults.items():
            if name not in seen_adapters:
                statuses.append({
                    "name": name,
                    "memoryType": memory_type,
                    "status": "unavailable",
                    "reason": reason,
                })

        selected, rank_exclusions = self._select(candidates, request)
        for reason, count in rank_exclusions.items():
            exclusions[reason] = exclusions.get(reason, 0) + count
        expires = build_time + timedelta(seconds=request["ttlSeconds"])
        if selected:
            candidate_expiries = [
                parse_time(item.envelope["validUntil"])
                for item in selected
                if item.envelope["validUntil"] is not None
            ]
            if candidate_expiries:
                expires = min(expires, min(candidate_expiries))

        conflict_groups = self._conflicts(selected)
        payloads = {item.envelope["payloadRef"]: item.content for item in selected}
        manifest_candidates = []
        for rank, item in enumerate(selected, start=1):
            envelope = dict(item.envelope)
            envelope["rank"] = rank
            envelope["estimatedTokens"] = item.token_count
            envelope["conflictGroupHash"] = conflict_groups.get(item.envelope["memoryId"])
            manifest_candidates.append(envelope)
        payload = {"schemaVersion": 1, "payloads": payloads}
        payload_hash = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        warnings = []
        if conflict_groups:
            warnings.append("conflicting_candidates_preserved")
        if any(item["status"] not in {"available", "empty"} for item in statuses):
            warnings.append("one_or_more_adapters_unavailable")
        manifest = {
            "schemaVersion": 1,
            "packId": "pending",
            "createdAt": format_time(build_time),
            "expiresAt": format_time(expires),
            "requestHash": request["requestHash"],
            "tenantHash": _scope_hash(request["tenant"]),
            "projectHash": _scope_hash(request["project"]),
            "taskHash": _scope_hash(request["task"]),
            "adapterStatuses": sorted(statuses, key=lambda item: item["name"]),
            "candidates": manifest_candidates,
            "exclusionReasonCounts": dict(sorted(exclusions.items())[:12]),
            "exclusionReasonKindsTruncated": max(0, len(exclusions) - 12),
            "totalEstimatedTokens": sum(item.token_count for item in selected),
            "payloadHash": payload_hash,
            "policy": {
                "version": "memory-context-ranking-v1",
                "automaticInjection": False,
                "writeBack": False,
            },
            "warnings": warnings,
        }
        identity = {key: value for key, value in manifest.items() if key != "packId"}
        manifest["packId"] = (
            f"memory-{sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')))[:32]}"
        )
        validate_manifest(manifest)
        return manifest, payload

    def _validate_request(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("request must be an object")
        _strict_keys(
            value,
            {
                "tenant", "project", "task", "query", "allowedSensitivity",
                "totalTokenBudget", "laneBudgets", "ttlSeconds",
            },
            "request",
        )
        tenant = _safe_id(value.get("tenant"), "tenant")
        project = _safe_id(value.get("project"), "project")
        task = value.get("task")
        if task is not None:
            task = _safe_id(task, "task")
        query = value.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be non-empty")
        allowed = value.get("allowedSensitivity", ["internal"])
        if not isinstance(allowed, list) or not allowed or any(item not in SENSITIVITY_ORDER for item in allowed):
            raise ValueError("allowedSensitivity is invalid")
        total = value.get("totalTokenBudget", 4_000)
        ttl = value.get("ttlSeconds", 3_600)
        if not isinstance(total, int) or not 1 <= total <= 100_000:
            raise ValueError("totalTokenBudget is outside the supported range")
        if not isinstance(ttl, int) or not 60 <= ttl <= 86_400:
            raise ValueError("ttlSeconds is outside the supported range")
        lane_budgets = value.get("laneBudgets", DEFAULT_LANE_BUDGETS)
        if not isinstance(lane_budgets, dict) or set(lane_budgets) - set(MEMORY_TYPES):
            raise ValueError("laneBudgets contains an unknown memory type")
        normalized_budgets: dict[str, dict[str, int]] = {}
        for memory_type in MEMORY_TYPES:
            budget = lane_budgets.get(memory_type, DEFAULT_LANE_BUDGETS[memory_type])
            if not isinstance(budget, dict) or set(budget) != {"maxItems", "maxTokens"}:
                raise ValueError(f"lane budget for {memory_type} is invalid")
            if not all(isinstance(budget[key], int) and budget[key] >= 0 for key in budget):
                raise ValueError(f"lane budget for {memory_type} must be non-negative")
            normalized_budgets[memory_type] = dict(budget)
        return {
            "tenant": tenant,
            "project": project,
            "task": task,
            "allowedSensitivity": tuple(allowed),
            "totalTokenBudget": total,
            "laneBudgets": normalized_budgets,
            "ttlSeconds": ttl,
            "requestHash": sha256(query.strip()),
        }

    def _normalize_adapter(
        self, value: Any, request: dict[str, Any], now: datetime
    ) -> tuple[dict[str, Any], list[Candidate], dict[str, int]]:
        if not isinstance(value, dict):
            raise ValueError("adapter must be an object")
        _strict_keys(value, {"name", "memoryType", "status", "reason", "protocolVersion", "candidates"}, "adapter")
        name = _safe_id(value.get("name"), "adapter name")
        memory_type = value.get("memoryType")
        if memory_type not in MEMORY_TYPES:
            raise ValueError("adapter memoryType is invalid")
        status = value.get("status")
        if status not in ADAPTER_STATUSES:
            raise ValueError("adapter status is invalid")
        reason = _safe_id(value.get("reason", "none"), "adapter reason")
        protocol = value.get("protocolVersion")
        if name == "host-episodic" and protocol != "supported-episodic-read-v1":
            status, reason = "unavailable", "supported_api_not_supplied"
        if name == "procedural-memory":
            # The planned JSON recall contract is not shipped yet. Merely claiming its
            # future version must not turn prose or registry access into an adapter.
            status, reason = "unavailable", "machine_readable_recall_not_implemented"
        raw_candidates = value.get("candidates", [])
        if not isinstance(raw_candidates, list):
            raise ValueError("adapter candidates must be an array")
        if status not in {"available", "partial"} and raw_candidates:
            raise ValueError("only an available or partial adapter may return candidates")
        candidates: list[Candidate] = []
        rejected: dict[str, int] = {}
        for candidate in raw_candidates:
            normalized, exclusion = self._normalize_candidate(
                candidate, name, memory_type, status, request, now
            )
            if normalized:
                candidates.append(normalized)
            else:
                rejected[exclusion] = rejected.get(exclusion, 0) + 1
        if status == "available" and not candidates and not raw_candidates:
            status = "empty"
        return (
            {"name": name, "memoryType": memory_type, "status": status, "reason": reason},
            candidates,
            rejected,
        )

    def _normalize_candidate(
        self,
        value: Any,
        adapter_name: str,
        memory_type: str,
        adapter_status: str,
        request: dict[str, Any],
        now: datetime,
    ) -> tuple[Candidate | None, str]:
        if not isinstance(value, dict):
            raise ValueError("candidate must be an object")
        allowed = {
            "sourceSystem", "sourceId", "sourceRevision", "tenant", "project", "task",
            "sensitivity", "validFrom", "validUntil", "recordedAt", "extractionVersion",
            "trustClass", "confidence", "retentionClass", "provenance", "contentRole",
            "relevance", "claimKey", "supersedes", "content",
        }
        _strict_keys(value, allowed, "candidate")
        source_system = _safe_id(value.get("sourceSystem"), "sourceSystem")
        if re.search(r"transcript|conversation-log|private-history", source_system, re.IGNORECASE):
            raise ValueError("private transcript sources are not supported adapters")
        if (adapter_name == "graph-memory") != (source_system == "graphify-neo4j"):
            raise ValueError("graph-memory candidates require the governed graph source domain")
        source_id = _safe_id(value.get("sourceId"), "sourceId")
        source_revision = _safe_id(value.get("sourceRevision"), "sourceRevision")
        tenant = _safe_id(value.get("tenant"), "candidate tenant")
        project = _safe_id(value.get("project"), "candidate project")
        task = value.get("task")
        if task is not None:
            task = _safe_id(task, "candidate task")
        if tenant != request["tenant"] or project != request["project"]:
            return None, "scope_denied"
        if task is not None and task != request["task"]:
            return None, "scope_denied"
        sensitivity = value.get("sensitivity", "internal")
        if sensitivity not in SENSITIVITY_ORDER:
            raise ValueError("candidate sensitivity is invalid")
        maximum_allowed = max(SENSITIVITY_ORDER[item] for item in request["allowedSensitivity"])
        if SENSITIVITY_ORDER[sensitivity] > maximum_allowed:
            return None, "acl_denied"
        valid_from = value.get("validFrom")
        valid_until = value.get("validUntil")
        recorded_at = value.get("recordedAt")
        for timestamp in (valid_from, valid_until, recorded_at):
            if timestamp is not None:
                parse_time(timestamp)
        if valid_from is not None and parse_time(valid_from) > now:
            return None, "not_yet_valid"
        if valid_until is not None and parse_time(valid_until) <= now:
            return None, "expired"
        trust = value.get("trustClass", "unverified")
        if trust not in TRUST_ORDER:
            raise ValueError("candidate trustClass is invalid")
        confidence = value.get("confidence")
        if confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
            raise ValueError("candidate confidence is invalid")
        retention = value.get("retentionClass", "project")
        if retention not in {"transient", "session", "project", "durable"}:
            raise ValueError("candidate retentionClass is invalid")
        relevance = value.get("relevance", 0.0)
        if not isinstance(relevance, (int, float)) or not 0 <= relevance <= 1:
            raise ValueError("candidate relevance is invalid")
        content = value.get("content")
        if not isinstance(content, str) or not content:
            raise ValueError("candidate content must be non-empty")
        content_role = value.get("contentRole", "data")
        if content_role not in CONTENT_ROLES:
            raise ValueError("candidate contentRole is invalid")
        authority = _authority(memory_type, source_system, content_role, trust)
        source_hash = sha256(source_id)
        content_hash = sha256(content)
        memory_id = sha256(f"{adapter_name}:{source_id}:{source_revision}:{content_hash}")
        claim_key = value.get("claimKey")
        if claim_key is not None and not isinstance(claim_key, str):
            raise ValueError("claimKey must be a string")
        provenance = value.get("provenance", [])
        supersedes = value.get("supersedes", [])
        if not isinstance(provenance, list) or not all(isinstance(item, str) for item in provenance):
            raise ValueError("candidate provenance must be an array of identifiers")
        if not isinstance(supersedes, list) or not all(isinstance(item, str) for item in supersedes):
            raise ValueError("candidate supersedes must be an array of identifiers")
        payload_ref = f"payload-{content_hash[:32]}"
        envelope = {
            "schemaVersion": 1,
            "memoryId": memory_id,
            "memoryType": memory_type,
            "sourceSystem": source_system,
            "sourceIdHash": source_hash,
            "sourceRevision": source_revision,
            "scope": {
                "tenantHash": _scope_hash(tenant),
                "projectHash": _scope_hash(project),
                "taskHash": _scope_hash(task),
            },
            "sensitivity": sensitivity,
            "validFrom": valid_from,
            "validUntil": valid_until,
            "recordedAt": recorded_at,
            "extractionVersion": _safe_id(value.get("extractionVersion", "explicit-v1"), "extractionVersion"),
            "trustClass": trust,
            "confidence": confidence,
            "retentionClass": retention,
            "provenanceHashes": [sha256(item) for item in provenance],
            "contentRole": content_role,
            "authorityClass": authority,
            "processingPolicy": "reference-only" if memory_type == "procedural" else "inert",
            "scopeDecision": "allowed",
            "adapterStatus": adapter_status,
            "contentHash": content_hash,
            "payloadRef": payload_ref,
            "relevance": float(relevance),
            "claimKeyHash": sha256(claim_key) if claim_key else None,
            "supersedesHashes": [sha256(item) for item in supersedes],
        }
        return Candidate(envelope, content, max(1, (len(content.encode()) + 3) // 4)), ""

    def _select(
        self, candidates: list[Candidate], request: dict[str, Any]
    ) -> tuple[list[Candidate], dict[str, int]]:
        per_lane: dict[str, list[Candidate]] = {memory_type: [] for memory_type in MEMORY_TYPES}
        for item in candidates:
            per_lane[item.envelope["memoryType"]].append(item)
        eligible: dict[str, list[Candidate]] = {}
        exclusions: dict[str, int] = {}
        for memory_type, items in per_lane.items():
            ordered = sorted(items, key=_candidate_sort_key)
            budget = request["laneBudgets"][memory_type]
            lane: list[Candidate] = []
            used_tokens = 0
            for item in ordered:
                if len(lane) >= budget["maxItems"] or used_tokens + item.token_count > budget["maxTokens"]:
                    exclusions["lane_budget_exceeded"] = exclusions.get("lane_budget_exceeded", 0) + 1
                    continue
                lane.append(item)
                used_tokens += item.token_count
            eligible[memory_type] = lane
        selected: list[Candidate] = []
        total_tokens = 0
        cursor = 0
        while True:
            progressed = False
            for memory_type in MEMORY_TYPES:
                lane = eligible[memory_type]
                if cursor >= len(lane):
                    continue
                progressed = True
                item = lane[cursor]
                if total_tokens + item.token_count <= request["totalTokenBudget"]:
                    selected.append(item)
                    total_tokens += item.token_count
                else:
                    exclusions["total_budget_exceeded"] = exclusions.get("total_budget_exceeded", 0) + 1
            if not progressed:
                break
            cursor += 1
        return selected, exclusions

    def _conflicts(self, selected: Iterable[Candidate]) -> dict[str, str]:
        by_claim: dict[str, list[Candidate]] = {}
        for item in selected:
            claim = item.envelope["claimKeyHash"]
            if claim:
                by_claim.setdefault(claim, []).append(item)
        conflicts: dict[str, str] = {}
        for claim, items in by_claim.items():
            if len({item.envelope["contentHash"] for item in items}) <= 1:
                continue
            group = sha256(f"conflict:{claim}")
            for item in items:
                conflicts[item.envelope["memoryId"]] = group
        return conflicts


def _authority(memory_type: str, source_system: str, content_role: str, trust: str) -> str:
    if memory_type == "procedural":
        return "derived"
    if memory_type == "working" and source_system == "host-current-context":
        return "current-session"
    if source_system in {"canonical-state", "canonical-file", "obsidian"}:
        if trust not in {"verified", "operator-approved"}:
            return "untrusted"
        if content_role == "policy-reference" and trust == "operator-approved":
            return "canonical-policy"
        if content_role == "decision-summary" and trust == "operator-approved":
            return "human-decision"
        return "verified-fact"
    if source_system == "graphify-neo4j":
        return "derived"
    if memory_type == "episodic":
        return "derived"
    return "untrusted"


def _candidate_sort_key(item: Candidate) -> tuple[Any, ...]:
    envelope = item.envelope
    recorded = (
        -parse_time(envelope["recordedAt"]).timestamp()
        if envelope["recordedAt"]
        else float("inf")
    )
    return (
        AUTHORITY_ORDER[envelope["authorityClass"]],
        TRUST_ORDER[envelope["trustClass"]],
        -envelope["relevance"],
        recorded,
        envelope["sourceSystem"],
        envelope["memoryId"],
    )


def validate_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "schemaVersion", "packId", "createdAt", "expiresAt", "requestHash", "tenantHash",
        "projectHash", "taskHash", "adapterStatuses", "candidates", "exclusionReasonCounts",
        "exclusionReasonKindsTruncated", "totalEstimatedTokens", "payloadHash", "policy", "warnings",
    }
    if set(manifest) != required or manifest.get("schemaVersion") != 1:
        raise ValueError("memory context manifest has an invalid shape")
    if not re.fullmatch(r"memory-[a-f0-9]{32}", str(manifest["packId"])):
        raise ValueError("memory context packId is invalid")
    identity = {key: value for key, value in manifest.items() if key != "packId"}
    expected_pack_id = (
        f"memory-{sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')))[:32]}"
    )
    if manifest["packId"] != expected_pack_id:
        raise ValueError("memory context packId does not match its manifest")
    for key in ("requestHash", "tenantHash", "projectHash", "payloadHash"):
        if not re.fullmatch(r"[a-f0-9]{64}", str(manifest[key])):
            raise ValueError(f"memory context {key} is invalid")
    task_hash = manifest["taskHash"]
    if task_hash is not None and not re.fullmatch(r"[a-f0-9]{64}", str(task_hash)):
        raise ValueError("memory context taskHash is invalid")
    parse_time(manifest["createdAt"])
    parse_time(manifest["expiresAt"])
    if manifest["policy"] != {
        "version": "memory-context-ranking-v1", "automaticInjection": False, "writeBack": False
    }:
        raise ValueError("memory context policy is invalid")
    candidate_keys = {
        "schemaVersion", "memoryId", "memoryType", "sourceSystem", "sourceIdHash",
        "sourceRevision", "scope", "sensitivity", "validFrom", "validUntil",
        "recordedAt", "extractionVersion", "trustClass", "confidence",
        "retentionClass", "provenanceHashes", "contentRole", "authorityClass",
        "processingPolicy", "scopeDecision", "adapterStatus", "contentHash",
        "payloadRef", "relevance", "claimKeyHash", "supersedesHashes", "rank",
        "estimatedTokens", "conflictGroupHash",
    }
    if not isinstance(manifest["candidates"], list):
        raise ValueError("memory context candidates are invalid")
    for candidate in manifest["candidates"]:
        if not isinstance(candidate, dict) or set(candidate) != candidate_keys:
            raise ValueError("memory context candidate has an invalid shape")
        if candidate["schemaVersion"] != 1 or candidate["memoryType"] not in MEMORY_TYPES:
            raise ValueError("memory context candidate type is invalid")
        for key in ("memoryId", "sourceIdHash", "contentHash"):
            if not re.fullmatch(r"[a-f0-9]{64}", str(candidate[key])):
                raise ValueError(f"memory context candidate {key} is invalid")
        if not re.fullmatch(r"payload-[a-f0-9]{32}", str(candidate["payloadRef"])):
            raise ValueError("memory context candidate payloadRef is invalid")
        if candidate["payloadRef"] != f"payload-{candidate['contentHash'][:32]}":
            raise ValueError("memory context candidate payload binding is invalid")
        scope = candidate["scope"]
        if not isinstance(scope, dict) or set(scope) != {"tenantHash", "projectHash", "taskHash"}:
            raise ValueError("memory context candidate scope is invalid")
        for key in ("tenantHash", "projectHash"):
            if not re.fullmatch(r"[a-f0-9]{64}", str(scope[key])):
                raise ValueError("memory context candidate scope hash is invalid")
        if scope["taskHash"] is not None and not re.fullmatch(r"[a-f0-9]{64}", str(scope["taskHash"])):
            raise ValueError("memory context candidate task scope is invalid")
        if (
            scope["tenantHash"] != manifest["tenantHash"]
            or scope["projectHash"] != manifest["projectHash"]
            or scope["taskHash"] not in {None, manifest["taskHash"]}
        ):
            raise ValueError("memory context candidate scope does not match the pack")
        if candidate["sensitivity"] not in SENSITIVITY_ORDER:
            raise ValueError("memory context candidate sensitivity is invalid")
        if candidate["trustClass"] not in TRUST_ORDER or candidate["authorityClass"] not in AUTHORITY_ORDER:
            raise ValueError("memory context candidate trust or authority is invalid")
        if candidate["contentRole"] not in CONTENT_ROLES:
            raise ValueError("memory context candidate content role is invalid")
        if candidate["adapterStatus"] not in {"available", "partial"}:
            raise ValueError("memory context candidate adapter status is invalid")
        if candidate["processingPolicy"] not in {"inert", "reference-only"} or candidate["scopeDecision"] != "allowed":
            raise ValueError("memory context candidate processing policy is invalid")
        for key in ("provenanceHashes", "supersedesHashes"):
            if not isinstance(candidate[key], list) or any(
                not re.fullmatch(r"[a-f0-9]{64}", str(value)) for value in candidate[key]
            ):
                raise ValueError(f"memory context candidate {key} is invalid")
    serialized = json.dumps(manifest, sort_keys=True)
    if re.search(r"(?:^|[\" ])/(?:Users|home|private|tmp)/", serialized):
        raise ValueError("memory context manifest contains an absolute path")


class MemoryStore:
    """Exact-target private pack persistence and source revocation."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve(strict=False)
        self.packs = self.root / "memory-packs"
        self.index_path = self.root / "memory-revocations-v1.json"
        self.lock_path = self.root / "memory-context.lock"

    @contextmanager
    def _locked(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def write(self, manifest: dict[str, Any], payload: dict[str, Any]) -> tuple[Path, Path]:
        validate_manifest(manifest)
        if self.packs.is_symlink():
            raise ValueError("memory pack directory cannot be a symlink")
        self.packs.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.packs, 0o700)
        pack_id = manifest["packId"]
        manifest_path = self.packs / f"{pack_id}.json"
        payload_path = self.packs / f"{pack_id}.payload.json"
        manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        payload_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        with self._locked():
            if manifest_path.exists() or payload_path.exists():
                if (
                    manifest_path.is_file()
                    and payload_path.is_file()
                    and not manifest_path.is_symlink()
                    and not payload_path.is_symlink()
                    and manifest_path.read_text() == manifest_text
                    and payload_path.read_text() == payload_text
                ):
                    self._index_pack(manifest)
                    return manifest_path, payload_path
                raise FileExistsError(f"memory pack id collides with different content: {pack_id}")
            _write_private(manifest_path, manifest_text)
            try:
                _write_private(payload_path, payload_text)
                self._index_pack(manifest)
            except Exception:
                manifest_path.unlink(missing_ok=True)
                payload_path.unlink(missing_ok=True)
                raise
        return manifest_path, payload_path

    def verify(
        self,
        manifest_path: Path,
        payload_path: Path,
        *,
        now: datetime | None = None,
        source_state: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        raw_manifest_path = manifest_path.expanduser()
        raw_payload_path = payload_path.expanduser()
        if (
            self.packs.is_symlink()
            or raw_manifest_path.is_symlink()
            or raw_payload_path.is_symlink()
        ):
            raise ValueError("memory pack artifacts cannot be symlinks")
        manifest_path = raw_manifest_path.resolve(strict=True)
        payload_path = raw_payload_path.resolve(strict=True)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        validate_manifest(manifest)
        expected_manifest = (self.packs / f"{manifest['packId']}.json").resolve(strict=False)
        expected_payload = (self.packs / f"{manifest['packId']}.payload.json").resolve(strict=False)
        if manifest_path != expected_manifest or payload_path != expected_payload:
            raise ValueError("memory pack artifact path does not match its packId")
        reasons = []
        if parse_time(manifest["expiresAt"]) <= (now or utc_now()):
            reasons.append("expired")
        if manifest_path.stat().st_mode & 0o777 != 0o600 or payload_path.stat().st_mode & 0o777 != 0o600:
            reasons.append("insecure_file_mode")
        digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        if digest != manifest["payloadHash"]:
            reasons.append("payload_hash_mismatch")
        expected_refs = {item["payloadRef"]: item["contentHash"] for item in manifest["candidates"]}
        if not isinstance(payload, dict) or set(payload) != {"schemaVersion", "payloads"} or payload.get("schemaVersion") != 1 or not isinstance(payload.get("payloads"), dict):
            reasons.append("payload_shape_invalid")
        elif set(payload["payloads"]) != set(expected_refs) or any(
            not isinstance(content, str) or sha256(content) != expected_refs[reference]
            for reference, content in payload["payloads"].items()
        ):
            reasons.append("payload_candidate_binding_mismatch")
        index = self._read_index()
        revoked = set(index["revokedSources"])
        if any(item["sourceIdHash"] in revoked for item in manifest["candidates"]):
            reasons.append("source_revoked")
        if source_state is None:
            reasons.append("source_state_required")
        else:
            current = {sha256(source_id): revision for source_id, revision in source_state.items()}
            for item in manifest["candidates"]:
                if current.get(item["sourceIdHash"]) != item["sourceRevision"]:
                    reasons.append("source_revision_changed")
                    break
        return {"valid": not reasons, "packId": manifest["packId"], "reasons": sorted(set(reasons))}

    def purge(self, source_id: str, now: datetime | None = None) -> dict[str, Any]:
        source_hash = sha256(_safe_id(source_id, "sourceId"))
        with self._locked():
            index = self._read_index()
            pack_ids = set(index["sourcePacks"].get(source_hash, []))
            if self.packs.is_dir():
                for manifest_path in sorted(self.packs.glob("memory-*.json")):
                    if manifest_path.name.endswith(".payload.json") or manifest_path.is_symlink():
                        continue
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    validate_manifest(manifest)
                    if manifest_path.name != f"{manifest['packId']}.json":
                        raise ValueError("memory pack filename does not match its packId")
                    if any(item["sourceIdHash"] == source_hash for item in manifest["candidates"]):
                        pack_ids.add(manifest["packId"])
            removed = []
            for pack_id in sorted(pack_ids):
                if not re.fullmatch(r"memory-[a-f0-9]{32}", pack_id):
                    raise ValueError("revocation index contains an invalid pack id")
                manifest_path = self.packs / f"{pack_id}.json"
                payload_path = self.packs / f"{pack_id}.payload.json"
                manifest_path.unlink(missing_ok=True)
                payload_path.unlink(missing_ok=True)
                removed.append(pack_id)
            index["revokedSources"][source_hash] = format_time(now or utc_now())
            index["sourcePacks"].pop(source_hash, None)
            for packs in index["sourcePacks"].values():
                packs[:] = [pack_id for pack_id in packs if pack_id not in removed]
            self._write_index(index)
        return {"sourceIdHash": source_hash, "invalidatedPackIds": removed, "rawSourceRetained": True}

    def cleanup_expired(self, now: datetime | None = None) -> dict[str, Any]:
        cutoff = now or utc_now()
        removed = []
        with self._locked():
            if self.packs.is_symlink():
                raise ValueError("memory pack directory cannot be a symlink")
            if not self.packs.is_dir():
                return {"removedPackIds": removed}
            index = self._read_index()
            for manifest_path in sorted(self.packs.glob("memory-*.json")):
                if manifest_path.name.endswith(".payload.json") or manifest_path.is_symlink():
                    continue
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                validate_manifest(manifest)
                pack_id = manifest["packId"]
                if manifest_path.name != f"{pack_id}.json":
                    raise ValueError("memory pack filename does not match its packId")
                if parse_time(manifest["expiresAt"]) > cutoff:
                    continue
                manifest_path.unlink()
                (self.packs / f"{pack_id}.payload.json").unlink(missing_ok=True)
                removed.append(pack_id)
            if removed:
                for packs in index["sourcePacks"].values():
                    packs[:] = [pack_id for pack_id in packs if pack_id not in removed]
                self._write_index(index)
        return {"removedPackIds": removed}

    def _index_pack(self, manifest: dict[str, Any]) -> None:
        index = self._read_index()
        pack_id = manifest["packId"]
        for item in manifest["candidates"]:
            source_hash = item["sourceIdHash"]
            if source_hash in index["revokedSources"]:
                raise ValueError("cannot write a pack containing a revoked source")
            packs = index["sourcePacks"].setdefault(source_hash, [])
            if pack_id not in packs:
                packs.append(pack_id)
                packs.sort()
        self._write_index(index)

    def _read_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"schemaVersion": 1, "sourcePacks": {}, "revokedSources": {}}
        value = json.loads(self.index_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) != {"schemaVersion", "sourcePacks", "revokedSources"}:
            raise ValueError("memory revocation index is invalid")
        return value

    def _write_index(self, index: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        _write_private_replace(self.index_path, json.dumps(index, indent=2, sort_keys=True) + "\n")


def default_memory_root() -> Path:
    override = os.environ.get("RHIZE_CONTEXT_HOME")
    if override:
        return Path(override).expanduser() / "memory-context"
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "rhize" / "context-manager" / "memory-context"


def _write_private(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, content.encode())
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _write_private_replace(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, content.encode())
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
