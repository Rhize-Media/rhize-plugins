#!/usr/bin/env python3
"""Functionize representation, gate, and traversal contracts for RT-166."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = REPO_ROOT / "generated" / "skill-map.static.json"
INDEXES_PATH = REPO_ROOT / "generated" / "skill-map.indexes.json"
QUERIES_PATH = REPO_ROOT / "catalog" / "queries.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / "skill-map.schema.json"
QUERY_SCRIPT = REPO_ROOT / "scripts" / "query_skill_map.py"
ROUTER_SCRIPT = REPO_ROOT / "rhize-context-manager" / "hooks" / "skill-router.js"

FUNCTIONIZE = "skill:procedural-memory/functionize"
PROCEDURAL_MEMORY = "skill:procedural-memory/procedural-memory"
RUNTIME = "external:rhize-skill-cli"
FUNCTIONIZE_COMMANDS = {
    "command:procedural-memory/functionize",
    "command:procedural-memory/functionize-generate",
    "command:procedural-memory/functionize-review",
}


def _document() -> dict:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def _edges(doc: dict, *, edge_type: str | None = None) -> list[dict]:
    edges = doc["edges"]
    return [edge for edge in edges if edge_type is None or edge["type"] == edge_type]


def test_functionize_is_a_first_class_packaged_skill_and_command_surface() -> None:
    doc = _document()
    nodes = {node["id"]: node for node in doc["nodes"]}
    assert FUNCTIONIZE in nodes
    assert nodes[FUNCTIONIZE]["kind"] == "skill"
    assert nodes[FUNCTIONIZE]["path"] == "procedural-memory/skills/functionize/SKILL.md"
    assert FUNCTIONIZE_COMMANDS <= nodes.keys()
    contains = {
        (edge["from"], edge["to"])
        for edge in _edges(doc, edge_type="contains")
    }
    assert ("plugin:procedural-memory", FUNCTIONIZE) in contains
    assert {
        ("plugin:procedural-memory", command_id)
        for command_id in FUNCTIONIZE_COMMANDS
    } <= contains


def test_functionize_uses_discriminating_canonical_tags() -> None:
    doc = _document()
    tags = {
        edge["to"]
        for edge in doc["edges"]
        if edge["from"] == FUNCTIONIZE and edge["type"] in {"topic-tag", "stack-tag"}
    }
    assert tags == {"tag:topic/automation", "tag:stack/functionize"}


def test_functionize_and_registry_execution_share_only_the_runtime_dependency() -> None:
    doc = _document()
    nodes = {node["id"]: node for node in doc["nodes"]}
    assert nodes[RUNTIME]["kind"] == "external"
    dependencies = {
        (edge["from"], edge["to"])
        for edge in _edges(doc, edge_type="depends-on")
    }
    assert (FUNCTIONIZE, RUNTIME) in dependencies
    assert (PROCEDURAL_MEMORY, RUNTIME) in dependencies

    misleading_types = {
        "augments",
        "extends",
        "fork-of",
        "overlaps-with",
        "precedes",
        "remediates",
        "replaces",
        "supersedes",
    }
    assert not [
        edge
        for edge in doc["edges"]
        if FUNCTIONIZE in {edge["from"], edge["to"]} and edge["type"] in misleading_types
    ]


def test_skill_neighborhood_query_covers_every_edge_type() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    edge_types = set(schema["$defs"]["edgeType"]["enum"])
    query = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))["queries"]["skill-neighborhood"]
    steps = query["steps"]
    assert {step["edge"] for step in steps} == edge_types
    assert {(step["edge"], step["direction"]) for step in steps} == {
        (edge_type, direction)
        for edge_type in edge_types
        for direction in ("in", "out")
    }
    assert len({step["as"] for step in steps}) == len(steps)

    result = subprocess.run(
        [sys.executable, str(QUERY_SCRIPT), "skill-neighborhood", "procedural-memory/functionize"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["containsIn"] == ["plugin:procedural-memory"]
    assert payload["topicTagOut"] == ["tag:topic/automation"]
    assert payload["stackTagOut"] == ["tag:stack/functionize"]
    assert payload["dependsOnOut"] == [RUNTIME]
    assert payload["precedesIn"] == []
    assert payload["precedesOut"] == []


def _route(prompt: str, tmp_path: Path) -> str | None:
    context_dir = tmp_path / "context-manager"
    context_dir.mkdir(parents=True, exist_ok=True)
    (context_dir / "skill-map.indexes.json").write_bytes(INDEXES_PATH.read_bytes())
    result = subprocess.run(
        ["node", str(ROUTER_SCRIPT)],
        input=json.dumps({"prompt": prompt}),
        capture_output=True,
        text=True,
        env={**os.environ, "RHIZE_CONTEXT_MANAGER_DIR": str(context_dir)},
        check=True,
    )
    if not result.stdout.strip():
        return None
    message = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    match = re.search(r"Consider the ([\w.-]+):([\w./-]+) skill", message)
    assert match, message
    return f"skill:{match.group(1)}/{match.group(2)}"


def test_realistic_intents_route_to_the_correct_gate(tmp_path: Path) -> None:
    assert _route(
        "Use Functionize to turn this repeated CLI pattern into an inert proposal.",
        tmp_path,
    ) == FUNCTIONIZE
    assert _route(
        "Review the Functionize candidate without promoting or running it.",
        tmp_path,
    ) == FUNCTIONIZE
    assert _route(
        "Use procedural memory automation to recall and run a proven registry artifact.",
        tmp_path,
    ) == PROCEDURAL_MEMORY
