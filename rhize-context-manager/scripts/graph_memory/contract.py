"""Canonical ontology compiler and governed compilation validator.

This module deliberately has no Neo4j dependency. It generates checksummed migration
descriptions for an adapter to apply under a separately authorized migration role.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_VERSION = 1
ADAPTER_VERSION = "1.0.0"
MAX_JSON_BYTES = 128 * 1024 * 1024
MAX_COMPILATION_RECORDS = 400_000
MAX_COMPILATION_RELATIONSHIPS = 1_000_000
MAX_COMPILATION_REJECTIONS = 300_000
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SAFE_NAMESPACE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
SAFE_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
SAFE_RELATIONSHIP = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
RECEIPT_STATUSES = {
    "staged", "accepted", "replayed", "rejected", "failed", "superseded", "purged",
}


class ContractError(ValueError):
    """Raised when an ontology or governed compilation violates the contract."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_value(value: Any) -> str:
    payload = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ContractError(f"JSON contract exceeds the {MAX_JSON_BYTES}-byte limit: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON contract {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"JSON contract must be an object: {path}")
    return value


def default_catalog_path() -> Path:
    return Path(__file__).resolve().parents[2] / "catalog" / "graph-ontology" / "core-v1.json"


@dataclass(frozen=True)
class Migration:
    name: str
    statement: str
    checksum: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "statement": self.statement, "checksum": self.checksum}


@dataclass(frozen=True)
class CompiledOntology:
    core: Mapping[str, Any]
    packs: tuple[Mapping[str, Any], ...]
    checksum: str
    migrations: tuple[Migration, ...]
    node_types: frozenset[str]
    subtypes: Mapping[str, str]
    relationship_types: frozenset[str]
    relationship_contracts: Mapping[str, Mapping[str, Any]]

    def writer_contract(self) -> dict[str, Any]:
        return {
            "contractVersion": CONTRACT_VERSION,
            "ontologyVersion": self.core["ontologyVersion"],
            "ontologyChecksum": self.checksum,
            "nodeTypes": sorted(self.node_types),
            "subtypes": dict(sorted(self.subtypes.items())),
            "relationshipTypes": sorted(self.relationship_types),
        }

    def reader_contract(self) -> dict[str, Any]:
        return {
            **self.writer_contract(),
            "operations": ["get_claim_sources", "get_related_artifacts", "query_context"],
            "budgets": self.core["queryBudgets"],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "writer": self.writer_contract(),
            "reader": self.reader_contract(),
            "migrations": [migration.to_dict() for migration in self.migrations],
            "packs": [
                {"namespace": pack["namespace"], "packVersion": pack["packVersion"]}
                for pack in self.packs
            ],
        }


class OntologyCompiler:
    """Validate one core vocabulary and namespaced extension packs."""

    def compile(
        self,
        core: Mapping[str, Any],
        packs: Iterable[Mapping[str, Any]] = (),
    ) -> CompiledOntology:
        self._validate_core(core)
        ordered_packs = tuple(sorted((dict(pack) for pack in packs), key=lambda item: item["namespace"]))
        node_types = frozenset(core["nodeTypes"])
        relationships = set(core["relationshipTypes"])
        relationship_contracts: dict[str, dict[str, Any]] = {
            name: {**dict(contract), "extension": False}
            for name, contract in core["relationshipTypes"].items()
        }
        subtypes: dict[str, str] = {}
        namespaces: set[str] = {str(core["namespace"])}

        for pack in ordered_packs:
            namespace = self._validate_pack(pack, core, node_types, subtypes, relationships)
            if namespace in namespaces:
                raise ContractError(f"duplicate ontology namespace: {namespace}")
            namespaces.add(namespace)
            for subtype in pack["nodeSubtypes"]:
                qualified = f"{namespace}:{subtype['name']}"
                if qualified in subtypes:
                    raise ContractError(f"duplicate extension subtype: {qualified}")
                subtypes[qualified] = subtype["parent"]
            local_subtypes = {item["name"] for item in pack["nodeSubtypes"]}
            for relationship in pack["relationshipTypes"]:
                name = relationship["name"]
                relationships.add(name)
                relationship_contracts[name] = {
                    "sources": [_qualify_endpoint(relationship["source"], namespace, local_subtypes)],
                    "targets": [_qualify_endpoint(relationship["target"], namespace, local_subtypes)],
                    "extension": True,
                }

        source = {"core": core, "packs": ordered_packs}
        checksum = sha256_value(source)
        migrations = self._compile_migrations(checksum, relationships)
        return CompiledOntology(
            core=dict(core),
            packs=ordered_packs,
            checksum=checksum,
            migrations=migrations,
            node_types=node_types,
            subtypes=subtypes,
            relationship_types=frozenset(relationships),
            relationship_contracts=relationship_contracts,
        )

    @staticmethod
    def _validate_core(core: Mapping[str, Any]) -> None:
        required = {
            "schemaVersion",
            "ontologyVersion",
            "namespace",
            "nodeTypes",
            "relationshipTypes",
            "graphify",
            "trustPolicy",
            "queryBudgets",
        }
        missing = required - set(core)
        unknown = set(core) - required - {"description"}
        if missing or unknown:
            raise ContractError(
                f"core ontology fields missing={sorted(missing)} unknown={sorted(unknown)}"
            )
        if core["schemaVersion"] != 1 or core["namespace"] != "rhize.core":
            raise ContractError("core ontology must be schema v1 in rhize.core")
        if (
            not isinstance(core["ontologyVersion"], str)
            or not re.fullmatch(r"\d+\.\d+\.\d+", core["ontologyVersion"])
        ):
            raise ContractError("core ontologyVersion must be semantic version text")
        if not isinstance(core["nodeTypes"], dict) or not core["nodeTypes"]:
            raise ContractError("core nodeTypes must be a non-empty object")
        if not isinstance(core["relationshipTypes"], dict) or not core["relationshipTypes"]:
            raise ContractError("core relationshipTypes must be a non-empty object")
        for name, contract in core["nodeTypes"].items():
            if not SAFE_TYPE.fullmatch(name) or not isinstance(contract, dict):
                raise ContractError(f"invalid core node type: {name!r}")
            if set(contract) != {"identityEligible", "requiredProperties", "allowedProperties"}:
                raise ContractError(f"node type {name} has missing or unknown fields")
            if not isinstance(contract["identityEligible"], bool):
                raise ContractError(f"node type {name} identityEligible must be boolean")
            required_properties = contract.get("requiredProperties")
            allowed_properties = contract.get("allowedProperties")
            if not isinstance(required_properties, list) or not isinstance(allowed_properties, list):
                raise ContractError(f"node type {name} needs requiredProperties and allowedProperties")
            if not _valid_unique_strings(required_properties) or not _valid_unique_strings(allowed_properties):
                raise ContractError(f"node type {name} property declarations are invalid")
            if not set(required_properties).issubset(allowed_properties):
                raise ContractError(f"node type {name} requires a property it does not allow")
            if not all(SAFE_TYPE.fullmatch(value) for value in allowed_properties):
                raise ContractError(f"node type {name} property declarations are invalid")
        for name, contract in core["relationshipTypes"].items():
            if not SAFE_RELATIONSHIP.fullmatch(name) or not isinstance(contract, dict):
                raise ContractError(f"invalid core relationship type: {name!r}")
            if set(contract) - {"sources", "targets", "requiresSemanticType"} or not {
                "sources", "targets"
            }.issubset(contract):
                raise ContractError(f"relationship {name} has missing or unknown fields")
            if not isinstance(contract["sources"], list) or not _valid_unique_strings(contract["sources"]):
                raise ContractError(f"relationship {name} needs at least one source type")
            if not isinstance(contract["targets"], list) or not _valid_unique_strings(contract["targets"]):
                raise ContractError(f"relationship {name} needs at least one target type")
            if "requiresSemanticType" in contract and not isinstance(
                contract["requiresSemanticType"], bool
            ):
                raise ContractError(f"relationship {name} requiresSemanticType must be boolean")
            if not set(contract["sources"]).issubset(core["nodeTypes"]):
                raise ContractError(f"relationship {name} has an unknown source type")
            if not set(contract["targets"]).issubset(core["nodeTypes"]):
                raise ContractError(f"relationship {name} has an unknown target type")
        graphify = core["graphify"]
        if not isinstance(graphify, dict) or set(graphify) != {
            "allowedFileTypes", "allowedConfidenceClasses", "allowedNodeFields",
            "allowedEdgeFields", "allowedHyperedgeFields",
        }:
            raise ContractError("core graphify contract has missing or unknown fields")
        if any(
            not isinstance(values, list)
            or not values
            or not _valid_unique_strings(values)
            for values in graphify.values()
        ):
            raise ContractError("core graphify allowlists must be non-empty arrays")
        trust_policy = core["trustPolicy"]
        if not isinstance(trust_policy, dict) or set(trust_policy) != {
            "levels", "graphifyCeilings", "normalQueryMinimum", "identityMinimum",
        }:
            raise ContractError("core trustPolicy has missing or unknown fields")
        trust_levels = trust_policy["levels"]
        if trust_levels != ["high", "medium", "low", "unverified"]:
            raise ContractError("core trust levels must use the governed order")
        if (
            not isinstance(trust_policy["graphifyCeilings"], dict)
            or set(trust_policy["graphifyCeilings"]) != set(graphify["allowedConfidenceClasses"])
            or not all(
                isinstance(value, str)
                for value in trust_policy["graphifyCeilings"].values()
            )
            or not set(trust_policy["graphifyCeilings"].values()).issubset(trust_levels)
            or trust_policy["normalQueryMinimum"] not in trust_levels
            or trust_policy["identityMinimum"] not in trust_levels
        ):
            raise ContractError("core trust ceilings and query thresholds are invalid")
        budgets = core["queryBudgets"]
        if (
            not isinstance(budgets, dict)
            or set(budgets) != {"maxDepth", "maxResults", "maxRuntimeMs"}
            or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in budgets.values())
            or budgets["maxDepth"] > 10
            or budgets["maxResults"] > 1000
            or budgets["maxRuntimeMs"] > 60_000
        ):
            raise ContractError("core queryBudgets must be positive bounded integers")

    @staticmethod
    def _validate_pack(
        pack: Mapping[str, Any],
        core: Mapping[str, Any],
        node_types: frozenset[str],
        existing_subtypes: Mapping[str, str],
        existing_relationships: set[str],
    ) -> str:
        required = {
            "schemaVersion",
            "packVersion",
            "namespace",
            "extendsCoreVersion",
            "nodeSubtypes",
            "relationshipTypes",
        }
        missing = required - set(pack)
        unknown = set(pack) - required - {"description"}
        if missing or unknown:
            raise ContractError(
                f"extension pack fields missing={sorted(missing)} unknown={sorted(unknown)}"
            )
        namespace = pack["namespace"]
        if not isinstance(namespace, str) or not SAFE_NAMESPACE.fullmatch(namespace):
            raise ContractError(f"invalid extension namespace: {namespace!r}")
        if namespace == core["namespace"] or not namespace.startswith("rhize."):
            raise ContractError("extension packs must use a non-core rhize.* namespace")
        if pack["schemaVersion"] != 1 or pack["extendsCoreVersion"] != core["ontologyVersion"]:
            raise ContractError(f"extension pack {namespace} targets the wrong core version")
        if (
            not isinstance(pack["packVersion"], str)
            or not re.fullmatch(r"\d+\.\d+\.\d+", pack["packVersion"])
            or not isinstance(pack["nodeSubtypes"], list)
            or not isinstance(pack["relationshipTypes"], list)
        ):
            raise ContractError(f"extension pack {namespace} has invalid version or collections")
        local_subtypes: set[str] = set()
        for subtype in pack["nodeSubtypes"]:
            if not isinstance(subtype, dict) or set(subtype) != {"name", "parent", "queryJustification"}:
                raise ContractError(f"invalid subtype declaration in {namespace}")
            name, parent = subtype["name"], subtype["parent"]
            if not SAFE_TYPE.fullmatch(name) or name in node_types or name in local_subtypes:
                raise ContractError(f"extension pack cannot redefine subtype {name!r}")
            if parent not in node_types:
                raise ContractError(f"subtype {name} has unknown parent {parent}")
            if not str(subtype["queryJustification"]).strip():
                raise ContractError(f"subtype {name} has no demonstrated query")
            local_subtypes.add(name)
        local_relationships: set[str] = set()
        allowed_endpoints = set(node_types) | local_subtypes | set(existing_subtypes)
        for relation in pack["relationshipTypes"]:
            if not isinstance(relation, dict) or set(relation) != {
                "name", "source", "target", "queryJustification"
            }:
                raise ContractError(f"invalid relationship declaration in {namespace}")
            name = relation["name"]
            if (
                not SAFE_RELATIONSHIP.fullmatch(name)
                or name in existing_relationships
                or name in local_relationships
            ):
                raise ContractError(f"extension pack cannot redefine relationship {name!r}")
            if relation["source"] not in allowed_endpoints or relation["target"] not in allowed_endpoints:
                raise ContractError(f"relationship {name} has an unknown endpoint")
            if not str(relation["queryJustification"]).strip():
                raise ContractError(f"relationship {name} has no demonstrated query")
            local_relationships.add(name)
        return namespace

    @staticmethod
    def _compile_migrations(
        ontology_checksum: str,
        relationships: Iterable[str],
    ) -> tuple[Migration, ...]:
        statements = [
            (
                "governed_identity_v1",
                "CREATE CONSTRAINT rhize_governed_identity_v1 IF NOT EXISTS "
                "FOR (n:RhizeGoverned) REQUIRE (n.tenantKey, n.namespaceKey, n.governedId) IS UNIQUE",
            ),
            (
                "compilation_identity_v1",
                "CREATE CONSTRAINT rhize_compilation_identity_v1 IF NOT EXISTS "
                "FOR (n:RhizeCompilation) REQUIRE (n.tenantKey, n.namespaceKey, n.compilationId) IS UNIQUE",
            ),
            (
                "accepted_compilation_lookup_v1",
                "CREATE INDEX rhize_accepted_compilation_v1 IF NOT EXISTS "
                "FOR (n:RhizeCompilation) ON (n.tenantKey, n.namespaceKey, n.corpusKey, n.status)",
            ),
            (
                "source_revision_lookup_v1",
                "CREATE INDEX rhize_source_revision_v1 IF NOT EXISTS "
                "FOR (n:RhizeGoverned) ON (n.tenantKey, n.namespaceKey, n.sourceRevision)",
            ),
            (
                "ontology_ledger_v1",
                "MERGE (m:RhizeMigration {ontologyChecksum: $ontologyChecksum}) "
                "ON CREATE SET m.relationshipTypes = $relationshipTypes",
            ),
        ]
        parameters = canonical_json(
            {"ontologyChecksum": ontology_checksum, "relationshipTypes": sorted(relationships)}
        )
        return tuple(
            Migration(name, statement, sha256_value(f"{statement}\n{parameters}"))
            for name, statement in statements
        )


def compile_ontology(
    core_path: Path | None = None,
    pack_paths: Sequence[Path] = (),
) -> CompiledOntology:
    core = load_json(core_path or default_catalog_path())
    packs = [load_json(path) for path in pack_paths]
    return OntologyCompiler().compile(core, packs)


def validate_compilation(compilation: Mapping[str, Any], ontology: CompiledOntology) -> None:
    """Validate the stricter invariants not expressible in the portable JSON schema."""

    required = {
        "contractVersion",
        "ontologyChecksum",
        "artifactHash",
        "manifestHash",
        "tenantKey",
        "namespaceKey",
        "corpusKey",
        "sourceRevision",
        "compilationId",
        "records",
        "relationships",
        "rejections",
    }
    unknown = set(compilation) - required
    missing = required - set(compilation)
    if missing or unknown:
        raise ContractError(f"compilation fields missing={sorted(missing)} unknown={sorted(unknown)}")
    if compilation["contractVersion"] != CONTRACT_VERSION:
        raise ContractError("unsupported graph compilation contractVersion")
    if compilation["ontologyChecksum"] != ontology.checksum:
        raise ContractError("ontology checksum mismatch")
    for field in (
        "ontologyChecksum", "artifactHash", "manifestHash", "tenantKey", "namespaceKey",
        "corpusKey", "compilationId",
    ):
        if not isinstance(compilation[field], str) or not HASH_PATTERN.fullmatch(compilation[field]):
            raise ContractError(f"{field} must be a sha256 hash")
    if (
        not isinstance(compilation["sourceRevision"], str)
        or not compilation["sourceRevision"]
        or len(compilation["sourceRevision"]) > 256
    ):
        raise ContractError("sourceRevision is required")
    if (
        not isinstance(compilation["records"], list)
        or not compilation["records"]
        or not isinstance(compilation["relationships"], list)
        or not isinstance(compilation["rejections"], list)
    ):
        raise ContractError("records and relationships must be arrays")
    if (
        len(compilation["records"]) > MAX_COMPILATION_RECORDS
        or len(compilation["relationships"]) > MAX_COMPILATION_RELATIONSHIPS
        or len(compilation["rejections"]) > MAX_COMPILATION_REJECTIONS
    ):
        raise ContractError("compilation exceeds the governed size budget")

    record_by_id: dict[str, Mapping[str, Any]] = {}
    for record in compilation["records"]:
        _validate_record(record, ontology)
        governed_id = record["governedId"]
        if governed_id in record_by_id:
            raise ContractError(f"duplicate governed record id: {governed_id}")
        record_by_id[governed_id] = record

    for record in record_by_id.values():
        provenance_source = record_by_id.get(record["provenance"]["sourceId"])
        if provenance_source is None or provenance_source["recordType"] != "Source":
            raise ContractError("record provenance must resolve to a Source in this compilation")
        if record["recordType"] == "Source" and record["provenance"]["sourceId"] != record["governedId"]:
            raise ContractError("Source provenance must be self-bound")
        if (
            record["recordType"] == "Source"
            and record["properties"]["sourceRevision"] != compilation["sourceRevision"]
        ):
            raise ContractError("Source revision does not match its compilation")
        if (
            record["provenance"]["artifactHash"] != compilation["artifactHash"]
            or record["provenance"]["sourceRevision"] != compilation["sourceRevision"]
            or record["recordedAt"] != record["provenance"]["recordedAt"]
        ):
            raise ContractError("record provenance does not match its compilation")
        if not set(record["acl"]).issubset(provenance_source["acl"]):
            raise ContractError("record ACL weakens its provenance Source")
        if _sensitivity_rank(record["sensitivity"]) < _sensitivity_rank(provenance_source["sensitivity"]):
            raise ContractError("record sensitivity weakens its provenance Source")
        if _trust_rank(record["trust"]) > _trust_rank(provenance_source["trust"]):
            raise ContractError("record trust cannot exceed its provenance Source")
        if record["provenance"]["sourceRefHash"] != provenance_source["properties"]["sourceRefHash"]:
            raise ContractError("record sourceRefHash does not match its provenance Source")
        if record["recordType"] == "Claim":
            properties = record["properties"]
            if properties["subjectId"] not in record_by_id or properties["objectId"] not in record_by_id:
                raise ContractError("Claim subject/object must resolve in this compilation")
            if any(
                participant not in record_by_id for participant in properties.get("participants", [])
            ):
                raise ContractError("Claim participants must resolve in this compilation")

    relationship_ids: set[str] = set()
    for relationship in compilation["relationships"]:
        _validate_relationship(relationship, ontology, record_by_id)
        governed_id = relationship["governedId"]
        if governed_id in relationship_ids:
            raise ContractError(f"duplicate governed relationship id: {governed_id}")
        relationship_ids.add(governed_id)

    for relationship in compilation["relationships"]:
        provenance_source = record_by_id.get(relationship["provenance"]["sourceId"])
        if provenance_source is None or provenance_source["recordType"] != "Source":
            raise ContractError("relationship provenance must resolve to a Source")
        if (
            relationship["provenance"]["artifactHash"] != compilation["artifactHash"]
            or relationship["provenance"]["sourceRevision"] != compilation["sourceRevision"]
            or relationship["recordedAt"] != relationship["provenance"]["recordedAt"]
        ):
            raise ContractError("relationship provenance does not match its compilation")
        if not set(relationship["acl"]).issubset(provenance_source["acl"]):
            raise ContractError("relationship ACL weakens its provenance Source")
        if _trust_rank(relationship["trust"]) > _trust_rank(provenance_source["trust"]):
            raise ContractError("relationship trust cannot exceed its provenance Source")

    for rejection in compilation["rejections"]:
        if (
            not isinstance(rejection, dict)
            or set(rejection) != {"kind", "index", "code"}
            or rejection["kind"] not in {"node", "edge", "hyperedge", "codeReference"}
            or isinstance(rejection["index"], bool)
            or not isinstance(rejection["index"], int)
            or rejection["index"] < 0
            or not isinstance(rejection["code"], str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", rejection["code"])
        ):
            raise ContractError("rejection ledger entries must be bounded and privacy-safe")


def validate_receipt(
    receipt: Mapping[str, Any],
    ontology: CompiledOntology,
    compilation: Mapping[str, Any] | None = None,
) -> None:
    """Validate a privacy-safe ingest receipt and its optional compilation binding."""

    required = {
        "receiptVersion", "runId", "status", "tenantHash", "namespaceHash",
        "sourceRevisionHash", "compilationHash", "artifactHash", "ontologyChecksum",
        "migrationChecksums", "counts", "adapterVersion",
    }
    optional = {"currentCompilationHash", "failureStage"}
    if not isinstance(receipt, dict):
        raise ContractError("ingest receipt must be an object")
    missing = required - set(receipt)
    unknown = set(receipt) - required - optional
    if missing or unknown:
        raise ContractError(
            f"receipt fields missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    if receipt["receiptVersion"] != 1 or receipt["status"] not in RECEIPT_STATUSES:
        raise ContractError("unsupported ingest receipt version or status")
    for field in (
        "runId", "tenantHash", "namespaceHash", "sourceRevisionHash", "compilationHash",
        "artifactHash", "ontologyChecksum",
    ):
        _validate_hash(receipt[field], f"receipt {field}")
    current = receipt.get("currentCompilationHash")
    if current is not None:
        _validate_hash(current, "receipt currentCompilationHash")
    if receipt["ontologyChecksum"] != ontology.checksum:
        raise ContractError("receipt ontology checksum mismatch")
    expected_migrations = sorted(migration.checksum for migration in ontology.migrations)
    if receipt["migrationChecksums"] != expected_migrations:
        raise ContractError("receipt migration checksums do not match the ontology")
    counts = receipt["counts"]
    if (
        not isinstance(counts, dict)
        or set(counts) != {"records", "relationships", "rejections", "quarantined"}
        or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts.values())
        or counts["quarantined"] > counts["records"] + counts["relationships"]
    ):
        raise ContractError("receipt counts are invalid")
    adapter_version = receipt["adapterVersion"]
    if not isinstance(adapter_version, str) or not adapter_version or len(adapter_version) > 128:
        raise ContractError("receipt adapterVersion must be bounded text")
    failure_stage = receipt.get("failureStage")
    if failure_stage is not None and (
        not isinstance(failure_stage, str) or not failure_stage or len(failure_stage) > 64
    ):
        raise ContractError("receipt failureStage must be bounded text")
    if receipt["status"] in {"accepted", "replayed"} and current != receipt["compilationHash"]:
        raise ContractError(
            f"{receipt['status']} receipt must identify its current compilation"
        )
    if receipt["status"] in {"staged", "purged"} and current is not None:
        raise ContractError(f"{receipt['status']} receipt cannot identify a current compilation")

    if compilation is None:
        return
    validate_compilation(compilation, ontology)
    quarantined = sum(
        1 for item in [*compilation["records"], *compilation["relationships"]]
        if item["quarantined"]
    )
    expected = {
        "tenantHash": compilation["tenantKey"],
        "namespaceHash": compilation["namespaceKey"],
        "sourceRevisionHash": sha256_value(compilation["sourceRevision"]),
        "compilationHash": compilation["compilationId"],
        "artifactHash": compilation["artifactHash"],
        "ontologyChecksum": compilation["ontologyChecksum"],
        "counts": {
            "records": len(compilation["records"]),
            "relationships": len(compilation["relationships"]),
            "rejections": len(compilation["rejections"]),
            "quarantined": quarantined,
        },
    }
    if any(receipt[field] != value for field, value in expected.items()):
        raise ContractError("receipt does not match its governed compilation")


def _validate_record(record: Any, ontology: CompiledOntology) -> None:
    required = {
        "governedId", "recordType", "subtype", "acl", "sensitivity", "trust",
        "confidenceClass", "confidenceScore", "quarantined", "recordedAt", "properties",
        "provenance",
    }
    if not isinstance(record, dict) or set(record) != required:
        raise ContractError("governed record has missing or unknown fields")
    _validate_hash(record["governedId"], "record governedId")
    record_type = record["recordType"]
    if record_type not in ontology.node_types:
        raise ContractError(f"unknown recordType: {record_type}")
    subtype = record["subtype"]
    if subtype is not None and ontology.subtypes.get(subtype) != record_type:
        raise ContractError(f"subtype {subtype!r} is not registered under {record_type}")
    _validate_scope(record)
    _validate_timestamp(record["recordedAt"], "record recordedAt")
    contract = ontology.core["nodeTypes"][record_type]
    properties = record["properties"]
    if not isinstance(properties, dict):
        raise ContractError("record properties must be an object")
    missing = set(contract["requiredProperties"]) - set(properties)
    unknown = set(properties) - set(contract["allowedProperties"])
    if missing or unknown:
        raise ContractError(
            f"{record_type} properties missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    _validate_record_properties(record_type, properties)
    if record_type == "Event":
        valid_from = properties["validFrom"]
        valid_until = properties.get("validUntil")
        _validate_timestamp(valid_from, "Event validFrom")
        if valid_until is not None:
            _validate_timestamp(valid_until, "Event validUntil")
        valid_from_time = datetime.fromisoformat(valid_from.replace("Z", "+00:00"))
        valid_until_time = (
            datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
            if valid_until is not None else None
        )
        if valid_until_time is not None and valid_until_time < valid_from_time:
            raise ContractError("Event validUntil cannot precede validFrom")
    _validate_provenance(record["provenance"])


def _validate_relationship(
    relationship: Any,
    ontology: CompiledOntology,
    record_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    required = {
        "governedId", "relationshipType", "sourceId", "targetId", "acl", "trust",
        "confidenceClass", "confidenceScore", "quarantined", "recordedAt", "properties",
        "provenance",
    }
    if not isinstance(relationship, dict) or set(relationship) != required:
        raise ContractError("governed relationship has missing or unknown fields")
    _validate_hash(relationship["governedId"], "relationship governedId")
    relationship_type = relationship["relationshipType"]
    if relationship_type not in ontology.relationship_types:
        raise ContractError(f"unknown relationshipType: {relationship_type}")
    source = record_by_id.get(relationship["sourceId"])
    target = record_by_id.get(relationship["targetId"])
    if source is None or target is None:
        raise ContractError("relationship endpoint is missing from this compilation")
    _validate_scope(relationship)
    _validate_timestamp(relationship["recordedAt"], "relationship recordedAt")
    if not set(relationship["acl"]).issubset(source["acl"]) or not set(relationship["acl"]).issubset(target["acl"]):
        raise ContractError("relationship ACL weakens an endpoint scope")
    if _trust_rank(relationship["trust"]) > min(_trust_rank(source["trust"]), _trust_rank(target["trust"])):
        raise ContractError("relationship trust cannot exceed an endpoint")
    if not isinstance(relationship["properties"], dict) or len(canonical_json(relationship["properties"]).encode("utf-8")) > 65_536:
        raise ContractError("relationship properties must be a bounded object")
    contract = ontology.relationship_contracts[relationship_type]
    source_type = source["subtype"] if contract["extension"] and source["subtype"] else source["recordType"]
    target_type = target["subtype"] if contract["extension"] and target["subtype"] else target["recordType"]
    if source_type not in contract["sources"] or target_type not in contract["targets"]:
        raise ContractError(f"invalid endpoints for relationship {relationship_type}")
    if not contract["extension"]:
        if contract.get("requiresSemanticType") and not relationship["properties"].get("semanticType"):
            raise ContractError(f"relationship {relationship_type} requires semanticType")
    _validate_provenance(relationship["provenance"])


def _validate_scope(item: Mapping[str, Any]) -> None:
    acl = item["acl"]
    if (
        not isinstance(acl, list)
        or not acl
        or len(acl) > 64
        or len(acl) != len(set(acl))
        or not all(isinstance(scope, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", scope) for scope in acl)
    ):
        raise ContractError("ACL must be a non-empty unique array")
    sensitivity = item.get("sensitivity")
    if sensitivity is not None and sensitivity not in {
        "public", "internal", "confidential", "restricted"
    }:
        raise ContractError("invalid sensitivity")
    if item["trust"] not in {"high", "medium", "low", "unverified"}:
        raise ContractError("invalid trust")
    if item["confidenceClass"] not in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}:
        raise ContractError("invalid confidence class")
    score = item["confidenceScore"]
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        raise ContractError("confidence score must be between 0 and 1")
    if not isinstance(item["quarantined"], bool):
        raise ContractError("quarantined must be boolean")
    if item["confidenceClass"] == "AMBIGUOUS" and (
        item["trust"] != "unverified" or not item["quarantined"]
    ):
        raise ContractError("AMBIGUOUS evidence must stay unverified and quarantined")
    if item["confidenceClass"] == "INFERRED" and item["trust"] in {"high", "medium"}:
        raise ContractError("INFERRED evidence cannot establish medium or high trust")


def _validate_provenance(provenance: Any) -> None:
    required = {
        "sourceId", "sourceRevision", "sourceRefHash", "artifactHash", "extractorVersion",
        "recordedAt",
    }
    optional = {"sourceLocation", "wrapperVersion", "buildCommit", "modelId", "promptHash"}
    if not isinstance(provenance, dict):
        raise ContractError("provenance must be an object")
    missing = required - set(provenance)
    unknown = set(provenance) - required - optional
    if missing or unknown:
        raise ContractError(f"provenance fields missing={sorted(missing)} unknown={sorted(unknown)}")
    for field in ("sourceId", "sourceRefHash", "artifactHash"):
        _validate_hash(provenance[field], f"provenance {field}")
    prompt_hash = provenance.get("promptHash")
    if prompt_hash is not None:
        _validate_hash(prompt_hash, "provenance promptHash")
    if not provenance["sourceRevision"] or not provenance["extractorVersion"]:
        raise ContractError("provenance sourceRevision and extractorVersion are required")
    _validate_timestamp(provenance["recordedAt"], "provenance recordedAt")
    for field in ("sourceRevision", "extractorVersion", "wrapperVersion", "buildCommit", "modelId"):
        value = provenance.get(field)
        if value is not None and (not isinstance(value, str) or not value or len(value) > 256):
            raise ContractError(f"provenance {field} must be bounded text")
    location = provenance.get("sourceLocation")
    if location is not None and (not isinstance(location, str) or len(location) > 512):
        raise ContractError("provenance sourceLocation must be bounded text")


def _validate_hash(value: Any, name: str) -> None:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise ContractError(f"{name} must be a sha256 hash")


def _validate_timestamp(value: Any, name: str) -> None:
    if not isinstance(value, str) or "T" not in value or len(value) > 64:
        raise ContractError(f"{name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise ContractError(f"{name} must include a timezone")


def _qualify_endpoint(name: str, namespace: str, local_subtypes: set[str]) -> str:
    return f"{namespace}:{name}" if name in local_subtypes else name


def _valid_unique_strings(values: Sequence[Any]) -> bool:
    return bool(values) and all(isinstance(value, str) and value for value in values) and len(
        values
    ) == len(set(values))


def _validate_record_properties(record_type: str, properties: Mapping[str, Any]) -> None:
    if len(canonical_json(properties).encode("utf-8")) > 65_536:
        raise ContractError(f"{record_type} properties exceed the size budget")
    if record_type == "Source":
        _validate_hash(properties["sourceRefHash"], "Source sourceRefHash")
        if (
            not isinstance(properties["sourceRevision"], str)
            or not properties["sourceRevision"]
            or len(properties["sourceRevision"]) > 256
        ):
            raise ContractError("Source sourceRevision must be bounded text")
        if properties.get("medium") is not None:
            _validate_text(properties["medium"], "Source medium", 128)
        if properties.get("capturedAt") is not None:
            _validate_timestamp(properties["capturedAt"], "Source capturedAt")
        for field in ("canonicalUrlHash", "authorHash", "contributorHash"):
            if properties.get(field) is not None:
                _validate_hash(properties[field], f"Source {field}")
    elif record_type in {"Entity", "Artifact"}:
        _validate_text(properties["label"], f"{record_type} label", 4096)
        type_field = "entityType" if record_type == "Entity" else "artifactType"
        _validate_text(properties[type_field], f"{record_type} {type_field}", 128)
        _validate_hash(properties["rawIdHash"], f"{record_type} rawIdHash")
        for field in ("rationaleHash", "graphifyMetadataHash"):
            if properties.get(field) is not None:
                _validate_hash(properties[field], f"{record_type} {field}")
        if properties.get("codeReference") is not None:
            _validate_code_reference(properties["codeReference"])
    elif record_type == "Claim":
        if not isinstance(properties["predicate"], str) or not properties["predicate"] or len(properties["predicate"]) > 256:
            raise ContractError("Claim predicate must be bounded text")
        _validate_hash(properties["subjectId"], "Claim subjectId")
        _validate_hash(properties["objectId"], "Claim objectId")
        participants = properties.get("participants")
        if participants is not None:
            if not isinstance(participants, list) or len(participants) < 3 or len(participants) > 256:
                raise ContractError("Claim participants must be a bounded hyperedge")
            for participant in participants:
                _validate_hash(participant, "Claim participant")
        if properties.get("evidenceContextHash") is not None:
            _validate_hash(properties["evidenceContextHash"], "Claim evidenceContextHash")
        if properties.get("graphifyMetadataHash") is not None:
            _validate_hash(properties["graphifyMetadataHash"], "Claim graphifyMetadataHash")
        weight = properties.get("weight")
        if weight is not None and (isinstance(weight, bool) or not isinstance(weight, (int, float))):
            raise ContractError("Claim weight must be numeric")
        if properties.get("label") is not None:
            _validate_text(properties["label"], "Claim label", 4096)
    elif record_type == "Event":
        _validate_text(properties["label"], "Event label", 4096)
    elif record_type == "Preference":
        _validate_text(properties["label"], "Preference label", 4096)
        _validate_text(properties["scope"], "Preference scope", 256)
        if properties.get("supersededBy") is not None:
            _validate_hash(properties["supersededBy"], "Preference supersededBy")
    elif record_type == "Compilation":
        _validate_hash(properties["compilationHash"], "Compilation compilationHash")
        _validate_hash(properties["artifactHash"], "Compilation artifactHash")
        _validate_text(properties["status"], "Compilation status", 64)
        if properties.get("extractorVersion") is not None:
            _validate_text(properties["extractorVersion"], "Compilation extractorVersion", 128)
        if properties.get("promptHash") is not None:
            _validate_hash(properties["promptHash"], "Compilation promptHash")
        if properties.get("modelId") is not None:
            _validate_text(properties["modelId"], "Compilation modelId", 256)


def _trust_rank(level: str) -> int:
    return {"unverified": 0, "low": 1, "medium": 2, "high": 3}[level]


def _sensitivity_rank(level: str) -> int:
    return {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}[level]


def _validate_text(value: Any, name: str, maximum: int) -> None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ContractError(f"{name} must be bounded text")


def _validate_code_reference(value: Any) -> None:
    required = {
        "repositoryId", "commitSha", "relativePath", "qualifiedSymbol", "toolVersion",
        "validation",
    }
    optional = {"indexFingerprint"}
    if not isinstance(value, dict) or required - set(value) or set(value) - required - optional:
        raise ContractError("codeReference has missing or unknown fields")
    _validate_text(value["repositoryId"], "codeReference repositoryId", 256)
    if not isinstance(value["commitSha"], str) or not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", value["commitSha"]):
        raise ContractError("codeReference commitSha must be a Git object hash")
    relative_path = value["relativePath"]
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or len(relative_path) > 4096
        or Path(relative_path).is_absolute()
        or ".." in Path(relative_path).parts
    ):
        raise ContractError("codeReference relativePath is unsafe")
    _validate_text(value["qualifiedSymbol"], "codeReference qualifiedSymbol", 1024)
    _validate_text(value["toolVersion"], "codeReference toolVersion", 128)
    if value["validation"] != "same_revision_metadata":
        raise ContractError("codeReference validation state is invalid")
    if value.get("indexFingerprint") is not None:
        _validate_hash(value["indexFingerprint"], "codeReference indexFingerprint")
