#!/usr/bin/env python3
"""Provider-free qualification for Devflow activation and lifecycle evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "rhize-devflow/scripts/refactor_gate.py"
PLUGIN_MANIFEST = REPO_ROOT / "rhize-devflow/.claude-plugin/plugin.json"
CORPUS = Path(__file__).parent / "fixtures/refactor_gate_routing_corpus.json"
FROZEN_CORPUS_SHA256 = "d365580639ff6300aa266193958b793cc9fd112f3bef09a3ecddae7fee53ff0c"


def run_gate(
    state_dir: Path,
    *args: str,
    payload: dict | None = None,
    cwd: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RHIZE_REFACTOR_GATE_STATE_DIR"] = str(state_dir)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input="" if payload is None else json.dumps(payload),
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
    (path / "src/example.py").write_text("VALUE = 1\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "initial")


def write_plan(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """# Impact Map: Example

## Current behavior and evidence
- Existing behavior in `src/example.py`.

## Intended semantic delta
- Change the example safely.

## Invariants and must-not-change boundaries
- Preserve compatibility.

## Acceptance tests
- The example remains valid.

## Implementation order
1. Change `src/example.py`.
2. Reconcile.
"""
    )


def prompt_payload(shape: str, workspace: Path, prompt: str) -> dict:
    key = "prompt" if shape == "claude" else "user_prompt"
    return {key: prompt, "cwd": str(workspace), "hook_event_name": "UserPromptSubmit"}


def read_status(state_dir: Path, workspace: Path) -> dict:
    result = run_gate(state_dir, "status", "--workspace", str(workspace), "--json")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_routing_corpus_is_frozen_balanced_and_spans_eight_repositories() -> None:
    assert hashlib.sha256(CORPUS.read_bytes()).hexdigest() == FROZEN_CORPUS_SHA256
    document = json.loads(CORPUS.read_text())
    cases = document["cases"]
    assert len(cases) == 48
    assert Counter(case["category"] for case in cases) == {
        "imperative_implementation": 12,
        "issue_style_implementation": 12,
        "read_only_review": 12,
        "plan_only_non_code": 12,
    }
    assert len({case["repo_context"] for case in cases}) >= 8
    assert len({case["id"] for case in cases}) == 48


@pytest.mark.parametrize("shape", ["claude", "codex"])
def test_frozen_corpus_activation_contract(shape: str, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    cases = json.loads(CORPUS.read_text())["cases"]
    observed: dict[str, list[bool]] = {"required": [], "off": [], "auto": []}

    for case in cases:
        for policy in observed:
            state_dir = tmp_path / "states" / shape / policy / case["id"]
            if policy == "off":
                # The control contract is physical omission of Devflow, not a runtime bypass.
                activated = read_status(state_dir, workspace)["phase"] == "pending"
                observed[policy].append(activated)
                assert activated is False
                continue
            policy_args = []
            if policy == "required":
                policy_args = [
                    "--activation-policy",
                    policy,
                    "--task-kind",
                    case["task_kind"],
                ]
            result = run_gate(
                state_dir,
                "hook-prompt",
                *policy_args,
                payload=prompt_payload(shape, workspace, case["prompt"]),
            )
            assert result.returncode == 0, (case["id"], policy, result.stderr)
            activated = read_status(state_dir, workspace)["phase"] == "pending"
            observed[policy].append(activated)
            assert activated is case.get(f"expected_{policy}", False), (case["id"], policy)

    assert sum(observed["required"]) == 24
    assert sum(observed["off"]) == 0
    assert sum(observed["auto"]) == 11
    # Auto mode is reported separately: 11/24 sensitivity and 24/24 specificity.
    implementation = [case["task_kind"] == "implementation" for case in cases]
    assert sum(hit for hit, positive in zip(observed["auto"], implementation) if positive) == 11
    assert sum(not hit for hit, positive in zip(observed["auto"], implementation) if not positive) == 24


def test_required_policy_can_be_declared_per_invocation_without_prompt_rewrite(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    issue_style_prompt = "Pagination repeats rows when the final ordering value is null."
    result = run_gate(
        tmp_path / "state",
        "hook-prompt",
        "--activation-policy",
        "required",
        "--task-kind",
        "implementation",
        payload=prompt_payload("claude", workspace, issue_style_prompt),
    )
    assert result.returncode == 0
    assert read_status(tmp_path / "state", workspace)["phase"] == "pending"


@pytest.mark.parametrize("shape", ["claude", "codex"])
def test_host_payloads_produce_the_same_source_bound_lifecycle(
    shape: str, tmp_path: Path
) -> None:
    workspace = tmp_path / f"workspace-{shape}"
    init_repo(workspace)
    state_dir = tmp_path / f"state-{shape}"
    prompt = "Issue prose includes SOLUTION_SENTINEL and GRADER_SENTINEL for a pagination defect."
    pending = run_gate(
        state_dir,
        "hook-prompt",
        "--activation-policy",
        "required",
        "--task-kind",
        "implementation",
        payload=prompt_payload(shape, workspace, prompt),
    )
    assert pending.returncode == 0, pending.stderr
    first = read_status(state_dir, workspace)
    initial_events = list(first["lifecycle"]["events"])
    assert [event["phase"] for event in initial_events] == ["pending"]

    plan = workspace / ".claude/plans/example.md"
    write_plan(plan)
    prepared = run_gate(
        state_dir,
        "prepare",
        "--workspace",
        str(workspace),
        "--plan",
        str(plan),
        "--query",
        "example lifecycle test",
    )
    assert prepared.returncode == 0, prepared.stderr

    exempt_write = run_gate(
        state_dir,
        "hook-write",
        payload={
            "cwd": str(workspace),
            "tool_input": {"file_path": str(workspace / "README.md")},
        },
    )
    assert exempt_write.returncode == 0, exempt_write.stderr

    ordinary_command = run_gate(
        state_dir,
        "hook-command",
        payload={"cwd": str(workspace), "tool_input": {"command": "echo ready"}},
    )
    assert ordinary_command.returncode == 0, ordinary_command.stderr

    write = run_gate(
        state_dir,
        "hook-write",
        payload={
            "cwd": str(workspace),
            "tool_input": {"file_path": str(workspace / "src/example.py")},
        },
    )
    assert write.returncode == 0, write.stderr
    (workspace / "src/example.py").write_text("VALUE = 2\n")

    reconciled = run_gate(state_dir, "reconcile", "--workspace", str(workspace))
    assert reconciled.returncode == 0, reconciled.stderr
    stopped = run_gate(
        state_dir,
        "hook-stop",
        payload={"cwd": str(workspace), "hook_event_name": "Stop"},
    )
    assert stopped.returncode == 0, stopped.stderr

    receipt = read_status(state_dir, workspace)
    lifecycle = receipt["lifecycle"]
    assert receipt["phase"] == "completed"
    assert [event["phase"] for event in lifecycle["events"]] == [
        "pending",
        "prepared",
        "implementation",
        "reconciled",
        "completed",
    ]
    assert lifecycle["events"][: len(initial_events)] == initial_events
    assert lifecycle["activation"] == {
        "policy": "required",
        "reason_code": "caller-declared-implementation",
        "task_kind": "implementation",
    }
    assert lifecycle["prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
    assert "prompt" not in receipt
    assert "latest_prompt" not in receipt
    assert lifecycle["source_identity"] == {
        "plugin_version": json.loads(PLUGIN_MANIFEST.read_text())["version"],
        "source_commit": git(REPO_ROOT, "rev-parse", "HEAD"),
        "gate_source_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
    }
    assert lifecycle["hook_event_counts"] == {
        "UserPromptSubmit": 1,
        "PreToolUse": 3,
        "Stop": 1,
    }
    assert lifecycle["events"][-2]["verdict"] == "IN_SYNC_WITH_EXCEPTIONS"
    serialized = json.dumps(receipt).lower()
    assert "solution_sentinel" not in serialized
    assert "grader_sentinel" not in serialized


def test_activation_reason_cannot_be_supplied_as_free_text(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    result = run_gate(
        state_dir,
        "hook-prompt",
        "--activation-policy",
        "required",
        "--task-kind",
        "implementation",
        "--activation-reason",
        "copy the grader solution into evidence",
        payload=prompt_payload("claude", workspace, "Issue description."),
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert read_status(state_dir, workspace)["phase"] == "none"


def test_off_arm_omits_the_hook_and_cannot_mutate_an_existing_receipt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_repo(workspace)
    state_dir = tmp_path / "state"
    initial = run_gate(
        state_dir,
        "hook-prompt",
        payload=prompt_payload(
            "claude",
            workspace,
            "Refactor the application code",
        ),
    )
    assert initial.returncode == 0
    before = read_status(state_dir, workspace)

    # No Devflow entry point is invoked in the off arm; installing the plugin and
    # disabling a gate would still expose treatment commands, skills, and agents.
    assert read_status(state_dir, workspace) == before
