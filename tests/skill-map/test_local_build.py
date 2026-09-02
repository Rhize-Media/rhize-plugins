#!/usr/bin/env python3
"""test_local_build.py — tests for scripts/build_local_skill_map.py (Phase 3
"local overlay" of the skill-map-graph-substrate plan).

Covers:
  1. Full-input build: a fixture monitor co-occurrence snapshot + a fake
     HOME (installed_plugins.json, stack.config.json) + a fake third-party
     cached plugin produce a skill-map.local.json overlay and a
     skill-map.resolved.json that validates against the schema, with the
     expected usage-cooccurs edge resolved from the fixture pair AND the
     fixture third-party plugin/skill/command nodes tagged
     "origin": "third-party" — while the committed static artifact stays
     byte-identical.
  2. Degradation path: with all optional inputs absent, the resolved
     artifact is content-equal to the committed static artifact (never
     fails).

Plain-script style (no pytest), matching the other tests/skill-map/*.py
files. Exit code 0 on success, 1 on any failure.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
# Runs the plugin copy directly (moved from scripts/ 2026-09-02, R3 task 8 of the
# portability-readiness plan) — keeps this test hermetic against the plugin's own
# source rather than the root compatibility shim.
BUILD_LOCAL_SCRIPT = REPO_ROOT / "rhize-context-manager" / "scripts" / "build_local_skill_map.py"
VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "validate_skill_map.py"
STATIC_PATH = REPO_ROOT / "generated" / "skill-map.static.json"

# Two real skill ids from the committed static artifact, used as a fixture
# co-occurrence pair. If these skills are ever removed, update this pair to
# any two skills that still coexist in the same plugin (or two plugins).
FIXTURE_PLUGIN = "obsidian-second-brain"
FIXTURE_SKILL_A = "defuddle"
FIXTURE_SKILL_B = "json-canvas"


def run_build(*extra_args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, str(BUILD_LOCAL_SCRIPT), *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result


def test_full_inputs() -> None:
    static_doc_before = STATIC_PATH.read_bytes()
    static_doc = json.loads(static_doc_before)
    a_id = f"skill:{FIXTURE_PLUGIN}/{FIXTURE_SKILL_A}"
    b_id = f"skill:{FIXTURE_PLUGIN}/{FIXTURE_SKILL_B}"
    static_skill_ids = {n["id"] for n in static_doc["nodes"] if n["kind"] == "skill"}
    if a_id not in static_skill_ids or b_id not in static_skill_ids:
        raise AssertionError(
            f"fixture skills {a_id}/{b_id} not found in {STATIC_PATH} — "
            "update FIXTURE_SKILL_A/B in this test"
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_dir = tmp_path / "context-manager"

        # Fixture monitor co-occurrence snapshot — counts only, matching
        # monitor.py's build_cooccurrence() output shape.
        cooc_path = tmp_path / "skill-cooccurrence.json"
        a_name = f"{FIXTURE_PLUGIN}:{FIXTURE_SKILL_A}"
        b_name = f"{FIXTURE_PLUGIN}:{FIXTURE_SKILL_B}"
        cooc_path.write_text(json.dumps({
            "windowDays": 7,
            "totalSessions": 10,
            "pairs": [{"a": a_name, "b": b_name, "sessions": 3}],
            "totals": {a_name: 5, b_name: 4},
        }))

        # Fixture third-party cached plugin — mirrors the real
        # ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/ layout:
        # a .claude-plugin/plugin.json, one skills/*/SKILL.md, one
        # commands/*.md.
        marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
        tp_marketplace, tp_plugin = "acme-marketplace", "acme-plugin"
        tp_root = tmp_path / "cache" / tp_marketplace / tp_plugin / "1.0.0"
        (tp_root / ".claude-plugin").mkdir(parents=True)
        (tp_root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"description": "Acme plugin for widgets."})
        )
        (tp_root / "skills" / "widget-builder").mkdir(parents=True)
        (tp_root / "skills" / "widget-builder" / "SKILL.md").write_text(
            "---\nname: widget-builder\ndescription: Builds widgets fast.\n---\n\nBody.\n"
        )
        (tp_root / "commands").mkdir()
        (tp_root / "commands" / "build-widget.md").write_text(
            "---\ndescription: Build a widget via command.\n---\n\nDo it.\n"
        )
        tp_plugin_id = f"plugin:{tp_marketplace}/{tp_plugin}"
        tp_skill_id = f"skill:{tp_marketplace}/{tp_plugin}/widget-builder"
        tp_command_id = f"command:{tp_marketplace}/{tp_plugin}/build-widget"

        # Fixture installed_plugins.json — enable this repo's plugins at
        # user scope (mirrors the real v2 shape), plus the fixture
        # third-party plugin pointed at its cached install path above.
        installed_path = tmp_path / "installed_plugins.json"
        installed_plugins = {
            f"{p['name']}@{marketplace['name']}": [{"scope": "user"}]
            for p in marketplace["plugins"]
        }
        installed_plugins[f"{tp_plugin}@{tp_marketplace}"] = [
            {"scope": "user", "installPath": str(tp_root), "version": "1.0.0"}
        ]
        installed_path.write_text(json.dumps({"version": 2, "plugins": installed_plugins}))

        # Fixture global settings.json — the third-party plugin must be
        # "enabled" via the enabledPlugins map (installed_plugins.json alone
        # doesn't carry an enabled bit).
        global_settings_path = tmp_path / "global-settings.json"
        global_settings_path.write_text(json.dumps({
            "enabledPlugins": {f"{tp_plugin}@{tp_marketplace}": True}
        }))
        # No local settings override in this fixture — missing is fine
        # (degrades cleanly, same contract as the other optional inputs).
        local_settings_path = tmp_path / "local-settings.json"

        # Fixture stack.config.json — schemaVersion 2, minimal valid shape.
        stack_path = tmp_path / "stack.config.json"
        stack_path.write_text(json.dumps({
            "schemaVersion": 2,
            "layers": [{"name": "Test Layer", "layer": "cli", "scope": "global", "notes": ""}],
        }))

        result = run_build(
            "--out-dir", str(out_dir),
            "--cooccurrence", str(cooc_path),
            "--installed-plugins", str(installed_path),
            "--stack-config", str(stack_path),
            "--global-settings", str(global_settings_path),
            "--local-settings", str(local_settings_path),
        )
        if result.returncode != 0:
            raise AssertionError(f"build_local_skill_map.py failed:\n{result.stdout}\n{result.stderr}")

        local_doc = json.loads((out_dir / "skill-map.local.json").read_text())
        resolved_doc = json.loads((out_dir / "skill-map.resolved.json").read_text())

        expected_plugins = sorted(p["name"] for p in marketplace["plugins"])
        if local_doc["enabledPlugins"] != expected_plugins:
            raise AssertionError(
                f"enabledPlugins {local_doc['enabledPlugins']} != {expected_plugins}"
            )
        if local_doc["stack"] is None:
            raise AssertionError("expected a stack fingerprint from the fixture stack config")
        if len(local_doc["usageCooccursEdges"]) != 1:
            raise AssertionError(
                f"expected exactly 1 usage-cooccurs edge, got {local_doc['usageCooccursEdges']}"
            )
        edge = local_doc["usageCooccursEdges"][0]
        if {edge["from"], edge["to"]} != {a_id, b_id}:
            raise AssertionError(f"edge endpoints {edge['from']}/{edge['to']} != {a_id}/{b_id}")
        if edge["usageWeight"]["sessions"] != 3:
            raise AssertionError(f"expected sessions=3, got {edge['usageWeight']}")

        # Third-party inventory: exactly the one fixture plugin/skill/command.
        tp_summary = local_doc["thirdParty"]["summary"]
        if (tp_summary["plugins"], tp_summary["skills"], tp_summary["commands"]) != (1, 1, 1):
            raise AssertionError(f"unexpected third-party summary: {tp_summary}")
        if tp_summary["skippedPlugins"] != 0 or tp_summary["skippedEntries"] != 0:
            raise AssertionError(f"unexpected skips in third-party summary: {tp_summary}")

        tp_nodes_by_id = {n["id"]: n for n in local_doc["thirdParty"]["nodes"]}
        for node_id, kind in (
            (tp_plugin_id, "plugin"), (tp_skill_id, "skill"), (tp_command_id, "command")
        ):
            node = tp_nodes_by_id.get(node_id)
            if node is None:
                raise AssertionError(f"expected third-party node {node_id!r} in local overlay")
            if node["kind"] != kind or node.get("origin") != "third-party":
                raise AssertionError(f"third-party node {node_id!r} has unexpected shape: {node}")
        if tp_nodes_by_id[tp_skill_id]["description"] != "Builds widgets fast.":
            raise AssertionError(
                f"unexpected skill description: {tp_nodes_by_id[tp_skill_id]['description']!r}"
            )

        tp_edge_pairs = {(e["from"], e["to"]) for e in local_doc["thirdParty"]["edges"]}
        if {(tp_plugin_id, tp_skill_id), (tp_plugin_id, tp_command_id)} != tp_edge_pairs:
            raise AssertionError(f"unexpected third-party contains edges: {tp_edge_pairs}")

        # resolved = static nodes/edges (verbatim, in order) + the overlay's
        # usage-cooccurs edge + the third-party nodes/edges above.
        n_static = len(static_doc["nodes"])
        if resolved_doc["nodes"][:n_static] != static_doc["nodes"]:
            raise AssertionError("resolved nodes must start with static nodes verbatim")
        resolved_tp_node_ids = {n["id"] for n in resolved_doc["nodes"][n_static:]}
        if {tp_plugin_id, tp_skill_id, tp_command_id} - resolved_tp_node_ids:
            raise AssertionError(
                f"resolved.nodes missing third-party fixture ids: {resolved_tp_node_ids}"
            )
        if len(resolved_doc["edges"]) != len(static_doc["edges"]) + 1 + 2:
            raise AssertionError(
                "resolved edges must be static edges + 1 usage-cooccurs edge + "
                "2 third-party contains edges"
            )

        # The committed static artifact must stay byte-identical — the
        # third-party inventory is local-overlay/resolved only.
        if STATIC_PATH.read_bytes() != static_doc_before:
            raise AssertionError("committed static artifact was modified by the local build")

        validate_mod = load_module(VALIDATE_SCRIPT, "validate_skill_map")
        if not validate_mod.validate_document(resolved_doc, "skill-map.resolved.json (fixture)"):
            raise AssertionError("resolved artifact failed schema/referential validation")

    print("PASS test_full_inputs")


def test_degradation_no_inputs() -> None:
    static_doc = json.loads(STATIC_PATH.read_text())

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_dir = tmp_path / "context-manager"
        result = run_build(
            "--out-dir", str(out_dir),
            "--cooccurrence", str(tmp_path / "no-cooccurrence.json"),
            "--installed-plugins", str(tmp_path / "no-installed-plugins.json"),
            "--stack-config", str(tmp_path / "no-stack-config.json"),
            "--global-settings", str(tmp_path / "no-global-settings.json"),
            "--local-settings", str(tmp_path / "no-local-settings.json"),
        )
        if result.returncode != 0:
            raise AssertionError(f"build_local_skill_map.py failed:\n{result.stdout}\n{result.stderr}")

        local_doc = json.loads((out_dir / "skill-map.local.json").read_text())
        resolved_doc = json.loads((out_dir / "skill-map.resolved.json").read_text())

        marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
        expected_all_plugins = sorted(p["name"] for p in marketplace["plugins"])
        if local_doc["enabledPlugins"] != expected_all_plugins:
            raise AssertionError(
                "missing installed_plugins.json should degrade to 'all repo plugins enabled', "
                f"got {local_doc['enabledPlugins']}"
            )
        if local_doc["stack"] is not None:
            raise AssertionError("missing stack config should degrade to stack=None")
        if local_doc["usageCooccursEdges"] != []:
            raise AssertionError("missing cooccurrence snapshot should degrade to no edges")

        tp_summary = local_doc["thirdParty"]["summary"]
        if (tp_summary["plugins"], tp_summary["skills"], tp_summary["commands"]) != (0, 0, 0):
            raise AssertionError(
                f"missing installed_plugins.json should degrade to zero third-party "
                f"inventory, got {tp_summary}"
            )

        if resolved_doc["nodes"] != static_doc["nodes"]:
            raise AssertionError("degraded resolved.nodes must equal static.nodes")
        if resolved_doc["edges"] != static_doc["edges"]:
            raise AssertionError("degraded resolved.edges must equal static.edges (no inputs)")

        validate_mod = load_module(VALIDATE_SCRIPT, "validate_skill_map")
        if not validate_mod.validate_document(resolved_doc, "skill-map.resolved.json (degraded)"):
            raise AssertionError("degraded resolved artifact failed validation")

    print("PASS test_degradation_no_inputs")


def main() -> int:
    if not STATIC_PATH.is_file():
        print(
            f"ERROR: {STATIC_PATH} not found — run scripts/build_skill_map.py first",
            file=sys.stderr,
        )
        return 1
    try:
        test_full_inputs()
        test_degradation_no_inputs()
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("All test_local_build.py checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
