#!/usr/bin/env python3
"""Behavior tests for the global refactor evidence gate."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "rhize-devflow/scripts/refactor_gate.py"


def run_gate(
    state_dir: Path,
    *args: str,
    payload: dict | str | None = None,
    cwd: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RHIZE_REFACTOR_GATE_STATE_DIR"] = str(state_dir)
    if extra_env:
        env.update(extra_env)
    stdin = "" if payload is None else payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    (path / "src").mkdir()
    (path / "src/example.ts").write_text("export const value = 1\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "initial")


def write_plan(
    path: Path,
    mentioned_files: tuple[str, ...] = (),
    *,
    preparation_id: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    files = "\n".join(f"- `{name}`" for name in mentioned_files)
    preparation = f"Preparation ID: {preparation_id}\n" if preparation_id else ""
    path.write_text(
        f"""# Impact Map: Example refactor

{preparation}Discovery query: `Refactor the application example safely`

## Current behavior and evidence
- Existing behavior.

## Intended semantic delta
- Change the behavior safely.

## Invariants and must-not-change boundaries
- Preserve compatibility.

## Current structural touchpoints
{files or '- No production files yet.'}

## Acceptance tests
- Boundary behavior remains covered.

## Implementation order
1. Add tests.
2. Implement.
3. Reconcile.
"""
    )


RELEASE_FIXTURE = "git " + "commit -m unrelated-work"


@pytest.mark.parametrize("entrypoint", ["hook-write", "hook-command"])
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".planning/STATE.md", 0),
        (".planning/phases/01/01-SUMMARY.md", 0),
        ("docs/design-record.md", 0),
        ("docs/context/notes.rst", 0),
        ("README.md", 0),
        ("packages/app/AGENTS.md", 0),
        ("packages/app/STATE.md", 0),
        (".planning/fix.py", 2),
        ("docs/fix.ts", 2),
        ("docs/component.mdx", 2),
        (".planning/component.mdx", 2),
        ("claudedocs/component.mdx", 2),
        (".claude/analyses/mcp-impact.md", 0),
        (".codex/analyses/report.md", 0),
        (".claude/analyses/probe.py", 2),
        (".codex/analyses/probe.py", 2),
        ("src/example.ts", 2),
        ("src/content.md", 2),
    ],
)
def test_context_documents_are_exempt_but_source_stays_gated(
    tmp_path: Path, entrypoint: str, path: str, expected: int
) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    # Native edit paths and the exact absolute-path Codex patch shape both matter.
    tool_input = {"file_path": str(workspace / path)} if entrypoint == "hook-write" else {
        "input": f"*** Begin Patch\n*** Update File: {workspace / path}\n@@\n-old\n+new\n*** End Patch"
    }
    result = run_gate(state_dir, entrypoint, payload={"cwd": str(workspace), "tool_input": tool_input})
    assert result.returncode == expected, result.stderr
    status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
    assert json.loads(status.stdout)["phase"] == "pending"


def test_context_document_patch_cannot_hide_a_source_edit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    patch = "*** Begin Patch\n*** Update File: .planning/STATE.md\n@@\n-old\n+new\n*** Update File: src/example.ts\n@@\n-old\n+new\n*** End Patch"
    result = run_gate(state_dir, "hook-command", payload={"cwd": str(workspace), "tool_input": {"input": patch}})
    assert result.returncode == 2


@pytest.mark.parametrize("path", [".planning/STATE.md", "docs/triage.md", "packages/app/AGENTS.md"])
def test_context_only_release_and_reconciliation_exemptions(tmp_path: Path, path: str) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    prepared = run_gate(state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan), "--query", "Refactor the application example safely")
    assert prepared.returncode == 0, prepared.stderr
    document = workspace / path
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("Verified investigation findings.\n")
    payload = {"cwd": str(workspace), "tool_input": {"command": RELEASE_FIXTURE}}
    allowed = run_gate(state_dir, "hook-command", payload=payload)
    assert allowed.returncode == 0, allowed.stderr
    # Docs need no mention in the source impact map, but source is never exempt.
    (workspace / "src/example.ts").write_text("export const value = 2\n")
    blocked = run_gate(state_dir, "hook-command", payload=payload)
    assert blocked.returncode == 2, blocked.stderr
    reconciled = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert reconciled.returncode == 0, reconciled.stderr


@pytest.mark.parametrize("entrypoint", ["hook-write", "hook-command"])
@pytest.mark.parametrize("operation", ["Add", "Update"])
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("Projects/Client/Planning/Telemetry — review.md", 0),
        ("Daily Notes/Follow-up.markdown", 0),
        ("Projects/Client/script.py", 2),
        ("Projects/Client/component.mdx", 2),
        (".obsidian/plugins/example/main.js", 2),
        (".obsidian/plugins/example/instructions.md", 2),
        (".agents/skills/example/instructions.md", 2),
        ("Projects/Client/SKILL.md", 2),
    ],
)
def test_obsidian_documents_are_exempt_without_exempting_runtime_files(
    tmp_path: Path, entrypoint: str, operation: str, path: str, expected: int
) -> None:
    workspace = tmp_path / "Obsidian Vault"
    (workspace / ".obsidian").mkdir(parents=True)
    target = workspace / path
    if operation == "Update":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old\n")
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    tool_input = {"file_path": str(target)} if entrypoint == "hook-write" else {
        "input": f"*** Begin Patch\n*** {operation} File: {target}\n+new\n*** End Patch"
    }
    result = run_gate(state_dir, entrypoint, payload={"cwd": str(workspace), "tool_input": tool_input})
    assert result.returncode == expected, result.stderr
    status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
    assert json.loads(status.stdout)["phase"] == "pending"


@pytest.mark.parametrize("boundary", ["subfolder", "nested-vault", "git-dir", "git-file", "plugin", "symlink"])
def test_obsidian_detection_respects_workspace_and_repository_boundaries(
    tmp_path: Path, boundary: str
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".obsidian").mkdir(parents=True)
    folder = workspace / "Projects" / "Client"
    folder.mkdir(parents=True)
    target = folder / "content.md"
    expected = 0
    if boundary == "subfolder":
        workspace = folder
    elif boundary == "nested-vault":
        workspace = tmp_path
    elif boundary == "git-dir":
        (folder / ".git").mkdir()
        expected = 2
    elif boundary == "git-file":
        (folder / ".git").write_text("gitdir: elsewhere\n")
        expected = 2
    elif boundary == "plugin":
        (folder / ".claude-plugin").mkdir()
        expected = 2
    elif boundary == "symlink":
        (folder / ".git").mkdir()
        target.write_text("runtime instructions\n")
        link = workspace / "Linked note.md"
        link.symlink_to(target)
        target = link
        expected = 2
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    result = run_gate(state_dir, "hook-write", payload={"cwd": str(workspace), "tool_input": {"file_path": str(target)}})
    assert result.returncode == expected, result.stderr


def test_obsidian_note_patch_cannot_hide_source(tmp_path: Path) -> None:
    workspace = tmp_path / "vault"
    (workspace / ".obsidian").mkdir(parents=True)
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    patch = "*** Begin Patch\n*** Add File: Projects/note.md\n+note\n*** Add File: Projects/script.py\n+print(1)\n*** End Patch"
    result = run_gate(state_dir, "hook-command", payload={"cwd": str(workspace), "tool_input": {"input": patch}})
    assert result.returncode == 2, result.stderr


def test_obsidian_only_release_and_reconciliation(tmp_path: Path) -> None:
    workspace = tmp_path / "vault"
    init_repo(workspace)
    (workspace / ".obsidian").mkdir()
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    prepared = run_gate(state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan), "--query", "Refactor the application example safely")
    assert prepared.returncode == 0, prepared.stderr
    note = workspace / "Projects/new note.md"
    note.parent.mkdir()
    note.write_text("A new document.\n")
    payload = {"cwd": str(workspace), "tool_input": {"command": RELEASE_FIXTURE}}
    assert run_gate(state_dir, "hook-command", payload=payload).returncode == 0
    (workspace / "src/example.ts").write_text("export const value = 2\n")
    assert run_gate(state_dir, "hook-command", payload=payload).returncode == 2
    reconciled = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert reconciled.returncode == 0, reconciled.stderr
    assert json.loads(reconciled.stdout)["reconciliation"]["unmapped_files"] == []


def prompt_payload(workspace: Path, prompt: str) -> dict:
    return {"prompt": prompt, "cwd": str(workspace), "hook_event_name": "UserPromptSubmit"}


def test_material_prompt_creates_pending_gate_but_review_prompt_does_not(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"

    review = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Review the current implementation and report findings"),
    )
    assert review.returncode == 0
    assert review.stdout == ""

    plan_only = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Create an implementation plan for refactoring the API"),
    )
    assert plan_only.returncode == 0
    assert plan_only.stdout == ""

    material = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Create a plan and then refactor the API implementation"),
    )
    assert material.returncode == 0
    assert "impact-map evidence is required" in material.stdout

    status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
    assert json.loads(status.stdout)["phase"] == "pending"


@pytest.mark.parametrize(
    ("prompt", "should_gate"),
    [
        ("Simplify and consolidate this React component code", True),
        ("Deduplicate this repository function", True),
        ("Reduce complexity in this app code", True),
        ("Review this code for simplification opportunities and report findings", False),
        ("Simplify this component code, but do not edit anything", False),
        ("Simplify the fraction 12/18", False),
        ("Review this code and then simplify the implementation", True),
        ("Change the read-only field in this schema", True),
    ],
)
def test_simplify_prompts_respect_material_and_read_only_boundaries(
    tmp_path: Path, prompt: str, should_gate: bool
) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"

    result = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, prompt),
    )

    assert result.returncode == 0
    if should_gate:
        assert "impact-map evidence is required" in result.stdout
        status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
        assert json.loads(status.stdout)["phase"] == "pending"
    else:
        assert result.stdout == ""
        status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
        assert status.returncode == 0
        assert json.loads(status.stdout)["phase"] == "none"


def test_pending_gate_blocks_claude_write_and_codex_patch_but_allows_plan(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Refactor the application code"),
    )

    claude = run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
    )
    assert claude.returncode == 2
    assert "BLOCKED" in claude.stderr

    patch = "*** Begin Patch\n*** Update File: src/example.ts\n@@\n-old\n+new\n*** End Patch"
    codex = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(workspace), "tool_input": {"input": patch}},
    )
    assert codex.returncode == 2

    codex_orchestrated = run_gate(
        state_dir,
        "hook-command",
        payload={
            "cwd": str(workspace),
            "tool_input": {"input": f"const patch = `{patch}`; await tools.apply_patch(patch);"},
        },
    )
    assert codex_orchestrated.returncode == 2

    plan_write = run_gate(
        state_dir,
        "hook-write",
        payload={
            "cwd": str(workspace),
            "tool_input": {"file_path": str(workspace / ".claude/plans/refactor.md")},
        },
    )
    assert plan_write.returncode == 0


def test_pending_gate_auto_prepares_one_recent_complete_map_before_source_write(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    pending = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Refactor the application code"),
    )
    preparation_id = re.search(r"Preparation ID: ([a-f0-9]{24})", pending.stdout)
    assert preparation_id
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",), preparation_id=preparation_id.group(1))

    result = run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
    )

    assert result.returncode == 0, result.stderr
    assert "Prepared the only complete impact map" in result.stdout
    status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
    receipt = json.loads(status.stdout)
    assert receipt["phase"] == "implementation"
    assert Path(receipt["plan"]["path"]) == plan
    assert [event["phase"] for event in receipt["lifecycle"]["events"]] == [
        "pending",
        "prepared",
        "implementation",
    ]


def test_pending_gate_keeps_multiple_recent_maps_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    pending = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Refactor the application code"),
    )
    preparation_id = re.search(r"Preparation ID: ([a-f0-9]{24})", pending.stdout)
    assert preparation_id
    write_plan(workspace / ".claude/plans/first.md", preparation_id=preparation_id.group(1))
    write_plan(workspace / ".claude/plans/second.md", preparation_id=preparation_id.group(1))

    result = run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
    )

    assert result.returncode == 2
    assert "2 recent maps" in result.stderr
    status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
    assert json.loads(status.stdout)["phase"] == "pending"


def test_pending_gate_does_not_auto_prepare_a_map_from_another_request(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    first = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Refactor the application code"),
    )
    first_id = re.search(r"Preparation ID: ([a-f0-9]{24})", first.stdout)
    assert first_id
    plan = workspace / ".claude/plans/old.md"
    write_plan(plan, preparation_id=first_id.group(1))
    os.utime(plan, (0, 0))

    second = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Fix the application route"),
    )
    second_id = re.search(r"Preparation ID: ([a-f0-9]{24})", second.stdout)
    assert second_id and second_id.group(1) != first_id.group(1)
    result = run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
    )

    assert result.returncode == 2
    assert "no recent complete map matching the active Preparation ID" in result.stderr


def test_pending_gate_does_not_auto_prepare_an_incomplete_map(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    pending = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Refactor the application code"),
    )
    preparation_id = re.search(r"Preparation ID: ([a-f0-9]{24})", pending.stdout)
    assert preparation_id
    plan = workspace / ".claude/plans/incomplete.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(
        f"Preparation ID: {preparation_id.group(1)}\n"
        "Discovery query: `Refactor the application example safely`\n"
        "This map lacks the required sections.\n"
    )

    result = run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
    )

    assert result.returncode == 2
    assert "no recent complete map matching the active Preparation ID" in result.stderr


def test_prepare_requires_complete_plan_and_records_registry_fallback(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    plan = workspace / ".claude/plans/refactor.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("# incomplete\n")
    (workspace / "COMPONENT_REGISTRY.md").write_text("# Registry\n- ExampleWidget\n")

    bad = run_gate(
        state_dir,
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example widget refactor",
    )
    assert bad.returncode == 2
    assert "missing required section" in bad.stderr

    write_plan(plan, ("src/example.ts",))
    good = run_gate(
        state_dir,
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example widget refactor",
    )
    assert good.returncode == 0, good.stderr
    receipt = json.loads(good.stdout)
    assert receipt["phase"] == "prepared"
    # refactor_gate resolves rg via shutil.which, so the fallback mode depends on whether an
    # rg BINARY exists (a shell function/alias is invisible to which). Assert the exact mode
    # this environment should produce rather than assuming ripgrep is installed.
    expected_mode = "rg-fallback" if shutil.which("rg") else "python-fallback"
    assert receipt["repositories"][0]["structural_evidence"]["mode"] == expected_mode
    assert receipt["registries"][0]["path"].endswith("COMPONENT_REGISTRY.md")


def test_prepare_discovers_nested_repos_and_uses_existing_codegraph(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    backend = workspace / "backend"
    frontend = workspace / "frontend"
    init_repo(backend)
    init_repo(frontend)
    (backend / ".codegraph").mkdir()
    (frontend / ".codegraph").mkdir()
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("backend/src/example.ts", "frontend/src/example.ts"))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    codegraph = fake_bin / "codegraph"
    codegraph.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  status) echo 'Index is up to date' ;;\n"
        "  explore) echo 'symbol callers tests' ;;\n"
        "  sync) echo 'Index synchronized' ;;\n"
        "esac\n"
    )
    codegraph.chmod(0o755)

    result = run_gate(
        tmp_path / "state",
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example refactor callers tests",
        extra_env={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert len(receipt["repositories"]) == 2
    assert {item["structural_evidence"]["mode"] for item in receipt["repositories"]} == {
        "codegraph"
    }


def test_prepare_synchronizes_a_stale_existing_codegraph_without_initializing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    (workspace / ".codegraph").mkdir()
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "synced"
    codegraph = fake_bin / "codegraph"
    codegraph.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = status ]; then\n"
        "  if [ -f \"$FAKE_CODEGRAPH_MARKER\" ]; then echo 'Index is up to date'; else echo 'Index is stale'; fi\n"
        "elif [ \"$1\" = sync ]; then touch \"$FAKE_CODEGRAPH_MARKER\"; echo 'Index synchronized'\n"
        "elif [ \"$1\" = explore ]; then echo 'symbol callers tests'\n"
        "fi\n"
    )
    codegraph.chmod(0o755)
    result = run_gate(
        tmp_path / "state",
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example callers tests",
        extra_env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_CODEGRAPH_MARKER": str(marker),
        },
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)["repositories"][0]["structural_evidence"]
    assert evidence["mode"] == "codegraph"
    assert marker.is_file()


def test_plan_hash_change_relocks_source_writes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    prepared = run_gate(
        state_dir,
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example refactor",
    )
    assert prepared.returncode == 0
    plan.write_text(plan.read_text() + "\n- New scope.\n")

    result = run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
    )
    assert result.returncode == 2
    assert "impact map changed" in result.stderr


def test_reprepare_after_map_change_preserves_original_git_baseline(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    assert run_gate(
        state_dir,
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example refactor",
    ).returncode == 0

    (workspace / "src/example.ts").write_text("export const value = 2\n")
    plan.write_text(plan.read_text() + "\n- Expanded acceptance evidence.\n")

    prepared_again = run_gate(
        state_dir,
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example refactor",
    )
    assert prepared_again.returncode == 0, prepared_again.stderr
    receipt = json.loads(prepared_again.stdout)
    assert "src/example.ts" not in receipt["repositories"][0]["dirty"]

    reconciled = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert reconciled.returncode == 0, reconciled.stderr
    assert "src/example.ts" in json.loads(reconciled.stdout)["reconciliation"]["changed_files"]


def test_reconcile_requires_actual_changed_files_in_map_and_unblocks_commit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    assert run_gate(
        state_dir,
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example refactor",
    ).returncode == 0

    write_hook = run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
    )
    assert write_hook.returncode == 0
    (workspace / "src/example.ts").write_text("export const value = 2\n")

    blocked = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(workspace), "tool_input": {"cmd": "git commit -am refactor"}},
    )
    assert blocked.returncode == 2

    reconciled = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert reconciled.returncode == 0, reconciled.stderr
    assert json.loads(reconciled.stdout)["reconciliation"]["verdict"] == "IN_SYNC_WITH_EXCEPTIONS"

    allowed = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(workspace), "tool_input": {"command": "git commit -am refactor"}},
    )
    assert allowed.returncode == 0


def test_reconcile_rejects_an_unmapped_changed_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    assert run_gate(
        state_dir,
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example refactor",
    ).returncode == 0
    (workspace / "src/unmapped.ts").write_text("export const missed = true\n")

    result = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert result.returncode == 2
    assert "src/unmapped.ts" in result.stderr


def test_stop_closes_reconciled_receipt_without_contaminating_the_next_task(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    assert run_gate(
        state_dir,
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example refactor",
    ).returncode == 0
    assert run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
    ).returncode == 0
    (workspace / "src/example.ts").write_text("export const value = 2\n")
    assert run_gate(state_dir, "reconcile", "--workspace", str(workspace)).returncode == 0

    stopped = run_gate(
        state_dir,
        "hook-stop",
        payload={"cwd": str(workspace), "hook_event_name": "Stop"},
    )
    assert stopped.returncode == 0
    status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
    assert json.loads(status.stdout)["phase"] == "completed"

    unrelated_write = run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/unrelated.ts")}},
    )
    assert unrelated_write.returncode == 0
    status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
    assert json.loads(status.stdout)["phase"] == "completed"

    next_refactor = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Refactor the application code again"),
    )
    assert next_refactor.returncode == 0
    status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
    assert json.loads(status.stdout)["phase"] == "pending"


def test_unchanged_preexisting_dirty_file_is_not_charged_to_refactor(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    (workspace / "src/preexisting.ts").write_text("export const userWork = true\n")
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    state_dir = tmp_path / "state"
    assert run_gate(
        state_dir,
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example refactor",
    ).returncode == 0
    (workspace / "src/example.ts").write_text("export const value = 3\n")

    result = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert result.returncode == 0, result.stderr
    changed = json.loads(result.stdout)["reconciliation"]["changed_files"]
    assert "src/example.ts" in changed
    assert "src/preexisting.ts" not in changed


def test_dismiss_and_environment_bypass_prevent_lockout(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Refactor the application code"),
    )
    dismissed = run_gate(
        state_dir,
        "dismiss",
        "--workspace",
        str(workspace),
        "--reason",
        "False positive: documentation-only task",
    )
    assert dismissed.returncode == 0
    assert run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
    ).returncode == 0

    bypassed = run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
        extra_env={"RHIZE_REFACTOR_GATE": "off"},
    )
    assert bypassed.returncode == 0


@pytest.mark.parametrize("command", ["hook-prompt", "hook-write", "hook-command", "hook-stop"])
def test_hook_modes_fail_open_on_malformed_json_without_state(tmp_path: Path, command: str) -> None:
    result = run_gate(tmp_path / "state", command, payload="not json{{{")
    assert result.returncode == 0


def test_malformed_write_payload_fails_closed_when_workspace_is_pending(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(workspace, "Refactor the application code"),
    )
    result = run_gate(
        state_dir,
        "hook-write",
        payload="not json{{{",
        extra_env={"CLAUDE_PROJECT_DIR": str(workspace)},
    )
    assert result.returncode == 2
    assert "malformed write payload" in result.stderr


# --- filesystem-root arming ------------------------------------------------------------
# Regression cluster for 2026-09-09: a Projectless context (no repo cwd) armed a `pending`
# receipt at "/". Because find_state_for_path falls back to a longest-prefix containment
# scan, that receipt matched every path on the machine - blocking release commands in
# unrelated repositories, and (via hook_stop on phase "implementation") blocking turn end
# for every session, which is how a scheduled routine could hang mid-run.


def test_material_prompt_at_filesystem_root_arms_nothing(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    result = run_gate(
        state_dir,
        "hook-prompt",
        payload={
            # Exactly the prompt the sibling test proves IS material, so this asserts the
            # root guard specifically and not merely that the prompt was uninteresting.
            "prompt": "Create a plan and then refactor the API implementation",
            "cwd": "/",
            "hook_event_name": "UserPromptSubmit",
        },
    )

    assert result.returncode == 0, result.stderr
    assert list(state_dir.glob("*.json")) == []


def test_stale_root_receipt_never_blocks_a_release_elsewhere(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    # Hand-write the exact artifact the old version produced.
    root_state = {
        "schema_version": 1,
        "workspace": "/",
        "phase": "pending",
        "created_at": "2026-09-09T12:45:42Z",
        "prompt": "Generate 0 to 3 hyperpersonalized suggestions in this Projectless task",
    }
    (state_dir / "root-8a5edab282632443219e.json").write_text(json.dumps(root_state))

    outside = tmp_path / "not-a-repo"
    outside.mkdir()

    result = run_gate(
        state_dir,
        "hook-command",
        payload={
            "tool_name": "Bash",
            "tool_input": {"command": RELEASE_FIXTURE},
            "cwd": str(outside),
        },
    )

    assert result.returncode == 0, result.stderr
    assert "BLOCKED" not in result.stderr


def test_stale_root_receipt_stays_visible_to_operators(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "root-8a5edab282632443219e.json").write_text(
        json.dumps({"schema_version": 1, "workspace": "/", "phase": "pending"})
    )

    # The guard lives in the containment scan, not in read_state, so a direct lookup of the
    # root workspace must still report it - otherwise nobody could find or clear the file.
    result = run_gate(state_dir, "status", "--workspace", "/")

    assert result.returncode == 0, result.stderr
    assert "pending" in result.stdout


def test_prepare_at_filesystem_root_is_a_warning_not_a_failure(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    plan = tmp_path / "plan.md"
    write_plan(plan)

    result = run_gate(state_dir, "prepare", "--workspace", "/", "--plan", str(plan), "--query", "q")

    # Exit 0 on purpose: a nonzero exit here would be a NEW failure mode in automation that
    # cannot ask a human, which is strictly worse than doing nothing.
    assert result.returncode == 0, result.stderr
    assert "SKIPPED" in result.stderr
    assert list(state_dir.glob("*.json")) == []


# --- Command-derived workspace resolution (cd / git -C / --git-dir / --work-tree) -----------
#
# Regression coverage for: a session whose payload cwd is repo A running
# `cd /path/to/repoB && git commit ...` (no `git -C`) must be judged against repo B's own
# receipt, not repo A's — mirroring the `git -C` support that already existed. Each test below
# arms repo A with a hard-blocking `implementation`-phase receipt (any release command judged
# against repo A must return 2) so a returncode of 0 can only mean the gate correctly resolved
# the command to a *different*, unblocked repo.


def arm_implementation_receipt(state_dir: Path, workspace: Path) -> None:
    """Prepare `workspace`, then trigger a gated source write so its receipt lands in the
    `implementation` phase — the phase that unconditionally blocks commit/push/merge with no
    config/planning exemption, making it an unambiguous blocking signal for these tests."""
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    assert run_gate(
        state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan), "--query", "example refactor"
    ).returncode == 0
    write_hook = run_gate(
        state_dir,
        "hook-write",
        payload={"cwd": str(workspace), "tool_input": {"file_path": str(workspace / "src/example.ts")}},
    )
    assert write_hook.returncode == 0
    (workspace / "src/example.ts").write_text("export const value = 2\n")
    status = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
    assert json.loads(status.stdout)["phase"] == "implementation"


def test_cd_prefixed_release_is_judged_against_target_repo_not_cwd(tmp_path: Path) -> None:
    repo_a = tmp_path / "repoA"
    repo_b = tmp_path / "repoB"
    init_repo(repo_a)
    init_repo(repo_b)
    state_dir = tmp_path / "state"
    arm_implementation_receipt(state_dir, repo_a)

    # Sanity: committing against cwd (repo A) directly is genuinely blocked.
    direct = run_gate(
        state_dir, "hook-command", payload={"cwd": str(repo_a), "tool_input": {"command": "git commit -am x"}}
    )
    assert direct.returncode == 2, direct.stderr

    # A leading `cd <repoB> &&` must be judged against repo B's (clean, receipt-free) state.
    redirected = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(repo_a), "tool_input": {"command": f"cd {repo_b} && git commit -am x"}},
    )
    assert redirected.returncode == 0, redirected.stderr

    # A `cd <repoB>;` (semicolon separator) form resolves the same way.
    redirected_semicolon = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(repo_a), "tool_input": {"command": f"cd {repo_b}; git commit -am x"}},
    )
    assert redirected_semicolon.returncode == 0, redirected_semicolon.stderr


def test_git_dash_c_release_is_judged_against_target_repo_not_cwd(tmp_path: Path) -> None:
    repo_a = tmp_path / "repoA"
    repo_b = tmp_path / "repoB"
    init_repo(repo_a)
    init_repo(repo_b)
    state_dir = tmp_path / "state"
    arm_implementation_receipt(state_dir, repo_a)

    result = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(repo_a), "tool_input": {"command": f"git -C {repo_b} commit -am x"}},
    )
    assert result.returncode == 0, result.stderr


def test_git_dir_and_work_tree_flags_are_judged_against_target_repo(tmp_path: Path) -> None:
    repo_a = tmp_path / "repoA"
    repo_b = tmp_path / "repoB"
    init_repo(repo_a)
    init_repo(repo_b)
    state_dir = tmp_path / "state"
    arm_implementation_receipt(state_dir, repo_a)

    work_tree = run_gate(
        state_dir,
        "hook-command",
        payload={
            "cwd": str(repo_a),
            "tool_input": {"command": f"git --work-tree={repo_b} --git-dir={repo_b}/.git commit -am x"},
        },
    )
    assert work_tree.returncode == 0, work_tree.stderr

    git_dir_only = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(repo_a), "tool_input": {"command": f"git --git-dir={repo_b}/.git commit -am x"}},
    )
    assert git_dir_only.returncode == 0, git_dir_only.stderr


def test_relative_cd_resolves_against_payload_cwd(tmp_path: Path) -> None:
    repo_a = tmp_path / "repoA"
    repo_b = tmp_path / "repoB"
    init_repo(repo_a)
    init_repo(repo_b)
    state_dir = tmp_path / "state"
    arm_implementation_receipt(state_dir, repo_a)

    result = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(repo_a), "tool_input": {"command": "cd ../repoB && git commit -am x"}},
    )
    assert result.returncode == 0, result.stderr


def test_ambiguous_multi_cd_stays_cwd_based(tmp_path: Path) -> None:
    repo_a = tmp_path / "repoA"
    repo_b = tmp_path / "repoB"
    repo_c = tmp_path / "repoC"
    init_repo(repo_a)
    init_repo(repo_b)
    init_repo(repo_c)
    state_dir = tmp_path / "state"
    arm_implementation_receipt(state_dir, repo_a)

    # Two different leading `cd` targets before the git verb: today's cwd-based behavior
    # must be kept rather than guessing which target was meant, so this still resolves to
    # repo A (which is blocked) instead of either repo B or repo C (both clean).
    chained = run_gate(
        state_dir,
        "hook-command",
        payload={
            "cwd": str(repo_a),
            "tool_input": {"command": f"cd {repo_b} && cd {repo_c} && git commit -am x"},
        },
    )
    assert chained.returncode == 2, chained.stderr

    # A second `cd` separated by an intervening command is just as ambiguous as one
    # immediately chained onto the first — the git verb actually runs in repo C here, not
    # repo B, so naively taking the *first* `cd` would silently point the check at the
    # wrong repo instead of falling back to cwd.
    separated = run_gate(
        state_dir,
        "hook-command",
        payload={
            "cwd": str(repo_a),
            "tool_input": {"command": f"cd {repo_b} && npm test && cd {repo_c} && git commit -am x"},
        },
    )
    assert separated.returncode == 2, separated.stderr


@pytest.mark.parametrize("bogus_kind", ["nonexistent", "not-a-git-repo"])
def test_nonexistent_or_non_git_cd_target_falls_back_to_cwd(tmp_path: Path, bogus_kind: str) -> None:
    repo_a = tmp_path / "repoA"
    init_repo(repo_a)
    state_dir = tmp_path / "state"
    arm_implementation_receipt(state_dir, repo_a)

    if bogus_kind == "nonexistent":
        bogus = tmp_path / "does-not-exist"
    else:
        bogus = tmp_path / "plain-dir"
        bogus.mkdir()

    # The `cd` target does not resolve to a real Git repository, so the gate must fall back
    # to judging the command against cwd (repo A, which is blocked) rather than silently
    # allowing it because the bogus target has no receipt of its own.
    result = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(repo_a), "tool_input": {"command": f"cd {bogus} && git commit -am x"}},
    )
    assert result.returncode == 2, result.stderr


def test_subshell_and_pushd_cd_stay_cwd_based(tmp_path: Path) -> None:
    repo_a = tmp_path / "repoA"
    repo_b = tmp_path / "repoB"
    init_repo(repo_a)
    init_repo(repo_b)
    state_dir = tmp_path / "state"
    arm_implementation_receipt(state_dir, repo_a)

    subshell = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(repo_a), "tool_input": {"command": f"(cd {repo_b} && git commit -am x)"}},
    )
    assert subshell.returncode == 2, subshell.stderr

    pushd = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(repo_a), "tool_input": {"command": f"pushd {repo_b} && git commit -am x"}},
    )
    assert pushd.returncode == 2, pushd.stderr

    variable = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(repo_a), "tool_input": {"command": "cd $REPO && git commit -am x"}},
    )
    assert variable.returncode == 2, variable.stderr


def test_apply_patch_source_write_resolves_cd_prefixed_target_repo(tmp_path: Path) -> None:
    """The same command-derived resolution applies to the patch-carried source-write check
    (Codex `functions.exec`/apply_patch text arriving through `hook-command`), not just the
    release-command block."""
    repo_a = tmp_path / "repoA"
    repo_b = tmp_path / "repoB"
    init_repo(repo_a)
    init_repo(repo_b)
    state_dir = tmp_path / "state"
    # repo B is pending (material prompt seen, no map prepared yet), so a gated source write
    # routed there must be blocked; repo A (cwd) has no receipt at all, so if the write were
    # mis-attributed to cwd it would be wrongly allowed.
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(repo_b, "Refactor the application code"))
    patch = "*** Begin Patch\n*** Update File: src/example.ts\n@@\n-old\n+new\n*** End Patch"

    result = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(repo_a), "tool_input": {"command": f"cd {repo_b} && apply_patch <<'EOF'\n{patch}\nEOF"}},
    )
    assert result.returncode == 2, result.stderr


# --- Stop ownership ---------------------------------------------------------------------
# Regression for 2026-09-28: a read-only Q&A session in the same checkout was blocked at
# every Stop while a different session held the workspace in "implementation". The Stop
# block now applies only to sessions that performed a gated source write (the owners);
# write and release gates stay workspace-wide, and missing identity fails closed.


def _prepared_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    assert run_gate(
        state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan),
        "--query", "example refactor",
    ).returncode == 0
    return workspace, state_dir, plan


def _owned_write(state_dir: Path, workspace: Path, session_id: str) -> None:
    result = run_gate(
        state_dir,
        "hook-write",
        payload={
            "session_id": session_id,
            "cwd": str(workspace),
            "tool_input": {"file_path": str(workspace / "src/example.ts")},
        },
    )
    assert result.returncode == 0, result.stderr


def _stop(state_dir: Path, workspace: Path, session_id: str | None) -> subprocess.CompletedProcess[str]:
    payload: dict = {"cwd": str(workspace), "hook_event_name": "Stop"}
    if session_id is not None:
        payload["session_id"] = session_id
    return run_gate(state_dir, "hook-stop", payload=payload)


def _status(state_dir: Path, workspace: Path) -> dict:
    return json.loads(run_gate(state_dir, "status", "--workspace", str(workspace), "--json").stdout)


def test_stop_blocks_the_session_that_wrote(tmp_path: Path) -> None:
    workspace, state_dir, _plan = _prepared_workspace(tmp_path)
    _owned_write(state_dir, workspace, "writer-session")

    stopped = _stop(state_dir, workspace, "writer-session")

    assert stopped.returncode == 2
    assert "has not been reconciled" in stopped.stderr
    state = _status(state_dir, workspace)
    assert state["phase"] == "implementation"
    assert state["owner_sessions"] == ["writer-session"]


def test_stop_allows_a_read_only_session_in_the_same_workspace(tmp_path: Path) -> None:
    workspace, state_dir, _plan = _prepared_workspace(tmp_path)
    _owned_write(state_dir, workspace, "writer-session")

    stopped = _stop(state_dir, workspace, "reader-session")

    assert stopped.returncode == 0, stopped.stderr
    state = _status(state_dir, workspace)
    assert state["phase"] == "implementation"
    assert state["owner_sessions"] == ["writer-session"]
    # The owner is still held to reconciliation.
    assert _stop(state_dir, workspace, "writer-session").returncode == 2


def test_stop_fails_closed_without_a_session_id(tmp_path: Path) -> None:
    workspace, state_dir, _plan = _prepared_workspace(tmp_path)
    _owned_write(state_dir, workspace, "writer-session")

    assert _stop(state_dir, workspace, None).returncode == 2
    assert _stop(state_dir, workspace, "").returncode == 2


def test_stop_fails_closed_when_no_owner_was_recorded(tmp_path: Path) -> None:
    workspace, state_dir, _plan = _prepared_workspace(tmp_path)
    # A source change made outside the write hooks reaches "implementation" only through an
    # OUT_OF_SYNC reconcile, which has no session identity to record.
    (workspace / "src/unmapped.ts").write_text("export const other = 1\n")
    assert run_gate(state_dir, "reconcile", "--workspace", str(workspace)).returncode == 2
    assert _status(state_dir, workspace)["phase"] == "implementation"

    assert _stop(state_dir, workspace, "any-session").returncode == 2


def test_every_writing_session_is_an_owner(tmp_path: Path) -> None:
    workspace, state_dir, _plan = _prepared_workspace(tmp_path)
    _owned_write(state_dir, workspace, "session-b")
    _owned_write(state_dir, workspace, "session-a")
    _owned_write(state_dir, workspace, "session-b")

    assert _status(state_dir, workspace)["owner_sessions"] == ["session-a", "session-b"]
    assert _stop(state_dir, workspace, "session-a").returncode == 2
    assert _stop(state_dir, workspace, "session-b").returncode == 2
    assert _stop(state_dir, workspace, "session-c").returncode == 0


def test_reprepare_during_implementation_keeps_owners(tmp_path: Path) -> None:
    workspace, state_dir, plan = _prepared_workspace(tmp_path)
    _owned_write(state_dir, workspace, "writer-session")
    write_plan(plan, ("src/example.ts", "src/extra.ts"))
    assert run_gate(
        state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan),
        "--query", "example refactor",
    ).returncode == 0

    assert _status(state_dir, workspace)["owner_sessions"] == ["writer-session"]


def test_non_owner_stop_does_not_relax_workspace_release_gate(tmp_path: Path) -> None:
    workspace, state_dir, _plan = _prepared_workspace(tmp_path)
    _owned_write(state_dir, workspace, "writer-session")
    (workspace / "src/example.ts").write_text("export const value = 2\n")
    assert _stop(state_dir, workspace, "reader-session").returncode == 0

    release = run_gate(
        state_dir,
        "hook-command",
        payload={
            "session_id": "reader-session",
            "cwd": str(workspace),
            "tool_input": {"command": RELEASE_FIXTURE},
        },
    )

    assert release.returncode == 2
    assert "reconciled refactor-evidence receipt" in release.stderr


# --- Shell writes while pending (2026-10-16: an executor edited six source files through Bash
# heredocs, `sed -i` and redirects before any map existed; only the commit was caught). ---

SHELL_PATCH = """diff --git a/src/example.ts b/src/example.ts
--- a/src/example.ts
+++ b/src/example.ts
@@ -1 +1 @@
-export const value = 1
+export const value = 2
"""

SHELL_SOURCE_WRITES = [
    "python3 - <<'EOF'\np = 'src/example.ts'\nopen(p, 'w').write('export const value = 2\\n')\nEOF",
    "python3 -c \"open('src/example.ts', 'w').write('x')\"",
    "node -e \"require('fs').writeFileSync('src/example.ts', 'x')\"",
    "sed -i '' 's/1/2/' src/example.ts",
    "perl -pi -e 's/1/2/' src/example.ts",
    "echo 'export const value = 2' > src/example.ts",
    "cat <<'EOF' > src/created.ts\nexport const created = true\nEOF",
    "printf x | tee -a src/example.ts",
    "cp /etc/hosts src/example.ts",
    "cd src && echo x >> example.ts",
    "git apply fix.patch",
    "rtk sed -i '' 's/1/2/' src/example.ts",
    "rtk proxy python3 -c \"open('src/example.ts', 'w').write('x')\"",
    "FOO=1 rtk proxy tee src/example.ts < /dev/null",
    # Verifier follow-ups: comments, `#` inside a word, ANSI-C quotes, runner prefixes, loops.
    "npm test # run tests first\nsed -i '' 's/1/2/' src/example.ts",
    "curl -s https://example.test/#frag > src/example.ts",
    "echo $'it\\'s' && sed -i '' 's/1/2/' src/example.ts",
    "uv run python -c \"open('src/example.ts', 'w')\"",
    "python3 - <<'EOF'\nfor p in ['src/example.ts']:\n    Path(p).write_text('x')\nEOF",
    "echo x > src/my\\ file.ts",
]


def _isolated_repo(workspace: Path) -> None:
    init_repo(workspace)
    # The gate shells out to git itself; keep the user's global excludes out of the fixture.
    git(workspace, "config", "core.excludesFile", "/dev/null")
    (workspace / ".gitignore").write_text("dist/\n")
    (workspace / "fix.patch").write_text(SHELL_PATCH)
    git(workspace, "add", ".gitignore", "fix.patch")
    git(workspace, "commit", "-qm", "ignore build output; patch fixture")


def _shell(state_dir: Path, workspace: Path, command: str, mode: str = "hook-command"):
    return run_gate(
        state_dir,
        mode,
        payload={"session_id": "executor", "cwd": str(workspace), "tool_input": {"command": command}},
    )


@pytest.mark.parametrize("command", SHELL_SOURCE_WRITES)
def test_pending_gate_blocks_shell_writes_to_source(tmp_path: Path, command: str) -> None:
    workspace = tmp_path / "workspace"
    _isolated_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))

    blocked = _shell(state_dir, workspace, command)

    assert blocked.returncode == 2, blocked.stderr
    assert "source edits require a prepared refactor-evidence receipt" in blocked.stderr
    assert "prepare --workspace" in blocked.stderr
    assert "src/" in blocked.stderr
    assert _status(state_dir, workspace)["phase"] == "pending"


@pytest.mark.parametrize("command", SHELL_SOURCE_WRITES)
def test_prepared_gate_allows_shell_writes_and_records_the_owner(tmp_path: Path, command: str) -> None:
    workspace = tmp_path / "workspace"
    _isolated_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts", "src/created.ts"))
    assert run_gate(
        state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan),
        "--query", "Refactor the application example safely",
    ).returncode == 0

    allowed = _shell(state_dir, workspace, command)

    assert allowed.returncode == 0, allowed.stderr
    receipt = _status(state_dir, workspace)
    assert receipt["phase"] == "implementation"
    assert receipt["owner_sessions"] == ["executor"]


@pytest.mark.parametrize(
    "command",
    [
        "cat src/example.ts",
        "grep -n value src/example.ts",
        "rtk grep -n value src",
        "git diff -- src/example.ts",
        "rtk git diff",
        "python3 -m pytest -q 2>&1 | tail -5",
        "npm run build > /dev/null 2>&1",
        "python3 -c \"print(open('src/example.ts').read())\"",
        "sed -n 1p src/example.ts",
        "git apply --check fix.patch",
        "echo 'a > b.ts' | cat",
        "echo x > dist/out.js",
        "echo x > build.log",
        "echo notes > docs/notes.md",
        "cat <<'EOF' > .claude/plans/next.md\n# plan > src/example.ts\nEOF",
        "python3 - <<'EOF'\nimport json\njson.dump({}, open('/tmp/out.json', 'w'))\nEOF",
        "cp src/example.ts {scratch}/copy.ts",
        "echo x > {scratch}/out.ts",
        # Quoted or escaped operators are arguments, not redirects.
        "grep -c '>' src/example.ts",
        "rg -n \">>\" src/example.ts",
        "echo 'x' \\> src/example.ts",
        "perl -Ilib src/example.ts",
        # A variable write target no longer charges every file the snippet reads.
        "python3 -c \"import sys; d = open('src/example.ts').read(); open(sys.argv[1], 'w').write(d)\" /tmp/x",
        "python3 - <<'EOF'\nimport os, tempfile\nout = os.path.join(tempfile.gettempdir(), 'probe.py')\nopen(out, 'w').write('x')\nEOF",
        "python3 - <<'EOF'\nf = 'src/example.ts'\ndata = open(f).read()\nf = '/tmp/out.ts'\nopen(f, 'w').write(data)\nEOF",
        "echo ok 2>&1 | tee test-output.log",
    ],
)
def test_pending_gate_allows_read_only_and_non_source_shell_commands(tmp_path: Path, command: str) -> None:
    workspace = tmp_path / "workspace"
    _isolated_repo(workspace)
    (workspace / "dist").mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))

    result = _shell(state_dir, workspace, command.replace("{scratch}", str(scratch)))

    assert result.returncode == 0, result.stderr
    assert _status(state_dir, workspace)["phase"] == "pending"


@pytest.mark.parametrize(
    "interpreter",
    [sys.executable] + (["/usr/bin/python3"] if Path("/usr/bin/python3").exists() else []),
)
@pytest.mark.parametrize(
    "command",
    [
        "sed -i '' 's/1/2/' " + "a" * 3000 + ".ts",
        "echo x > " + "b" * 3000 + "/c.ts",
        "sed -i '' 's/1/2/' src/ex\x00ample.ts",
        "echo 'unterminated > src/example.ts",
        "python3 - <<'EOF'\nopen('src/example.ts', 'w')\n",
    ],
)
def test_shell_write_detection_never_crashes_the_hook(tmp_path: Path, interpreter: str, command: str) -> None:
    # Runs on every Bash call: Python 3.9 hosts raise ENAMETOOLONG/NUL errors that 3.14 swallows.
    workspace = tmp_path / "workspace"
    _isolated_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    env = {**os.environ, "RHIZE_REFACTOR_GATE_STATE_DIR": str(state_dir)}
    result = subprocess.run(
        [interpreter, str(SCRIPT), "hook-command"],
        input=json.dumps({"cwd": str(workspace), "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode in (0, 2), result.stderr
    assert "Traceback" not in result.stderr


def test_post_command_records_source_changed_while_pending_and_reconcile_requires_it(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _isolated_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    # A write no static rule can see (a script, `bash -c`, `npm run codemod`) lands while pending.
    (workspace / "src/example.ts").write_text("export const value = 2\n")

    flagged = _shell(state_dir, workspace, "./scripts/codemod.sh", mode="hook-command-post")

    assert flagged.returncode == 2
    assert "src/example.ts" in flagged.stderr
    assert "prepare --workspace" in flagged.stderr
    assert _shell(state_dir, workspace, "true", mode="hook-command-post").returncode == 0  # once
    assert _status(state_dir, workspace)["unprepared_source_changes"] == ["src/example.ts"]

    # The arm-time baseline survives prepare, so a map that omits the file cannot reconcile.
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan)
    query = "Refactor the application example safely"
    assert run_gate(state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan), "--query", query).returncode == 0
    unmapped = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert unmapped.returncode == 2
    assert "src/example.ts" in unmapped.stderr

    write_plan(plan, ("src/example.ts",))
    assert run_gate(state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan), "--query", query).returncode == 0
    reconciled = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert reconciled.returncode == 0, reconciled.stderr


def test_rearmed_pending_receipt_still_requires_recorded_unprepared_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _isolated_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    (workspace / "src/example.ts").write_text("export const value = 2\n")
    assert _shell(state_dir, workspace, "./scripts/codemod.sh", mode="hook-command-post").returncode == 2

    # A new material prompt re-arms pending with a fresh baseline; the record carries over.
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Now fix the failing tests"))
    assert _status(state_dir, workspace)["unprepared_source_changes"] == ["src/example.ts"]
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan)
    assert run_gate(
        state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan),
        "--query", "Refactor the application example safely",
    ).returncode == 0
    unmapped = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert unmapped.returncode == 2
    assert "src/example.ts" in unmapped.stderr


def test_post_command_ignores_exempt_changes_and_non_pending_receipts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _isolated_repo(workspace)
    state_dir = tmp_path / "state"
    assert _shell(state_dir, workspace, "true", mode="hook-command-post").returncode == 0  # no receipt
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    (workspace / "docs").mkdir()
    (workspace / "docs/notes.md").write_text("findings\n")
    (workspace / "STATE.md").write_text("progress\n")
    # Logs, notes and other non-code untracked files are not source (same rule as pre-command).
    (workspace / "test-output.log").write_text("ok\n")
    (workspace / "notes.txt").write_text("x\n")
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan, ("src/example.ts",))
    assert _shell(state_dir, workspace, "true", mode="hook-command-post").returncode == 0
    assert "unprepared_source_changes" not in _status(state_dir, workspace)

    assert run_gate(
        state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan),
        "--query", "Refactor the application example safely",
    ).returncode == 0
    (workspace / "src/example.ts").write_text("export const value = 2\n")
    assert _shell(state_dir, workspace, "true", mode="hook-command-post").returncode == 0


@pytest.mark.parametrize("commit", [RELEASE_FIXTURE, "git -c user.name=z " + "commit -qam sneak"])
def test_post_command_sees_a_hidden_write_committed_in_the_same_command(tmp_path: Path, commit: str) -> None:
    workspace = tmp_path / "workspace"
    _isolated_repo(workspace)
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Refactor the application code"))
    commit_command = "bash -c 'echo x > src/example.ts' && " + commit

    # Someone else's commit arriving through a pull is not charged; the stored HEAD advances.
    (workspace / "src/other.ts").write_text("export const other = 1\n")
    git(workspace, "add", "src/other.ts")
    git(workspace, "commit", "-qm", "upstream work")
    assert _shell(state_dir, workspace, "git pull --ff-only", mode="hook-command-post").returncode == 0

    # The pre-command check saw a clean tree; the post check sees what the commit carried.
    (workspace / "src/example.ts").write_text("export const value = 9\n")
    git(workspace, "commit", "-qam", "sneak")
    flagged = _shell(state_dir, workspace, commit_command, mode="hook-command-post")

    assert flagged.returncode == 2
    assert _status(state_dir, workspace)["unprepared_source_changes"] == ["src/example.ts"]
    plan = workspace / ".claude/plans/refactor.md"
    write_plan(plan)
    assert run_gate(
        state_dir, "prepare", "--workspace", str(workspace), "--plan", str(plan),
        "--query", "Refactor the application example safely",
    ).returncode == 0
    unmapped = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert unmapped.returncode == 2
    assert "src/example.ts" in unmapped.stderr
    assert "src/other.ts" not in unmapped.stderr


def test_docs_only_commit_ignores_an_untracked_nested_worktree(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _isolated_repo(workspace)
    git(workspace, "worktree", "add", "-q", ".claude/worktrees/agent", "-b", "agent")
    (workspace / ".claude/worktrees/agent/src/example.ts").write_text("agent work\n")
    # Control: the nested worktree really is visible to git as an untracked entry.
    assert "?? .claude/worktrees/agent/" in git(workspace, "status", "--porcelain", "--untracked-files=all")
    state_dir = tmp_path / "state"
    run_gate(state_dir, "hook-prompt", payload=prompt_payload(workspace, "Fix the application bug"))
    (workspace / "STATE.md").write_text("progress\n")
    (workspace / "docs").mkdir()
    (workspace / "docs/m1-queue.md").write_text("queue\n")
    command = "git add STATE.md docs/m1-queue.md && " + RELEASE_FIXTURE

    allowed = _shell(state_dir, workspace, command)
    assert allowed.returncode == 0, allowed.stderr

    (workspace / "src/example.ts").write_text("export const value = 2\n")
    assert _shell(state_dir, workspace, command).returncode == 2


def test_prepare_accepts_a_map_in_the_primary_checkout_of_a_linked_worktree(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    init_repo(primary)
    worktree = tmp_path / "agent"
    git(primary, "worktree", "add", "-q", str(worktree), "-b", "agent")
    plan = primary / ".claude/plans/agent.md"
    write_plan(plan, ("src/example.ts",))
    elsewhere = tmp_path / "elsewhere.md"
    write_plan(elsewhere, ("src/example.ts",))
    state_dir = tmp_path / "state"

    def prepare(workspace: Path, map_path: Path) -> subprocess.CompletedProcess[str]:
        return run_gate(
            state_dir, "prepare", "--workspace", str(workspace), "--plan", str(map_path),
            "--query", "example refactor",
        )

    accepted = prepare(worktree, plan)
    assert accepted.returncode == 0, accepted.stderr
    assert _status(state_dir, worktree)["plan"]["path"] == str(plan.resolve())
    for workspace in (worktree, primary):
        rejected = prepare(workspace, elsewhere)
        assert rejected.returncode == 2
        assert "inside the workspace" in rejected.stderr
