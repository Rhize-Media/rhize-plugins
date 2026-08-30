"""Minimal, validated PROV-O export for accepted Rhize decision records.

The export is an interoperability view, never the internal authority or proof of compliance.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contract import sha256_value
from .decisions import DecisionError, validate_decision_record


PROV_CONTEXT = {
    "prov": "http://www.w3.org/ns/prov#",
    "rhize": "https://rhize.media/ns/decision-accountability#",
}


def export_prov_o(record: Mapping[str, Any]) -> dict[str, Any]:
    """Map one validated, non-purged decision into a small privacy-safe PROV-O JSON-LD view."""

    validate_decision_record(record)
    if record["status"] == "purged":
        raise DecisionError("purged decisions cannot be exported")
    decision_id = _urn("decision", record["decisionId"])
    evidence_id = _urn("evidence-set", record["evidenceSet"]["evidenceSetId"])
    policy_id = _urn("policy", record["policySnapshot"]["policyIdHash"])
    approval_id = _urn("approval", record["approval"]["approvalIdHash"])
    actor_id = _urn("actor", record["actorHash"])
    graph: list[dict[str, Any]] = [
        {
            "@id": decision_id,
            "@type": "prov:Activity",
            "rhize:decisionClass": record["decisionClass"],
            "rhize:status": record["status"],
            "prov:used": [evidence_id, policy_id, approval_id],
            "prov:wasAssociatedWith": actor_id,
        },
        {
            "@id": evidence_id,
            "@type": "prov:Collection",
            "rhize:digest": record["evidenceSet"]["digest"],
        },
        {
            "@id": policy_id,
            "@type": "prov:Entity",
            "rhize:digest": record["policySnapshot"]["digest"],
            "rhize:version": record["policySnapshot"]["version"],
        },
        {
            "@id": approval_id,
            "@type": "prov:Entity",
            "rhize:digest": record["approval"]["digest"],
        },
        {"@id": actor_id, "@type": "prov:Agent"},
    ]
    for effect in record["effects"]:
        graph.append({
            "@id": _urn("effect", effect["effectId"]),
            "@type": "prov:Activity",
            "prov:wasInformedBy": decision_id,
            "rhize:status": effect["status"],
        })
    for outcome in record["outcomes"]:
        graph.append({
            "@id": _urn("outcome", outcome["observationId"]),
            "@type": "prov:Entity",
            "prov:wasGeneratedBy": _urn("effect", outcome["effectId"]),
            "rhize:sourceReceiptHash": outcome["sourceReceiptHash"],
            "rhize:status": outcome["status"],
        })
    export = {
        "@context": PROV_CONTEXT,
        "@graph": graph,
        "rhize:exportDigest": sha256_value(graph),
        "rhize:authority": "interoperability_view_only",
    }
    validate_prov_o(export)
    return export


def validate_prov_o(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "@context", "@graph", "rhize:exportDigest", "rhize:authority"
    }:
        raise DecisionError("PROV-O export has missing or unknown fields")
    if value["@context"] != PROV_CONTEXT or value["rhize:authority"] != "interoperability_view_only":
        raise DecisionError("PROV-O export context or authority marker is invalid")
    graph = value["@graph"]
    if not isinstance(graph, list) or not 5 <= len(graph) <= 261:
        raise DecisionError("PROV-O graph is outside the bounded export contract")
    identifiers: set[str] = set()
    for item in graph:
        if not isinstance(item, Mapping) or "@id" not in item or "@type" not in item:
            raise DecisionError("PROV-O graph item is invalid")
        identifier = item["@id"]
        if not isinstance(identifier, str) or not identifier.startswith("urn:rhize:"):
            raise DecisionError("PROV-O identifiers must be Rhize URNs")
        if identifier in identifiers:
            raise DecisionError("PROV-O identifiers must be unique")
        identifiers.add(identifier)
        if item["@type"] not in {"prov:Activity", "prov:Collection", "prov:Entity", "prov:Agent"}:
            raise DecisionError("unsupported PROV-O type")
    if value["rhize:exportDigest"] != sha256_value(graph):
        raise DecisionError("PROV-O export digest mismatch")


def _urn(kind: str, identifier: str) -> str:
    return f"urn:rhize:{kind}:{identifier}"


__all__ = ["export_prov_o", "validate_prov_o"]
