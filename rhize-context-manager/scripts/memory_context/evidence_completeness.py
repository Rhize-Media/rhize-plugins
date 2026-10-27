"""Advisory declared-source coverage; never a semantic completeness or approval gate."""
from __future__ import annotations

from typing import Any

from .core import MemoryContextAssembler, _safe_id, parse_time, sha256, validate_manifest


def diagnose(document: dict[str, Any], manifest: dict[str, Any], requirements: dict[str, Any],
             assembler: MemoryContextAssembler | None = None) -> dict[str, Any]:
    """Bind a source checklist to the exact preview without changing its selection."""
    validate_manifest(manifest)
    if not isinstance(requirements, dict) or set(requirements) != {"schemaVersion", "requirements"} or requirements["schemaVersion"] != 1:
        raise ValueError("evidence requirements must contain schemaVersion 1 and requirements")
    items = requirements["requirements"]
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("evidence requirements must be an array of at most 100 items")
    normalized = []
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "adapter", "sourceId", "sourceRevision"}:
            raise ValueError("each requirement needs id, adapter, sourceId and sourceRevision")
        for key in item:
            _safe_id(item[key], f"requirement {key}")
        if item["id"] in seen:
            raise ValueError("duplicate evidence requirement id")
        seen.add(item["id"])
        normalized.append(item)

    assembler = assembler or MemoryContextAssembler()
    now = parse_time(manifest["createdAt"])
    # Reassemble at the same instant so foreign manifests cannot grade another request.
    expected, _ = assembler.assemble(document, now)
    if expected != manifest:
        raise ValueError("evidence report must bind the exact source document and preview")
    request = assembler._validate_request(document["request"])
    eligible = {}
    for adapter in document["adapters"]:
        _, candidates, _ = assembler._normalize_adapter(adapter, request, now)
        eligible[adapter["name"]] = candidates
    statuses = {item["name"]: item for item in manifest["adapterStatuses"]}
    selected = {item["memoryId"] for item in manifest["candidates"]}
    rows = []
    for item in normalized:
        status = statuses.get(item["adapter"])
        matches = [candidate for candidate in eligible.get(item["adapter"], [])
                   if candidate.envelope["sourceIdHash"] == sha256(item["sourceId"])
                   and candidate.envelope["sourceRevision"] == item["sourceRevision"]]
        if any(candidate.envelope["memoryId"] in selected for candidate in matches):
            state, reason = "selected", "exact_source_revision_present"
        elif matches:
            state, reason = "excluded", "selection_budget"
        elif status is None:
            state, reason = "unavailable", "adapter_not_supplied"
        elif status["status"] == "empty":
            state, reason = "empty", "adapter_returned_no_records"
        elif status["status"] not in {"available", "partial"}:
            state, reason = "unavailable", status["status"]
        elif status["status"] == "partial":
            state, reason = "unknown", "adapter_partial"
        else:
            # Denied records never establish that a foreign/private source exists.
            state, reason = "missing", "not_in_admissible_snapshot"
        rows.append({"requirementIdHash": sha256(item["id"]), "sourceIdHash": sha256(item["sourceId"]),
                     "sourceRevisionHash": sha256(item["sourceRevision"]), "status": state, "reason": reason})
    return {"schemaVersion": "memory-evidence-completeness-v1", "packId": manifest["packId"],
            "payloadHash": manifest["payloadHash"], "advisory": True,
            "scope": "declared_exact_source_revisions_only", "semanticCompleteness": None,
            "coverage": "unknown" if not rows else ("complete" if all(row["status"] == "selected" for row in rows) else "incomplete"),
            "requirements": rows}
