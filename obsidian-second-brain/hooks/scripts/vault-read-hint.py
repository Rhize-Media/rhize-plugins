#!/usr/bin/env python3
"""PostToolUse advisory hint for the obsidian-second-brain plugin.

Matcher: Read (set in hooks.json). Same $TOOL_INPUT bug as
vault-write-hint.py -- see that file's docstring.

Fast path: exits silently (no output, exit 0) unless the file just read is a
.md file inside the Obsidian vault path. Advisory only -- never blocks (T3,
exit 0 always).

Vault path resolution (env var -> Obsidian's registered vaults -> iCloud
default) lives in the sibling vault_resolve.py module, shared with
vault-write-hint.py -- see that module's docstring for the resolution order.
"""
import json
import sys
from pathlib import Path

# Legacy fallback marker, used only if the shared helper module fails to
# import (e.g. a broken plugin install) -- keeps this hook from going silent.
ICLOUD_VAULT_MARKER = "iCloud~md~obsidian/Documents/Obsidian Vault"

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
    if not path or not path.endswith(".md"):
        return

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from vault_resolve import is_vault_path
        in_vault = is_vault_path(path)
    except Exception:
        in_vault = ICLOUD_VAULT_MARKER in path

    if not in_vault:
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
