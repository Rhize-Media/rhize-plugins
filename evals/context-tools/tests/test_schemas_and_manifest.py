from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "rhize-context-manager"


def test_all_phase_one_json_documents_parse() -> None:
    paths = [
        PLUGIN_ROOT / "schemas" / "context-experiment-config-v1.schema.json",
        PLUGIN_ROOT / "schemas" / "context-experiment-receipt-v1.schema.json",
        PLUGIN_ROOT / "schemas" / "context-experiment-receipt-v2.schema.json",
        PLUGIN_ROOT / "schemas" / "context-experiment-evidence-v1.schema.json",
        PLUGIN_ROOT / "schemas" / "context-pack-v1.schema.json",
        PLUGIN_ROOT / "schemas" / "context-pack-v2.schema.json",
        PLUGIN_ROOT / "schemas" / "memory-envelope-v1.schema.json",
        PLUGIN_ROOT / "schemas" / "memory-context-pack-v1.schema.json",
        PLUGIN_ROOT / "setup" / "manifest.json",
        PLUGIN_ROOT / ".codex-plugin" / "plugin.json",
    ]
    for path in paths:
        assert isinstance(json.loads(path.read_text()), dict), path


def test_receipt_schema_requires_explicit_arm_and_metric_variant_accounting() -> None:
    schema = json.loads(
        (PLUGIN_ROOT / "schemas" / "context-experiment-receipt-v1.schema.json").read_text()
    )
    required = set(schema["required"])
    assert {
        "armsRequested",
        "armsExecuted",
        "armsSkipped",
        "liveVariant",
        "fallbackUsed",
    }.issubset(required)
    metric_required = set(schema["properties"]["metrics"]["items"]["required"])
    assert {"variant", "role", "unit", "evidence"}.issubset(metric_required)


def test_receipt_v2_is_digest_bound_to_source_free_review_evidence() -> None:
    receipt = json.loads(
        (PLUGIN_ROOT / "schemas" / "context-experiment-receipt-v2.schema.json").read_text()
    )
    assert {
        "evidenceDigest",
        "claimPackVerified",
        "finalPackVerification",
    }.issubset(receipt["required"])
    evidence = json.loads(
        (PLUGIN_ROOT / "schemas" / "context-experiment-evidence-v1.schema.json").read_text()
    )
    assert evidence["additionalProperties"] is False
    assert "prompt" not in evidence["properties"]
    assert "source" not in evidence["properties"]
    assert "output" not in evidence["properties"]
    assert "path" not in evidence["properties"]
    assert "url" not in evidence["properties"]


def test_config_schema_is_strict_and_caps_armed_runs() -> None:
    schema = json.loads(
        (PLUGIN_ROOT / "schemas" / "context-experiment-config-v1.schema.json").read_text()
    )
    assert schema["additionalProperties"] is False
    capability = schema["$defs"]["capability"]
    assert capability["additionalProperties"] is False
    assert capability["properties"]["armedRuns"]["maximum"] == 10


def test_context_pack_schema_matches_upstream_adapter_contract() -> None:
    schema = json.loads(
        (PLUGIN_ROOT / "schemas" / "context-pack-v1.schema.json").read_text()
    )
    assert schema["additionalProperties"] is False
    assert {"repoId", "snapshot", "taskHash", "targetPath", "compiler", "diagnostics", "policy", "reductionPercent"}.issubset(
        schema["required"]
    )
    entry = schema["properties"]["entries"]["items"]
    assert {"path", "tier", "hopDistance", "contentHash"}.issubset(entry["required"])
    diagnostics = set(schema["properties"]["diagnostics"]["required"])
    assert {
        "dynamicDispatchFileCount",
        "decoratorHintFileCount",
        "callbackRegistrationFileCount",
        "syntaxErrorFileCount",
    }.issubset(diagnostics)


def test_native_context_pack_schema_is_provider_neutral_and_source_free() -> None:
    schema = json.loads(
        (PLUGIN_ROOT / "schemas" / "context-pack-v2.schema.json").read_text()
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["provider"]["properties"]["name"]["const"] == "rhize-native"
    entry = schema["properties"]["entries"]["items"]
    assert {"path", "role", "reason", "sourceHash", "renderedHash"}.issubset(entry["required"])
    assert set(entry["properties"]["role"]["enum"]) == {"FULL", "INTERFACE"}
    assert "content" not in entry["properties"]
    assert schema["properties"]["provider"]["properties"]["revision"]["const"] == "rhize-native-context-pack-v2"
    assert "exclusionLedger" in schema["required"]


def test_cross_host_skills_and_metadata_share_one_launcher() -> None:
    for name in ("context-pack", "memory-context"):
        root = PLUGIN_ROOT / "skills" / name
        assert (root / "SKILL.md").exists()
        assert (root / "agents" / "openai.yaml").exists()
        assert (root / "scripts" / f"{name}.sh").exists()
    codex = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text())
    assert codex["skills"] == "./skills/"
    assert codex["version"] == json.loads(
        (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
    )["version"]


def test_opt_in_manifest_wires_both_fail_silent_hooks() -> None:
    manifest = json.loads((PLUGIN_ROOT / "setup" / "manifest.json").read_text())
    by_id = {item["id"]: item for item in manifest["items"]}
    selector = by_id["context-experiment-selector"]
    finalizer = by_id["context-experiment-finalizer"]
    assert selector["default"] is False and selector["event"] == "UserPromptSubmit"
    assert finalizer["default"] is False and finalizer["event"] == "Stop"
    assert (PLUGIN_ROOT / "hooks" / "context-experiment-selector.js").exists()
    assert (PLUGIN_ROOT / "hooks" / "context-experiment-finalizer.js").exists()
