"""Transactional fake Neo4j adapter used for governed contract verification.

The adapter models migration, staging, publication, bounded reads, purge, and restore
without importing a driver or opening a network connection. A live adapter is an RT-159
follow-up and must implement this behavior before it can be enabled.
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .contract import (
    ADAPTER_VERSION,
    CompiledOntology,
    ContractError,
    canonical_json,
    sha256_value,
    validate_compilation,
    validate_receipt,
)


class StoreError(RuntimeError):
    """Raised when authority, optimistic concurrency, or store state is invalid."""


@dataclass(frozen=True)
class QueryBudget:
    depth: int = 1
    results: int = 20
    runtime_ms: int = 250


@dataclass
class _StoredCompilation:
    compilation: dict[str, Any]
    status: str
    run_id: str


class InMemoryNeo4jAdapter:
    """A deterministic stage-and-publish implementation with Neo4j-shaped semantics."""

    MIGRATION_ROLE = "migration_admin"
    INGEST_ROLE = "ingest"
    QUERY_ROLE = "query"
    REVIEW_ROLE = "review"

    def __init__(self, ontology: CompiledOntology) -> None:
        self.ontology = ontology
        self._lock = threading.RLock()
        self._migrations: dict[str, str] = {}
        self._compilations: dict[str, _StoredCompilation] = {}
        self._accepted: dict[tuple[str, str, str], str] = {}
        self._receipts: dict[str, dict[str, Any]] = {}
        self._run_compilations: dict[str, str] = {}

    def apply_migrations(
        self,
        *,
        role: str,
        failure_at: str | None = None,
    ) -> list[dict[str, str]]:
        self._require_role(role, self.MIGRATION_ROLE)
        applied: list[dict[str, str]] = []
        with self._lock:
            for migration in self.ontology.migrations:
                existing = self._migrations.get(migration.name)
                if existing is not None and existing != migration.checksum:
                    raise StoreError(f"migration checksum drift: {migration.name}")
                if existing is not None:
                    continue
                if failure_at == f"before_migration:{migration.name}":
                    raise StoreError(f"injected failure before migration {migration.name}")
                self._migrations[migration.name] = migration.checksum
                applied.append(migration.to_dict())
                if failure_at == f"after_migration:{migration.name}":
                    raise StoreError(f"injected failure after migration {migration.name}")
        return applied

    def stage(
        self,
        compilation: Mapping[str, Any],
        *,
        role: str,
        idempotency_key: str,
        failure_at: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(role, self.INGEST_ROLE)
        expected_migrations = {
            migration.name: migration.checksum for migration in self.ontology.migrations
        }
        if self._migrations != expected_migrations:
            raise StoreError("all checksummed migrations must be applied before ingest")
        if not idempotency_key or len(idempotency_key) > 256:
            raise StoreError("a bounded idempotency key is required")
        validate_compilation(compilation, self.ontology)
        if failure_at == "after_validation":
            raise StoreError("injected failure after validation")
        compilation_copy = copy.deepcopy(dict(compilation))
        compilation_id = compilation_copy["compilationId"]
        run_id = sha256_value(f"ingest:{idempotency_key}")

        with self._lock:
            prior_compilation = self._run_compilations.get(run_id)
            if prior_compilation is not None and prior_compilation != compilation_id:
                raise StoreError("idempotency key was already bound to another compilation")
            prior_receipt = self._receipts.get(run_id)
            if prior_receipt is not None:
                return copy.deepcopy(prior_receipt)
            existing = self._compilations.get(compilation_id)
            if existing is not None:
                if canonical_json(existing.compilation) != canonical_json(compilation_copy):
                    raise StoreError("compilation id collision with different content")
                if existing.status != "accepted":
                    raise StoreError("compilation is already bound to another ingest run")
                self._run_compilations[run_id] = compilation_id
                receipt = self._receipt(
                    compilation_copy,
                    run_id=run_id,
                    status="replayed",
                    current_compilation=compilation_id,
                )
                self._receipts[run_id] = receipt
                return copy.deepcopy(receipt)
            self._compilations[compilation_id] = _StoredCompilation(
                compilation=compilation_copy,
                status="staged",
                run_id=run_id,
            )
            self._run_compilations[run_id] = compilation_id
            receipt = self._receipt(compilation_copy, run_id=run_id, status="staged")
            self._receipts[run_id] = receipt
            if failure_at == "after_stage":
                raise StoreError("injected failure after stage")
            return copy.deepcopy(receipt)

    def publish(
        self,
        compilation_id: str,
        *,
        role: str,
        expected_current: str | None,
        failure_at: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(role, self.INGEST_ROLE)
        with self._lock:
            stored = self._compilations.get(compilation_id)
            if stored is None or stored.status not in {"staged", "accepted"}:
                raise StoreError("compilation is not staged for publication")
            key = self._partition_key(stored.compilation)
            current = self._accepted.get(key)
            if stored.status == "accepted" and current == compilation_id:
                return copy.deepcopy(self._receipts[stored.run_id])
            if current != expected_current:
                stored.status = "rejected"
                self._receipts[stored.run_id] = self._receipt(
                    stored.compilation,
                    run_id=stored.run_id,
                    status="rejected",
                    current_compilation=current,
                )
                raise StoreError("accepted compilation changed; optimistic publication rejected")
            if failure_at == "before_publish":
                raise StoreError("injected failure before atomic publication")

            if current is not None:
                previous = self._compilations[current]
                previous.status = "superseded"
                self._receipts[previous.run_id] = self._receipt(
                    previous.compilation,
                    run_id=previous.run_id,
                    status="superseded",
                    current_compilation=compilation_id,
                )
            stored.status = "accepted"
            self._accepted[key] = compilation_id
            receipt = self._receipt(
                stored.compilation,
                run_id=stored.run_id,
                status="accepted",
                current_compilation=compilation_id,
            )
            self._receipts[stored.run_id] = receipt
            return copy.deepcopy(receipt)

    def ingest(
        self,
        compilation: Mapping[str, Any],
        *,
        role: str,
        idempotency_key: str,
        expected_current: str | None,
        failure_at: str | None = None,
    ) -> dict[str, Any]:
        staged = self.stage(
            compilation,
            role=role,
            idempotency_key=idempotency_key,
            failure_at=failure_at if failure_at in {"after_validation", "after_stage"} else None,
        )
        if staged["status"] == "replayed":
            return staged
        return self.publish(
            compilation["compilationId"],
            role=role,
            expected_current=expected_current,
            failure_at=failure_at if failure_at == "before_publish" else None,
        )

    def query(
        self,
        operation: str,
        *,
        tenant_key: str,
        namespace_key: str,
        corpus_key: str,
        principal_scopes: Sequence[str],
        role: str,
        budget: QueryBudget = QueryBudget(),
        query_text: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(role, self.QUERY_ROLE, self.REVIEW_ROLE)
        self._validate_budget(budget)
        if not principal_scopes:
            raise StoreError("at least one principal scope is required")
        if operation not in {"query_context", "get_claim_sources", "get_related_artifacts"}:
            raise StoreError("unsupported bounded graph operation")
        started = time.monotonic()
        key = (tenant_key, namespace_key, corpus_key)
        with self._lock:
            compilation_id = self._accepted.get(key)
            if compilation_id is None:
                return self._empty_query(operation)
            compilation = copy.deepcopy(self._compilations[compilation_id].compilation)

        visible_records = {
            record["governedId"]: record
            for record in compilation["records"]
            if self._visible(record, principal_scopes)
        }
        visible_relationships = [
            relationship
            for relationship in compilation["relationships"]
            if self._visible(relationship, principal_scopes)
            and relationship["sourceId"] in visible_records
            and relationship["targetId"] in visible_records
        ]
        if operation == "query_context":
            if not query_text or len(query_text) > 512:
                raise StoreError("query_context requires bounded non-empty query_text")
            terms = {term.casefold() for term in query_text.split() if len(term) >= 2}
            records = [
                record for record in visible_records.values()
                if any(term in canonical_json(record["properties"]).casefold() for term in terms)
            ]
        elif operation == "get_claim_sources":
            if record_id is None:
                raise StoreError("get_claim_sources requires record_id")
            claim = visible_records.get(record_id)
            records = []
            if claim is not None and claim["recordType"] == "Claim":
                source_ids = {
                    edge["sourceId"]
                    for edge in visible_relationships
                    if edge["relationshipType"] == "ASSERTS" and edge["targetId"] == record_id
                }
                records = [visible_records[source_id] for source_id in source_ids]
        else:
            if record_id is None:
                raise StoreError("get_related_artifacts requires record_id")
            records = self._related_artifacts(
                record_id, visible_records, visible_relationships, budget.depth, started, budget.runtime_ms
            )

        if (time.monotonic() - started) * 1000 > budget.runtime_ms:
            raise StoreError("graph query exceeded runtime budget")
        records.sort(key=lambda item: item["governedId"])
        selected = records[: budget.results]
        return {
            "operation": operation,
            "status": "ok",
            "truncated": len(records) > len(selected),
            "results": [self._query_record(record) for record in selected],
        }

    def purge_source_revision(
        self,
        *,
        tenant_key: str,
        namespace_key: str,
        corpus_key: str,
        source_revision: str,
        role: str,
    ) -> list[dict[str, Any]]:
        self._require_role(role, self.INGEST_ROLE)
        receipts: list[dict[str, Any]] = []
        key = (tenant_key, namespace_key, corpus_key)
        with self._lock:
            for stored in self._compilations.values():
                compilation = stored.compilation
                if self._partition_key(compilation) != key or compilation["sourceRevision"] != source_revision:
                    continue
                stored.status = "purged"
                if self._accepted.get(key) == compilation["compilationId"]:
                    del self._accepted[key]
                receipt = self._receipt(
                    compilation, run_id=stored.run_id, status="purged", current_compilation=None
                )
                self._receipts[stored.run_id] = receipt
                receipts.append(copy.deepcopy(receipt))
        return receipts

    def backup(self, *, role: str) -> dict[str, Any]:
        self._require_role(role, self.MIGRATION_ROLE)
        with self._lock:
            payload = {
                "migrations": copy.deepcopy(self._migrations),
                "compilations": {
                    key: {
                        "compilation": copy.deepcopy(value.compilation),
                        "status": value.status,
                        "runId": value.run_id,
                    }
                    for key, value in self._compilations.items()
                },
                "accepted": {"|".join(key): value for key, value in self._accepted.items()},
                "receipts": copy.deepcopy(self._receipts),
                "runCompilations": copy.deepcopy(self._run_compilations),
            }
        return {"snapshotVersion": 1, "checksum": sha256_value(payload), "payload": payload}

    def restore(self, snapshot: Mapping[str, Any], *, role: str) -> None:
        self._require_role(role, self.MIGRATION_ROLE)
        if set(snapshot) != {"snapshotVersion", "checksum", "payload"} or snapshot["snapshotVersion"] != 1:
            raise StoreError("unsupported backup snapshot")
        payload = snapshot["payload"]
        if snapshot["checksum"] != sha256_value(payload):
            raise StoreError("backup checksum mismatch")
        if not isinstance(payload, dict) or set(payload) != {
            "migrations", "compilations", "accepted", "receipts", "runCompilations"
        }:
            raise StoreError("backup payload has missing or unknown fields")
        expected_migrations = {
            migration.name: migration.checksum for migration in self.ontology.migrations
        }
        if payload["migrations"] != expected_migrations:
            raise StoreError("backup migration ledger does not match this ontology")
        if not all(isinstance(value, dict) for value in (
            payload["compilations"], payload["accepted"], payload["receipts"], payload["runCompilations"]
        )):
            raise StoreError("backup payload collections must be objects")
        for compilation_id, value in payload["compilations"].items():
            if (
                not isinstance(value, dict)
                or set(value) != {"compilation", "status", "runId"}
                or value["status"] not in {"staged", "accepted", "rejected", "superseded", "purged"}
                or compilation_id != value["compilation"].get("compilationId")
            ):
                raise StoreError("backup compilation entry is invalid")
            try:
                validate_compilation(value["compilation"], self.ontology)
            except ContractError as exc:
                raise StoreError(f"backup compilation contract failed: {exc}") from exc
        expected_accepted: dict[str, str] = {}
        for compilation_id, value in payload["compilations"].items():
            if value["status"] != "accepted":
                continue
            partition = "|".join(self._partition_key(value["compilation"]))
            if partition in expected_accepted:
                raise StoreError("backup has competing accepted compilations")
            expected_accepted[partition] = compilation_id
        if payload["accepted"] != expected_accepted:
            raise StoreError("backup accepted-compilation index is incomplete")
        for partition, compilation_id in payload["accepted"].items():
            if (
                not isinstance(partition, str)
                or len(partition.split("|")) != 3
                or compilation_id not in payload["compilations"]
                or payload["compilations"][compilation_id]["status"] != "accepted"
            ):
                raise StoreError("backup accepted-compilation index is invalid")
            compilation = payload["compilations"][compilation_id]["compilation"]
            if partition != "|".join(self._partition_key(compilation)):
                raise StoreError("backup accepted-compilation partition is invalid")
        if set(payload["receipts"]) != set(payload["runCompilations"]):
            raise StoreError("backup receipt and idempotency ledgers disagree")
        for run_id, compilation_id in payload["runCompilations"].items():
            value = payload["compilations"].get(compilation_id)
            receipt = payload["receipts"].get(run_id)
            if (
                value is None
                or not isinstance(receipt, dict)
                or receipt.get("runId") != run_id
            ):
                raise StoreError("backup run ledger is invalid")
            try:
                validate_receipt(receipt, self.ontology, value["compilation"])
            except ContractError as exc:
                raise StoreError(f"backup receipt contract failed: {exc}") from exc
        for compilation_id, value in payload["compilations"].items():
            if payload["runCompilations"].get(value["runId"]) != compilation_id:
                raise StoreError("backup compilation is missing its originating run")
            if payload["receipts"][value["runId"]]["status"] != value["status"]:
                raise StoreError("backup compilation status disagrees with its receipt")
        with self._lock:
            self._migrations = copy.deepcopy(payload["migrations"])
            self._compilations = {
                key: _StoredCompilation(
                    compilation=copy.deepcopy(value["compilation"]),
                    status=value["status"],
                    run_id=value["runId"],
                )
                for key, value in payload["compilations"].items()
            }
            self._accepted = {
                tuple(key.split("|", 2)): value for key, value in payload["accepted"].items()
            }
            self._receipts = copy.deepcopy(payload["receipts"])
            self._run_compilations = copy.deepcopy(payload["runCompilations"])

    def status(self) -> dict[str, Any]:
        with self._lock:
            statuses: dict[str, int] = {}
            for compilation in self._compilations.values():
                statuses[compilation.status] = statuses.get(compilation.status, 0) + 1
            return {
                "adapter": "in-memory-neo4j-contract",
                "adapterVersion": ADAPTER_VERSION,
                "liveNeo4jEnabled": False,
                "migrationCount": len(self._migrations),
                "compilationStatuses": dict(sorted(statuses.items())),
                "acceptedPartitions": len(self._accepted),
            }

    def compilation_status(self, compilation_id: str) -> str | None:
        with self._lock:
            stored = self._compilations.get(compilation_id)
            return stored.status if stored is not None else None

    def current_compilation(
        self,
        tenant_key: str,
        namespace_key: str,
        corpus_key: str,
    ) -> str | None:
        with self._lock:
            return self._accepted.get((tenant_key, namespace_key, corpus_key))

    def _receipt(
        self,
        compilation: Mapping[str, Any],
        *,
        run_id: str,
        status: str,
        current_compilation: str | None = None,
    ) -> dict[str, Any]:
        quarantined = sum(
            1 for item in [*compilation["records"], *compilation["relationships"]]
            if item["quarantined"]
        )
        receipt = {
            "receiptVersion": 1,
            "runId": run_id,
            "status": status,
            "tenantHash": compilation["tenantKey"],
            "namespaceHash": compilation["namespaceKey"],
            "sourceRevisionHash": sha256_value(compilation["sourceRevision"]),
            "compilationHash": compilation["compilationId"],
            "artifactHash": compilation["artifactHash"],
            "ontologyChecksum": compilation["ontologyChecksum"],
            "currentCompilationHash": current_compilation,
            "migrationChecksums": sorted(self._migrations.values()),
            "counts": {
                "records": len(compilation["records"]),
                "relationships": len(compilation["relationships"]),
                "rejections": len(compilation["rejections"]),
                "quarantined": quarantined,
            },
            "adapterVersion": ADAPTER_VERSION,
            "failureStage": None,
        }
        validate_receipt(receipt, self.ontology, compilation)
        return receipt

    def _validate_budget(self, budget: QueryBudget) -> None:
        limits = self.ontology.core["queryBudgets"]
        if not 0 <= budget.depth <= limits["maxDepth"]:
            raise StoreError("query depth exceeds ontology budget")
        if not 1 <= budget.results <= limits["maxResults"]:
            raise StoreError("query result limit exceeds ontology budget")
        if not 1 <= budget.runtime_ms <= limits["maxRuntimeMs"]:
            raise StoreError("query runtime exceeds ontology budget")

    @staticmethod
    def _visible(item: Mapping[str, Any], principal_scopes: Sequence[str]) -> bool:
        return (
            not item["quarantined"]
            and item["trust"] in {"high", "medium"}
            and bool(set(item["acl"]).intersection(principal_scopes))
        )

    @staticmethod
    def _related_artifacts(
        record_id: str,
        records: Mapping[str, Mapping[str, Any]],
        relationships: Sequence[Mapping[str, Any]],
        depth: int,
        started: float,
        runtime_ms: int,
    ) -> list[Mapping[str, Any]]:
        if record_id not in records:
            return []
        adjacency: dict[str, set[str]] = {}
        for relationship in relationships:
            adjacency.setdefault(relationship["sourceId"], set()).add(relationship["targetId"])
            adjacency.setdefault(relationship["targetId"], set()).add(relationship["sourceId"])
        visited = {record_id}
        frontier = {record_id}
        for _ in range(depth):
            if (time.monotonic() - started) * 1000 > runtime_ms:
                raise StoreError("graph query exceeded runtime budget")
            frontier = {
                neighbor
                for node_id in frontier
                for neighbor in adjacency.get(node_id, ())
                if neighbor not in visited
            }
            visited.update(frontier)
        return [records[node_id] for node_id in visited if records[node_id]["recordType"] == "Artifact"]

    @staticmethod
    def _query_record(record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "governedId": record["governedId"],
            "recordType": record["recordType"],
            "subtype": record["subtype"],
            "trust": record["trust"],
            "properties": copy.deepcopy(record["properties"]),
            "provenance": copy.deepcopy(record["provenance"]),
        }

    @staticmethod
    def _empty_query(operation: str) -> dict[str, Any]:
        return {"operation": operation, "status": "ok", "truncated": False, "results": []}

    @staticmethod
    def _partition_key(compilation: Mapping[str, Any]) -> tuple[str, str, str]:
        return (
            compilation["tenantKey"], compilation["namespaceKey"], compilation["corpusKey"]
        )

    @staticmethod
    def _require_role(role: str, *allowed: str) -> None:
        if role not in allowed:
            raise StoreError("role is not authorized for this operation")
