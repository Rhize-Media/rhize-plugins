#!/usr/bin/env python3
"""PostToolUse advisory hint for the obsidian-second-brain plugin.

Matcher: Read (set in hooks.json). Same $TOOL_INPUT bug as
vault-write-hint.py -- see that file's docstring.

Fast path: exits silently (no output, exit 0) unless the file just read is a
.md file inside the Obsidian vault path. Advisory only -- never blocks (T3,
exit 0 always).
"""
import json
import sys

VAULT_MARKER = "iCloud~md~obsidian/Documents/Obsidian Vault"

MESSAGE = (
    "Vault note loaded. Consider: Are there [[wikilinks]] to follow? Tags to "
    "search? Related notes via /vault-connect? Orphaned or poorly linked? "
    "Try /vault-align to check health."
)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("filePath") or ""
    if not path or VAULT_MARKER not in path or not path.endswith(".md"):
        return

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": MESSAGE,
        }
    }))


if __name__ == "__main__":
    main()
    sys.exit(0)
