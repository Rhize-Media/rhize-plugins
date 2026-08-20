#!/usr/bin/env python3
"""Behavior tests for the global refactor evidence gate."""

from __future__ import annotations

import json
import os
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


def write_plan(path: Path, mentioned_files: tuple[str, ...] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    files = "\n".join(f"- `{name}`" for name in mentioned_files)
    path.write_text(
        f"""# Impact Map: Example refactor

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
    assert receipt["repositories"][0]["structural_evidence"]["mode"] == "rg-fallback"
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
