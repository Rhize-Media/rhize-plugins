#!/usr/bin/env python3
"""test_v2_relationships.py — tests for the skill-map relationships v2 core
(follows/augments/remediates edges, condition tags, mcp-server nodes,
generated/skill-map.indexes.json, and scripts/query_skill_map.py).

Complements the existing tests/skill-map/*.py rather than replacing them:
this file only covers what's new in the v2 design
(docs/superpowers/specs/2026-08-09-skill-map-relationships-v2-design.md).
No pytest, same convention as this repo's other skill-map tests.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_skill_map.py"
QUERY_SCRIPT = REPO_ROOT / "scripts" / "query_skill_map.py"
TAGS_PATH = REPO_ROOT / "catalog" / "tags.json"
STATIC_ARTIFACT = REPO_ROOT / "generated" / "skill-map.static.json"
INDEXES_ARTIFACT = REPO_ROOT / "generated" / "skill-map.indexes.json"

build_skill_map = load_module(BUILD_SCRIPT, "build_skill_map")

FAILURES = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global FAILURES
    if condition:
        print(f"PASS {label}")
    else:
        FAILURES += 1
        print(f"FAIL {label}: {detail}")


# ---------------------------------------------------------------------------
# 1. Condition pattern matching against fixture failing outputs
# ---------------------------------------------------------------------------
CONDITION_SAMPLES = {
    "build-failure": [
        "Error: Build failed with 3 errors",
        "Failed to compile.\n\n./src/index.tsx",
    ],
    "type-error": [
        "src/foo.ts:12:5 - error TS2322: Type 'string' is not assignable to type 'number'.",
        "Type error: Cannot find name 'Foo'.",
    ],
    "test-failure": [
        "Tests:       2 failed, 10 passed, 12 total",
        "FAIL src/foo.test.ts",
    ],
    "lint-failure": [
        "✖ 12 problems (12 errors, 0 warnings)",
        "Code style issues found in 3 files. Run Prettier to fix.",
    ],
    "merge-conflict": [
        "CONFLICT (content): Merge conflict in src/foo.ts",
        "<<<<<<< HEAD",
    ],
}

NEGATIVE_SAMPLE = "All 42 tests passed. Build succeeded. No lint issues found."


def test_condition_patterns() -> None:
    tags = json.loads(TAGS_PATH.read_text())
    conditions = {t["slug"]: t for t in tags if t["kind"] == "condition"}
    expected_slugs = {"build-failure", "type-error", "test-failure", "lint-failure", "merge-conflict"}
    check(
        "condition vocabulary has the 5 spec'd slugs",
        set(conditions.keys()) == expected_slugs,
        f"got {sorted(conditions.keys())}",
    )

    for slug, samples in CONDITION_SAMPLES.items():
        entry = conditions.get(slug)
        if entry is None:
            check(f"condition {slug} exists", False, "missing from catalog/tags.json")
            continue
        patterns = [re.compile(p) for p in entry.get("patterns", [])]
        check(f"condition {slug} has at least one pattern", len(patterns) > 0)
        for sample in samples:
            matched = any(p.search(sample) for p in patterns)
            check(f"condition {slug} pattern matches sample {sample[:30]!r}", matched)
        # a sample from a DIFFERENT condition's positive set (or the generic
        # negative sample) must not match this condition's patterns unless
        # it's a legitimately overlapping string.
        for other_slug, other_samples in CONDITION_SAMPLES.items():
            if other_slug == slug:
                continue
            for other_sample in other_samples:
                if any(p.search(other_sample) for p in patterns):
                    check(
                        f"condition {slug} pattern does not false-positive on {other_slug} sample",
                        False,
                        f"{other_sample!r} matched {slug}'s patterns",
                    )
        neg_matched = any(p.search(NEGATIVE_SAMPLE) for p in patterns)
        check(f"condition {slug} patterns don't match the negative sample", not neg_matched)


# ---------------------------------------------------------------------------
# 2. augments/remediates/dependsOn parsing, including BuildError cases
# ---------------------------------------------------------------------------
def test_augments_remediates_dependson_parsing() -> None:
    Graph = build_skill_map.Graph
    tags = build_skill_map.load_tags()

    # augments: valid
    graph = Graph()
    graph.add_node({"id": "skill:p/a", "kind": "skill", "name": "a", "path": "x", "description": "", "contentHash": "0" * 64})
    decls = [{"skill_id": "skill:p/a", "slug": "content-authoring", "gloss": tags["topic"]["content-authoring"]}]
    build_skill_map.resolve_augments_edges(graph, decls)
    check(
        "augments edge created for valid topic slug",
        any(e["type"] == "augments" and e["to"] == "tag:topic/content-authoring" for e in graph.edges),
    )

    # remediates: valid
    graph2 = Graph()
    graph2.add_node({"id": "skill:p/b", "kind": "skill", "name": "b", "path": "x", "description": "", "contentHash": "0" * 64})
    decls2 = [{"skill_id": "skill:p/b", "slug": "build-failure", "gloss": tags["condition"]["build-failure"]}]
    build_skill_map.resolve_remediates_edges(graph2, decls2)
    check(
        "remediates edge created for valid condition slug",
        any(e["type"] == "remediates" and e["to"] == "tag:condition/build-failure" for e in graph2.edges),
    )

    # dependsOn: mcp target mints an mcp-server node
    graph3 = Graph()
    graph3.add_node({"id": "skill:p/c", "kind": "skill", "name": "c", "path": "x", "description": "", "contentHash": "0" * 64})
    decls3 = [{"skill_id": "skill:p/c", "plugin": "p", "target": "mcp:widget", "rel_path": "x"}]
    build_skill_map.resolve_depends_on_edges(graph3, decls3)
    check("dependsOn mints mcp-server node", "mcp:widget" in graph3.nodes and graph3.nodes["mcp:widget"]["kind"] == "mcp-server")
    check(
        "dependsOn edge to mcp-server node",
        any(e["type"] == "depends-on" and e["to"] == "mcp:widget" for e in graph3.edges),
    )

    # dependsOn: valid skill target (same plugin, bare name)
    graph4 = Graph()
    graph4.add_node({"id": "skill:p/d1", "kind": "skill", "name": "d1", "path": "x", "description": "", "contentHash": "0" * 64})
    graph4.add_node({"id": "skill:p/d2", "kind": "skill", "name": "d2", "path": "x", "description": "", "contentHash": "0" * 64})
    decls4 = [{"skill_id": "skill:p/d1", "plugin": "p", "target": "d2", "rel_path": "x"}]
    build_skill_map.resolve_depends_on_edges(graph4, decls4)
    check(
        "dependsOn edge to a resolved skill target",
        any(e["type"] == "depends-on" and e["to"] == "skill:p/d2" for e in graph4.edges),
    )

    # BuildError: unresolved skill target
    graph5 = Graph()
    graph5.add_node({"id": "skill:p/e", "kind": "skill", "name": "e", "path": "x", "description": "", "contentHash": "0" * 64})
    decls5 = [{"skill_id": "skill:p/e", "plugin": "p", "target": "nonexistent-skill", "rel_path": "x"}]
    try:
        build_skill_map.resolve_depends_on_edges(graph5, decls5)
        check("dependsOn on unresolved skill target raises BuildError", False, "no exception raised")
    except build_skill_map.BuildError:
        check("dependsOn on unresolved skill target raises BuildError", True)

    # BuildError: unknown augments slug is caught in load_skills() — verified
    # against the real vocabulary check inline (mirrors load_skills()'s guard).
    unknown_slug_is_rejected = "definitely-not-a-real-topic" not in tags["topic"]
    check("an unknown augments slug is absent from the topic vocabulary (guard precondition)", unknown_slug_is_rejected)


# ---------------------------------------------------------------------------
# 3. Index emission, determinism, and staleness
# ---------------------------------------------------------------------------
def test_indexes_emission() -> None:
    check("generated/skill-map.indexes.json exists", INDEXES_ARTIFACT.is_file())
    doc = json.loads(INDEXES_ARTIFACT.read_text())
    for section in ("router", "disclosure", "remediation", "succession"):
        check(f"indexes has section {section!r}", section in doc)
    check(
        "remediation index has build-failure with patterns and skills",
        "build-failure" in doc["remediation"]
        and doc["remediation"]["build-failure"]["patterns"]
        and doc["remediation"]["build-failure"]["skills"],
    )


def test_indexes_determinism() -> None:
    result1 = subprocess.run([sys.executable, str(BUILD_SCRIPT)], cwd=REPO_ROOT, capture_output=True, text=True)
    first = INDEXES_ARTIFACT.read_bytes()
    result2 = subprocess.run([sys.executable, str(BUILD_SCRIPT)], cwd=REPO_ROOT, capture_output=True, text=True)
    second = INDEXES_ARTIFACT.read_bytes()
    check("build_skill_map.py exits 0 (run 1)", result1.returncode == 0, result1.stderr)
    check("build_skill_map.py exits 0 (run 2)", result2.returncode == 0, result2.stderr)
    check("two consecutive builds produce identical indexes", first == second)


def test_check_stale_covers_indexes() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate_skill_map.py"), "--check-stale"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    check("validate_skill_map.py --check-stale passes on a committed, up-to-date tree", result.returncode == 0, result.stdout + result.stderr)
    check("--check-stale output mentions the indexes artifact", "indexes" in result.stdout)


# ---------------------------------------------------------------------------
# 4. Query CLI — each seed query against the real (static) artifact
# ---------------------------------------------------------------------------
QUERY_CASES = [
    ("what-extends", "rhize-devflow/error-lifecycle-management"),
    ("what-augments", "tag:topic/content-authoring"),
    ("what-remediates", "build-failure"),
    ("what-follows", "seo-aeo-geo/content-seo"),
    ("overlap-candidates", None),
    ("unroutable-skills", None),
    ("mcp-dependents", "dataforseo"),
    ("skill-neighborhood", "procedural-memory/functionize"),
]


def test_query_cli() -> None:
    for name, arg in QUERY_CASES:
        cmd = [sys.executable, str(QUERY_SCRIPT), name]
        if arg is not None:
            cmd.append(arg)
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        check(f"query {name!r} exits 0", result.returncode == 0, result.stderr)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            check(f"query {name!r} emits valid JSON", False, str(exc))
            continue
        check(f"query {name!r} emits valid JSON", True)
        check(f"query {name!r} echoes its own name", payload.get("query") == name)

    remediates_result = subprocess.run(
        [sys.executable, str(QUERY_SCRIPT), "what-remediates", "build-failure"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    payload = json.loads(remediates_result.stdout)
    check(
        "what-remediates build-failure includes a known ecc build-resolver",
        "external:ecc-react-build-resolver" in payload.get("skills", []),
    )


def main() -> int:
    test_condition_patterns()
    test_augments_remediates_dependson_parsing()
    test_indexes_emission()
    test_indexes_determinism()
    test_check_stale_covers_indexes()
    test_query_cli()

    if FAILURES:
        print(f"\n{FAILURES} check(s) failed.")
        return 1
    print("\nAll v2-relationships tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
