"""Shared deterministic fixtures for the decision-accountability evals."""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "rhize-context-manager" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from graph_memory.contract import canonical_json, sha256_value  # noqa: E402
from graph_memory.decisions import (  # noqa: E402
    DecisionPreviewStore,
    InMemoryDecisionLedger,
    decision_bindings,
)


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
ACTOR = sha256_value("actor:fixture")
PRINCIPAL = sha256_value("principal:fixture")
SCOPES = ["decision:record", "group:rhize-tools"]
NONCE = "fixture-nonce-0001"


def policy_evaluation(*, policy_digest: str | None = None, result: str = "allow") -> dict[str, Any]:
    digest = policy_digest or sha256_value("policy:v1")
    evaluated_at = "2026-08-30T12:00:00Z"
    value = {
        "policyIdHash": sha256_value("policy:release"),
        "policyVersion": "policy-v1",
        "policyDigest": digest,
        "inputRefs": [sha256_value("input:one")],
        "result": result,
        "status": "reproduced",
        "evaluatorVersion": "fixture-v1",
    }
    output = sha256_value(value)
    return {
        "evaluationVersion": 1,
        "evaluationId": sha256_value([
            value["policyIdHash"], value["policyVersion"], output, evaluated_at
        ]),
        **value,
        "evaluatedAt": evaluated_at,
        "deterministic": True,
        "outputDigest": output,
    }


def proposal(*, source_revision: str = "source-v1", policy_digest: str | None = None) -> dict[str, Any]:
    evidence_items = [{
        "evidenceId": sha256_value("evidence:one"),
        "system": "git",
        "idHash": sha256_value("git:commit"),
        "revision": "commit-a",
        "digest": sha256_value("git:contents"),
        "status": "available",
    }]
    evaluation = policy_evaluation(policy_digest=policy_digest)
    return {
        "tenantRef": "tenant-rhize-internal",
        "projectRef": "project-rhize-tools",
        "domain": "release-governance",
        "decisionClass": "promotion",
        "source": {
            "system": "jira",
            "idHash": sha256_value("RT-fixture"),
            "revision": source_revision,
            "digest": sha256_value(f"RT-fixture:{source_revision}"),
        },
        "workflow": {"id": "rhize-devflow", "revision": "workflow-v1"},
        "actorHash": ACTOR,
        "acl": ["group:rhize-tools"],
        "sensitivity": "internal",
        "rationaleSummaryHash": sha256_value("evidence-policy-threshold-uncertainty"),
        "evidenceSet": {
            "evidenceSetId": sha256_value(evidence_items),
            "digest": sha256_value(evidence_items),
            "items": evidence_items,
        },
        "policySnapshot": {
            "policyIdHash": evaluation["policyIdHash"],
            "version": evaluation["policyVersion"],
            "digest": evaluation["policyDigest"],
            "status": "current",
        },
        "policyEvaluation": evaluation,
        "approval": {
            "approvalIdHash": sha256_value("approval:one"),
            "source": "jira",
            "revision": "approval-v1",
            "digest": sha256_value("approval:one:v1"),
            "actorHash": ACTOR,
            "scopes": ["decision:record", "group:rhize-tools"],
            "granted": True,
            "expiresAt": _iso(NOW + timedelta(hours=1)),
        },
        "retentionUntil": _iso(NOW + timedelta(days=1)),
    }


def record_one(root: Path, *, source_revision: str = "source-v1", idempotency_key: str = "decision-one"):
    store = DecisionPreviewStore(root)
    ledger = InMemoryDecisionLedger(store)
    item = proposal(source_revision=source_revision)
    preview = ledger.preview(
        item,
        principal_hash=PRINCIPAL,
        principal_scopes=SCOPES,
        idempotency_key=idempotency_key,
        nonce=NONCE,
        now=NOW,
    )
    result = ledger.record(
        preview["previewId"],
        tenant_ref=item["tenantRef"],
        project_ref=item["projectRef"],
        actor_hash=ACTOR,
        workflow=item["workflow"],
        principal_hash=PRINCIPAL,
        principal_scopes=SCOPES,
        nonce=NONCE,
        current_bindings=decision_bindings(item),
        role=ledger.RECORD_ROLE,
        now=NOW,
    )
    decision_id = result["record"]["decisionId"]
    return ledger, item, decision_id, result


def correction_approval() -> dict[str, Any]:
    value = copy.deepcopy(proposal()["approval"])
    value["approvalIdHash"] = sha256_value("approval:correction")
    value["digest"] = sha256_value("approval:correction:v1")
    return value


def load_fixture(name: str) -> dict[str, Any]:
    path = ROOT / "evals" / "decision-accountability" / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


__all__ = [
    "ACTOR", "NONCE", "NOW", "PRINCIPAL", "ROOT", "SCOPES", "canonical_json",
    "correction_approval", "decision_bindings", "load_fixture", "policy_evaluation",
    "proposal", "record_one", "sha256_value",
]
