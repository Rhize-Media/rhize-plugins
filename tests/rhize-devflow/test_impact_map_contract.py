#!/usr/bin/env python3
"""Contract tests for the shared CodeGraph + impact-map workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND = REPO_ROOT / "rhize-devflow/commands/impact-map.md"
REFERENCE = REPO_ROOT / "rhize-devflow/docs/impact-map-reference.md"
CM_ADAPTER = REPO_ROOT / "rhize-context-manager/commands/impact-map.md"
FOUNDATION = (
    REPO_ROOT
    / "rhize-devflow/skills/dev-flow-foundations/SKILL-dependency-graph-v1.md"
)
DEVFLOW_SKILL = REPO_ROOT / "rhize-devflow/skills/dev-flow-foundations/SKILL.md"
GENERATED_MAP = REPO_ROOT / "generated/skill-map.static.json"
RELATIONS = REPO_ROOT / "catalog/skill-relations.json"
DOCS = (
    REPO_ROOT / "rhize-devflow/README.md",
    REPO_ROOT / "rhize-devflow/GUIDE.md",
    REPO_ROOT / "rhize-context-manager/README.md",
    REPO_ROOT / "rhize-context-manager/GUIDE.md",
)


def section_between(text: str, heading: str, next_heading: str) -> str:
    start = text.index(heading) + len(heading)
    end = text.index(next_heading, start)
    return text[start:end]


def normalized(text: str) -> str:
    return " ".join(text.split())


def test_dev_flow_is_the_only_impact_map_command_owner() -> None:
    """Dev Flow owns the canonical body; Context Manager keeps only a deprecation adapter."""
    assert COMMAND.exists()
    assert CM_ADAPTER.exists()
    command_files = sorted(REPO_ROOT.glob("*/commands/impact-map.md"))
    assert command_files == sorted([COMMAND, CM_ADAPTER])

    adapter_text = CM_ADAPTER.read_text()
    assert "> **Deprecated:**" in adapter_text
    assert "/rhize-devflow:impact-map" in adapter_text
    assert "## Phase 5: Reconcile After Implementation" not in adapter_text

    graph = json.loads(GENERATED_MAP.read_text())
    command_nodes = [
        node
        for node in graph["nodes"]
        if node.get("kind") == "command" and node.get("name") == "impact-map"
    ]
    assert sorted(node["path"] for node in command_nodes) == sorted(
        [
            "rhize-devflow/commands/impact-map.md",
            "rhize-context-manager/commands/impact-map.md",
        ]
    )

    expected_edge = {
        "from": "command:rhize-devflow/impact-map",
        "to": "skill:rhize-devflow/dev-flow-foundations",
        "type": "depends-on",
        "source": "relations-catalog",
    }
    obsolete_edge = {
        "from": "command:rhize-context-manager/impact-map",
        "to": "skill:rhize-devflow/dev-flow-foundations",
        "type": "depends-on",
        "source": "relations-catalog",
    }
    source_edges = json.loads(RELATIONS.read_text())["edges"]
    assert [edge for edge in source_edges if edge == expected_edge] == [expected_edge]
    assert obsolete_edge not in source_edges

    ownership_edges = [
        edge
        for edge in graph["edges"]
        if edge.get("from") == expected_edge["from"]
        and edge.get("to") == expected_edge["to"]
    ]
    assert ownership_edges == [expected_edge]

    replaces_edge = {
        "from": "command:rhize-devflow/impact-map",
        "to": "command:rhize-context-manager/impact-map",
        "type": "replaces",
        "source": "relations-catalog",
    }
    assert replaces_edge in source_edges
    assert replaces_edge in graph["edges"]


def test_command_is_compact_and_uses_codegraph_before_text_search() -> None:
    command = COMMAND.read_text()
    assert len(command.split()) <= 500
    assert "Load [`../docs/impact-map-reference.md`]" in command
    assert "use CodeGraph before text search or manual reads" in command
    for required in (
        "codegraph status",
        "codegraph explore",
        "codegraph impact",
        "codegraph affected",
        "command -v codegraph",
        "missing, corrupt, stale after synchronization, or unsupported",
        "Never run `codegraph init`",
    ):
        assert required.lower() in command.lower()
    assert "Use `rg` before CodeGraph" not in command
    assert "Use text search before CodeGraph" not in command
    assert "grep -r" not in command


def test_on_demand_reference_retains_safe_fallback_and_multi_repo_details() -> None:
    command = COMMAND.read_text()
    reference = REFERENCE.read_text()
    reference_normalized = normalized(reference).lower()
    assert len(reference.split()) > len(command.split())
    assert "the command owns the executable contract" in reference
    for required in (
        "Do not require a shell preflight when MCP is the active interface",
        "MCP error indicating a missing, stale, or corrupt index triggers the fallback",
        "Do not initialize CodeGraph. Indexing is a project/user decision",
        "For multiple repositories",
        "dynamic dispatch",
        "external systems",
        "Common Failure Modes",
    ):
        assert required.lower() in reference_normalized


def test_impact_map_is_semantic_delta_not_a_second_dependency_dump() -> None:
    command = COMMAND.read_text()
    for required in (
        "CodeGraph is authoritative for current structural truth",
        "impact map is authoritative for intended change",
        "Current behavior and evidence",
        "Intended semantic delta",
        "Invariants and must-not-change boundaries",
        "Planned additions and deletions",
        "External and operational effects",
        "Acceptance tests",
        "Explicitly unaffected paths",
        "Unknowns and confidence",
    ):
        assert required in command
    assert "Generate `IMPACT_MAP.md`" not in command


def test_progressive_disclosure_preserves_required_sections_and_gate_commands() -> None:
    command = COMMAND.read_text()
    reference = REFERENCE.read_text()
    required_sections = (
        "Current behavior and evidence",
        "Intended semantic delta",
        "Invariants and must-not-change boundaries",
        "Current structural touchpoints",
        "Planned additions and deletions",
        "External and operational effects",
        "Acceptance tests",
        "Explicitly unaffected paths",
        "Unknowns and confidence",
        "Implementation order",
    )
    for section in required_sections:
        assert f"`{section}`" in command
        assert f"## {section}" in reference
    for required in (
        "refactor_gate.py\" prepare",
        "refactor_gate.py\" reconcile",
        "dismiss --workspace",
        "blocks source edits until preparation",
        "Commit, push, merge, and completion remain blocked until reconciliation",
    ):
        assert required in command


def test_command_requires_post_implementation_reconciliation() -> None:
    command = COMMAND.read_text()
    reconciliation = section_between(
        command,
        "## Phase 5: Reconcile After Implementation",
        "## On-Demand Reference",
    )
    reconciliation_normalized = normalized(reconciliation)
    for required in (
        "codegraph sync",
        "Report one **Reconciliation verdict**",
        "`IN_SYNC` — evidence, diff, and map agree.",
        "`IN_SYNC_WITH_EXCEPTIONS` — named dynamic, generated, or external edges need manual evidence.",
        "`OUT_OF_SYNC` — an unexplained diff, missing consumer, stale graph, or unverified invariant remains.",
        "Do not declare completion while `OUT_OF_SYNC`.",
        "Repeat the original discovery branch for every root.",
        "repeat the original `rg` queries and targeted reads",
    ):
        assert required in reconciliation_normalized
    lowered = reconciliation.lower()
    assert "reconciliation is optional" not in lowered
    assert "reconciliation is unnecessary" not in lowered
    assert "reconciliation is not required" not in lowered


def test_foundation_and_docs_share_the_same_contract() -> None:
    foundation = FOUNDATION.read_text()
    foundation_normalized = normalized(foundation)
    skill = DEVFLOW_SKILL.read_text()
    for required in (
        "CodeGraph is authoritative for current structural truth",
        "impact map is authoritative for intended change",
        "CodeGraph-first",
        "command -v codegraph",
        "If neither interface is available",
        "Do not require a shell preflight when MCP is the active interface",
        "For every repository root, repeat the same discovery branch",
        "For a fallback root, repeat the original `rg` queries and targeted reads",
        "Absence of a graph is not evidence of synchronization",
    ):
        assert required in foundation_normalized
    assert "CodeGraph-first" in skill
    assert "rhize-context-manager" in skill

    for path in DOCS:
        text = path.read_text()
        assert "CodeGraph" in text, path
        assert "semantic" in text.lower(), path
        assert "impact-map" in text, path

    for path in DOCS[:3]:
        text = path.read_text()
        if "codex plugin add" in text:
            assert "codex plugin marketplace add" in text, path


def main() -> int:
    tests = [
        test_dev_flow_is_the_only_impact_map_command_owner,
        test_command_is_compact_and_uses_codegraph_before_text_search,
        test_on_demand_reference_retains_safe_fallback_and_multi_repo_details,
        test_impact_map_is_semantic_delta_not_a_second_dependency_dump,
        test_progressive_disclosure_preserves_required_sections_and_gate_commands,
        test_command_requires_post_implementation_reconciliation,
        test_foundation_and_docs_share_the_same_contract,
    ]
    failures = 0
    for function in tests:
        try:
            function()
            print(f"PASS {function.__name__}")
        except (AssertionError, ValueError, FileNotFoundError) as error:
            failures += 1
            print(f"FAIL {function.__name__}: {error}")
    if failures:
        print(f"\n{failures} test(s) failed.")
        return 1
    print("\nAll impact-map contract tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
