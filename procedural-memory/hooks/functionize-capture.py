#!/usr/bin/env python3
"""functionize-capture.py — async PostToolUse hook (matcher: Bash).

WHY. An agent's Bash calls never reach the interactive shell's history file (there is no
`~/.zsh_history` line for a tool-invoked command), so Functionize's `mine` (which reads shell
history) has nothing to mine from an agent session. `functionize.sh mine <cli> --source agent`
closes that gap by reading a live JSONL capture file instead. This hook is what writes it.

CONTRACT. One line per successful Bash call: `{"v":1,"host":"claude","ts":<UTC ISO-8601 Z>,
"session_id":...,"tool_use_id":...,"command":...}` — those six keys, nothing else, ever. In
particular this hook NEVER reads or writes `tool_output`, `tool_use_result`, `tool_response`,
`tool_input.description`, `cwd`, `transcript_path`, or any other field the PostToolUse payload
may carry: only the command text and the two correlation ids are read. Mining downstream still
runs the existing redaction pass over `command` before treating it as a shape.

PostToolUse/Bash only fires on success. As documented in this plugin's post-bash-candidate-queue.sh
(measured 2026-08-24): the Bash `tool_response` payload has no exit-code field, and more to the
point, PostToolUse for Bash was found NOT to fire at all when the tool result is an error. So by
the time this hook runs, the command already succeeded — there is nothing to check here either.

ASYNC. Registered with `"async": true` in hooks.json: Claude Code runs this in the background,
discards its output, and does not enforce its timeout. That means this script must never print
anything (nothing is listening) and must never be relied on to block the tool call. It is
allowed to be a little slow; it must never crash the session, so every failure mode below is a
silent, exit-0 no-write rather than a raised exception.

Stdlib-only, Python 3.9-compatible (this plugin's hooks call bare `python3`, and the Cowork host
runs 3.9): no `datetime.UTC`, no `match` statements, no `X | Y` runtime unions.
"""

from __future__ import annotations

import datetime
import json
import os
import sys

MAX_STDIN_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_CAPTURE_BYTES = 50 * 1024 * 1024
CAPTURE_FILE_NAME = "agent-bash.jsonl"
ROTATED_SUFFIX = ".1"
DISABLE_VALUES = {"off", "0", "false", "disabled"}


def _is_disabled():
    return os.environ.get("RHIZE_FUNCTIONIZE_CAPTURE", "").strip().lower() in DISABLE_VALUES


def _capture_dir():
    override = os.environ.get("RHIZE_FUNCTIONIZE_CAPTURE_DIR")
    if override:
        return os.path.expanduser(override)
    return os.path.expanduser(os.path.join("~", ".local", "share", "rhize", "functionize"))


def _max_capture_bytes():
    override = os.environ.get("RHIZE_FUNCTIONIZE_CAPTURE_MAX_BYTES")
    if override:
        try:
            return int(override)
        except ValueError:
            return DEFAULT_MAX_CAPTURE_BYTES
    return DEFAULT_MAX_CAPTURE_BYTES


def _read_stdin_payload():
    """Read stdin capped at MAX_STDIN_BYTES; return the decoded dict, or None to do nothing."""
    raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
    if not raw or len(raw) > MAX_STDIN_BYTES:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _extract_fields(payload):
    """Return (session_id, tool_use_id, command) if the payload qualifies, else None.

    Only reads tool_name, tool_input.command, session_id, tool_use_id — see module docstring.
    """
    if payload.get("tool_name") != "Bash":
        return None

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or command == "":
        return None

    session_id = payload.get("session_id")
    if not isinstance(session_id, str):
        return None
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_use_id, str):
        return None

    return session_id, tool_use_id, command


def _utc_timestamp():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _build_record(session_id, tool_use_id, command):
    record = {
        "v": 1,
        "host": "claude",
        "ts": _utc_timestamp(),
        "session_id": session_id,
        "tool_use_id": tool_use_id,
        "command": command,
    }
    return json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"


def _ensure_capture_dir(capture_dir):
    """Create the capture dir at 0700 if missing. Return False (refuse) if it is a symlink."""
    if os.path.islink(capture_dir):
        return False
    if not os.path.isdir(capture_dir):
        os.makedirs(capture_dir, mode=0o700, exist_ok=True)
        try:
            os.chmod(capture_dir, 0o700)
        except OSError:
            pass
    return True


def _rotate_if_needed(file_path, max_bytes):
    try:
        size = os.path.getsize(file_path)
    except OSError:
        return
    if size > max_bytes:
        rotated_path = file_path + ROTATED_SUFFIX
        try:
            os.replace(file_path, rotated_path)
        except OSError:
            pass


def _write_record(capture_dir, line):
    if not _ensure_capture_dir(capture_dir):
        return
    file_path = os.path.join(capture_dir, CAPTURE_FILE_NAME)
    if os.path.islink(file_path):
        return

    _rotate_if_needed(file_path, _max_capture_bytes())

    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = None
    try:
        fd = os.open(file_path, flags, 0o600)
        os.write(fd, line.encode("utf-8"))
    except OSError:
        return
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def main():
    if _is_disabled():
        return
    payload = _read_stdin_payload()
    if payload is None:
        return
    fields = _extract_fields(payload)
    if fields is None:
        return
    session_id, tool_use_id, command = fields
    line = _build_record(session_id, tool_use_id, command)
    _write_record(_capture_dir(), line)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
