"""Tests for hooks/functionize-capture.py — async PostToolUse/Bash hook that appends one
redacted-shape record per successful Bash call to a live capture file, so `functionize.sh mine
<cli> --source agent` has a `agent_transcript`-class source for Claude Code (Codex sessions are
read directly from disk and need no hook). Background: PostToolUse for Bash was found (see
post-bash-candidate-queue.sh's header) never to fire when the tool result is an error, so a hook
firing here means the command already succeeded; the hook runs async (fire-and-forget) and must
never block, never raise past its own boundary, and never persist anything beyond the six
contract keys.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "procedural-memory"
HOOK = PLUGIN / "hooks/functionize-capture.py"

# Prefer the real target interpreter (3.9, the Cowork host python) when present, so the suite
# exercises the same compatibility floor the hook is written for; fall back to whatever python3
# runs this test suite otherwise.
PY39 = "/usr/bin/python3"
PYTHON = PY39 if Path(PY39).exists() else sys.executable

CAPTURE_FILE_NAME = "agent-bash.jsonl"
CONTRACT_KEYS = {"v", "host", "ts", "session_id", "tool_use_id", "command"}


def run_hook(payload, capture_dir: Path, extra_env: dict | None = None, stdin_bytes: bytes | None = None):
    env = dict(os.environ)
    env["RHIZE_FUNCTIONIZE_CAPTURE_DIR"] = str(capture_dir)
    env.pop("RHIZE_FUNCTIONIZE_CAPTURE", None)
    if extra_env:
        env.update(extra_env)
    if stdin_bytes is None:
        stdin_bytes = json.dumps(payload).encode("utf-8") if payload is not None else b""
    return subprocess.run(
        [PYTHON, str(HOOK)],
        input=stdin_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=10,
    )


def valid_payload(**overrides):
    payload = {
        "session_id": "sess-123",
        "transcript_path": "/Users/jim/.claude/projects/x/transcript.jsonl",
        "cwd": "/Users/jim/dev-local/RHIZE/rhize-plugins",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git status", "description": "check status"},
        "tool_response": {"stdout": "clean", "stderr": "", "interrupted": False},
        "tool_use_id": "tu-456",
    }
    payload.update(overrides)
    return payload


def read_lines(capture_dir: Path, name: str = CAPTURE_FILE_NAME):
    path = capture_dir / name
    if not path.exists():
        return []
    return [line for line in path.read_text().splitlines() if line]


# --- Acceptance test 1: valid payload -> exactly one line, exactly six contract keys ---


def test_valid_payload_writes_exactly_one_line_with_six_keys(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    result = run_hook(valid_payload(), capture_dir)

    assert result.returncode == 0
    assert result.stdout == b""
    lines = read_lines(capture_dir)
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert set(record.keys()) == CONTRACT_KEYS
    assert record["v"] == 1
    assert record["host"] == "claude"
    assert record["session_id"] == "sess-123"
    assert record["tool_use_id"] == "tu-456"
    assert record["command"] == "git status"
    # UTC ISO-8601 with a literal Z suffix.
    assert record["ts"].endswith("Z")
    assert "T" in record["ts"]


# --- Acceptance test 2: secrets in untracked fields never reach the file ---


def test_secrets_in_untracked_fields_never_written(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    secret_output = "AKIA_FAKESECRET_OUTPUT_1234567890"
    secret_result = "sk-FAKESECRET_TOOLUSERESULT_abcdef"
    secret_response = "ghp_FAKESECRET_TOOLRESPONSE_zzzzzz"
    secret_description = "xoxb-FAKESECRET_DESCRIPTION_000000"
    secret_cwd = "/Users/jim/FAKESECRET_CWD_should_never_appear"
    secret_transcript = "/tmp/FAKESECRET_TRANSCRIPT_PATH.jsonl"

    payload = valid_payload(
        cwd=secret_cwd,
        transcript_path=secret_transcript,
        tool_output=secret_output,
        tool_use_result=secret_result,
        tool_response={"stdout": secret_response, "stderr": "", "interrupted": False},
    )
    payload["tool_input"]["description"] = secret_description

    result = run_hook(payload, capture_dir)
    assert result.returncode == 0

    raw = (capture_dir / CAPTURE_FILE_NAME).read_text()
    for secret in (
        secret_output,
        secret_result,
        secret_response,
        secret_description,
        secret_cwd,
        secret_transcript,
    ):
        assert secret not in raw


# --- Acceptance test 3: non-Bash / missing-or-bad fields / malformed / empty -> no write, exit 0 ---


def test_non_bash_tool_no_write(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    result = run_hook(valid_payload(tool_name="Read"), capture_dir)
    assert result.returncode == 0
    assert not (capture_dir / CAPTURE_FILE_NAME).exists()


def test_missing_command_no_write(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    payload = valid_payload()
    del payload["tool_input"]["command"]
    result = run_hook(payload, capture_dir)
    assert result.returncode == 0
    assert not (capture_dir / CAPTURE_FILE_NAME).exists()


def test_non_string_command_no_write(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    payload = valid_payload()
    payload["tool_input"]["command"] = ["git", "status"]
    result = run_hook(payload, capture_dir)
    assert result.returncode == 0
    assert not (capture_dir / CAPTURE_FILE_NAME).exists()


def test_empty_string_command_no_write(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    result = run_hook(valid_payload(tool_input={"command": "", "description": "x"}), capture_dir)
    assert result.returncode == 0
    assert not (capture_dir / CAPTURE_FILE_NAME).exists()


def test_non_string_session_id_no_write(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    result = run_hook(valid_payload(session_id=12345), capture_dir)
    assert result.returncode == 0
    assert not (capture_dir / CAPTURE_FILE_NAME).exists()


def test_non_string_tool_use_id_no_write(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    result = run_hook(valid_payload(tool_use_id=None), capture_dir)
    assert result.returncode == 0
    assert not (capture_dir / CAPTURE_FILE_NAME).exists()


def test_malformed_json_no_write(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    result = run_hook(None, capture_dir, stdin_bytes=b"{not valid json")
    assert result.returncode == 0
    assert not (capture_dir / CAPTURE_FILE_NAME).exists()


def test_empty_stdin_no_write(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    result = run_hook(None, capture_dir, stdin_bytes=b"")
    assert result.returncode == 0
    assert not (capture_dir / CAPTURE_FILE_NAME).exists()


def test_oversized_stdin_no_write(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    # Larger than the 8 MB cap; must not be parsed or written.
    oversized = b'{"pad": "' + (b"a" * (8 * 1024 * 1024 + 100)) + b'"}'
    result = run_hook(None, capture_dir, stdin_bytes=oversized)
    assert result.returncode == 0
    assert not (capture_dir / CAPTURE_FILE_NAME).exists()


# --- Acceptance test 4: opt-out via env ---


@pytest.mark.parametrize("value", ["off", "0", "false", "disabled", "OFF", "False", "DISABLED"])
def test_disabled_via_env_no_write(tmp_path: Path, value: str) -> None:
    capture_dir = tmp_path / "functionize"
    result = run_hook(valid_payload(), capture_dir, extra_env={"RHIZE_FUNCTIONIZE_CAPTURE": value})
    assert result.returncode == 0
    assert not (capture_dir / CAPTURE_FILE_NAME).exists()


def test_enabled_env_value_still_writes(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    result = run_hook(valid_payload(), capture_dir, extra_env={"RHIZE_FUNCTIONIZE_CAPTURE": "on"})
    assert result.returncode == 0
    assert len(read_lines(capture_dir)) == 1


# --- Acceptance test 5: symlink refusal + created permissions ---


def test_symlinked_capture_dir_no_write(tmp_path: Path) -> None:
    real_target = tmp_path / "elsewhere"
    real_target.mkdir()
    capture_dir = tmp_path / "functionize-link"
    capture_dir.symlink_to(real_target, target_is_directory=True)

    result = run_hook(valid_payload(), capture_dir)
    assert result.returncode == 0
    assert not (real_target / CAPTURE_FILE_NAME).exists()
    assert list(real_target.iterdir()) == []


def test_symlinked_capture_file_no_write(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    capture_dir.mkdir(mode=0o700)
    real_target = tmp_path / "elsewhere.jsonl"
    real_target.write_text("")
    (capture_dir / CAPTURE_FILE_NAME).symlink_to(real_target)

    result = run_hook(valid_payload(), capture_dir)
    assert result.returncode == 0
    assert real_target.read_text() == ""


def test_created_dir_is_0700_and_file_is_0600(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize" / "nested"
    result = run_hook(valid_payload(), capture_dir)
    assert result.returncode == 0

    dir_mode = capture_dir.stat().st_mode & 0o777
    assert dir_mode == 0o700

    file_path = capture_dir / CAPTURE_FILE_NAME
    file_mode = file_path.stat().st_mode & 0o777
    assert file_mode == 0o600


# --- Acceptance test 6: rotation ---


def test_rotation_when_file_exceeds_threshold(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    capture_dir.mkdir(mode=0o700)
    target = capture_dir / CAPTURE_FILE_NAME
    target.write_bytes(b"x" * 200)

    result = run_hook(
        valid_payload(),
        capture_dir,
        extra_env={"RHIZE_FUNCTIONIZE_CAPTURE_MAX_BYTES": "100"},
    )
    assert result.returncode == 0

    rotated = capture_dir / f"{CAPTURE_FILE_NAME}.1"
    assert rotated.exists()
    assert rotated.read_bytes() == b"x" * 200

    lines = read_lines(capture_dir)
    assert len(lines) == 1


def test_no_rotation_under_threshold(tmp_path: Path) -> None:
    capture_dir = tmp_path / "functionize"
    capture_dir.mkdir(mode=0o700)
    target = capture_dir / CAPTURE_FILE_NAME
    target.write_bytes(b"x" * 50)

    result = run_hook(
        valid_payload(),
        capture_dir,
        extra_env={"RHIZE_FUNCTIONIZE_CAPTURE_MAX_BYTES": "1000"},
    )
    assert result.returncode == 0
    rotated = capture_dir / f"{CAPTURE_FILE_NAME}.1"
    assert not rotated.exists()
    lines = read_lines(capture_dir)
    assert len(lines) == 1


# --- Acceptance test 7: hooks.json wiring ---


def test_hooks_json_registers_async_capture_hook_after_existing_entry() -> None:
    doc = json.loads((PLUGIN / "hooks/hooks.json").read_text())
    bash_groups = [g for g in doc["hooks"]["PostToolUse"] if g["matcher"] == "Bash"]
    assert len(bash_groups) == 1
    entries = bash_groups[0]["hooks"]

    assert len(entries) == 2
    queue_entry, capture_entry = entries

    assert queue_entry == {
        "type": "command",
        "command": '"${CLAUDE_PLUGIN_ROOT}/hooks/post-bash-candidate-queue.sh"',
        "timeout": 5,
    }

    assert capture_entry["type"] == "command"
    assert "functionize-capture.py" in capture_entry["command"]
    assert capture_entry.get("async") is True
    assert capture_entry.get("timeout") == 10


def test_hooks_json_is_valid_json() -> None:
    # json.loads above already proves this, but keep an explicit assertion of intent: a bad
    # edit to hooks.json must fail the suite loudly, not just this one test's setup.
    (PLUGIN / "hooks/hooks.json").read_text()
    json.loads((PLUGIN / "hooks/hooks.json").read_text())


# --- Acceptance test 8: compiles under Python 3.9 ---


def test_script_compiles_under_python39() -> None:
    if not Path(PY39).exists():
        pytest.skip("/usr/bin/python3 not present on this machine")
    result = subprocess.run(
        [PY39, "-m", "py_compile", str(HOOK)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_hook_is_executable() -> None:
    assert os.access(HOOK, os.X_OK)
