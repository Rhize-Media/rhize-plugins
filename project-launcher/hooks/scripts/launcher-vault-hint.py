#!/usr/bin/env python3
"""PreToolUse advisory hint for the project-launcher plugin.

Matcher: Write|Edit (set in hooks.json). Claude Code pipes the tool-call
payload as JSON on stdin -- {"tool_name": ..., "tool_input": {...}, ...} --
NOT via a $TOOL_INPUT environment variable, which the previous version of
this hook read (always unset, so it was silently a no-op on every call).

Fast path: exits silently (no output, exit 0) unless BOTH (a) the file looks
like a launcher artifact (PRD, requirements, research, etc.) and (b) an
Obsidian vault is present on disk. Advisory only -- never blocks (T3, exit 0
always).
"""
import json
import os
import sys

LAUNCHER_PATTERNS = (
    "prd", "requirements", "research", "context", "gap-analysis",
    "interview", "discovery", "roadmap", "project.md", "requirements.md",
)
CONTENT_HEADING_PATTERNS = (
    "## prd", "## requirements", "## research",
    "# product requirements", "## project overview",
)
VAULT_PATH = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault"
)

MESSAGE = (
    "Launcher artifact detected and Obsidian vault found. Also save this to "
    "the vault using second-brain methodology: [[wikilinks]] to related "
    "projects, #tags in frontmatter, and place under the appropriate "
    "Projects/ folder with MOC links."
)


def is_launcher_artifact(path: str, content: str) -> bool:
    path_lower = path.lower()
    if any(p in path_lower for p in LAUNCHER_PATTERNS):
        return True
    content_head = content[:200].lower()
    return any(p in content_head for p in CONTENT_HEADING_PATTERNS)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("filePath") or ""
    content = tool_input.get("content") or tool_input.get("new_string") or ""
    if not path:
        return

    if not is_launcher_artifact(path, content):
        return
    if not os.path.isdir(VAULT_PATH):
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
