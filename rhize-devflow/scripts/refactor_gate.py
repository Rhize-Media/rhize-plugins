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
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = "rhize-refactor-gate-v1"
ACTIVATION_POLICIES = {"auto", "required"}
IMPLEMENTATION_TASK_KIND = "implementation"
REQUIRED_PLAN_SECTIONS = (
    "current behavior",
    "intended semantic delta",
    "invariants",
    "acceptance tests",
    "implementation order",
)
DISCOVERY_QUERY_LINE = re.compile(r"(?im)^Discovery query:\s*(.+?)\s*$")
PREPARATION_ID_LINE = re.compile(r"(?im)^Preparation ID:\s*([a-f0-9]{24})\s*$")
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
# Context and documentation are prose about work, not source implementation.
# Keep this shared by write, reconciliation, and release classification so a
# permitted context update cannot become an unmapped-source failure later.
DOCS_PATHS = (
    # Agent-written reports/analyses (the global instructions' designated
    # location). Prose only: code parked here stays gated like any docs tree.
    ".claude/analyses/",
    ".codex/analyses/",
    "claudedocs/",
    ".planning/",
    "docs/",
)
DOCS_FILES = PLANNING_FILES | {"README.md", "ROADMAP.md", "GUIDE.md", "CHANGELOG.md"}
DOCS_EXTENSIONS = {".md", ".markdown", ".txt", ".rst"}
CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".ini", ".properties", ".cfg", ".conf"}
CONFIG_BASENAMES = {
    ".npmrc",
    ".nvmrc",
    ".yarnrc",
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    ".prettierignore",
    ".eslintignore",
    ".editorconfig",
    "yarn.lock",
    "bun.lockb",
    "Gemfile.lock",
    "poetry.lock",
    "Cargo.lock",
}
CODE_EXTENSIONS = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".mts",
    ".cts",
    ".py",
    ".rb",
    ".go",
    ".rs",
    ".sh",
    ".zsh",
    ".bash",
    ".swift",
    ".java",
    ".kt",
    ".php",
    ".sql",
    ".vue",
    ".svelte",
    ".astro",
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
    r"update|add|remove|delete|replace|build|create|reduce|"
    r"simplif(?:y|ies|ied|ication)|consolidat(?:e|es|ed|ing|ion)|"
    r"deduplicat(?:e|es|ed|ing|ion))\b",
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
    r"\b(then|and)\b.{0,80}\b(implement|refactor|fix|repair|modify|change|update|add|remove|"
    r"reduce|simplif(?:y|ies|ied)|consolidat(?:e|es|ed|ing)|"
    r"deduplicat(?:e|es|ed|ing))\b",
    re.IGNORECASE | re.DOTALL,
)
READ_ONLY_REQUEST = re.compile(
    r"(?:^\s*(?:please\s+)?(?:do\s+(?:an?|the)\s+)?read[- ]only\b|"
    r"\b(?:do not|don't)\s+(?:edit|change|modify)\b|"
    r"\bwithout\s+(?:editing|changing|modifying)\b|"
    r"\bno\s+(?:source\s+)?edits\b)",
    re.IGNORECASE,
)
RELEASE_COMMAND = re.compile(
    r"(?:\bgit(?:\s+-C\s+\S+)?\s+(?:commit|push|merge)\b|\bgh\s+pr\s+merge\b)",
    re.IGNORECASE,
)
# A bare path token stops at shell metacharacters so e.g. `-C /repo&&echo hi` does not
# swallow the operator into the path; a quoted path may contain anything.
_PATH_TOKEN = r"\"([^\"]+)\"|'([^']+)'|([^\s&;|()<>]+)"
GIT_DASH_C_PATH = re.compile(r"\bgit\s+-C\s+(" + _PATH_TOKEN + r")")
GIT_DIR_FLAG_PATH = re.compile(r"--git-dir=(" + _PATH_TOKEN + r")")
WORK_TREE_FLAG_PATH = re.compile(r"--work-tree=(" + _PATH_TOKEN + r")")
# Anchored at the very start of the command: only a single leading `cd <dir> &&`/
# `cd <dir>;` counts as unambiguous. A subshell (`(cd ... )`) or `pushd` never matches
# this pattern at all, so they fall through to the cwd fallback without special-casing.
LEADING_CD_PREFIX = re.compile(r"^\s*cd\s+(" + _PATH_TOKEN + r")\s*(?:&&|;)\s*")
# A variable or command-substitution token anywhere in a resolved path keeps the day's
# behavior (cwd) rather than expanding it ourselves.
AMBIGUOUS_PATH_TOKEN = re.compile(r"[$`]")


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


def is_filesystem_root(path: Path) -> bool:
    """True for `/` (and any platform's drive root).

    A filesystem root can never describe real work, but it *contains* every path on the
    machine — so a receipt armed there matches everything in `find_state_for_path`'s
    containment scan and blocks writes and releases for every session, in every repository
    (and turn end for its owning sessions, or for every session when no owner was recorded).
    Projectless contexts (no repo cwd) are how such a receipt gets written.
    """
    resolved = canonical(path)
    return resolved.parent == resolved


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
        if is_filesystem_root(workspace):
            # A stale root receipt (older version, or another machine) must never match.
            # Deliberately NOT filtered in read_state: `status`/`dismiss --workspace /` must
            # still see and clear such a file.
            continue
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


def payload_session_id(payload: dict[str, Any] | None) -> str | None:
    value = (payload or {}).get("session_id")
    return value if isinstance(value, str) and value.strip() else None


def record_owner(state: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Record the writing session as an owner of the implementation; True when added.

    Owners are the only sessions the Stop hook holds to reconciliation. Write and release
    gates stay workspace-wide, so this never widens what any session may change.
    """
    session_id = payload_session_id(payload)
    if session_id is None:
        return False
    owners = state.get("owner_sessions")
    current = {item for item in owners if isinstance(item, str)} if isinstance(owners, list) else set()
    if session_id in current:
        return False
    state["owner_sessions"] = sorted(current | {session_id})
    return True


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


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


def should_activate(prompt: str, policy: str, task_kind: str) -> bool:
    if policy == "required":
        return task_kind == IMPLEMENTATION_TASK_KIND
    return is_material_prompt(prompt)


def plugin_version() -> str:
    manifest = Path(__file__).resolve().parents[1] / ".claude-plugin/plugin.json"
    try:
        value = json.loads(manifest.read_text()).get("version")
    except (OSError, json.JSONDecodeError):
        value = None
    return value if isinstance(value, str) and value else "unavailable"


def source_commit() -> str:
    result = run(["git", "rev-parse", "HEAD"], Path(__file__).resolve().parents[1])
    commit = result.stdout.strip().lower() if result.returncode == 0 else ""
    return commit if re.fullmatch(r"[0-9a-f]{40}", commit) else "unavailable"


def source_identity() -> dict[str, str]:
    return {
        "plugin_version": plugin_version(),
        "source_commit": source_commit(),
        "gate_source_sha256": sha256_file(Path(__file__).resolve()),
    }


def new_lifecycle(
    workspace: Path,
    prompt: str | None,
    policy: str,
    task_kind: str,
    reason_code: str,
    at: str,
) -> dict[str, Any]:
    digest = prompt_sha256(prompt) if prompt is not None else None
    trial_material = f"{workspace}\0{digest or ''}\0{at}".encode()
    return {
        "trial_id": hashlib.sha256(trial_material).hexdigest()[:24],
        "activation": {"policy": policy, "reason_code": reason_code, "task_kind": task_kind},
        "prompt_sha256": digest,
        "source_identity": source_identity(),
        "hook_event_counts": {
            "UserPromptSubmit": 1 if prompt is not None else 0,
            "PreToolUse": 0,
            "Stop": 0,
        },
        "events": [{"phase": "pending", "at": at, "verdict": "activated"}]
        if prompt is not None
        else [],
    }


def ensure_lifecycle(state: dict[str, Any], workspace: Path) -> dict[str, Any]:
    lifecycle = state.get("lifecycle")
    if isinstance(lifecycle, dict):
        return lifecycle
    lifecycle = new_lifecycle(
        workspace,
        None,
        "auto",
        "",
        "manual-prepare",
        state.get("created_at") or utc_now(),
    )
    state["lifecycle"] = lifecycle
    return lifecycle


def count_hook_event(state: dict[str, Any], workspace: Path, event: str) -> None:
    lifecycle = ensure_lifecycle(state, workspace)
    counts = lifecycle.setdefault("hook_event_counts", {})
    counts[event] = int(counts.get(event, 0)) + 1


def active_receipt(state: dict[str, Any] | None) -> bool:
    return bool(
        state
        and state.get("phase") in {"pending", "prepared", "implementation", "reconciled"}
    )


def append_lifecycle_event(
    state: dict[str, Any], workspace: Path, phase: str, at: str, verdict: str | None = None
) -> None:
    lifecycle = ensure_lifecycle(state, workspace)
    event = {"phase": phase, "at": at}
    if verdict is not None:
        event["verdict"] = verdict
    lifecycle.setdefault("events", []).append(event)


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
    if READ_ONLY_REQUEST.search(prompt) and not EXECUTION_AFTER_REVIEW.search(prompt):
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


def prepare(workspace: Path, plan: Path, query: str, *, quiet: bool = False) -> int:
    if is_filesystem_root(workspace):
        # Warn, but exit 0 and write nothing. A nonzero exit here would be a NEW failure
        # mode in automation that cannot ask a human; a no-op only ever removes a block.
        sys.stderr.write(
            "SKIPPED: refusing to arm a refactor-evidence receipt at the filesystem root "
            f"({workspace}) — it would match every path on this machine. Re-run prepare with "
            "--workspace pointing at the repository you are actually changing.\n"
        )
        return 0
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
    prepared_at = utc_now()
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(workspace),
        "phase": "prepared",
        "created_at": previous.get("created_at", prepared_at),
        "prepared_at": prepared_at,
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
    if isinstance(previous.get("lifecycle"), dict):
        state["lifecycle"] = previous["lifecycle"]
    # Sessions that already wrote under this receipt still own the pending reconciliation.
    if previous.get("phase") in {"prepared", "implementation"} and isinstance(
        previous.get("owner_sessions"), list
    ):
        state["owner_sessions"] = previous["owner_sessions"]
    append_lifecycle_event(state, workspace, "prepared", prepared_at, "prepared")
    write_state(workspace, state)
    if not quiet:
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
        if not is_config_path(path)
        and not is_docs_path(path)
        and path.lower() not in plan_text
        and Path(path).name.lower() not in plan_text
    ]
    if unmapped:
        failed_at = utc_now()
        state["phase"] = "implementation"
        state["reconciliation"] = {
            "at": failed_at,
            "verdict": "OUT_OF_SYNC",
            "changed_files": changed,
            "unmapped_files": unmapped,
            "exceptions": exceptions,
            "structural_evidence": structural,
        }
        append_lifecycle_event(state, workspace, "reconciled", failed_at, "OUT_OF_SYNC")
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
    append_lifecycle_event(state, workspace, "reconciled", state["reconciled_at"], verdict)
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


def is_docs_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    posix = PurePosixPath(normalized)
    # Check extension first: executable code (including MDX) remains gated even
    # inside a documentation tree. Named context files can live in subprojects.
    return posix.suffix.lower() in DOCS_EXTENSIONS and (
        posix.name in DOCS_FILES
        or any(normalized.startswith(prefix) for prefix in DOCS_PATHS)
    )


def is_config_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    posix = PurePosixPath(normalized)
    basename = posix.name
    suffix = posix.suffix
    # Extension precedence is deliberate: a dotfile-shaped config path that is
    # actually executable code (e.g. `.eslintrc.js`) must stay gated.
    if suffix in CODE_EXTENSIONS:
        return False
    if suffix in CONFIG_EXTENSIONS:
        return True
    if basename in CONFIG_BASENAMES:
        return True
    if basename.startswith(".env"):
        return True
    return False


def recent_impact_maps(workspace: Path, state: dict[str, Any]) -> list[tuple[Path, str]]:
    """Find complete maps authored for this pending receipt, with explicit query metadata."""
    raw_created_at = state.get("created_at")
    lifecycle = state.get("lifecycle")
    trial_id = lifecycle.get("trial_id") if isinstance(lifecycle, dict) else None
    if not isinstance(raw_created_at, str) or not isinstance(trial_id, str):
        return []
    try:
        created_at = dt.datetime.fromisoformat(raw_created_at.replace("Z", "+00:00"))
    except ValueError:
        return []
    plans_dir = workspace / ".claude" / "plans"
    if not plans_dir.is_dir():
        return []

    matches: list[tuple[Path, str]] = []
    for candidate in plans_dir.glob("*.md"):
        try:
            if candidate.stat().st_mtime < created_at.timestamp():
                continue
            text = validate_plan(canonical(candidate), workspace)
        except (OSError, ValueError):
            continue
        preparation_match = PREPARATION_ID_LINE.search(text)
        query_match = DISCOVERY_QUERY_LINE.search(text)
        if preparation_match and preparation_match.group(1) == trial_id and query_match:
            query = query_match.group(1).strip().strip("`").strip('"').strip()
            if query:
                matches.append((canonical(candidate), query))
    return matches


def hook_prompt(
    activation_policy: str = "auto",
    task_kind: str = "",
) -> int:
    if gate_disabled():
        return 0
    payload = read_payload()
    if not payload:
        return 0
    prompt = payload.get("prompt") or payload.get("user_prompt")
    workspace = payload_workspace(payload)
    if is_filesystem_root(workspace):
        # Fail open and write nothing: a root receipt would match every path on the machine.
        return 0
    current = read_state(workspace)
    if active_receipt(current):
        count_hook_event(current, workspace, "UserPromptSubmit")
        write_state(workspace, current)
    if not isinstance(prompt, str) or not should_activate(prompt, activation_policy, task_kind):
        return 0
    if activation_policy == "auto" and "/rhize-devflow:impact-map" in prompt:
        return 0
    if current and current.get("phase") in {"prepared", "implementation"}:
        current["latest_prompt_sha256"] = prompt_sha256(prompt)
        current["updated_at"] = utc_now()
        write_state(workspace, current)
    else:
        created_at = utc_now()
        reason_code = (
            "material-prompt-selector"
            if activation_policy == "auto"
            else "caller-declared-implementation"
        )
        write_state(
            workspace,
            {
                "schema_version": SCHEMA_VERSION,
                "workspace": str(workspace),
                "phase": "pending",
                "created_at": created_at,
                "lifecycle": new_lifecycle(
                    workspace,
                    prompt,
                    activation_policy,
                    task_kind,
                    reason_code,
                    created_at,
                ),
            },
        )
    active = read_state(workspace) or {}
    lifecycle = active.get("lifecycle")
    preparation_id = lifecycle.get("trial_id", "") if isinstance(lifecycle, dict) else ""
    auto_prepare_hint = (
        f" If the single-map auto-prepare fallback is needed, begin the map with "
        f"Preparation ID: {preparation_id} and Discovery query: <the exact query used for the map>."
        if active.get("phase") == "pending"
        else ""
    )
    print(
        "<user-prompt-submit-hook>\n"
        "Refactor evidence gate: impact-map evidence is required before source edits. "
        "Run /rhize-devflow:impact-map, persist its map, then execute the prepare command "
        f"shown by that workflow.{auto_prepare_hint}\n"
        f"Gate CLI: {Path(__file__).resolve()}\n"
        "</user-prompt-submit-hook>"
    )
    return 0


def enforce_write_payload(
    payload: dict[str, Any],
    *,
    count_invocation: bool = True,
    cwd_override: Path | None = None,
) -> int:
    cwd = cwd_override if cwd_override is not None else payload_workspace(payload)
    workspace, state = find_state_for_path(cwd)
    if count_invocation and active_receipt(state):
        count_hook_event(state, workspace, "PreToolUse")
        write_state(workspace, state)
    paths = extract_write_paths(payload)
    relevant = [
        relative
        for path in paths
        if (relative := normalized_relative_path(path, workspace)) is not None
        and not is_planning_path(relative)
        and not is_config_path(relative)
        and not is_docs_path(relative)
    ]
    if not relevant or not state or state.get("phase") == "dismissed":
        return 0
    phase = state.get("phase")
    if phase == "pending":
        candidates = recent_impact_maps(workspace, state)
        if len(candidates) != 1:
            reason = (
                "no recent complete map matching the active Preparation ID and Discovery query was found"
                if not candidates
                else f"{len(candidates)} recent maps match the active Preparation ID and Discovery query"
            )
            sys.stderr.write(
                "BLOCKED: source edits require a prepared refactor-evidence receipt; "
                f"{reason}. Keep the map in .claude/plans and run: python3 "
                f"{Path(__file__).resolve()} prepare --workspace \"{workspace}\" "
                "--plan \"<selected-map>\" --query \"<same discovery query>\".\n"
            )
            return 2
        plan, query = candidates[0]
        if prepare(workspace, plan, query, quiet=True) != 0:
            return 2
        sys.stdout.write(
            "Prepared the only complete impact map created for this request before the source write.\n"
        )
        state = read_state(workspace)
        if not state:
            sys.stderr.write("BLOCKED: auto-prepared impact-map receipt could not be re-read\n")
            return 2
        phase = state.get("phase")
    if phase in {"prepared", "implementation", "reconciled"} and not state_plan_is_current(state):
        sys.stderr.write("BLOCKED: impact map changed after preparation; run prepare again.\n")
        return 2
    if phase == "reconciled":
        state["reconciliation"] = None
    owner_added = phase in {"prepared", "implementation", "reconciled"} and record_owner(
        state, payload
    )
    if phase == "implementation" and owner_added:
        write_state(workspace, state)
    if phase in {"prepared", "reconciled"}:
        implementation_started_at = utc_now()
        state["phase"] = "implementation"
        state["implementation_started_at"] = implementation_started_at
        append_lifecycle_event(
            state,
            workspace,
            "implementation",
            implementation_started_at,
            "source-write-observed",
        )
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
            count_hook_event(state, _workspace, "PreToolUse")
            write_state(_workspace, state)
            sys.stderr.write(
                "BLOCKED: active refactor gate could not validate a malformed write payload. "
                "Retry the write with a valid harness payload.\n"
            )
            return 2
        return 0
    return enforce_write_payload(payload)


def _quoted_or_bare(match: re.Match[str]) -> str:
    return match.group(2) or match.group(3) or match.group(4) or ""


def explicit_git_target(command: str) -> tuple[str, bool] | None:
    """Return `(raw_path, from_git_dir_flag)` for the first `git -C`, `--work-tree=`, or
    `--git-dir=` argument in `command`, checked in that priority order.

    These flags anchor the git invocation explicitly regardless of any `cd`, so they are
    resolved before a leading `cd` prefix is even considered.
    """
    for pattern, from_git_dir_flag in (
        (GIT_DASH_C_PATH, False),
        (WORK_TREE_FLAG_PATH, False),
        (GIT_DIR_FLAG_PATH, True),
    ):
        match = pattern.search(command)
        if match:
            raw = _quoted_or_bare(match)
            if raw:
                return raw, from_git_dir_flag
    return None


def leading_cd_target(command: str) -> str | None:
    """Return the raw argument of a single, unambiguous leading `cd <dir> &&`/`cd <dir>;`.

    Only exactly one `cd` in the whole command counts. Any further `cd` after the leading
    one — whether immediately chained (`cd a && cd b && ...`) or separated by another
    command (`cd a && npm test && cd b && git commit`) — makes the target ambiguous: the
    caller keeps today's cwd-based behavior instead of guessing which one the command
    actually meant to be in when the git verb ran. A subshell (`(cd ... )`) or `pushd`
    never matches the anchored pattern at all, so they fall through to the same cwd
    fallback without special-casing.
    """
    match = LEADING_CD_PREFIX.match(command)
    if not match:
        return None
    raw = _quoted_or_bare(match)
    if not raw or AMBIGUOUS_PATH_TOKEN.search(raw):
        return None
    remainder = command[match.end() :]
    if re.search(r"(?:^|[;&|]|\n)\s*cd\s", remainder):
        return None
    return raw


def resolve_relative_to(raw: str, base: Path) -> Path:
    if raw.startswith("~") or os.path.isabs(raw):
        return canonical(raw)
    return canonical(base / raw)


def repo_root_or_fallback(candidate: Path, cwd: Path) -> Path:
    """Resolve `candidate`'s Git repo root; fall back to `cwd` if it is not a directory
    inside a Git repository — the same trust the gate already places in `cwd` itself when
    nothing more specific is known. Never point a check at a directory with no receipt and
    no dirty-tree signal of its own just because a command happened to name it.
    """
    if not candidate.is_dir():
        return cwd
    top = run(["git", "rev-parse", "--show-toplevel"], candidate)
    if top.returncode != 0 or not top.stdout.strip():
        return cwd
    return canonical(top.stdout.strip())


def resolve_command_target_directory(command: str, cwd: Path) -> Path:
    """Resolve the Git workspace a shell command targets, when unambiguous.

    Checked in order: an explicit `git -C <dir>` / `--work-tree=<dir>` / `--git-dir=<dir>`
    (these anchor the git invocation regardless of shell state), then a single leading
    `cd <dir> &&` or `cd <dir>;` prefix with no further `cd` anywhere later in the command
    (absolute, `~`, or relative to `cwd`). Anything ambiguous — any further `cd` after the
    leading one, a subshell, `pushd`, or a variable/command substitution in the path —
    keeps today's behavior and returns `cwd` unchanged rather than guessing. A resolved
    directory that does not exist or is not inside a Git repository also falls back to
    `cwd` for the same reason.
    """
    if not command:
        return cwd

    explicit = explicit_git_target(command)
    if explicit is not None:
        raw, from_git_dir_flag = explicit
        if AMBIGUOUS_PATH_TOKEN.search(raw):
            return cwd
        candidate = resolve_relative_to(raw, cwd)
        if from_git_dir_flag and candidate.name == ".git":
            candidate = candidate.parent
        return repo_root_or_fallback(candidate, cwd)

    cd_target = leading_cd_target(command)
    if cd_target is not None:
        return repo_root_or_fallback(resolve_relative_to(cd_target, cwd), cwd)

    return cwd


def release_targets_only_exempt_changes(hint: Path) -> bool | None:
    """True if every dirty path at/above `hint` is config, planning, or documentation.

    None means the repo toplevel could not be resolved, so the caller should fall back
    to the existing unconditional block rather than guess.
    """
    top = run(["git", "rev-parse", "--show-toplevel"], hint)
    if top.returncode != 0 or not top.stdout.strip():
        return None
    repo = canonical(top.stdout.strip())
    dirty = git_status_snapshot(repo)
    if not dirty:
        # A pending/prepared receipt with nothing actually edited is a pure false
        # positive for this gate — allow it.
        return True
    return all(
        is_config_path(path) or is_planning_path(path) or is_docs_path(path) for path in dirty
    )


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
    cwd = payload_workspace(payload)
    is_release = isinstance(command, str) and bool(RELEASE_COMMAND.search(command))
    # A leading `cd <dir> &&`/`cd <dir>;`, a `git -C <path>`, or a `--git-dir=`/
    # `--work-tree=` flag can target a different repo than the payload's own cwd;
    # resolve that target once (falling back to cwd whenever it is ambiguous or does
    # not resolve to a real Git repo) and reuse it for the receipt lookup, the
    # patch-carried source-write check, and the dirty check below, so a receipt under
    # the resolved target is not missed.
    resolved_hint = (
        resolve_command_target_directory(command, cwd) if isinstance(command, str) else cwd
    )
    event_hint = resolved_hint if is_release else cwd
    event_workspace, event_state = find_state_for_path(event_hint)
    if active_receipt(event_state):
        count_hook_event(event_state, event_workspace, "PreToolUse")
        write_state(event_workspace, event_state)
    if isinstance(command, str) and "*** Begin Patch" in command:
        write_result = enforce_write_payload(
            payload, count_invocation=False, cwd_override=resolved_hint
        )
        if write_result != 0:
            return write_result
    if not is_release:
        return 0
    hint = event_hint
    state = event_state
    phase = state.get("phase") if state else None
    if phase not in {None, "reconciled", "completed", "dismissed"}:
        if phase in {"pending", "prepared"}:
            # No gated source write has happened yet in either phase. Rather than
            # block on the receipt's existence alone, check whether the release
            # command's own repo is actually dirty with anything other than
            # config/planning changes — that is the real false-positive case.
            only_exempt = release_targets_only_exempt_changes(hint)
            if only_exempt is True:
                return 0
        sys.stderr.write(
            "BLOCKED: commit/push/merge requires a reconciled refactor-evidence receipt. "
            "Only configuration, planning, or documentation-only changes are exempt from this gate. "
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
    if state and state.get("phase") not in {None, "completed", "dismissed"}:
        count_hook_event(state, _workspace, "Stop")
        write_state(_workspace, state)
    if state and state.get("phase") == "implementation":
        # Only sessions that wrote under this receipt owe the reconciliation. A session with
        # no identity, or a receipt with no recorded owner (legacy, or reached through an
        # OUT_OF_SYNC reconcile), fails closed so nothing unreconciled slips past.
        owners = state.get("owner_sessions")
        session_id = payload_session_id(payload)
        if session_id is not None and isinstance(owners, list) and owners and session_id not in owners:
            return 0
        sys.stderr.write(
            "BLOCKED: implementation changed after preparation but has not been reconciled. "
            "Run the impact-map reconciliation before declaring completion.\n"
        )
        return 2
    if state and state.get("phase") == "reconciled":
        workspace = canonical(state["workspace"])
        state["phase"] = "completed"
        state["completed_at"] = utc_now()
        append_lifecycle_event(
            state, workspace, "completed", state["completed_at"], "completed"
        )
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
    append_lifecycle_event(state, workspace, "dismissed", state["dismissed_at"], "dismissed")
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
    prompt_parser = sub.add_parser("hook-prompt")
    prompt_parser.add_argument(
        "--activation-policy", choices=sorted(ACTIVATION_POLICIES), default="auto"
    )
    prompt_parser.add_argument("--task-kind", default="")
    for hook in ("hook-write", "hook-command", "hook-stop"):
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
        return hook_prompt(args.activation_policy, args.task_kind.strip().lower())
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
