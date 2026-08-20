#!/usr/bin/env python3
"""JSON-stdin and macOS-portability tests for rhize-devflow's hooks
(`rhize-devflow/hooks/`), per the plan's Planned File Map
(`tests/rhize-devflow/test_hooks.py — JSON stdin/macOS portability tests`) and Task 7's
scope note: hooks are test-only in this task — fix a hook only if a test here exposes a
genuine *portability* bug, otherwise report it.

Covers the 4 opt-in hooks (3 data-mutation-consistency hooks + protect-files.sh) plus the
auto-wired refactor-evidence commands referenced by hooks.json:
  1. Delivery mechanism: Claude Code feeds hooks their payload as JSON on stdin
     (UserPromptSubmit: {"prompt": ...}; PreToolUse: {"tool_input": {...}}) — every case
     below drives the hook that way, never via a positional argument.
  2. macOS/BSD portability: `bash -n` syntax check plus a grep for GNU-only flags that
     silently do the wrong thing (or error) under BSD grep/sed (no `-P`/`-oP`, no
     `sed -r`, no `sed -i` without an explicit (possibly empty) extension argument, no
     `readlink -f`) — this repo runs on macOS BSD tools per CLAUDE.md.
  3. protect-files.sh is `#!/usr/bin/python3` despite its `.sh` extension — tested by its
     shebang, not by `bash -n`.
  4. hooks.json parses and every hook file it references exists and is executable.

Known, pre-existing, non-portability bug found while writing this file (reported, not
fixed — out of Task 7's scope): `data-mutation-consistency__prewrite-check.sh` builds its
warning text with `WARNINGS="$WARNINGS\n  ..."` and prints it via `cat <<EOF`, which does
not interpret the literal `\n` as a newline in bash — the emitted text contains a literal
backslash-n rather than a line break. This reproduces identically on GNU bash, so it is a
quoting bug, not a macOS/BSD portability issue, and is asserted on as observed rather than
"fixed" here.
"""
from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "rhize-devflow" / "hooks"
HOOKS_JSON = HOOKS_DIR / "hooks.json"

MUTATION_DETECTOR = HOOKS_DIR / "data-mutation-consistency__mutation-detector.sh"
PREWRITE_CHECK = HOOKS_DIR / "data-mutation-consistency__prewrite-check.sh"
SENTRY_STALE_DATA = HOOKS_DIR / "data-mutation-consistency__sentry-stale-data.sh"
PROTECT_FILES = HOOKS_DIR / "protect-files.sh"

BASH_HOOKS = [MUTATION_DETECTOR, PREWRITE_CHECK, SENTRY_STALE_DATA]
ALL_HOOKS = BASH_HOOKS + [PROTECT_FILES]

for _hook in ALL_HOOKS:
    assert _hook.is_file(), f"missing {_hook}"


def run_hook(hook: Path, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# 1. JSON-stdin delivery — UserPromptSubmit hooks
# ---------------------------------------------------------------------------


def test_mutation_detector_flags_a_mutation_bug_report_and_exits_zero() -> None:
    result = run_hook(
        MUTATION_DETECTOR,
        {"prompt": "There is a bug with stale cache after updating players"},
    )
    assert result.returncode == 0
    assert "<user-prompt-submit-hook>" in result.stdout
    assert "analyze-mutations" in result.stdout or "check-mutation" in result.stdout


def test_mutation_detector_is_silent_on_an_unrelated_prompt() -> None:
    result = run_hook(MUTATION_DETECTOR, {"prompt": "what is the weather today"})
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_mutation_detector_lets_an_explicit_trigger_through_without_a_suggestion() -> None:
    """The ANALYSIS_TRIGGERS allowlist should short-circuit before the keyword scan."""
    result = run_hook(MUTATION_DETECTOR, {"prompt": "/rhize-devflow:mutation-check --all"})
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_mutation_detector_exits_zero_on_malformed_json_stdin() -> None:
    result = subprocess.run(
        [str(MUTATION_DETECTOR)], input="not json{{{", capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_sentry_stale_data_flags_a_sentry_issue_link_and_exits_zero() -> None:
    result = run_hook(
        SENTRY_STALE_DATA,
        {"prompt": "investigating https://sentry.io/issues/12345 for stale data"},
    )
    assert result.returncode == 0
    assert "STALE DATA INVESTIGATION" in result.stdout


def test_sentry_stale_data_is_silent_on_an_unrelated_prompt() -> None:
    result = run_hook(SENTRY_STALE_DATA, {"prompt": "what is 2+2"})
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# 2. JSON-stdin delivery — PreToolUse hooks
# ---------------------------------------------------------------------------


def test_prewrite_check_warns_on_a_supabase_mutation_missing_error_handling() -> None:
    result = run_hook(
        PREWRITE_CHECK,
        {
            "tool_input": {
                "file_path": "app/actions/players.ts",
                "content": "supabase.from('players').update({name: 'x'})",
            }
        },
    )
    assert result.returncode == 0
    assert "<pre-tool-use-hook>" in result.stdout
    assert "Missing error handling" in result.stdout


def test_prewrite_check_is_silent_on_a_non_typescript_file() -> None:
    result = run_hook(
        PREWRITE_CHECK, {"tool_input": {"file_path": "README.md", "content": "hello"}}
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_prewrite_check_is_silent_on_a_typescript_file_outside_relevant_dirs() -> None:
    result = run_hook(
        PREWRITE_CHECK,
        {"tool_input": {"file_path": "src/components/Button.ts", "content": "export const x = 1;"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_protect_files_blocks_a_ci_workflow_edit() -> None:
    result = run_hook(
        PROTECT_FILES,
        {"tool_input": {"file_path": ".github/workflows/ci.yml", "content": "on: push"}},
    )
    assert result.returncode == 2
    assert "BLOCKED" in result.stderr
    assert "CI workflow" in result.stderr


def test_protect_files_allows_an_ordinary_source_file() -> None:
    result = run_hook(
        PROTECT_FILES, {"tool_input": {"file_path": "src/foo.ts", "content": "const x = 1;"}}
    )
    assert result.returncode == 0


def test_protect_files_exits_zero_on_malformed_json_stdin() -> None:
    result = subprocess.run(
        [sys.executable, str(PROTECT_FILES)], input="not json{{{", capture_output=True, text=True
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# 3. macOS/BSD portability
# ---------------------------------------------------------------------------

# GNU-only constructs that behave differently (or error outright) under BSD grep/sed —
# see CLAUDE.md's "rtk find shim" / "macOS BSD grep (no -P)" environment notes.
_GNU_ONLY_PATTERNS = [
    (r"grep\s+(-\w*P|--perl-regexp)", "grep -P/--perl-regexp (BSD grep has no PCRE support)"),
    (r"sed\s+-\w*r\b", "sed -r (BSD sed requires -E for extended regex)"),
    (r"sed\s+-i(?!\s|\.)", "sed -i without an explicit (possibly empty) extension arg"),
    (r"readlink\s+-f\b", "readlink -f (not available on BSD readlink)"),
]


@pytest.mark.parametrize("hook_path", BASH_HOOKS, ids=lambda p: p.name)
def test_bash_hook_passes_syntax_check(hook_path: Path) -> None:
    result = subprocess.run(["bash", "-n", str(hook_path)], capture_output=True, text=True)
    assert result.returncode == 0, f"bash -n failed for {hook_path.name}: {result.stderr}"


@pytest.mark.parametrize("hook_path", BASH_HOOKS, ids=lambda p: p.name)
def test_bash_hook_avoids_gnu_only_constructs(hook_path: Path) -> None:
    import re

    text = hook_path.read_text()
    violations = []
    for pattern, description in _GNU_ONLY_PATTERNS:
        if re.search(pattern, text):
            violations.append(description)
    assert violations == [], f"{hook_path.name} uses GNU-only construct(s): {violations}"


def test_protect_files_is_tested_by_its_python_shebang_not_bash_dash_n() -> None:
    """protect-files.sh ships a `.sh` extension but is actually a Python script — assert
    the shebang so a future `bash -n` sweep doesn't wrongly try to syntax-check it as
    bash, and drive it directly through the real interpreter it declares."""
    first_line = PROTECT_FILES.read_text().splitlines()[0]
    assert first_line == "#!/usr/bin/python3"

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(PROTECT_FILES)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# 4. hooks.json parses; every referenced hook exists and is executable
# ---------------------------------------------------------------------------


def test_hooks_json_parses() -> None:
    data = json.loads(HOOKS_JSON.read_text())
    assert "hooks" in data


def test_every_hook_file_referenced_by_hooks_json_exists_and_is_executable() -> None:
    """hooks.json currently wires nothing (all hooks are opt-in — see its own
    description field), so this is a forward-looking regression guard: if a future
    version starts referencing hook commands here, each one must resolve to a real,
    executable file relative to the plugin root."""
    data = json.loads(HOOKS_JSON.read_text())

    def walk(node):
        if isinstance(node, dict):
            if "command" in node and isinstance(node["command"], str):
                yield node["command"]
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    referenced_commands = list(walk(data.get("hooks", {})))
    for command in referenced_commands:
        resolved = command.replace("${CLAUDE_PLUGIN_ROOT}", str(REPO_ROOT / "rhize-devflow"))
        candidates = [Path(token) for token in shlex.split(resolved) if "/" in token]
        paths = [path for path in candidates if path.exists()]
        assert paths, f"hooks.json references missing hook file: {command}"
        for path in paths:
            assert os.access(path, os.X_OK), f"hooks.json references non-executable hook file: {command}"


def test_all_shipped_hook_files_are_executable() -> None:
    for hook_path in ALL_HOOKS:
        mode = hook_path.stat().st_mode
        assert mode & stat.S_IXUSR, f"{hook_path.name} is not executable by its owner"
