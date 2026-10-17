#!/usr/bin/env python3
"""PreToolUse guard against explicit Keychain GUI access; never reads secrets."""
from __future__ import annotations

import json
import re
import shlex
import sys
import unicodedata

MAX_INPUT = 1024 * 1024
GUIDANCE = (
    "Credential safeguard: Keychain GUI access blocked. Use the credential-access "
    "skill: authenticated service CLI first, then an exact Keychain CLI lookup "
    "captured privately in the authorized child process. Never print credentials."
)
SOURCE_TOOLS = {"read", "write", "edit", "multiedit", "notebookedit", "apply_patch"}
KEYCHAIN = re.compile(r"keychain\s*access|com\.apple\.keychainaccess", re.I)
GUI_CODE = re.compile(r"\b(?:getapp|application|launchapplication|activateapplication)\s*\(|"
                      r"(?<![\w-])(?:/usr/bin/)?(?:open|osascript)\s|"
                      r"[\"'](?:/usr/bin/)?(?:open|osascript)[\"']|\btell\s+application\b", re.I)
GUI_TOOL = re.compile(r"cua|computer|desktop|open_app|launch_app|applescript", re.I)


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})",
                  lambda match: chr(int(match.group(1) or match.group(2), 16)), text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = re.sub(r"\\([ /])", r"\1", text)
    return re.sub(r"[\"']\s*\+\s*[\"']", "", text)


def source_read(command: str) -> bool:
    if "\n" in command or "\r" in command:
        return False
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return False
    return bool(tokens and tokens[0].rsplit("/", 1)[-1] in {"rg", "grep", "cat", "head", "tail"}
                and not any(t and all(c in ";&|()<>" for c in t) for t in tokens)
                and not any(t.startswith(("--pre", "--hostname-bin")) for t in tokens)
                and "$(" not in command and "`" not in command)


def strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def blocked(payload: object) -> bool:
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_name"), str):
        raise ValueError("invalid tool envelope")
    tool = payload["tool_name"]
    if tool.lower().split(".")[-1] in SOURCE_TOOLS:
        return False
    # Code-mode orchestration is not executed by this hook; nested tools are guarded.
    if tool in {"functions.exec", "exec"}:
        return False
    value = payload.get("tool_input")
    if not isinstance(value, (dict, str)):
        raise ValueError("invalid tool input")
    if isinstance(value, dict):
        # Only execution fields are code; issue bodies and source-file contents are data.
        text = "\n".join(v for k, v in value.items()
                         if k in {"code", "command", "cmd", "script", "input"} and isinstance(v, str))
        if GUI_TOOL.search(tool):
            text = "\n".join(strings(value))
    else:
        text = value
    text = normalized(text)
    if not KEYCHAIN.search(text):
        return False
    if tool == "Bash" and source_read(text):
        return False
    # shortcut: explicit targets only; arbitrary encoded/dynamic code needs a host sandbox.
    return bool(GUI_TOOL.search(tool) or GUI_CODE.search(text))


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError("tool envelope too large")
        deny = blocked(json.loads(raw))
    except (ValueError, TypeError, RecursionError):
        print("Credential safeguard: invalid tool envelope; retry with a valid bounded request.", file=sys.stderr)
        return 2
    if deny:
        print(GUIDANCE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
