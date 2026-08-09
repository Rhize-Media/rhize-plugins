#!/usr/bin/env python3
"""test_build.py — real-artifact tests for scripts/build_skill_map.py.

Complements tests/skill-map/validate_fixtures.py (which only exercises
small hand-written fixtures against the schema) with checks against the
actual, repo-wide generated artifact:

  1. Building twice produces byte-identical output (determinism contract).
  2. The generated artifact passes schema + referential-integrity checks
     (via scripts/validate_skill_map.py's own functions).
  3. Every plugin from .claude-plugin/marketplace.json, and every skill
     directory with a SKILL.md under any plugin's skills/, appears exactly
     once as a node in the generated artifact.

Exit code 0 on success, 1 on any failure. Does not use pytest (this repo's
other skill-map tests are plain scripts) so it runs with a bare
`python3 tests/skill-map/test_build.py` and no extra dependency.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_skill_map.py"
VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "validate_skill_map.py"
ARTIFACT_PATH = REPO_ROOT / "generated" / "skill-map.static.json"
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_build() -> None:
    result = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"build_skill_map.py failed:\n{result.stdout}\n{result.stderr}")


def test_determinism() -> None:
    run_build()
    first = ARTIFACT_PATH.read_bytes()
    run_build()
    second = ARTIFACT_PATH.read_bytes()
    if first != second:
        raise AssertionError("two consecutive builds produced different output")
    print("PASS test_determinism")


def test_generated_artifact_valid() -> None:
    validate_mod = _load_module(VALIDATE_SCRIPT, "validate_skill_map")
    doc = json.loads(ARTIFACT_PATH.read_text())
    if not validate_mod.validate_document(doc, "generated/skill-map.static.json"):
        raise AssertionError("generated artifact failed schema/referential validation")
    print("PASS test_generated_artifact_valid")


def test_every_plugin_and_skill_appears_once() -> None:
    doc = json.loads(ARTIFACT_PATH.read_text())
    node_ids = [n["id"] for n in doc["nodes"]]
    if len(node_ids) != len(set(node_ids)):
        dupes = {i for i in node_ids if node_ids.count(i) > 1}
        raise AssertionError(f"duplicate node ids in artifact: {dupes}")

    marketplace = json.loads(MARKETPLACE_PATH.read_text())
    expected_plugins = {entry["name"] for entry in marketplace["plugins"]}
    actual_plugins = {n["id"] for n in doc["nodes"] if n["kind"] == "plugin"}
    if actual_plugins != {f"plugin:{name}" for name in expected_plugins}:
        raise AssertionError(
            f"plugin node mismatch: expected {expected_plugins}, "
            f"got {sorted(actual_plugins)}"
        )

    expected_skill_ids = set()
    for entry in marketplace["plugins"]:
        plugin_name = entry["name"]
        source = entry["source"]
        plugin_dir_name = source[2:] if source.startswith("./") else source
        skills_dir = REPO_ROOT / plugin_dir_name / "skills"
        if not skills_dir.is_dir():
            continue
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
                expected_skill_ids.add(f"skill:{plugin_name}/{skill_dir.name}")

    actual_skill_ids = {n["id"] for n in doc["nodes"] if n["kind"] == "skill"}
    if actual_skill_ids != expected_skill_ids:
        missing = expected_skill_ids - actual_skill_ids
        extra = actual_skill_ids - expected_skill_ids
        raise AssertionError(f"skill node mismatch: missing={missing}, extra={extra}")

    print(
        f"PASS test_every_plugin_and_skill_appears_once "
        f"({len(actual_plugins)} plugins, {len(actual_skill_ids)} skills)"
    )


def main() -> int:
    tests = [
        test_determinism,
        test_generated_artifact_valid,
        test_every_plugin_and_skill_appears_once,
    ]
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            print(f"FAIL {test.__name__}: {exc}")
            failures += 1
    if failures:
        print(f"\n{failures} test(s) failed.")
        return 1
    print("\nAll build tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
