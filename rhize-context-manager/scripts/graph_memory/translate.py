"""Translate portable Graphify node-link artifacts into governed compilations."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contract import (
    CompiledOntology,
    ContractError,
    canonical_json,
    sha256_value,
    validate_compilation,
)


class GraphifyTranslationError(ContractError):
    """Raised when an artifact or manifest cannot be governed safely."""


_SAFE_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_POISON_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"system\s+prompt",
        r"reveal\s+(the\s+)?secret",
        r"execute\s+(this\s+)?(?:command|tool)",
        r"override\s+(?:policy|approval|permissions?)",
    )
)
_MANIFEST_REQUIRED = {
    "schemaVersion",
    "corpusId",
    "sourceRevision",
    "artifactSha256",
    "extractorVersion",
    "recordedAt",
    "defaultAcl",
    "defaultTrust",
    "sensitivity",
}
_MANIFEST_OPTIONAL = {
    "wrapperVersion", "graphifyBuildCommit", "modelId", "promptHash", "sourcePolicies",
}
_GRAPH_TOP_LEVEL = {
    "directed", "multigraph", "graph", "nodes", "links", "edges", "hyperedges",
    "built_at_commit",
}
_NODE_EXPORT_METADATA = {
    "_origin", "community", "community_name", "norm_label", "repo", "local_id",
}
_EDGE_EXPORT_METADATA = {"_origin"}
_CODE_REFERENCE_FIELDS = {
    "repositoryId", "commitSha", "relativePath", "qualifiedSymbol", "toolVersion",
}
MAX_NODES = 50_000
MAX_EDGES = 200_000
MAX_HYPEREDGES = 50_000
MAX_ITEM_BYTES = 65_536
MAX_PROJECTED_RELATIONSHIPS = 1_000_000


def validate_codegraph_reference(
    reference: Mapping[str, Any],
    *,
    repo_root: Path,
    repository_id: str,
    current_commit: str,
    tool_version: str,
    observed_index_fingerprint: str | None = None,
) -> dict[str, str]:
    """Validate a locator against caller-observed facts without invoking CodeGraph."""

    fields = set(reference)
    if fields - (_CODE_REFERENCE_FIELDS | {"indexFingerprint"}):
        raise GraphifyTranslationError("CodeGraph reference has unsupported fields")
    if not _CODE_REFERENCE_FIELDS.issubset(fields):
        raise GraphifyTranslationError("CodeGraph reference is incomplete")
    if not (repo_root / ".codegraph").is_dir():
        raise GraphifyTranslationError("CodeGraph reference cannot resolve without an existing index")
    for field, maximum in (("repositoryId", 256), ("toolVersion", 128)):
        if (
            not isinstance(reference[field], str)
            or not reference[field]
            or len(reference[field]) > maximum
        ):
            raise GraphifyTranslationError(f"CodeGraph {field} must be bounded text")
    if not isinstance(reference["commitSha"], str) or not re.fullmatch(
        r"[a-f0-9]{40}|[a-f0-9]{64}", reference["commitSha"]
    ):
        raise GraphifyTranslationError("CodeGraph commitSha must be a Git object hash")
    if reference["repositoryId"] != repository_id:
        raise GraphifyTranslationError("CodeGraph repository identity mismatch")
    if reference["commitSha"] != current_commit:
        raise GraphifyTranslationError("CodeGraph revision mismatch")
    if reference["toolVersion"] != tool_version:
        raise GraphifyTranslationError("CodeGraph tool version mismatch")
    relative_path = reference["relativePath"]
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or len(relative_path) > 4096
        or Path(relative_path).is_absolute()
        or ".." in Path(relative_path).parts
    ):
        raise GraphifyTranslationError("CodeGraph relativePath is unsafe")
    if (
        not isinstance(reference["qualifiedSymbol"], str)
        or not reference["qualifiedSymbol"]
        or len(reference["qualifiedSymbol"]) > 1024
    ):
        raise GraphifyTranslationError("CodeGraph qualifiedSymbol is required")
    expected_fingerprint = reference.get("indexFingerprint")
    if expected_fingerprint is not None:
        if not isinstance(expected_fingerprint, str) or not re.fullmatch(
            r"[a-f0-9]{64}", expected_fingerprint
        ):
            raise GraphifyTranslationError("CodeGraph index fingerprint must be a sha256 hash")
        if observed_index_fingerprint is None or expected_fingerprint != observed_index_fingerprint:
            raise GraphifyTranslationError("CodeGraph index fingerprint mismatch")
    return {
        "repositoryId": repository_id,
        "commitSha": current_commit,
        "relativePath": relative_path,
        "qualifiedSymbol": reference["qualifiedSymbol"],
        "toolVersion": tool_version,
        **({"indexFingerprint": expected_fingerprint} if expected_fingerprint else {}),
        "validation": "same_revision_metadata",
    }


class GraphifyTranslator:
    """Strict, deterministic adapter for Graphify's portable graph.json artifact."""

    def __init__(self, ontology: CompiledOntology) -> None:
        self.ontology = ontology
        graphify = ontology.core["graphify"]
        self.allowed_file_types = frozenset(graphify["allowedFileTypes"])
        self.allowed_node_fields = frozenset(graphify["allowedNodeFields"])
        self.allowed_edge_fields = frozenset(graphify["allowedEdgeFields"])
        self.allowed_hyperedge_fields = frozenset(graphify["allowedHyperedgeFields"])

    def translate(
        self,
        artifact: Mapping[str, Any],
        manifest: Mapping[str, Any],
        *,
        tenant: str,
        namespace: str,
        codegraph_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validate_artifact_envelope(artifact)
        self._validate_manifest(manifest, artifact)
        self._validate_partition(tenant, "tenant")
        self._validate_partition(namespace, "namespace")

        tenant_key = sha256_value(f"tenant:{tenant}")
        namespace_key = sha256_value(f"namespace:{namespace}")
        corpus_key = sha256_value(f"corpus:{manifest['corpusId']}")
        artifact_hash = manifest["artifactSha256"]
        scope = (tenant, namespace, manifest["corpusId"])
        manifest_hash = sha256_value(manifest)
        records: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        rejections: list[dict[str, Any]] = []
        source_ids: dict[str, str] = {}
        raw_to_governed: dict[str, str] = {}
        record_by_id: dict[str, dict[str, Any]] = {}

        for index, raw_node in enumerate(artifact["nodes"]):
            try:
                node, source = self._translate_node(
                    raw_node,
                    index=index,
                    scope=scope,
                    manifest=manifest,
                    artifact_hash=artifact_hash,
                    codegraph_context=codegraph_context,
                    rejections=rejections,
                )
            except GraphifyTranslationError as exc:
                rejections.append({"kind": "node", "index": index, "code": _error_code(exc)})
                continue
            source_ref_hash = source["properties"]["sourceRefHash"]
            source_id = source["governedId"]
            if source_ref_hash not in source_ids:
                source_ids[source_ref_hash] = source_id
                records.append(source)
                record_by_id[source_id] = source
            records.append(node)
            record_by_id[node["governedId"]] = node
            raw_to_governed[raw_node["id"]] = node["governedId"]
            relationships.append(
                self._relationship(
                    scope,
                    "DERIVED_FROM",
                    node["governedId"],
                    source_id,
                    node["acl"],
                    node["trust"],
                    node["confidenceClass"],
                    node["confidenceScore"],
                    node["quarantined"],
                    {},
                    node["provenance"],
                    f"node-source:{raw_node['id']}",
                )
            )

        raw_edges = artifact.get("links", artifact.get("edges", []))
        for index, raw_edge in enumerate(raw_edges):
            try:
                claim, claim_relationships = self._translate_edge(
                    raw_edge,
                    index=index,
                    scope=scope,
                    manifest=manifest,
                    artifact_hash=artifact_hash,
                    raw_to_governed=raw_to_governed,
                    record_by_id=record_by_id,
                    source_ids=source_ids,
                )
            except GraphifyTranslationError as exc:
                rejections.append({"kind": "edge", "index": index, "code": _error_code(exc)})
                continue
            records.append(claim)
            record_by_id[claim["governedId"]] = claim
            relationships.extend(claim_relationships)

        for index, raw_hyperedge in enumerate(artifact.get("hyperedges", [])):
            try:
                claim, claim_relationships = self._translate_hyperedge(
                    raw_hyperedge,
                    index=index,
                    scope=scope,
                    manifest=manifest,
                    artifact_hash=artifact_hash,
                    raw_to_governed=raw_to_governed,
                    record_by_id=record_by_id,
                    source_ids=source_ids,
                )
            except GraphifyTranslationError as exc:
                rejections.append({"kind": "hyperedge", "index": index, "code": _error_code(exc)})
                continue
            records.append(claim)
            record_by_id[claim["governedId"]] = claim
            relationships.extend(claim_relationships)

        records.sort(key=lambda item: item["governedId"])
        relationships.sort(key=lambda item: item["governedId"])
        rejections.sort(key=lambda item: (item["kind"], item["index"], item["code"]))
        compilation_id = sha256_value(
            {
                "ontology": self.ontology.checksum,
                "artifact": artifact_hash,
                "manifest": manifest_hash,
                "tenantKey": tenant_key,
                "namespaceKey": namespace_key,
                "corpusKey": corpus_key,
                "sourceRevision": manifest["sourceRevision"],
            }
        )
        compilation = {
            "contractVersion": 1,
            "ontologyChecksum": self.ontology.checksum,
            "artifactHash": artifact_hash,
            "manifestHash": manifest_hash,
            "tenantKey": tenant_key,
            "namespaceKey": namespace_key,
            "corpusKey": corpus_key,
            "sourceRevision": manifest["sourceRevision"],
            "compilationId": compilation_id,
            "records": records,
            "relationships": relationships,
            "rejections": rejections,
        }
        validate_compilation(compilation, self.ontology)
        return compilation

    def _translate_node(
        self,
        raw: Any,
        *,
        index: int,
        scope: Sequence[str],
        manifest: Mapping[str, Any],
        artifact_hash: str,
        codegraph_context: Mapping[str, Any] | None,
        rejections: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(raw, dict) or set(raw) - self.allowed_node_fields:
            raise GraphifyTranslationError("unsupported node fields")
        if len(canonical_json(raw).encode("utf-8")) > MAX_ITEM_BYTES:
            raise GraphifyTranslationError("node exceeds the size budget")
        required = {"id", "label", "file_type", "source_file"}
        if not required.issubset(raw) or not all(isinstance(raw[field], str) and raw[field] for field in required):
            raise GraphifyTranslationError("incomplete node")
        if len(raw["id"]) > 512 or len(raw["label"]) > 4096 or len(raw["source_file"]) > 4096:
            raise GraphifyTranslationError("node field exceeds the size budget")
        for field in ("source_location", "source_url", "captured_at", "author", "contributor", "rationale"):
            if raw.get(field) is not None and not isinstance(raw[field], str):
                raise GraphifyTranslationError(f"node {field} must be text")
        if raw.get("captured_at") is not None and not _is_iso_timestamp(raw["captured_at"]):
            raise GraphifyTranslationError("node captured_at must be an ISO-8601 timestamp")
        self._validate_node_export_metadata(raw)
        if raw.get("codegraph_ref") is not None and not isinstance(raw["codegraph_ref"], dict):
            raise GraphifyTranslationError("node codegraph_ref must be an object")
        if raw["file_type"] not in self.allowed_file_types:
            raise GraphifyTranslationError("unsupported file type")
        source_ref_hash = sha256_value(f"source:{raw['source_file']}")
        policy = _source_policy(manifest, source_ref_hash)
        acl = policy["acl"]
        sensitivity = policy["sensitivity"]
        source_trust = _minimum_trust("medium", policy["trust"])
        source_id = _governed_id(scope, "Source", source_ref_hash)
        provenance = _provenance(
            source_id, source_ref_hash, raw.get("source_location"), manifest, artifact_hash
        )
        poison = _contains_poison(raw)
        code_reference = None
        if raw.get("codegraph_ref") is not None:
            try:
                if codegraph_context is None:
                    raise GraphifyTranslationError("CodeGraph context is unavailable")
                code_reference = validate_codegraph_reference(
                    raw["codegraph_ref"],
                    repo_root=Path(codegraph_context["repoRoot"]),
                    repository_id=codegraph_context["repositoryId"],
                    current_commit=codegraph_context["currentCommit"],
                    tool_version=codegraph_context["toolVersion"],
                    observed_index_fingerprint=codegraph_context.get("indexFingerprint"),
                )
            except (KeyError, TypeError, GraphifyTranslationError) as exc:
                rejections.append(
                    {"kind": "codeReference", "index": index, "code": _error_code(exc)}
                )
                poison = True
        record_type = "Artifact" if raw["file_type"] == "code" else "Entity"
        property_type = "artifactType" if record_type == "Artifact" else "entityType"
        properties = {
            "label": raw["label"],
            property_type: f"Graphify{raw['file_type'].title()}",
            "rawIdHash": sha256_value(f"graphify-node:{raw['id']}"),
        }
        if raw.get("rationale") is not None:
            properties["rationaleHash"] = sha256_value(str(raw["rationale"]))
        if code_reference is not None:
            properties["codeReference"] = code_reference
        metadata_hash = _metadata_hash(raw, _NODE_EXPORT_METADATA)
        if metadata_hash:
            properties["graphifyMetadataHash"] = metadata_hash
        node = _record(
            governed_id=_governed_id(scope, record_type, raw["id"]),
            record_type=record_type,
            subtype=None,
            acl=acl,
            sensitivity=sensitivity,
            trust="unverified" if poison else source_trust,
            confidence_class="AMBIGUOUS" if poison else "EXTRACTED",
            confidence_score=0.1 if poison else 1.0,
            quarantined=poison,
            properties=properties,
            provenance=provenance,
        )
        source = _record(
            governed_id=source_id,
            record_type="Source",
            subtype=None,
            acl=acl,
            sensitivity=sensitivity,
            trust=source_trust,
            confidence_class="EXTRACTED",
            confidence_score=1.0,
            quarantined=False,
            properties={
                "sourceRefHash": source_ref_hash,
                "sourceRevision": manifest["sourceRevision"],
                "medium": raw["file_type"],
                **({"capturedAt": raw["captured_at"]} if raw.get("captured_at") else {}),
                **({"canonicalUrlHash": sha256_value(raw["source_url"])} if raw.get("source_url") else {}),
                **({"authorHash": sha256_value(str(raw["author"]))} if raw.get("author") else {}),
                **({"contributorHash": sha256_value(str(raw["contributor"]))} if raw.get("contributor") else {}),
            },
            provenance=provenance,
        )
        return node, source

    def _translate_edge(
        self,
        raw: Any,
        *,
        index: int,
        scope: Sequence[str],
        manifest: Mapping[str, Any],
        artifact_hash: str,
        raw_to_governed: Mapping[str, str],
        record_by_id: Mapping[str, Mapping[str, Any]],
        source_ids: Mapping[str, str],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not isinstance(raw, dict) or set(raw) - self.allowed_edge_fields:
            raise GraphifyTranslationError("unsupported edge fields")
        if len(canonical_json(raw).encode("utf-8")) > MAX_ITEM_BYTES:
            raise GraphifyTranslationError("edge exceeds the size budget")
        required = {"source", "target", "relation", "confidence", "confidence_score", "source_file"}
        if not required.issubset(raw):
            raise GraphifyTranslationError("incomplete edge")
        if not all(isinstance(raw[field], str) and raw[field] for field in ("source", "target", "relation", "source_file")):
            raise GraphifyTranslationError("edge identity and provenance must be text")
        if any(len(raw[field]) > 4096 for field in ("source", "target", "relation", "source_file")):
            raise GraphifyTranslationError("edge field exceeds the size budget")
        if raw.get("source_location") is not None and not isinstance(raw["source_location"], str):
            raise GraphifyTranslationError("edge source_location must be text")
        if raw.get("weight") is not None and (
            isinstance(raw["weight"], bool) or not isinstance(raw["weight"], (int, float))
        ):
            raise GraphifyTranslationError("edge weight must be numeric")
        self._validate_edge_export_metadata(raw)
        source_id = raw_to_governed.get(raw["source"])
        target_id = raw_to_governed.get(raw["target"])
        if source_id is None or target_id is None:
            raise GraphifyTranslationError("edge endpoint unavailable")
        confidence, score, trust, quarantined = self._confidence(raw)
        quarantined = quarantined or _contains_poison(raw) or record_by_id[source_id]["quarantined"] or record_by_id[target_id]["quarantined"]
        if quarantined:
            confidence, score, trust = "AMBIGUOUS", min(score, 0.3), "unverified"
        source_ref_hash = sha256_value(f"source:{raw['source_file']}")
        evidence_source = source_ids.get(source_ref_hash)
        if evidence_source is None:
            raise GraphifyTranslationError("edge source has no accepted Source record")
        endpoint_records = [record_by_id[source_id], record_by_id[target_id]]
        evidence_record = record_by_id[evidence_source]
        acl = _intersect_acl(evidence_record, *endpoint_records)
        if not acl:
            raise GraphifyTranslationError("edge has incompatible ACL scopes")
        sensitivity = _maximum_sensitivity(
            evidence_record["sensitivity"], *(record["sensitivity"] for record in endpoint_records)
        )
        trust = _minimum_trust(trust, evidence_record["trust"], *(record["trust"] for record in endpoint_records))
        provenance = _provenance(
            evidence_source, source_ref_hash, raw.get("source_location"), manifest, artifact_hash
        )
        raw_fingerprint = sha256_value({"index": index, "edge": raw})
        claim_id = _governed_id(scope, "Claim", raw_fingerprint)
        metadata_hash = _metadata_hash(raw, _EDGE_EXPORT_METADATA)
        claim = _record(
            governed_id=claim_id,
            record_type="Claim",
            subtype=None,
            acl=acl,
            sensitivity=sensitivity,
            trust=trust,
            confidence_class=confidence,
            confidence_score=score,
            quarantined=quarantined,
            properties={
                "predicate": str(raw["relation"]),
                "subjectId": source_id,
                "objectId": target_id,
                **({"evidenceContextHash": sha256_value(str(raw["context"]))} if raw.get("context") else {}),
                **({"weight": raw["weight"]} if raw.get("weight") is not None else {}),
                **({"graphifyMetadataHash": metadata_hash} if metadata_hash else {}),
            },
            provenance=provenance,
        )
        return claim, self._claim_relationships(
            scope, claim, evidence_source, [source_id, target_id], raw_fingerprint
        )

    def _translate_hyperedge(
        self,
        raw: Any,
        *,
        index: int,
        scope: Sequence[str],
        manifest: Mapping[str, Any],
        artifact_hash: str,
        raw_to_governed: Mapping[str, str],
        record_by_id: Mapping[str, Mapping[str, Any]],
        source_ids: Mapping[str, str],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not isinstance(raw, dict) or set(raw) - self.allowed_hyperedge_fields:
            raise GraphifyTranslationError("unsupported hyperedge fields")
        if len(canonical_json(raw).encode("utf-8")) > MAX_ITEM_BYTES:
            raise GraphifyTranslationError("hyperedge exceeds the size budget")
        required = {"id", "nodes", "relation", "confidence", "confidence_score", "source_file"}
        if (
            not required.issubset(raw)
            or not isinstance(raw["nodes"], list)
            or not 3 <= len(raw["nodes"]) <= 256
        ):
            raise GraphifyTranslationError("incomplete hyperedge")
        if not all(isinstance(raw[field], str) and raw[field] for field in ("id", "relation", "source_file")):
            raise GraphifyTranslationError("hyperedge identity and provenance must be text")
        if not all(isinstance(node_id, str) and node_id for node_id in raw["nodes"]):
            raise GraphifyTranslationError("hyperedge nodes must be text ids")
        if raw.get("label") is not None and not isinstance(raw["label"], str):
            raise GraphifyTranslationError("hyperedge label must be text")
        if raw.get("source_location") is not None and not isinstance(raw["source_location"], str):
            raise GraphifyTranslationError("hyperedge source_location must be text")
        participants = [raw_to_governed.get(node_id) for node_id in raw["nodes"]]
        if any(node_id is None for node_id in participants):
            raise GraphifyTranslationError("hyperedge endpoint unavailable")
        governed_participants = [str(node_id) for node_id in participants]
        confidence, score, trust, quarantined = self._confidence(raw)
        quarantined = quarantined or _contains_poison(raw) or any(
            record_by_id[node_id]["quarantined"] for node_id in governed_participants
        )
        if quarantined:
            confidence, score, trust = "AMBIGUOUS", min(score, 0.3), "unverified"
        source_ref_hash = sha256_value(f"source:{raw['source_file']}")
        evidence_source = source_ids.get(source_ref_hash)
        if evidence_source is None:
            raise GraphifyTranslationError("hyperedge source has no accepted Source record")
        participant_records = [record_by_id[node_id] for node_id in governed_participants]
        evidence_record = record_by_id[evidence_source]
        acl = _intersect_acl(evidence_record, *participant_records)
        if not acl:
            raise GraphifyTranslationError("hyperedge has incompatible ACL scopes")
        sensitivity = _maximum_sensitivity(
            evidence_record["sensitivity"], *(record["sensitivity"] for record in participant_records)
        )
        trust = _minimum_trust(
            trust, evidence_record["trust"], *(record["trust"] for record in participant_records)
        )
        provenance = _provenance(
            evidence_source, source_ref_hash, raw.get("source_location"), manifest, artifact_hash
        )
        raw_fingerprint = sha256_value({"index": index, "hyperedge": raw})
        claim_id = _governed_id(scope, "Claim", raw_fingerprint)
        claim = _record(
            governed_id=claim_id,
            record_type="Claim",
            subtype=None,
            acl=acl,
            sensitivity=sensitivity,
            trust=trust,
            confidence_class=confidence,
            confidence_score=score,
            quarantined=quarantined,
            properties={
                "predicate": str(raw["relation"]),
                "subjectId": governed_participants[0],
                "objectId": governed_participants[1],
                "participants": governed_participants,
                **({"label": str(raw["label"])} if raw.get("label") else {}),
            },
            provenance=provenance,
        )
        return claim, self._claim_relationships(
            scope, claim, evidence_source, governed_participants, raw_fingerprint
        )

    def _claim_relationships(
        self,
        scope: Sequence[str],
        claim: Mapping[str, Any],
        evidence_source: str,
        participants: Sequence[str],
        raw_fingerprint: str,
    ) -> list[dict[str, Any]]:
        relationships = [
            self._relationship(
                scope,
                "ASSERTS",
                evidence_source,
                claim["governedId"],
                claim["acl"],
                claim["trust"],
                claim["confidenceClass"],
                claim["confidenceScore"],
                claim["quarantined"],
                {},
                claim["provenance"],
                f"asserts:{raw_fingerprint}",
            )
        ]
        for position, participant in enumerate(participants):
            relationships.append(
                self._relationship(
                    scope,
                    "ABOUT",
                    claim["governedId"],
                    participant,
                    claim["acl"],
                    claim["trust"],
                    claim["confidenceClass"],
                    claim["confidenceScore"],
                    claim["quarantined"],
                    {},
                    claim["provenance"],
                    f"about:{raw_fingerprint}:{position}",
                )
            )
        return relationships

    @staticmethod
    def _relationship(
        scope: Sequence[str],
        relationship_type: str,
        source_id: str,
        target_id: str,
        acl: list[str],
        trust: str,
        confidence_class: str,
        confidence_score: float,
        quarantined: bool,
        properties: Mapping[str, Any],
        provenance: Mapping[str, Any],
        raw_identity: str,
    ) -> dict[str, Any]:
        return {
            "governedId": _governed_id(scope, relationship_type, raw_identity),
            "relationshipType": relationship_type,
            "sourceId": source_id,
            "targetId": target_id,
            "acl": list(acl),
            "trust": trust,
            "confidenceClass": confidence_class,
            "confidenceScore": confidence_score,
            "quarantined": quarantined,
            "recordedAt": provenance["recordedAt"],
            "properties": dict(properties),
            "provenance": dict(provenance),
        }

    @staticmethod
    def _confidence(raw: Mapping[str, Any]) -> tuple[str, float, str, bool]:
        confidence = raw["confidence"]
        score = raw["confidence_score"]
        if confidence not in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}:
            raise GraphifyTranslationError("unsupported confidence class")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise GraphifyTranslationError("invalid confidence score")
        if confidence == "EXTRACTED" and score != 1.0:
            raise GraphifyTranslationError("EXTRACTED confidence score must be 1.0")
        if confidence == "INFERRED" and score not in {0.55, 0.65, 0.75, 0.85, 0.95}:
            raise GraphifyTranslationError("INFERRED confidence score is outside the rubric")
        if confidence == "AMBIGUOUS" and not 0.1 <= score <= 0.3:
            raise GraphifyTranslationError("AMBIGUOUS confidence score is outside the rubric")
        trust = {"EXTRACTED": "medium", "INFERRED": "low", "AMBIGUOUS": "unverified"}[confidence]
        return confidence, float(score), trust, confidence == "AMBIGUOUS"

    @staticmethod
    def _validate_partition(value: str, name: str) -> None:
        if not isinstance(value, str) or not _SAFE_SCOPE.fullmatch(value):
            raise GraphifyTranslationError(f"unsafe {name} identifier")

    @staticmethod
    def _validate_artifact_envelope(artifact: Mapping[str, Any]) -> None:
        if not isinstance(artifact, dict) or set(artifact) - _GRAPH_TOP_LEVEL:
            raise GraphifyTranslationError("Graphify artifact has unsupported top-level fields")
        if not isinstance(artifact.get("nodes"), list):
            raise GraphifyTranslationError("Graphify artifact nodes must be an array")
        if not artifact["nodes"] or len(artifact["nodes"]) > MAX_NODES:
            raise GraphifyTranslationError("Graphify artifact node count is outside the budget")
        if "links" in artifact and "edges" in artifact:
            raise GraphifyTranslationError("Graphify artifact cannot define both links and edges")
        if not isinstance(artifact.get("links", artifact.get("edges", [])), list):
            raise GraphifyTranslationError("Graphify artifact links must be an array")
        if len(artifact.get("links", artifact.get("edges", []))) > MAX_EDGES:
            raise GraphifyTranslationError("Graphify artifact edge count exceeds the budget")
        if not isinstance(artifact.get("hyperedges", []), list):
            raise GraphifyTranslationError("Graphify artifact hyperedges must be an array")
        if len(artifact.get("hyperedges", [])) > MAX_HYPEREDGES:
            raise GraphifyTranslationError("Graphify artifact hyperedge count exceeds the budget")
        raw_edges = artifact.get("links", artifact.get("edges", []))
        projected_relationships = len(artifact["nodes"]) + 3 * len(raw_edges)
        for hyperedge in artifact.get("hyperedges", []):
            members = hyperedge.get("nodes", []) if isinstance(hyperedge, dict) else []
            projected_relationships += 1 + len(members) if isinstance(members, list) else 1
        if projected_relationships > MAX_PROJECTED_RELATIONSHIPS:
            raise GraphifyTranslationError("Graphify projection exceeds the relationship budget")
        if "directed" in artifact and not isinstance(artifact["directed"], bool):
            raise GraphifyTranslationError("Graphify directed metadata must be boolean")
        if "multigraph" in artifact and not isinstance(artifact["multigraph"], bool):
            raise GraphifyTranslationError("Graphify multigraph metadata must be boolean")
        graph_metadata = artifact.get("graph", {})
        if not isinstance(graph_metadata, dict) or set(graph_metadata) - {"name", "hyperedges"}:
            raise GraphifyTranslationError("Graphify graph metadata has unsupported fields")
        if "name" in graph_metadata and (
            not isinstance(graph_metadata["name"], str) or len(graph_metadata["name"]) > 256
        ):
            raise GraphifyTranslationError("Graphify graph name is invalid")
        nested_hyperedges = graph_metadata.get("hyperedges")
        if nested_hyperedges is not None and (
            not isinstance(nested_hyperedges, list)
            or canonical_json(nested_hyperedges) != canonical_json(artifact.get("hyperedges", []))
        ):
            raise GraphifyTranslationError("Graphify hyperedge metadata disagrees with top-level data")
        built_at_commit = artifact.get("built_at_commit")
        if built_at_commit is not None and (
            not isinstance(built_at_commit, str)
            or not built_at_commit
            or len(built_at_commit) > 256
        ):
            raise GraphifyTranslationError("Graphify built_at_commit must be bounded text")

    @staticmethod
    def _validate_manifest(manifest: Mapping[str, Any], artifact: Mapping[str, Any]) -> None:
        if not isinstance(manifest, dict):
            raise GraphifyTranslationError("Graphify manifest must be an object")
        missing = _MANIFEST_REQUIRED - set(manifest)
        unknown = set(manifest) - _MANIFEST_REQUIRED - _MANIFEST_OPTIONAL
        if missing or unknown:
            raise GraphifyTranslationError(
                f"Graphify manifest fields missing={sorted(missing)} unknown={sorted(unknown)}"
            )
        if manifest["schemaVersion"] != 1:
            raise GraphifyTranslationError("unsupported Graphify manifest schemaVersion")
        field_limits = {"corpusId": 128, "sourceRevision": 256, "extractorVersion": 128}
        for field, limit in field_limits.items():
            if not isinstance(manifest[field], str) or not manifest[field] or len(manifest[field]) > limit:
                raise GraphifyTranslationError(f"manifest {field} is required")
        if not _is_iso_timestamp(manifest["recordedAt"]):
            raise GraphifyTranslationError("manifest recordedAt must be an ISO-8601 timestamp")
        if manifest["artifactSha256"] != sha256_value(artifact):
            raise GraphifyTranslationError("Graphify artifact hash mismatch")
        acl = manifest["defaultAcl"]
        if (
            not isinstance(acl, list)
            or not acl
            or len(acl) > 64
            or len(acl) != len(set(acl))
            or not all(isinstance(scope, str) and _SAFE_SCOPE.fullmatch(scope) for scope in acl)
        ):
            raise GraphifyTranslationError("manifest defaultAcl must be a bounded unique scope list")
        if manifest["sensitivity"] not in {"public", "internal", "confidential", "restricted"}:
            raise GraphifyTranslationError("unsupported manifest sensitivity")
        if manifest["defaultTrust"] not in {"high", "medium", "low", "unverified"}:
            raise GraphifyTranslationError("unsupported manifest defaultTrust")
        prompt_hash = manifest.get("promptHash")
        if prompt_hash is not None and not re.fullmatch(r"[a-f0-9]{64}", str(prompt_hash)):
            raise GraphifyTranslationError("manifest promptHash must be a sha256 hash")
        for field in ("wrapperVersion", "graphifyBuildCommit", "modelId"):
            if manifest.get(field) is not None and (
                not isinstance(manifest[field], str) or not manifest[field] or len(manifest[field]) > 256
            ):
                raise GraphifyTranslationError(f"manifest {field} must be bounded text")
        artifact_commit = artifact.get("built_at_commit")
        if artifact_commit is not None and artifact_commit != manifest.get("graphifyBuildCommit"):
            raise GraphifyTranslationError("Graphify build commit does not match the manifest")
        source_policies = manifest.get("sourcePolicies", {})
        if not isinstance(source_policies, dict) or len(source_policies) > MAX_NODES:
            raise GraphifyTranslationError("manifest sourcePolicies must be a bounded object")
        for source_ref_hash, policy in source_policies.items():
            if not re.fullmatch(r"[a-f0-9]{64}", str(source_ref_hash)):
                raise GraphifyTranslationError("source policy key must be a sourceRefHash")
            if not isinstance(policy, dict) or set(policy) != {"acl", "sensitivity", "trust"}:
                raise GraphifyTranslationError("source policy has missing or unknown fields")
            if (
                not isinstance(policy["acl"], list)
                or not policy["acl"]
                or len(policy["acl"]) > 64
                or len(policy["acl"]) != len(set(policy["acl"]))
                or not all(isinstance(scope, str) and _SAFE_SCOPE.fullmatch(scope) for scope in policy["acl"])
            ):
                raise GraphifyTranslationError("source policy ACL is invalid")
            if policy["sensitivity"] not in {"public", "internal", "confidential", "restricted"}:
                raise GraphifyTranslationError("source policy sensitivity is invalid")
            if policy["trust"] not in {"high", "medium", "low", "unverified"}:
                raise GraphifyTranslationError("source policy trust is invalid")

    @staticmethod
    def _validate_node_export_metadata(raw: Mapping[str, Any]) -> None:
        origin = raw.get("_origin")
        if origin is not None and origin not in {"ast", "semantic"}:
            raise GraphifyTranslationError("node _origin is invalid")
        community = raw.get("community")
        if community is not None and (
            isinstance(community, bool) or not isinstance(community, int)
        ):
            raise GraphifyTranslationError("node community must be an integer or null")
        for field in ("community_name", "norm_label", "repo", "local_id"):
            value = raw.get(field)
            if value is not None and (
                not isinstance(value, str) or not value or len(value) > 4096
            ):
                raise GraphifyTranslationError(f"node {field} must be bounded text")

    @staticmethod
    def _validate_edge_export_metadata(raw: Mapping[str, Any]) -> None:
        origin = raw.get("_origin")
        if origin is not None and origin not in {"ast", "semantic"}:
            raise GraphifyTranslationError("edge _origin is invalid")


def _record(
    *,
    governed_id: str,
    record_type: str,
    subtype: str | None,
    acl: Sequence[str],
    sensitivity: str,
    trust: str,
    confidence_class: str,
    confidence_score: float,
    quarantined: bool,
    properties: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "governedId": governed_id,
        "recordType": record_type,
        "subtype": subtype,
        "acl": list(acl),
        "sensitivity": sensitivity,
        "trust": trust,
        "confidenceClass": confidence_class,
        "confidenceScore": confidence_score,
        "quarantined": quarantined,
        "recordedAt": provenance["recordedAt"],
        "properties": dict(properties),
        "provenance": dict(provenance),
    }


def _provenance(
    source_id: str,
    source_ref_hash: str,
    source_location: Any,
    manifest: Mapping[str, Any],
    artifact_hash: str,
) -> dict[str, Any]:
    return {
        "sourceId": source_id,
        "sourceRevision": manifest["sourceRevision"],
        "sourceRefHash": source_ref_hash,
        "sourceLocation": str(source_location)[:512] if source_location is not None else None,
        "artifactHash": artifact_hash,
        "extractorVersion": manifest["extractorVersion"],
        "recordedAt": manifest["recordedAt"],
        "wrapperVersion": manifest.get("wrapperVersion"),
        "buildCommit": manifest.get("graphifyBuildCommit"),
        "modelId": manifest.get("modelId"),
        "promptHash": manifest.get("promptHash"),
    }


def _governed_id(scope: Sequence[str], record_type: str, raw_identity: str) -> str:
    return sha256_value({"scope": list(scope), "type": record_type, "raw": raw_identity})


def _metadata_hash(raw: Mapping[str, Any], fields: set[str]) -> str | None:
    metadata = {field: raw[field] for field in fields if field in raw}
    return sha256_value(metadata) if metadata else None


def _is_iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or "T" not in value or len(value) > 64:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() is not None


def _contains_poison(value: Any) -> bool:
    text = canonical_json(value)
    return any(pattern.search(text) for pattern in _POISON_PATTERNS)


def _error_code(error: BaseException) -> str:
    text = str(error).lower()
    if "codegraph" in text or "index" in text or "revision" in text:
        return "stale_code_reference"
    if "unsupported" in text:
        return "unsupported_field_or_value"
    if "endpoint" in text:
        return "missing_endpoint"
    if "confidence" in text:
        return "invalid_confidence"
    if "source" in text:
        return "missing_source_provenance"
    return "invalid_record"


def _source_policy(manifest: Mapping[str, Any], source_ref_hash: str) -> dict[str, Any]:
    policy = manifest.get("sourcePolicies", {}).get(source_ref_hash)
    if policy is not None:
        return {"acl": sorted(policy["acl"]), "sensitivity": policy["sensitivity"], "trust": policy["trust"]}
    return {
        "acl": sorted(manifest["defaultAcl"]),
        "sensitivity": manifest["sensitivity"],
        "trust": manifest["defaultTrust"],
    }


def _intersect_acl(*records: Mapping[str, Any]) -> list[str]:
    scopes = set(records[0]["acl"])
    for record in records[1:]:
        scopes.intersection_update(record["acl"])
    return sorted(scopes)


def _minimum_trust(*levels: str) -> str:
    rank = {"unverified": 0, "low": 1, "medium": 2, "high": 3}
    return min(levels, key=rank.__getitem__)


def _maximum_sensitivity(*levels: str) -> str:
    rank = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
    return max(levels, key=rank.__getitem__)
