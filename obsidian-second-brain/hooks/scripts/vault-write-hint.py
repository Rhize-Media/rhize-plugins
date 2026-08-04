#!/usr/bin/env python3
"""PreToolUse advisory hint for the obsidian-second-brain plugin.

Matcher: Write|Edit (set in hooks.json). Claude Code pipes the tool-call
payload as JSON on stdin -- {"tool_name": ..., "tool_input": {...}, ...} --
NOT via a $TOOL_INPUT environment variable, which the previous version of
this hook read (always unset, so it was silently a no-op on every call).

Fast path: exits silently (no output, exit 0) unless the target file is a
.md file inside the Obsidian vault path. Advisory only -- never blocks (T3,
exit 0 always).
"""
import json
import sys

VAULT_MARKER = "iCloud~md~obsidian/Documents/Obsidian Vault"

MESSAGE = (
    "Writing to Obsidian vault. Use [[wikilinks]] for internal links, not "
    "[text](path). Use callout syntax (> [!type]) for admonitions. Preserve "
    "existing frontmatter YAML. Add relevant #tags and ensure tags: array in "
    "frontmatter. Link to parent MOC where applicable."
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
            "hookEventName": "PreToolUse",
            "additionalContext": MESSAGE,
        }
    }))


if __name__ == "__main__":
    main()
    sys.exit(0)
