"""Explicit topic catalogs and verified expansion; no retrieval or host hooks."""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .core import (
    Candidate, MemoryContextAssembler, MemoryStore, _strict_keys,
    _validate_pack_payload, parse_time, sha256, utc_now,
)

TOPIC_PROTOCOL = "rhize-memory-topic-v1"
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_CANDIDATES = 200
MAX_SELECTION = 5


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def estimated_tokens(text: str) -> int:
    """UTF-8 bytes/4 estimate, not a model tokenizer or billed usage."""
    return (len(text.encode("utf-8")) + 3) // 4


def read_document(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = handle.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("awareness input exceeds 8 MiB")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("awareness input must be an object")
    return value


def _row(envelope: dict[str, Any], content: str) -> str:
    # Include identity, authority and conflict key in both arms' measured presentation.
    return canonical({
        "id": envelope["memoryId"], "type": envelope["memoryType"],
        "source": [envelope["sourceSystem"], envelope["sourceIdHash"], envelope["sourceRevision"]],
        "trust": envelope["trustClass"], "authority": envelope["authorityClass"],
        "role": envelope["contentRole"], "processing": envelope["processingPolicy"],
        "claim": envelope["claimKeyHash"], "validUntil": envelope["validUntil"],
        "content": content,
    }) + "\n"


def render_context(manifest: dict[str, Any], payload: dict[str, Any]) -> str:
    return "".join(_row(c, payload["payloads"][c["payloadRef"]]) for c in manifest["candidates"])


class _RenderedAssembler(MemoryContextAssembler):
    """Reuse v1 integrity/store contracts while accounting for visible metadata."""

    def _normalize_candidate(self, *args: Any, **kwargs: Any) -> tuple[Candidate | None, str]:
        candidate, reason = super()._normalize_candidate(*args, **kwargs)
        if candidate is None:
            return None, reason
        return Candidate(candidate.envelope, candidate.content, estimated_tokens(_row(candidate.envelope, candidate.content))), reason

    def _select(self, candidates: list[Candidate], request: dict[str, Any]) -> tuple[list[Candidate], dict[str, int]]:
        unique: dict[str, Candidate] = {}
        duplicates = 0
        for candidate in candidates:
            envelope = candidate.envelope
            key = canonical([envelope[k] for k in ("sourceSystem", "sourceIdHash", "sourceRevision", "scope")])
            previous = unique.get(key)
            if previous is not None:
                if previous != candidate:
                    raise ValueError("ambiguous source revision binding")
                duplicates += 1
            unique[key] = candidate
        selected, exclusions = super()._select(list(unique.values()), request)
        if duplicates:
            exclusions["exact_duplicate"] = duplicates
        return selected, exclusions


class _CatalogAssembler(_RenderedAssembler):
    def _conflicts(self, selected: list[Candidate]) -> dict[str, str]:
        # Different catalog wording is not itself a contradiction in the source body.
        by_claim: dict[str, list[tuple[str, str]]] = {}
        for item in selected:
            claim = item.envelope["claimKeyHash"]
            if not claim:
                continue
            digest = item.envelope["contentHash"]
            try:
                descriptor = json.loads(item.content)
                if isinstance(descriptor, dict) and descriptor.get("protocol") == TOPIC_PROTOCOL:
                    digest = descriptor["detailDigest"]
            except (ValueError, KeyError):
                pass
            by_claim.setdefault(claim, []).append((item.envelope["memoryId"], digest))
        return {memory_id: sha256(f"conflict:{claim}") for claim, records in by_claim.items()
                if len({digest for _, digest in records}) > 1 for memory_id, _ in records}


def _bounded(document: dict[str, Any]) -> None:
    if not isinstance(document, dict) or len(canonical(document).encode()) > MAX_INPUT_BYTES:
        raise ValueError("awareness input must be an object within 8 MiB")
    adapters = document.get("adapters")
    if not isinstance(adapters, list) or len(adapters) > 20:
        raise ValueError("awareness adapters must be an array of at most 20")
    count = 0
    for adapter in adapters:
        if not isinstance(adapter, dict) or not isinstance(adapter.get("candidates", []), list):
            raise ValueError("invalid awareness adapter")
        count += len(adapter.get("candidates", []))
    if count > MAX_CANDIDATES:
        raise ValueError("awareness input exceeds 200 candidates")
    request = document.get("request")
    if not isinstance(request, dict) or type(request.get("totalTokenBudget", 4000)) is not int:
        raise ValueError("totalTokenBudget must be an integer")


def _topic(value: Any, now: datetime) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("topic must be an object")
    _strict_keys(value, {"label", "keywords", "detailDigest", "verifiedAt"}, "topic")
    label, keywords, digest, verified = (value.get(k) for k in ("label", "keywords", "detailDigest", "verifiedAt"))
    if not isinstance(label, str) or not label.strip() or len(label) > 160:
        raise ValueError("topic label must have 1 to 160 characters")
    if not isinstance(keywords, list) or len(keywords) > 8 or any(not isinstance(k, str) or not k.strip() or len(k) > 40 for k in keywords):
        raise ValueError("topic keywords must contain at most 8 short strings")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("topic detailDigest must be a SHA-256 digest")
    if not isinstance(verified, str) or parse_time(verified) > now:
        raise ValueError("topic verifiedAt must not be in the future")
    return dict(value)


def build_catalog(document: dict[str, Any], now: datetime | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    _bounded(document)
    _strict_keys(document, {"schemaVersion", "request", "adapters", "catalogTokenBudget", "alreadyPresent"}, "catalog")
    build_time = now or utc_now()
    assembler = _CatalogAssembler()
    request = assembler._validate_request(document["request"])
    budget = document.get("catalogTokenBudget", 600)
    if type(budget) is not int or not 64 <= budget <= request["totalTokenBudget"]:
        raise ValueError("catalogTokenBudget must be between 64 and totalTokenBudget")
    present = document.get("alreadyPresent", [])
    if not isinstance(present, list) or len(present) > MAX_CANDIDATES:
        raise ValueError("alreadyPresent must be a bounded array of exact source bindings")
    present_keys = set()
    for binding in present:
        if not isinstance(binding, dict) or set(binding) != {"sourceSystem", "sourceId", "sourceRevision", "detailDigest"} or not all(isinstance(v, str) for v in binding.values()):
            raise ValueError("alreadyPresent requires exact system/id/revision/digest bindings")
        present_keys.add(canonical(binding))
    transformed = copy.deepcopy(document)
    transformed.pop("catalogTokenBudget", None)
    transformed.pop("alreadyPresent", None)
    transformed["request"]["totalTokenBudget"] = budget
    for adapter in transformed["adapters"]:
        converted = []
        for candidate in adapter.get("candidates", []):
            if not isinstance(candidate, dict) or "content" in candidate:
                raise ValueError("catalog candidates supply topic metadata instead of content")
            topic = _topic(candidate.pop("topic", None), build_time)
            candidate["content"] = canonical({"protocol": TOPIC_PROTOCOL, "adapter": adapter.get("name"), **topic})
            # Scope and ACL checks still run even for suppressed, already-present records.
            normalized, _ = assembler._normalize_candidate(candidate, adapter.get("name"), adapter.get("memoryType"), adapter.get("status"), request, build_time)
            binding = {k: candidate.get(k) for k in ("sourceSystem", "sourceId", "sourceRevision")} | {"detailDigest": topic["detailDigest"]}
            if normalized is None or canonical(binding) not in present_keys:
                converted.append(candidate)
        adapter["candidates"] = converted
    return assembler.assemble(transformed, build_time)


def expand_catalog(
    store: MemoryStore, manifest_path: Path, payload_path: Path,
    selection: list[str], details: dict[str, Any], source_state: dict[str, str],
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _bounded(details)
    _strict_keys(details, {"schemaVersion", "request", "adapters"}, "detail request")
    if not isinstance(selection, list) or len(selection) > MAX_SELECTION or any(not isinstance(x, str) for x in selection) or len(set(selection)) != len(selection):
        raise ValueError("selection must contain at most 5 unique catalog memory IDs")
    if not isinstance(source_state, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in source_state.items()):
        raise ValueError("source state must map exact source IDs to revisions")
    build_time = now or utc_now()
    for path in (manifest_path, payload_path):
        if path.lstat().st_size > MAX_INPUT_BYTES:
            raise ValueError("catalog artifact exceeds 8 MiB")
    verification = store.verify(manifest_path, payload_path, now=build_time, source_state=source_state)
    if not verification["valid"]:
        raise ValueError("catalog verification failed: " + ", ".join(verification["reasons"]))
    catalog, catalog_payload = read_document(manifest_path), read_document(payload_path)
    # Verification read the same files; validate our snapshots again against their hashes.
    _validate_pack_payload(catalog, catalog_payload)
    if catalog["packId"] != verification["packId"]:
        raise ValueError("catalog changed during expansion")
    assembler = _RenderedAssembler()
    request = assembler._validate_request(details["request"])
    expected = {"tenantHash": sha256(request["tenant"]), "projectHash": sha256(request["project"]), "taskHash": sha256(request["task"]) if request["task"] else None, "requestHash": request["requestHash"]}
    if any(catalog[k] != v for k, v in expected.items()):
        raise ValueError("expansion request is not bound to the catalog scope/query")
    topics = {c["memoryId"]: c for c in catalog["candidates"]}
    if set(selection) - set(topics):
        raise ValueError("selection contains an unknown catalog memory ID")
    # Recompute from the actual presentation, rather than trusting a supplied token count.
    catalog_tokens = sum(estimated_tokens(_row(c, catalog_payload["payloads"][c["payloadRef"]])) for c in catalog["candidates"])
    remaining = request["totalTokenBudget"] - catalog_tokens
    if remaining < 1:
        raise ValueError("combined catalog/detail budget exhausted")
    transformed = copy.deepcopy(details)
    transformed["request"]["totalTokenBudget"] = remaining
    wanted = {}
    for memory_id in selection:
        envelope = topics[memory_id]
        descriptor = json.loads(catalog_payload["payloads"][envelope["payloadRef"]])
        if (not isinstance(descriptor, dict) or descriptor.get("protocol") != TOPIC_PROTOCOL
                or set(descriptor) != {"protocol", "adapter", "label", "keywords", "detailDigest", "verifiedAt"}
                or not isinstance(descriptor["adapter"], str)):
            raise ValueError("selected pack is not a topic catalog")
        _topic({k: v for k, v in descriptor.items() if k not in {"protocol", "adapter"}}, build_time)
        key = (descriptor["adapter"], envelope["sourceIdHash"], envelope["sourceRevision"])
        if key in wanted:
            raise ValueError("ambiguous selected topic identity")
        wanted[key] = (envelope, descriptor)
    found = set()
    variable_fields = {"memoryId", "contentHash", "payloadRef", "rank", "estimatedTokens", "conflictGroupHash"}
    for adapter in transformed["adapters"]:
        _, normalized, _ = assembler._normalize_adapter(adapter, request, build_time)
        normalized_by_id = {c.envelope["memoryId"]: c for c in normalized}
        accepted = []
        for candidate in adapter.get("candidates", []):
            key = (adapter["name"], sha256(candidate["sourceId"]), candidate["sourceRevision"])
            if key not in wanted:
                continue
            topic_envelope, descriptor = wanted[key]
            detail_id = sha256(f"{adapter['name']}:{candidate['sourceId']}:{candidate['sourceRevision']}:{sha256(candidate['content'])}")
            detail = normalized_by_id.get(detail_id)
            if detail is None or detail.envelope["contentHash"] != descriptor["detailDigest"]:
                raise ValueError("selected detail is denied or has a mismatched digest")
            if any(detail.envelope.get(k) != v for k, v in topic_envelope.items() if k not in variable_fields):
                raise ValueError("selected detail metadata changed since catalog creation")
            if key in found:
                raise ValueError("duplicate selected detail")
            found.add(key)
            accepted.append(candidate)
        adapter["candidates"] = accepted
    if found != set(wanted):
        raise ValueError("selected details unavailable or missing")
    manifest, payload = assembler.assemble(transformed, build_time)
    # Recheck revocation, revisions, and files at the consumption boundary.
    final_verification = store.verify(manifest_path, payload_path, now=build_time, source_state=source_state)
    if not final_verification["valid"] or final_verification["packId"] != catalog["packId"]:
        raise ValueError("catalog changed during expansion")
    return manifest, payload, {
        "catalogEstimatedTokens": catalog_tokens,
        "detailEstimatedTokens": manifest["totalEstimatedTokens"],
        "combinedEstimatedTokens": catalog_tokens + manifest["totalEstimatedTokens"],
        "selectedCount": len(selection), "expandedCount": len(manifest["candidates"]),
        "estimateMethod": "sum_ceil_utf8_rendered_row_bytes_div_4",
        "automaticInjection": False, "writeBack": False,
    }
