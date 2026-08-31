"""Read-only Graphify/Neo4j projection into explicit memory-context candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from graph_memory.contract import canonical_json, sha256_value
from graph_memory.store import InMemoryNeo4jAdapter, QueryBudget, StoreError

from .core import parse_time


GRAPH_ADAPTER_NAME = "graph-memory"
GRAPH_PROTOCOL_VERSION = "bounded-graph-memory-read-v1"
GRAPH_SOURCE_SYSTEM = "graphify-neo4j"
MAX_RESULTS = 20
MAX_DEPTH = 2
MAX_RUNTIME_MS = 250
_HASH = re.compile(r"^[a-f0-9]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PROVENANCE_REQUIRED = {
    "sourceId", "sourceRevision", "sourceRefHash", "artifactHash", "extractorVersion",
    "recordedAt",
}
_PROVENANCE_OPTIONAL = {
    "sourceLocation", "wrapperVersion", "buildCommit", "modelId", "promptHash",
}
_QUERY_RECORD_FIELDS = {
    "governedId", "recordType", "subtype", "trust", "properties", "provenance",
}


@dataclass(frozen=True)
class GraphSnapshot:
    """Privacy-safe binding for one accepted governed graph compilation."""

    tenant: str
    project: str
    namespace: str
    corpus_id: str
    tenant_key: str
    namespace_key: str
    corpus_key: str
    compilation_id: str
    source_revision: str
    artifact_hash: str
    ontology_checksum: str
    sensitivity: str
    principal_scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("tenant", self.tenant),
            ("project", self.project),
            ("namespace", self.namespace),
            ("corpus_id", self.corpus_id),
            ("source_revision", self.source_revision),
        ):
            _require_safe_id(value, label)
        for label, value in (
            ("tenant_key", self.tenant_key),
            ("namespace_key", self.namespace_key),
            ("corpus_key", self.corpus_key),
            ("compilation_id", self.compilation_id),
            ("artifact_hash", self.artifact_hash),
            ("ontology_checksum", self.ontology_checksum),
        ):
            _require_hash(value, label)
        if self.tenant_key != sha256_value(f"tenant:{self.tenant}"):
            raise ValueError("graph snapshot tenant binding is invalid")
        if self.namespace_key != sha256_value(f"namespace:{self.namespace}"):
            raise ValueError("graph snapshot namespace binding is invalid")
        if self.corpus_key != sha256_value(f"corpus:{self.corpus_id}"):
            raise ValueError("graph snapshot corpus binding is invalid")
        if self.sensitivity not in {"public", "internal", "confidential", "restricted"}:
            raise ValueError("graph snapshot sensitivity is invalid")
        if (
            not isinstance(self.principal_scopes, tuple)
            or not self.principal_scopes
            or len(self.principal_scopes) > 32
            or len(self.principal_scopes) != len(set(self.principal_scopes))
        ):
            raise ValueError("graph snapshot principal scopes must be a bounded unique tuple")
        for scope in self.principal_scopes:
            _require_safe_id(scope, "principal scope")


class GraphMemoryAdapter:
    """Query the governed fake store without exposing a write or raw-Cypher surface."""

    def __init__(self, store: InMemoryNeo4jAdapter | None) -> None:
        if store is not None and type(store) is not InMemoryNeo4jAdapter:
            raise TypeError("graph memory v1 accepts only the governed in-memory query contract")
        self._store = store

    def recall(
        self,
        request: Mapping[str, Any],
        snapshot: GraphSnapshot,
    ) -> dict[str, Any]:
        normalized = _validate_request(request)
        if self._store is None:
            return _result("unavailable", "graph_store_unavailable")
        if (
            normalized["tenant"] != snapshot.tenant
            or normalized["project"] != snapshot.project
            or normalized["namespace"] != snapshot.namespace
            or normalized["corpusId"] != snapshot.corpus_id
        ):
            return _result("unauthorized", "graph_scope_binding_mismatch")

        status = self._store.status()
        if (
            status.get("adapter") != "in-memory-neo4j-contract"
            or status.get("liveNeo4jEnabled") is not False
        ):
            return _result("unavailable", "unsupported_graph_store")
        if self._store.ontology.checksum != snapshot.ontology_checksum:
            return _result("stale", "graph_ontology_changed")
        current = self._store.current_compilation(
            snapshot.tenant_key, snapshot.namespace_key, snapshot.corpus_key
        )
        if current is None:
            return _result("stale", "graph_snapshot_missing")
        if current != snapshot.compilation_id:
            return _result("stale", "graph_revision_changed")

        try:
            response = self._store.query(
                "query_context",
                tenant_key=snapshot.tenant_key,
                namespace_key=snapshot.namespace_key,
                corpus_key=snapshot.corpus_key,
                principal_scopes=snapshot.principal_scopes,
                role=InMemoryNeo4jAdapter.QUERY_ROLE,
                budget=QueryBudget(
                    normalized["maxDepth"], normalized["maxResults"], normalized["runtimeMs"]
                ),
                query_text=normalized["query"],
            )
            records, truncated = _validate_response(response, normalized["maxResults"])
            candidates = [
                _candidate(record, normalized, snapshot)
                for record in records
            ]
        except (StoreError, TypeError, ValueError):
            return _result("error", "bounded_graph_query_failed")
        if any(candidate is None for candidate in candidates):
            return _result("stale", "graph_provenance_mismatch")
        accepted = [candidate for candidate in candidates if candidate is not None]
        if not accepted:
            return _result("empty", "no_authorized_graph_results")
        if truncated:
            return _result("partial", "graph_results_truncated", accepted)
        return _result("available", "bounded_graph_query_complete", accepted)


def _validate_request(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schemaVersion", "tenant", "project", "task", "namespace", "corpusId", "query",
        "maxResults", "maxDepth", "runtimeMs",
    }
    if not isinstance(value, dict) or set(value) != required or value.get("schemaVersion") != 1:
        raise ValueError("graph memory request has missing or unknown fields")
    for field in ("tenant", "project", "namespace", "corpusId"):
        _require_safe_id(value[field], field)
    task = value["task"]
    if task is not None:
        _require_safe_id(task, "task")
    query = value["query"]
    if not isinstance(query, str) or not query.strip() or len(query) > 512:
        raise ValueError("graph memory query must be bounded non-empty text")
    limits = (
        ("maxResults", 1, MAX_RESULTS),
        ("maxDepth", 0, MAX_DEPTH),
        ("runtimeMs", 1, MAX_RUNTIME_MS),
    )
    for field, minimum, maximum in limits:
        item = value[field]
        if isinstance(item, bool) or not isinstance(item, int) or not minimum <= item <= maximum:
            raise ValueError(f"graph memory {field} exceeds the adapter budget")
    return {**value, "query": query.strip()}


def _validate_response(value: Any, max_results: int) -> tuple[list[dict[str, Any]], bool]:
    if (
        not isinstance(value, dict)
        or set(value) != {"operation", "status", "truncated", "results"}
        or value.get("operation") != "query_context"
        or value.get("status") != "ok"
        or not isinstance(value.get("truncated"), bool)
        or not isinstance(value.get("results"), list)
        or len(value["results"]) > max_results
    ):
        raise ValueError("bounded graph response is invalid")
    seen: set[str] = set()
    records = []
    for record in value["results"]:
        if not isinstance(record, dict) or set(record) != _QUERY_RECORD_FIELDS:
            raise ValueError("bounded graph record is invalid")
        governed_id = record["governedId"]
        _require_hash(governed_id, "governedId")
        if governed_id in seen:
            raise ValueError("bounded graph response contains duplicate records")
        seen.add(governed_id)
        _require_safe_id(record["recordType"], "recordType")
        if record["subtype"] is not None:
            _require_safe_id(record["subtype"], "subtype")
        if record["trust"] not in {"high", "medium", "low", "unverified"}:
            raise ValueError("bounded graph record trust is invalid")
        if (
            not isinstance(record["properties"], dict)
            or len(canonical_json(record["properties"]).encode()) > 65_536
        ):
            raise ValueError("bounded graph record properties are invalid")
        _validate_provenance(record["provenance"])
        records.append(record)
    return records, value["truncated"]


def _validate_provenance(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or _PROVENANCE_REQUIRED - set(value)
        or set(value) - _PROVENANCE_REQUIRED - _PROVENANCE_OPTIONAL
    ):
        raise ValueError("bounded graph provenance is incomplete")
    for field in ("sourceId", "sourceRefHash", "artifactHash"):
        _require_hash(value[field], field)
    prompt_hash = value.get("promptHash")
    if prompt_hash is not None:
        _require_hash(prompt_hash, "promptHash")
    _require_safe_id(value["sourceRevision"], "sourceRevision")
    _require_safe_id(value["extractorVersion"], "extractorVersion")
    parse_time(value["recordedAt"])
    for field in ("wrapperVersion", "buildCommit", "modelId"):
        item = value.get(field)
        if item is not None and (not isinstance(item, str) or not item or len(item) > 256):
            raise ValueError(f"bounded graph provenance {field} is invalid")
    location = value.get("sourceLocation")
    if location is not None and (not isinstance(location, str) or len(location) > 512):
        raise ValueError("bounded graph sourceLocation is invalid")


def _candidate(
    record: Mapping[str, Any],
    request: Mapping[str, Any],
    snapshot: GraphSnapshot,
) -> dict[str, Any] | None:
    provenance = record["provenance"]
    if (
        provenance["sourceRevision"] != snapshot.source_revision
        or provenance["artifactHash"] != snapshot.artifact_hash
    ):
        return None
    content = canonical_json({
        "schemaVersion": 1,
        "kind": "governed-graph-record",
        "record": {
            "governedId": record["governedId"],
            "recordType": record["recordType"],
            "subtype": record["subtype"],
            "properties": record["properties"],
        },
        "provenance": provenance,
    })
    properties = record["properties"]
    valid_from = properties.get("validFrom") if record["recordType"] == "Event" else None
    valid_until = properties.get("validUntil") if record["recordType"] == "Event" else None
    claim_key = None
    if record["recordType"] == "Claim":
        predicate = properties.get("predicate")
        subject_id = properties.get("subjectId")
        if isinstance(predicate, str) and isinstance(subject_id, str):
            claim_key = f"graph-claim:{subject_id}:{predicate}"
    return {
        "sourceSystem": GRAPH_SOURCE_SYSTEM,
        "sourceId": record["governedId"],
        "sourceRevision": snapshot.source_revision,
        "tenant": request["tenant"],
        "project": request["project"],
        "task": request["task"],
        "sensitivity": snapshot.sensitivity,
        "validFrom": valid_from,
        "validUntil": valid_until,
        "recordedAt": provenance["recordedAt"],
        "extractionVersion": provenance["extractorVersion"],
        "trustClass": {
            "high": "verified",
            "medium": "observed",
            "low": "unverified",
            "unverified": "unverified",
        }[record["trust"]],
        "confidence": None,
        "retentionClass": "durable",
        "provenance": _provenance_tokens(record, snapshot),
        "contentRole": "evidence" if record["recordType"] == "Claim" else "data",
        "relevance": 0.0,
        "claimKey": claim_key,
        "supersedes": [],
        "content": content,
    }


def _provenance_tokens(record: Mapping[str, Any], snapshot: GraphSnapshot) -> list[str]:
    tokens = [
        f"graph-record:{record['governedId']}",
        f"graph-compilation:{snapshot.compilation_id}",
        f"graph-ontology:{snapshot.ontology_checksum}",
    ]
    tokens.extend(
        f"graph-provenance:{key}:{canonical_json(value)}"
        for key, value in sorted(record["provenance"].items())
    )
    return tokens


def _result(status: str, reason: str, candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "name": GRAPH_ADAPTER_NAME,
        "memoryType": "semantic",
        "status": status,
        "reason": reason,
        "protocolVersion": GRAPH_PROTOCOL_VERSION,
        "candidates": candidates or [],
    }


def _require_safe_id(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(f"graph memory {label} must be a safe identifier")


def _require_hash(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError(f"graph memory {label} must be a sha256 hash")
