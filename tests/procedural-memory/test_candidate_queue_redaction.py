"""Tests for post-bash-candidate-queue.sh secret redaction and ~-relative cwd (R3 item 9)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "procedural-memory/hooks/post-bash-candidate-queue.sh"


def payload_for(command: str, cwd: str, session_id: str = "sess-1") -> str:
    # None of the fixtures below embed a literal double quote in `command` —
    # the hook's own documented limitation is that an unescaped `"` inside
    # tool_input.command defeats its lightweight extraction; that is a
    # pre-existing, separately-documented constraint, not something this
    # redaction test exercises.
    return (
        '{"tool_name":"Bash",'
        f'"session_id":"{session_id}",'
        f'"cwd":"{cwd}",'
        f'"tool_input":{{"command":"{command}"}},'
        '"tool_response":{"stdout":"ok","stderr":"","interrupted":false,'
        '"isImage":false,"noOutputExpected":false},'
        '"tool_use_id":"toolu_test123"}'
    )


# The hook declares #!/bin/sh. On macOS /bin/sh is bash in POSIX mode and tolerates
# bashisms that Debian/Ubuntu's dash rejects (the first CI run failed on a `<<<`
# herestring and a `${var:0:n}` expansion). Run every case under each POSIX shell
# present on the machine and require identical output, so the strict shell is
# exercised locally wherever dash is installed (it ships on macOS 15+ and Debian).
SHELLS = ["/bin/sh"] + [s for s in ("/bin/dash", "/usr/bin/dash") if Path(s).exists()]


def run_hook(payload: str, tmp_path: Path, home: Path) -> str:
    outputs = []
    for shell in SHELLS:
        queue = tmp_path / f"candidate-queue{SHELLS.index(shell)}.jsonl"
        env = {
            "HOME": str(home),
            "PATH": "/usr/bin:/bin",
            "PROCEDURAL_MEMORY_CANDIDATE_QUEUE": str(queue),
        }
        completed = subprocess.run(
            [shell, str(HOOK)], input=payload, capture_output=True, text=True, env=env
        )
        assert completed.returncode == 0, f"{shell}: {completed.stderr}"
        outputs.append(queue.read_text() if queue.exists() else "")
    # The timestamp field is the only thing allowed to differ between shells.
    import re
    normalized = {re.sub(r'"ts":"[^"]*"', '"ts":""', o) for o in outputs}
    assert len(normalized) == 1, f"shells disagree: {outputs}"
    return outputs[0]


@pytest.mark.parametrize(
    ("command", "secret"),
    (
        ("npm test -- --password=hunter2plaintext", "hunter2plaintext"),
        ("pytest --passwd=hunter2plaintext", "hunter2plaintext"),
        ("npm test --token=abcdef0123456789", "abcdef0123456789"),
        ("pytest --secret=topsecretvalue1", "topsecretvalue1"),
        ("npm test --api_key=abcd1234efgh5678", "abcd1234efgh5678"),
        ("pytest --apikey=zzzz9999yyyy8888", "zzzz9999yyyy8888"),
        ("curl -H 'Authorization: Bearer abc.def.ghi123456' && npm test", "abc.def.ghi123456"),
        ("AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP npm test", "AKIAABCDEFGHIJKLMNOP"),
        ("npm test && export OPENAI_KEY=sk-ABCDEFGHIJKLMNOPQRSTUVWX", "sk-ABCDEFGHIJKLMNOPQRSTUVWX"),
        ("npm test && export GH=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ01", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ01"),
        ("npm test && export SLACK=xoxb-1234567890-abcdefghij", "xoxb-1234567890-abcdefghij"),
        ("npm test && export SENTRY=sntrys_ABCDEFGHIJ0123456789", "sntrys_ABCDEFGHIJ0123456789"),
        ("MY_SECRET_TOKEN=extremelysensitive npm test", "extremelysensitive"),
    ),
)
def test_secret_shaped_values_are_redacted(tmp_path: Path, command: str, secret: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    contents = run_hook(payload_for(command, str(tmp_path / "repo")), tmp_path, home)
    assert contents, "hook did not write a queue line for a recognized test/build command"
    entry = json.loads(contents.strip())
    assert "[REDACTED]" in entry["command"]
    assert secret not in entry["command"]


def test_benign_command_is_unchanged(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    command = "npm test -- --coverage"
    contents = run_hook(payload_for(command, str(tmp_path / "repo")), tmp_path, home)
    entry = json.loads(contents.strip())
    assert entry["command"] == command
    assert "[REDACTED]" not in entry["command"]


def test_cwd_under_home_is_stored_tilde_relative(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    nested = home / "dev" / "myrepo"
    contents = run_hook(payload_for("npm test", str(nested)), tmp_path, home)
    entry = json.loads(contents.strip())
    assert entry["repo"] == "~/dev/myrepo"


def test_cwd_equal_to_home_is_stored_as_tilde(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    contents = run_hook(payload_for("npm test", str(home)), tmp_path, home)
    entry = json.loads(contents.strip())
    assert entry["repo"] == "~"


def test_cwd_outside_home_is_left_absolute(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "elsewhere" / "repo"
    contents = run_hook(payload_for("npm test", str(outside)), tmp_path, home)
    entry = json.loads(contents.strip())
    assert entry["repo"] == str(outside)
