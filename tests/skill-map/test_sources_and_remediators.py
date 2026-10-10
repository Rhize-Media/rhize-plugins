"""test_sources_and_remediators.py — the project-launcher fork ledger and the
condition remediators added on 2026-10-10.

Builds the map in-process (no files written) and checks:
  - rhize-visual-plan has a fork-of edge to its BuilderIO upstream, with
    driftCheck metadata and the recorded baseline hash on the external node;
  - test-failure and merge-conflict each have exactly the verified
    remediator, and lint-failure deliberately has none;
  - external remediators carry their catalog label into the remediation index.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
build_skill_map = load_module(REPO_ROOT / "scripts" / "build_skill_map.py", "build_skill_map_t")

DOCUMENT = build_skill_map.build()
INDEXES = build_skill_map.build_indexes(DOCUMENT, build_skill_map.load_condition_patterns())
NODES = {n["id"]: n for n in DOCUMENT["nodes"]}


def test_visual_plan_fork_of_edge_and_baseline() -> None:
    forks = [
        e for e in DOCUMENT["edges"]
        if e["type"] == "fork-of" and e["from"] == "skill:project-launcher/rhize-visual-plan"
    ]
    assert len(forks) == 1
    edge = forks[0]
    assert edge["to"] == "external:BuilderIO/skills/visual-plan"
    assert edge["source"] == "sources-md"
    assert edge["driftCheck"] == {
        "upstreamRepo": "BuilderIO/skills",
        "upstreamPath": "visual-plan",
        "method": "content-hash",
    }
    upstream = NODES[edge["to"]]
    assert upstream["url"] == (
        "https://raw.githubusercontent.com/BuilderIO/skills/main/skills/visual-plan/SKILL.md"
    )
    assert upstream["baselineHash"] == (
        "0ea94674b21ea75caa1e64a9944d04fb3d5488ce1e25cc2315d616b685bbaa68"
    )
    assert "contentHashNormalized" in NODES["skill:project-launcher/rhize-visual-plan"]


def test_condition_remediators() -> None:
    remediation = INDEXES["remediation"]
    assert remediation["test-failure"]["skills"] == ["external:superpowers-systematic-debugging"]
    assert remediation["merge-conflict"]["skills"] == ["external:ecc-git-workflow"]
    # No verified lint/format fixer exists; see docs/skill-map/edge-semantics.md.
    assert remediation["lint-failure"]["skills"] == []


def test_external_remediators_carry_kind_labels() -> None:
    remediation = INDEXES["remediation"]
    assert remediation["test-failure"]["labels"] == {
        "external:superpowers-systematic-debugging": "superpowers:systematic-debugging (skill)"
    }
    assert remediation["merge-conflict"]["labels"] == {
        "external:ecc-git-workflow": "ecc:git-workflow (skill)"
    }
    assert remediation["type-error"]["labels"] == {
        "external:ecc-build-error-resolver": "ecc:build-error-resolver (agent)"
    }
    assert "labels" not in remediation["lint-failure"]
