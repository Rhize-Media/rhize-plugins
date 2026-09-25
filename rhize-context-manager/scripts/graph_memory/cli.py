#!/usr/bin/env python3
"""Host-neutral CLI for the governed graph-memory contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from graph_memory.contract import ContractError, canonical_json, compile_ontology, load_json, sha256_value
    from graph_memory.decisions import (
        DECISION_CONTRACT_VERSION,
        DecisionError,
        DecisionPreviewStore,
        InMemoryDecisionLedger,
        parse_time,
    )
    from graph_memory.store import InMemoryNeo4jAdapter, QueryBudget, StoreError
    from graph_memory.translate import GraphifyTranslator
    from context_experiments.typed_candidates import assess as assess_candidates, write_receipt
else:
    from .contract import ContractError, canonical_json, compile_ontology, load_json, sha256_value
    from .decisions import (
        DECISION_CONTRACT_VERSION,
        DecisionError,
        DecisionPreviewStore,
        InMemoryDecisionLedger,
        parse_time,
    )
    from .store import InMemoryNeo4jAdapter, QueryBudget, StoreError
    from .translate import GraphifyTranslator
    from context_experiments.typed_candidates import assess as assess_candidates, write_receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="graph-memory",
        description="Preview and verify governed Rhize graph operations without live Neo4j access.",
    )
    parser.add_argument("--core", type=Path, help="override the canonical core ontology path")
    parser.add_argument("--pack", type=Path, action="append", default=[], help="namespaced extension pack")
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("compile", help="compile writer, reader, and migration contracts")
    subparsers.add_parser("status", help="report the disabled-live-adapter contract state")

    for command in ("validate", "preview", "ingest", "query"):
        child = subparsers.add_parser(command)
        _add_artifact_arguments(child)
    ingest = subparsers.choices["ingest"]
    ingest.add_argument("--role", required=True, choices=[InMemoryNeo4jAdapter.INGEST_ROLE])
    ingest.add_argument("--idempotency-key", required=True)
    ingest.add_argument(
        "--failure-at", choices=["after_validation", "after_stage", "before_publish"]
    )

    query = subparsers.choices["query"]
    query.add_argument("--role", required=True, choices=[InMemoryNeo4jAdapter.QUERY_ROLE, InMemoryNeo4jAdapter.REVIEW_ROLE])
    query.add_argument("--principal-scope", action="append", required=True)
    query.add_argument(
        "--operation",
        required=True,
        choices=["query_context", "get_claim_sources", "get_related_artifacts"],
    )
    query.add_argument("--query-text")
    query.add_argument("--record-id")
    query.add_argument("--depth", type=int, default=1)
    query.add_argument("--limit", type=int, default=20)
    query.add_argument("--runtime-ms", type=int, default=250)
    query.add_argument("--typed-shadow", action="store_true", help="score authorized results with local Laya without changing them")
    query.add_argument("--typed-signal", action="append", default=[], help="redacted one-token task signal; at most eight")
    query.add_argument("--typed-model", default="typed-decisions")
    query.add_argument("--typed-base-url", default="http://127.0.0.1:8000")
    query.add_argument("--typed-receipt-root", type=Path, default=Path.home() / ".local/share/rhize/typed-decisions/receipts")

    migrate = subparsers.add_parser("migrate", help="verify checksummed migrations in the fake adapter")
    migrate.add_argument("--role", required=True, choices=[InMemoryNeo4jAdapter.MIGRATION_ROLE])

    manifest = subparsers.add_parser("manifest", help="create a reviewable manifest for a graph.json artifact")
    manifest.add_argument("--graph", type=Path, required=True)
    manifest.add_argument("--corpus-id", required=True)
    manifest.add_argument("--source-revision", required=True)
    manifest.add_argument("--extractor-version", required=True)
    manifest.add_argument("--recorded-at", required=True)
    manifest.add_argument("--acl", action="append", required=True)
    manifest.add_argument(
        "--sensitivity",
        choices=["public", "internal", "confidential", "restricted"],
        default="internal",
    )
    manifest.add_argument(
        "--default-trust",
        choices=["high", "medium", "low", "unverified"],
        default="medium",
    )
    manifest.add_argument("--wrapper-version")
    manifest.add_argument("--build-commit")
    manifest.add_argument("--model-id")
    manifest.add_argument("--prompt-hash")

    decision = subparsers.add_parser(
        "decision",
        help="preview decisions or report governed projection availability",
    )
    decision_parsers = decision.add_subparsers(dest="decision_operation", required=True)
    preview = decision_parsers.add_parser("preview", help="create a private source-bound preview")
    preview.add_argument("--proposal", type=Path, required=True)
    preview.add_argument(
        "--preview-root",
        type=Path,
        required=True,
        help="absolute caller-owned mode-0700 directory outside the repository",
    )
    preview.add_argument("--principal-hash", required=True)
    preview.add_argument("--principal-scope", action="append", required=True)
    preview.add_argument("--idempotency-key", required=True)
    preview.add_argument("--nonce", required=True)
    preview.add_argument("--ttl-seconds", type=int, default=600)
    preview.add_argument("--at", help="timezone-aware time override for deterministic fixtures")

    record = decision_parsers.add_parser(
        "record", help="report availability for governed durable recording"
    )
    record.add_argument("--preview-id", required=True)

    decision_parsers.add_parser("status", help="report offline/live decision adapter availability")
    for operation in ("explain", "impact", "correct"):
        operation_parser = decision_parsers.add_parser(
            operation,
            help=f"report availability for the governed {operation} operation",
        )
        operation_parser.add_argument("--decision-id", required=True)
    precedents = decision_parsers.add_parser(
        "precedents", help="report availability for the governed precedent query"
    )
    precedents.add_argument("--decision-class", required=True)
    precedents.add_argument("--domain", required=True)
    precedents.add_argument("--current-policy-digest", required=True)

    hygiene = subparsers.add_parser(
        "hygiene",
        help="report governed graph-identity review capability",
    )
    hygiene_parsers = hygiene.add_subparsers(dest="hygiene_operation", required=True)
    hygiene_parsers.add_parser("status", help="report offline identity-review availability")
    for operation in HYGIENE_OPERATIONS:
        child = hygiene_parsers.add_parser(
            operation, help=f"report availability for the governed {operation} operation"
        )
        child.add_argument(
            "--state-artifact",
            type=Path,
            help="future caller-owned private state artifact",
        )
    return parser


def _add_artifact_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--namespace", required=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = _run(args)
    except (ContractError, DecisionError, StoreError, OSError, json.JSONDecodeError) as exc:
        print(canonical_json({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None))
    return 0


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "decision":
        return _run_decision(args)
    if args.command == "hygiene":
        return _run_hygiene(args)
    ontology = compile_ontology(args.core, args.pack)
    if args.command == "compile":
        return ontology.to_dict()
    if args.command == "status":
        return InMemoryNeo4jAdapter(ontology).status() | {
            "ontologyChecksum": ontology.checksum,
            "liveCanaryIssue": "RT-159",
        }
    if args.command == "migrate":
        store = InMemoryNeo4jAdapter(ontology)
        return {"applied": store.apply_migrations(role=args.role), "status": store.status()}
    if args.command == "manifest":
        artifact = load_json(args.graph)
        artifact_commit = artifact.get("built_at_commit")
        if args.build_commit and artifact_commit and args.build_commit != artifact_commit:
            raise ContractError("supplied build commit does not match the Graphify artifact")
        build_commit = args.build_commit or artifact_commit
        return {
            "schemaVersion": 1,
            "corpusId": args.corpus_id,
            "sourceRevision": args.source_revision,
            "artifactSha256": sha256_value(artifact),
            "extractorVersion": args.extractor_version,
            "recordedAt": args.recorded_at,
            "defaultAcl": sorted(set(args.acl)),
            "defaultTrust": args.default_trust,
            "sensitivity": args.sensitivity,
            **({"wrapperVersion": args.wrapper_version} if args.wrapper_version else {}),
            **({"graphifyBuildCommit": build_commit} if build_commit else {}),
            **({"modelId": args.model_id} if args.model_id else {}),
            **({"promptHash": args.prompt_hash} if args.prompt_hash else {}),
        }

    artifact = load_json(args.graph)
    manifest = load_json(args.manifest)
    compilation = GraphifyTranslator(ontology).translate(
        artifact, manifest, tenant=args.tenant, namespace=args.namespace
    )
    if args.command == "preview":
        return compilation
    if args.command == "validate":
        return {
            "status": "valid",
            "compilationHash": compilation["compilationId"],
            "ontologyChecksum": compilation["ontologyChecksum"],
            "counts": {
                "records": len(compilation["records"]),
                "relationships": len(compilation["relationships"]),
                "rejections": len(compilation["rejections"]),
                "quarantined": sum(
                    1 for item in [*compilation["records"], *compilation["relationships"]]
                    if item["quarantined"]
                ),
            },
        }

    store = InMemoryNeo4jAdapter(ontology)
    store.apply_migrations(role=InMemoryNeo4jAdapter.MIGRATION_ROLE)
    if args.command == "ingest":
        receipt = store.ingest(
            compilation,
            role=args.role,
            idempotency_key=args.idempotency_key,
            expected_current=None,
            failure_at=args.failure_at,
        )
        return {"receipt": receipt, "status": store.status()}

    store.ingest(
        compilation,
        role=InMemoryNeo4jAdapter.INGEST_ROLE,
        idempotency_key=f"query-preview:{compilation['compilationId']}",
        expected_current=None,
    )
    result = store.query(
        args.operation,
        tenant_key=compilation["tenantKey"],
        namespace_key=compilation["namespaceKey"],
        corpus_key=compilation["corpusKey"],
        principal_scopes=args.principal_scope,
        role=args.role,
        budget=QueryBudget(args.depth, args.limit, args.runtime_ms),
        query_text=args.query_text,
        record_id=args.record_id,
    )
    if args.typed_shadow:
        result["typedShadow"] = _score_authorized_graph_results(args, result, compilation)
    return result


def _score_authorized_graph_results(args: argparse.Namespace, result: dict, compilation: dict) -> dict:
    """Score only records the governed query has already ACL-filtered."""
    if not result["results"]:
        return {"status": "not_applicable", "variant": "A_incumbent", "reasonCode": "no_visible_results"}
    try:
        if not 1 <= len(args.typed_signal) <= 8 or any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", item) for item in args.typed_signal):
            raise ValueError("bounded redacted task signals required")
        visible = result["results"][:8]
        candidates = []
        for record in visible:
            candidate_id = "g" + hashlib.sha256(record["governedId"].encode()).hexdigest()[:16]
            hints = [re.sub(r"[^a-z0-9_-]+", "-", str(record[key]).lower()).strip("-")[:48] or "unknown" for key in ("recordType", "subtype", "trust")]
            candidates.append({"id": candidate_id, "hints": hints, "protected": True})
        state = {"schema": "rhize-typed-candidates-v1", "capability": "graph_memory",
                 "sourceSha256": sha256_value({"compilationId": compilation["compilationId"], "result": result}),
                 "taskSignals": args.typed_signal, "candidates": candidates,
                 "incumbentIds": [item["id"] for item in candidates]}
        assessment = assess_candidates(state, args.typed_model, args.typed_base_url)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        assessment = {"status": "unavailable", "variant": "A_incumbent",
                      "reasonCode": type(exc).__name__, "incumbentAltered": False}
    try:
        receipt = str(write_receipt(assessment, args.typed_receipt_root))
    except (OSError, ValueError):
        receipt = None
        assessment = {"status": "unavailable", "variant": "A_incumbent"}
    return {"status": assessment["status"], "variant": assessment["variant"],
            "candidatesEvaluated": min(len(result["results"]), 8),
            "candidatesDeferred": max(len(result["results"]) - 8, 0),
            "receipt": receipt, "resultsAltered": False}


def _run_decision(args: argparse.Namespace) -> dict[str, Any]:
    operation = args.decision_operation
    if operation == "status":
        return {
            "contractVersion": DECISION_CONTRACT_VERSION,
            "liveNeo4jEnabled": False,
            "offlineOperations": ["preview"],
            "projectionOperations": ["correct", "explain", "impact", "precedents", "record"],
            "shadowStoreCreated": False,
            "status": "offline_contract_only",
        }
    if operation in {"correct", "explain", "impact", "precedents", "record"}:
        return {
            "contractVersion": DECISION_CONTRACT_VERSION,
            "liveNeo4jEnabled": False,
            "operation": operation,
            "reason": "governed_decision_projection_not_configured",
            "shadowStoreCreated": False,
            "status": "unavailable",
        }

    at = parse_time(args.at, "at") if args.at else None
    proposal = load_json(args.proposal)
    preview = InMemoryDecisionLedger(DecisionPreviewStore(args.preview_root)).preview(
        proposal,
        principal_hash=args.principal_hash,
        principal_scopes=args.principal_scope,
        idempotency_key=args.idempotency_key,
        nonce=args.nonce,
        ttl_seconds=args.ttl_seconds,
        now=at,
    )
    return {
        "contractVersion": DECISION_CONTRACT_VERSION,
        "liveNeo4jEnabled": False,
        "previewReceipt": {
            "previewId": preview["previewId"],
            "previewDigest": preview["previewDigest"],
            "bindingDigest": preview["bindingDigest"],
            "expiresAt": preview["expiresAt"],
        },
        "publication": "not_published",
        "status": "previewed_offline",
    }


HYGIENE_OPERATIONS = (
    "list",
    "show",
    "lease",
    "preview",
    "decide",
    "defer",
    "reverse",
    "consolidate",
    "quality",
)


def _run_hygiene(args: argparse.Namespace) -> dict[str, Any]:
    operation = args.hygiene_operation
    capability = {
        "automaticSameAs": False,
        "contractVersion": 1,
        "inProcessContractOperations": list(HYGIENE_OPERATIONS),
        "liveNeo4jEnabled": False,
        "privateStateAdapterConfigured": False,
        "projectionPublished": False,
        "sharedCliOperations": ["status"],
    }
    if operation == "status":
        return capability | {"status": "offline_contract_only"}
    return capability | {
        "operation": operation,
        "reason": "governed_private_state_adapter_not_configured",
        "shadowStoreCreated": False,
        "stateArtifactSupplied": args.state_artifact is not None,
        "status": "unavailable",
    }


if __name__ == "__main__":
    raise SystemExit(main())
