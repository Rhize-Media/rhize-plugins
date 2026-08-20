#!/usr/bin/env python3
"""Stateful CodeGraph + impact-map + component-registry enforcement.

The hook modes consume Claude/Codex-compatible JSON on stdin. The CLI modes create and
reconcile a tool-neutral receipt under ~/.claude/rhize-devflow/refactor-gate by default.
The implementation is stdlib-only and never initializes CodeGraph.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rhize-refactor-gate-v1"
REQUIRED_PLAN_SECTIONS = (
    "current behavior",
    "intended semantic delta",
    "invariants",
    "acceptance tests",
    "implementation order",
)
PLANNING_PATHS = (
    ".claude/plans/",
    ".codex/plans/",
    ".Codex/plans/",
    ".wolf/",
)
PLANNING_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "CURRENT_SPRINT.md",
    "STATE.md",
}
SKIP_DISCOVERY_DIRS = {
    ".git",
    ".codegraph",
    ".next",
    ".turbo",
    "node_modules",
    "dist",
    "build",
    "coverage",
}
MATERIAL_VERBS = re.compile(
    r"\b(implement|refactor|restructure|rewrite|migrate|fix|repair|modify|change|"
    r"update|add|remove|delete|replace|build|create)\b",
    re.IGNORECASE,
)
CODE_CONTEXT = re.compile(
    r"\b(code|application|app|repository|repo|project|component|hook|function|class|"
    r"schema|migration|api|frontend|backend|test|tests|file|files|bug|issue|feature|"
    r"implementation|database|cache|route|endpoint)\b",
    re.IGNORECASE,
)
REVIEW_ONLY_LEAD = re.compile(
    r"^\s*(review|audit|inspect|explain|analy[sz]e|report|investigate|diagnose)\b",
    re.IGNORECASE,
)
PLAN_ONLY = re.compile(
    r"^\s*(?:(?:create|write|draft|design|prepare)\s+)?(?:an?\s+)?(?:implementation\s+|"
    r"refactor(?:ing)?\s+|remediation\s+)?plan\b",
    re.IGNORECASE,
)
EXECUTION_AFTER_REVIEW = re.compile(
    r"\b(then|and)\b.{0,80}\b(implement|refactor|fix|repair|modify|change|update|add|remove)\b",
    re.IGNORECASE | re.DOTALL,
)
RELEASE_COMMAND = re.compile(
    r"(?:\bgit(?:\s+-C\s+\S+)?\s+(?:commit|push|merge)\b|\bgh\s+pr\s+merge\b)",
    re.IGNORECASE,
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gate_disabled() -> bool:
    return os.environ.get("RHIZE_REFACTOR_GATE", "").strip().lower() in {
        "0",
        "false",
        "off",
        "disabled",
    }


def canonical(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def state_directory() -> Path:
    override = os.environ.get("RHIZE_REFACTOR_GATE_STATE_DIR")
    directory = canonical(override) if override else Path.home() / ".claude/rhize-devflow/refactor-gate"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    return directory


def workspace_key(workspace: Path) -> str:
    digest = hashlib.sha256(str(workspace).encode()).hexdigest()[:20]
    return f"{workspace.name or 'root'}-{digest}.json"


def state_path(workspace: Path) -> Path:
    return state_directory() / workspace_key(workspace)


def read_state(workspace: Path) -> dict[str, Any] | None:
    path = state_path(workspace)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_state(workspace: Path, state: dict[str, Any]) -> None:
    path = state_path(workspace)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=False) + "\n")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)


def all_states() -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for path in state_directory().glob("*.json"):
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("workspace"):
            states.append(value)
    return states


def find_state_for_path(path: Path) -> tuple[Path, dict[str, Any] | None]:
    direct = read_state(path)
    if direct:
        return path, direct
    matches: list[tuple[int, Path, dict[str, Any]]] = []
    for state in all_states():
        workspace = canonical(state["workspace"])
        try:
            path.relative_to(workspace)
        except ValueError:
            continue
        matches.append((len(str(workspace)), workspace, state))
    if not matches:
        return path, None
    _, workspace, state = max(matches, key=lambda item: item[0])
    return workspace, state


def read_payload() -> dict[str, Any] | None:
    try:
        value = json.load(sys.stdin)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def payload_workspace(payload: dict[str, Any] | None) -> Path:
    raw = (payload or {}).get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return canonical(raw)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_fingerprint(path: Path) -> str | None:
    try:
        return sha256_file(path) if path.is_file() else None
    except OSError:
        return None


def run(command: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))


def is_material_prompt(prompt: str) -> bool:
    if not MATERIAL_VERBS.search(prompt) or not CODE_CONTEXT.search(prompt):
        return False
    if REVIEW_ONLY_LEAD.search(prompt) and not EXECUTION_AFTER_REVIEW.search(prompt):
        return False
    if PLAN_ONLY.search(prompt) and not EXECUTION_AFTER_REVIEW.search(prompt):
        return False
    return True


def discover_repositories(workspace: Path) -> list[Path]:
    top = run(["git", "rev-parse", "--show-toplevel"], workspace)
    if top.returncode == 0 and top.stdout.strip():
        return [canonical(top.stdout.strip())]

    repositories: set[Path] = set()
    workspace_depth = len(workspace.parts)
    for root, dirs, _files in os.walk(workspace):
        root_path = Path(root)
        depth = len(root_path.parts) - workspace_depth
        dirs[:] = [name for name in dirs if name not in SKIP_DISCOVERY_DIRS]
        git_marker = root_path / ".git"
        if git_marker.exists():
            repositories.add(root_path.resolve())
            dirs[:] = []
            continue
        if depth >= 3:
            dirs[:] = []
    return sorted(repositories)


def query_tokens(query: str) -> list[str]:
    ignored = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "then",
        "code",
        "application",
        "implementation",
        "refactor",
    }
    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", query):
        lowered = token.lower()
        if lowered in ignored or lowered in tokens:
            continue
        tokens.append(lowered)
    return tokens[:8] or ["source"]


def rg_fallback(repo: Path, query: str, reason: str) -> dict[str, Any]:
    rg = shutil.which("rg")
    if not rg:
        return {
            "mode": "python-fallback",
            "reason": f"{reason}; rg unavailable",
            "query": query,
            "matches": [],
        }
    pattern = "|".join(re.escape(token) for token in query_tokens(query))
    result = run(
        [
            rg,
            "-n",
            "-i",
            "-m",
            "20",
            "--glob",
            "!.git/**",
            "--glob",
            "!.codegraph/**",
            "--glob",
            "!node_modules/**",
            pattern,
            ".",
        ],
        repo,
    )
    matches = result.stdout.splitlines()[:20] if result.returncode in (0, 1) else []
    return {
        "mode": "rg-fallback",
        "reason": reason,
        "query": query,
        "matches": matches,
    }


def codegraph_evidence(repo: Path, query: str, reconcile: bool = False) -> dict[str, Any]:
    if not (repo / ".codegraph").is_dir():
        return rg_fallback(repo, query, "no .codegraph index")
    executable = shutil.which("codegraph")
    if not executable:
        return rg_fallback(repo, query, ".codegraph exists but CodeGraph CLI is unavailable")

    sync_output = None
    if reconcile:
        sync = run([executable, "sync"], repo, timeout=120)
        sync_output = (sync.stdout or sync.stderr)[-2000:]
        if sync.returncode != 0:
            fallback = rg_fallback(repo, query, "CodeGraph sync failed during reconciliation")
            fallback["codegraph_sync"] = sync_output
            return fallback

    status = run([executable, "status"], repo, timeout=60)
    status_text = (status.stdout or status.stderr)[-4000:]
    if status.returncode != 0:
        fallback = rg_fallback(repo, query, "CodeGraph status failed")
        fallback["codegraph_status"] = status_text
        return fallback

    if not reconcile and re.search(r"\b(stale|out of date|out-of-date)\b", status_text, re.I):
        sync = run([executable, "sync"], repo, timeout=120)
        sync_output = (sync.stdout or sync.stderr)[-2000:]
        if sync.returncode != 0:
            fallback = rg_fallback(repo, query, "stale CodeGraph index could not be synchronized")
            fallback["codegraph_status"] = status_text
            fallback["codegraph_sync"] = sync_output
            return fallback
        status = run([executable, "status"], repo, timeout=60)
        status_text = (status.stdout or status.stderr)[-4000:]
        if status.returncode != 0:
            return rg_fallback(repo, query, "CodeGraph status failed after synchronization")

    explore = run([executable, "explore", query], repo, timeout=120)
    explore_text = (explore.stdout or explore.stderr)[-8000:]
    if explore.returncode != 0:
        fallback = rg_fallback(repo, query, "CodeGraph explore failed")
        fallback["codegraph_status"] = status_text
        fallback["codegraph_explore"] = explore_text
        return fallback
    return {
        "mode": "codegraph",
        "query": query,
        "status": status_text,
        "explore": explore_text,
        "sync": sync_output,
    }


def discover_registries(workspace: Path, repositories: list[Path], query: str) -> list[dict[str, Any]]:
    candidates: set[Path] = set()
    direct_roots = {workspace, *repositories, *(repo.parent for repo in repositories)}
    for root in direct_roots:
        candidate = root / "COMPONENT_REGISTRY.md"
        if candidate.is_file():
            candidates.add(candidate.resolve())
    workspace_depth = len(workspace.parts)
    for root, dirs, files in os.walk(workspace):
        root_path = Path(root)
        depth = len(root_path.parts) - workspace_depth
        dirs[:] = [name for name in dirs if name not in SKIP_DISCOVERY_DIRS]
        if "COMPONENT_REGISTRY.md" in files:
            candidates.add((root_path / "COMPONENT_REGISTRY.md").resolve())
        if depth >= 3:
            dirs[:] = []

    tokens = query_tokens(query)
    evidence: list[dict[str, Any]] = []
    for path in sorted(candidates):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        matches = [
            f"{number}:{line[:240]}"
            for number, line in enumerate(text.splitlines(), 1)
            if any(token in line.lower() for token in tokens)
        ][:20]
        evidence.append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "query": query,
                "matches": matches,
            }
        )
    return evidence


def git_status_snapshot(repo: Path) -> dict[str, dict[str, str | None]]:
    result = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], repo)
    if result.returncode != 0:
        return {}
    entries = result.stdout.split("\0")
    snapshot: dict[str, dict[str, str | None]] = {}
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status = entry[:2]
        path = entry[3:] if len(entry) > 3 else ""
        if status[0] in {"R", "C"} and index < len(entries):
            path = entries[index]
            index += 1
        if path:
            snapshot[path] = {
                "status": status,
                "sha256": file_fingerprint(repo / path),
            }
    return snapshot


def git_head(repo: Path) -> str | None:
    result = run(["git", "rev-parse", "HEAD"], repo)
    return result.stdout.strip() if result.returncode == 0 else None


def repo_display_prefix(workspace: Path, repo: Path) -> str:
    try:
        relative = repo.relative_to(workspace)
    except ValueError:
        return repo.name
    return "" if str(relative) == "." else str(relative)


def baseline_repository(workspace: Path, repo: Path, query: str) -> dict[str, Any]:
    return {
        "root": str(repo),
        "workspace_prefix": repo_display_prefix(workspace, repo),
        "head": git_head(repo),
        "dirty": git_status_snapshot(repo),
        "structural_evidence": codegraph_evidence(repo, query),
    }


def validate_plan(plan: Path, workspace: Path) -> str:
    try:
        plan.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("impact map must be stored inside the workspace") from exc
    if not plan.is_file():
        raise ValueError(f"impact map does not exist: {plan}")
    text = plan.read_text(encoding="utf-8", errors="ignore")
    lowered = text.lower()
    for section in REQUIRED_PLAN_SECTIONS:
        if section not in lowered:
            raise ValueError(f"impact map missing required section: {section}")
    return text


def state_plan_is_current(state: dict[str, Any]) -> bool:
    plan = Path(state.get("plan", {}).get("path", ""))
    expected = state.get("plan", {}).get("sha256")
    return bool(plan.is_file() and expected and sha256_file(plan) == expected)


def prepare(workspace: Path, plan: Path, query: str) -> int:
    try:
        plan_text = validate_plan(plan, workspace)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"BLOCKED: {exc}\n")
        return 2
    repositories = discover_repositories(workspace)
    if not repositories:
        sys.stderr.write("BLOCKED: no Git repository roots were found in the workspace\n")
        return 2
    previous = read_state(workspace) or {}
    previous_repositories = previous.get("repositories")
    preserve_baseline = (
        previous.get("phase") in {"prepared", "implementation"}
        and isinstance(previous_repositories, list)
        and {canonical(item["root"]) for item in previous_repositories}
        == set(repositories)
    )
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(workspace),
        "phase": "prepared",
        "created_at": previous.get("created_at", utc_now()),
        "prepared_at": utc_now(),
        "prompt": previous.get("prompt"),
        "query": query,
        "plan": {
            "path": str(plan),
            "sha256": hashlib.sha256(plan_text.encode()).hexdigest(),
        },
        # Re-preparing after an impact-map correction must not bless an already
        # dirty implementation as the new baseline. Preserve the original
        # repository snapshots until reconciliation succeeds.
        "repositories": (
            previous_repositories
            if preserve_baseline
            else [baseline_repository(workspace, repo, query) for repo in repositories]
        ),
        "registries": discover_registries(workspace, repositories, query),
        "reconciliation": None,
    }
    write_state(workspace, state)
    print(json.dumps(state, indent=2, sort_keys=False))
    return 0


def changed_since_baseline(workspace: Path, repo_state: dict[str, Any]) -> list[str]:
    repo = canonical(repo_state["root"])
    baseline_head = repo_state.get("head")
    baseline_dirty = repo_state.get("dirty") or {}
    candidates: set[str] = set()
    current_head = git_head(repo)
    if baseline_head and current_head and baseline_head != current_head:
        result = run(["git", "diff", "--name-only", f"{baseline_head}..{current_head}"], repo)
        if result.returncode == 0:
            candidates.update(line for line in result.stdout.splitlines() if line)
    current_dirty = git_status_snapshot(repo)
    for path, current in current_dirty.items():
        if baseline_dirty.get(path) != current:
            candidates.add(path)
    for path in list(candidates):
        baseline = baseline_dirty.get(path)
        if baseline and baseline.get("sha256") == file_fingerprint(repo / path):
            candidates.discard(path)

    prefix = repo_state.get("workspace_prefix") or ""
    displayed = [f"{prefix}/{path}" if prefix else path for path in candidates]
    return sorted(displayed)


def is_internal_evidence_path(path: str, plan_path: Path, workspace: Path) -> bool:
    try:
        relative_plan = str(plan_path.relative_to(workspace))
    except ValueError:
        relative_plan = str(plan_path)
    return (
        path == relative_plan
        or "/.codegraph/" in f"/{path}/"
        or path.startswith(".codegraph/")
        or path.startswith(".wolf/")
    )


def reconcile(workspace: Path) -> int:
    state = read_state(workspace)
    if not state or state.get("phase") not in {"prepared", "implementation", "reconciled"}:
        sys.stderr.write("BLOCKED: no prepared impact-map receipt exists for this workspace\n")
        return 2
    if not state_plan_is_current(state):
        sys.stderr.write("BLOCKED: impact map changed after preparation; run prepare again\n")
        return 2
    plan_path = canonical(state["plan"]["path"])
    plan_text = plan_path.read_text(encoding="utf-8", errors="ignore").lower()
    changed: list[str] = []
    structural: list[dict[str, Any]] = []
    exceptions: list[str] = []
    for repo_state in state["repositories"]:
        repo = canonical(repo_state["root"])
        changed.extend(changed_since_baseline(workspace, repo_state))
        evidence = codegraph_evidence(repo, state["query"], reconcile=True)
        structural.append({"root": str(repo), "evidence": evidence})
        if evidence.get("mode") != "codegraph":
            exceptions.append(f"{repo}: {evidence.get('reason', 'CodeGraph fallback')}")
    changed = sorted(
        path for path in set(changed) if not is_internal_evidence_path(path, plan_path, workspace)
    )
    unmapped = [
        path
        for path in changed
        if path.lower() not in plan_text and Path(path).name.lower() not in plan_text
    ]
    if unmapped:
        state["phase"] = "implementation"
        state["reconciliation"] = {
            "at": utc_now(),
            "verdict": "OUT_OF_SYNC",
            "changed_files": changed,
            "unmapped_files": unmapped,
            "exceptions": exceptions,
            "structural_evidence": structural,
        }
        write_state(workspace, state)
        sys.stderr.write(
            "BLOCKED: actual changed files are missing from the impact map: "
            + ", ".join(unmapped)
            + "\n"
        )
        return 2
    verdict = "IN_SYNC_WITH_EXCEPTIONS" if exceptions else "IN_SYNC"
    state["phase"] = "reconciled"
    state["reconciled_at"] = utc_now()
    state["reconciliation"] = {
        "at": state["reconciled_at"],
        "verdict": verdict,
        "changed_files": changed,
        "unmapped_files": [],
        "exceptions": exceptions,
        "structural_evidence": structural,
    }
    write_state(workspace, state)
    print(json.dumps(state, indent=2, sort_keys=False))
    return 0


def extract_write_paths(payload: dict[str, Any]) -> list[str]:
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, str):
        patch = tool_input
        direct: list[str] = []
    elif isinstance(tool_input, dict):
        direct = [
            value
            for value in (tool_input.get("file_path"), tool_input.get("path"))
            if isinstance(value, str) and value
        ]
        patch = next(
            (
                value
                for value in (
                    tool_input.get("input"),
                    tool_input.get("patch"),
                    tool_input.get("content"),
                    tool_input.get("command"),
                    tool_input.get("cmd"),
                )
                if isinstance(value, str) and "*** Begin Patch" in value
            ),
            "",
        )
    else:
        return []
    direct.extend(
        match.group(1).strip()
        for match in re.finditer(r"^\*\*\* (?:Add|Update|Delete) File:\s*(.+)$", patch, re.MULTILINE)
    )
    return sorted(set(direct))


def normalized_relative_path(path: str, workspace: Path) -> str | None:
    candidate = canonical(path) if os.path.isabs(path) else canonical(workspace / path)
    try:
        return str(candidate.relative_to(workspace))
    except ValueError:
        return None


def is_planning_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized in PLANNING_FILES or any(normalized.startswith(prefix) for prefix in PLANNING_PATHS)


def hook_prompt() -> int:
    if gate_disabled():
        return 0
    payload = read_payload()
    if not payload:
        return 0
    prompt = payload.get("prompt") or payload.get("user_prompt")
    if not isinstance(prompt, str) or not is_material_prompt(prompt):
        return 0
    if "/rhize-devflow:impact-map" in prompt:
        return 0
    workspace = payload_workspace(payload)
    current = read_state(workspace)
    if current and current.get("phase") in {"prepared", "implementation"}:
        current["latest_prompt"] = prompt
        current["updated_at"] = utc_now()
        write_state(workspace, current)
    else:
        write_state(
            workspace,
            {
                "schema_version": SCHEMA_VERSION,
                "workspace": str(workspace),
                "phase": "pending",
                "created_at": utc_now(),
                "prompt": prompt,
            },
        )
    print(
        "<user-prompt-submit-hook>\n"
        "Refactor evidence gate: impact-map evidence is required before source edits. "
        "Run /rhize-devflow:impact-map, persist its map, then execute the prepare command "
        "shown by that workflow.\n"
        f"Gate CLI: {Path(__file__).resolve()}\n"
        "</user-prompt-submit-hook>"
    )
    return 0


def enforce_write_payload(payload: dict[str, Any]) -> int:
    cwd = payload_workspace(payload)
    workspace, state = find_state_for_path(cwd)
    paths = extract_write_paths(payload)
    relevant = [
        relative
        for path in paths
        if (relative := normalized_relative_path(path, workspace)) is not None
        and not is_planning_path(relative)
    ]
    if not relevant or not state or state.get("phase") == "dismissed":
        return 0
    phase = state.get("phase")
    if phase == "pending":
        sys.stderr.write(
            "BLOCKED: source edits require a prepared refactor-evidence receipt. "
            "Run /rhize-devflow:impact-map and its prepare command first.\n"
        )
        return 2
    if phase in {"prepared", "implementation", "reconciled"} and not state_plan_is_current(state):
        sys.stderr.write("BLOCKED: impact map changed after preparation; run prepare again.\n")
        return 2
    if phase == "reconciled":
        state["reconciliation"] = None
    if phase in {"prepared", "reconciled"}:
        state["phase"] = "implementation"
        state["implementation_started_at"] = utc_now()
        write_state(workspace, state)
    return 0


def hook_write() -> int:
    if gate_disabled():
        return 0
    payload = read_payload()
    if not payload:
        workspace = canonical(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        _workspace, state = find_state_for_path(workspace)
        if state and state.get("phase") in {"pending", "prepared", "implementation", "reconciled"}:
            sys.stderr.write(
                "BLOCKED: active refactor gate could not validate a malformed write payload. "
                "Retry the write with a valid harness payload.\n"
            )
            return 2
        return 0
    return enforce_write_payload(payload)


def hook_command() -> int:
    if gate_disabled():
        return 0
    payload = read_payload()
    if not payload:
        return 0
    tool_input = payload.get("tool_input") or {}
    command = ""
    if isinstance(tool_input, dict):
        command = (
            tool_input.get("command")
            or tool_input.get("cmd")
            or tool_input.get("input")
            or ""
        )
    elif isinstance(tool_input, str):
        command = tool_input
    if isinstance(command, str) and "*** Begin Patch" in command:
        write_result = enforce_write_payload(payload)
        if write_result != 0:
            return write_result
    if not isinstance(command, str) or not RELEASE_COMMAND.search(command):
        return 0
    cwd = payload_workspace(payload)
    _workspace, state = find_state_for_path(cwd)
    if state and state.get("phase") not in {"reconciled", "completed", "dismissed"}:
        sys.stderr.write(
            "BLOCKED: commit/push/merge requires a reconciled refactor-evidence receipt. "
            "Run refactor_gate.py reconcile first.\n"
        )
        return 2
    return 0


def hook_stop() -> int:
    if gate_disabled():
        return 0
    payload = read_payload()
    if not payload:
        return 0
    cwd = payload_workspace(payload)
    _workspace, state = find_state_for_path(cwd)
    if state and state.get("phase") == "implementation":
        sys.stderr.write(
            "BLOCKED: implementation changed after preparation but has not been reconciled. "
            "Run the impact-map reconciliation before declaring completion.\n"
        )
        return 2
    if state and state.get("phase") == "reconciled":
        workspace = canonical(state["workspace"])
        state["phase"] = "completed"
        state["completed_at"] = utc_now()
        write_state(workspace, state)
    return 0


def dismiss(workspace: Path, reason: str) -> int:
    if len(reason.strip()) < 10:
        sys.stderr.write("BLOCKED: dismissal requires a specific reason of at least 10 characters\n")
        return 2
    state = read_state(workspace) or {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(workspace),
        "created_at": utc_now(),
    }
    state["phase"] = "dismissed"
    state["dismissed_at"] = utc_now()
    state["dismissal_reason"] = reason.strip()
    write_state(workspace, state)
    print(json.dumps(state, indent=2, sort_keys=False))
    return 0


def status(workspace: Path, as_json: bool) -> int:
    state = read_state(workspace) or {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(workspace),
        "phase": "none",
    }
    if as_json:
        print(json.dumps(state, indent=2, sort_keys=False))
    else:
        print(f"refactor evidence gate: {state['phase']} ({workspace})")
        if state.get("plan", {}).get("path"):
            print(f"impact map: {state['plan']['path']}")
        verdict = (state.get("reconciliation") or {}).get("verdict")
        if verdict:
            print(f"reconciliation: {verdict}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for hook in ("hook-prompt", "hook-write", "hook-command", "hook-stop"):
        sub.add_parser(hook)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--workspace", required=True)
    prepare_parser.add_argument("--plan", required=True)
    prepare_parser.add_argument("--query", required=True)
    reconcile_parser = sub.add_parser("reconcile")
    reconcile_parser.add_argument("--workspace", required=True)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--workspace", required=True)
    status_parser.add_argument("--json", action="store_true")
    dismiss_parser = sub.add_parser("dismiss")
    dismiss_parser.add_argument("--workspace", required=True)
    dismiss_parser.add_argument("--reason", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "hook-prompt":
        return hook_prompt()
    if args.command == "hook-write":
        return hook_write()
    if args.command == "hook-command":
        return hook_command()
    if args.command == "hook-stop":
        return hook_stop()
    workspace = canonical(args.workspace)
    if args.command == "prepare":
        return prepare(workspace, canonical(args.plan), args.query.strip())
    if args.command == "reconcile":
        return reconcile(workspace)
    if args.command == "status":
        return status(workspace, args.json)
    if args.command == "dismiss":
        return dismiss(workspace, args.reason)
    return 2


if __name__ == "__main__":
    sys.exit(main())
