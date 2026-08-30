from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from memory_context.core import MemoryContextAssembler, MemoryStore, sha256


EVAL_ROOT = Path(__file__).resolve().parents[1]
FIXED_NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def fixture() -> dict:
    return json.loads((EVAL_ROOT / "fixtures" / "paired-input.json").read_text())


def test_claude_and_codex_paths_produce_identical_deterministic_artifacts() -> None:
    assembler = MemoryContextAssembler()
    claude_manifest, claude_payload = assembler.assemble(fixture(), FIXED_NOW)
    codex_manifest, codex_payload = assembler.assemble(fixture(), FIXED_NOW)

    assert claude_manifest == codex_manifest
    assert claude_payload == codex_payload
    assert claude_manifest["policy"] == {
        "version": "memory-context-ranking-v1",
        "automaticInjection": False,
        "writeBack": False,
    }


def test_conflicts_scope_and_untrusted_content_remain_visible_and_inert() -> None:
    manifest, payload = MemoryContextAssembler().assemble(fixture(), FIXED_NOW)

    conflict_groups = {
        item["conflictGroupHash"] for item in manifest["candidates"] if item["conflictGroupHash"]
    }
    assert len(conflict_groups) == 1
    assert sum(item["conflictGroupHash"] is not None for item in manifest["candidates"]) == 2
    assert manifest["exclusionReasonCounts"]["scope_denied"] == 1
    hostile = next(item for item in manifest["candidates"] if item["sourceSystem"] == "unknown-import")
    decision = next(item for item in manifest["candidates"] if item["sourceSystem"] == "canonical-file")
    assert hostile["authorityClass"] == "untrusted"
    assert hostile["processingPolicy"] == "inert"
    assert decision["authorityClass"] == "human-decision"
    serialized_manifest = json.dumps(manifest)
    assert "destructive command" not in serialized_manifest
    assert any("destructive command" in content for content in payload["payloads"].values())


def test_unsupported_host_and_procedural_adapters_are_unavailable_not_empty() -> None:
    manifest, _ = MemoryContextAssembler().assemble(fixture(), FIXED_NOW)
    statuses = {item["name"]: item for item in manifest["adapterStatuses"]}

    assert statuses["host-episodic"]["status"] == "unavailable"
    assert statuses["host-episodic"]["reason"] == "supported_api_not_supplied"
    assert statuses["procedural-memory"]["status"] == "unavailable"
    assert statuses["procedural-memory"]["reason"] == "machine_readable_recall_not_implemented"


def test_private_write_verify_revision_and_exact_source_purge(tmp_path: Path) -> None:
    manifest, payload = MemoryContextAssembler().assemble(fixture(), FIXED_NOW)
    store = MemoryStore(tmp_path / "store")
    manifest_path, payload_path = store.write(manifest, payload)

    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert payload_path.stat().st_mode & 0o777 == 0o600
    assert store.verify(manifest_path, payload_path, now=FIXED_NOW)["valid"] is True
    source_state = {
        "decision-blue": "rev-1",
        "decision-red": "rev-2",
        "hostile-note": "changed",
    }
    assert store.verify(
        manifest_path, payload_path, now=FIXED_NOW, source_state=source_state
    )["reasons"] == ["source_revision_changed"]

    purge = store.purge("decision-blue", FIXED_NOW)
    assert purge["invalidatedPackIds"] == [manifest["packId"]]
    assert purge["rawSourceRetained"] is False
    assert not manifest_path.exists()
    index = json.loads(store.index_path.read_text())
    assert sha256("decision-blue") in index["revokedSources"]
    assert "decision-blue" not in store.index_path.read_text()


def test_ttl_cleanup_and_payload_tamper_fail_closed(tmp_path: Path) -> None:
    manifest, payload = MemoryContextAssembler().assemble(fixture(), FIXED_NOW)
    store = MemoryStore(tmp_path / "store")
    manifest_path, payload_path = store.write(manifest, payload)
    payload_path.write_text('{"schemaVersion":1,"payloads":{}}\n')
    payload_path.chmod(0o600)

    result = store.verify(manifest_path, payload_path, now=FIXED_NOW)
    assert result["valid"] is False
    assert "payload_hash_mismatch" in result["reasons"]
    cleanup = store.cleanup_expired(datetime(2026, 8, 30, 14, 0, tzinfo=timezone.utc))
    assert cleanup["removedPackIds"] == [manifest["packId"]]


def test_unknown_fields_and_available_candidates_on_failed_adapter_are_rejected() -> None:
    document = fixture()
    document["request"]["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        MemoryContextAssembler().assemble(document, FIXED_NOW)

    document = fixture()
    document["adapters"][0]["status"] = "timeout"
    with pytest.raises(ValueError, match="only an available adapter"):
        MemoryContextAssembler().assemble(document, FIXED_NOW)

    document = fixture()
    document["adapters"][0]["candidates"][0]["contentRole"] = "system-instruction"
    with pytest.raises(ValueError, match="contentRole"):
        MemoryContextAssembler().assemble(document, FIXED_NOW)


def test_lane_and_total_budgets_are_deterministic() -> None:
    document = fixture()
    document["request"]["laneBudgets"]["semantic"] = {"maxItems": 1, "maxTokens": 100}
    manifest, _ = MemoryContextAssembler().assemble(document, FIXED_NOW)

    assert len(manifest["candidates"]) == 1
    assert manifest["exclusionReasonCounts"]["lane_budget_exceeded"] == 2
    assert manifest["candidates"][0]["sourceSystem"] == "canonical-file"


def test_task_scope_and_not_yet_valid_candidates_fail_closed() -> None:
    document = fixture()
    document["request"]["task"] = None
    document["adapters"][0]["candidates"][2]["validFrom"] = "2026-09-01T00:00:00Z"
    manifest, _ = MemoryContextAssembler().assemble(document, FIXED_NOW)

    assert manifest["candidates"] == []
    assert manifest["exclusionReasonCounts"] == {
        "not_yet_valid": 1,
        "scope_denied": 3,
    }
    assert manifest["taskHash"] is None


def test_pack_identity_includes_scope_time_and_ttl_window(tmp_path: Path) -> None:
    assembler = MemoryContextAssembler()
    first_manifest, first_payload = assembler.assemble(fixture(), FIXED_NOW)
    second_manifest, second_payload = assembler.assemble(
        fixture(), FIXED_NOW + timedelta(seconds=1)
    )
    store = MemoryStore(tmp_path / "store")

    first_paths = store.write(first_manifest, first_payload)
    second_paths = store.write(second_manifest, second_payload)

    assert first_manifest["packId"] != second_manifest["packId"]
    assert first_manifest["taskHash"] == sha256("rt-130")
    assert all(path.exists() for path in (*first_paths, *second_paths))
