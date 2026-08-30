"""Contracts for the Rhize completed-branch promotion skill and its routing surfaces."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "rhize-devflow/skills/completed-branch-promotion/SKILL.md"
KEYWORDS_PATH = REPO_ROOT / "evals/rhize-devflow/keywords.json"
TRIGGERS_PATH = REPO_ROOT / "evals/rhize-devflow/trigger_cases.json"
RELATIONS_PATH = REPO_ROOT / "catalog/skill-relations.json"
SOURCES_PATH = REPO_ROOT / "rhize-devflow/skills/SOURCES.md"


def skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def frontmatter_description(text: str) -> str:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "skill must begin with YAML frontmatter"
    block = match.group(1)
    description = re.search(r"^description:\s*>-\n(?P<body>(?: {2}.*\n?)+)", block, re.MULTILINE)
    assert description, "skill must carry a folded frontmatter description"
    return " ".join(line.strip() for line in description.group("body").splitlines())


def test_exact_phrases_are_frontmatter_routing_triggers() -> None:
    description = frontmatter_description(skill_text()).lower()
    assert '"push to main"' in description
    assert '"push to dev and main"' in description
    assert "protected-branch" in description

    keywords = json.loads(KEYWORDS_PATH.read_text(encoding="utf-8"))
    assert keywords["skill:completed-branch-promotion"][:2] == [
        "push to main",
        "push to dev and main",
    ]

    triggers = json.loads(TRIGGERS_PATH.read_text(encoding="utf-8"))
    positive_prompts = {
        case["prompt"].lower()
        for case in triggers
        if case["target"] == "skill:completed-branch-promotion" and case["should_trigger"]
    }
    assert any("push to main" in prompt for prompt in positive_prompts)
    assert any("push to dev and main" in prompt for prompt in positive_prompts)


def test_skill_is_discoverable_by_both_host_manifests() -> None:
    claude_manifest = json.loads(
        (REPO_ROOT / "rhize-devflow/.claude-plugin/plugin.json").read_text(encoding="utf-8")
    )
    codex_manifest = json.loads(
        (REPO_ROOT / "rhize-devflow/.codex-plugin/plugin.json").read_text(encoding="utf-8")
    )
    assert claude_manifest["name"] == "rhize-devflow"
    assert codex_manifest["skills"] == "./skills/"
    assert SKILL_PATH.is_file()


def test_rhize_skill_is_single_owner_and_layers_on_existing_workflows() -> None:
    exact_trigger_owners = []
    for path in (REPO_ROOT / "rhize-devflow/skills").glob("*/SKILL.md"):
        description = frontmatter_description(path.read_text(encoding="utf-8")).lower()
        if '"push to main"' in description or '"push to dev and main"' in description:
            exact_trigger_owners.append(path.parent.name)
    assert exact_trigger_owners == ["completed-branch-promotion"]
    assert "extends: [dev-flow-foundations]" in skill_text()
    assert "consumes:\n  - superpowers:finishing-a-development-branch" in skill_text()
    assert "provenance: completed-branch-promotion" in skill_text()

    sources = SOURCES_PATH.read_text(encoding="utf-8")
    provenance_entry = sources.split("## completed-branch-promotion — 2026-08-30", 1)[1].split(
        "\n## ", 1
    )[0]
    assert "**Verb:** DEFER" in provenance_entry
    assert "**Graph relation:** consumes" in provenance_entry
    assert "**Upstream ref:** Superpowers 6.3.0" in provenance_entry
    assert "**License:** MIT" in provenance_entry
    assert "**Drift check:**" in provenance_entry

    relations = json.loads(RELATIONS_PATH.read_text(encoding="utf-8"))
    assert any(
        node["id"] == "external:superpowers-finishing-development-branch"
        for node in relations["nodes"]
    )
    assert {
        "from": "skill:rhize-devflow/completed-branch-promotion",
        "to": "external:superpowers-finishing-development-branch",
        "type": "depends-on",
        "source": "relations-catalog",
    } in relations["edges"]


def test_release_contract_covers_requested_failure_boundaries() -> None:
    text = skill_text().lower()
    required_evidence = {
        "explicit override": "an explicit narrower instruction wins",
        "manual push": "in a manual-push repository",
        "dev-less": "repository has no `dev` flow",
        "dirty worktree": "preserve unrelated staged, unstaged, and untracked work",
        "divergence": "non-fast-forward, diverged, or moved",
        "review failure": "fails blocks promotion",
        "deployment failure": "deployment, or smoke gate fails",
        "vercel author": "locally authored **empty release commit**",
        "no direct main push": '"push to main" never means a raw',
        "truthful result": "never claim \"regression-free\"",
        "upstream dependency": "if it is unavailable, stop before mutation",
    }
    missing = {name: phrase for name, phrase in required_evidence.items() if phrase not in text}
    assert missing == {}
