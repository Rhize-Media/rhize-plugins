from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "rhize-context-manager"


def test_all_phase_one_json_documents_parse() -> None:
    paths = [
        PLUGIN_ROOT / "schemas" / "context-experiment-config-v1.schema.json",
        PLUGIN_ROOT / "schemas" / "context-experiment-receipt-v1.schema.json",
        PLUGIN_ROOT / "schemas" / "context-pack-v1.schema.json",
        PLUGIN_ROOT / "setup" / "manifest.json",
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


def test_opt_in_manifest_wires_both_fail_silent_hooks() -> None:
    manifest = json.loads((PLUGIN_ROOT / "setup" / "manifest.json").read_text())
    by_id = {item["id"]: item for item in manifest["items"]}
    selector = by_id["context-experiment-selector"]
    finalizer = by_id["context-experiment-finalizer"]
    assert selector["default"] is False and selector["event"] == "UserPromptSubmit"
    assert finalizer["default"] is False and finalizer["event"] == "Stop"
    assert (PLUGIN_ROOT / "hooks" / "context-experiment-selector.js").exists()
    assert (PLUGIN_ROOT / "hooks" / "context-experiment-finalizer.js").exists()
