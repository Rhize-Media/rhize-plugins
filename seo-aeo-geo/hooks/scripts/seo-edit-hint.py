#!/usr/bin/env python3
"""PreToolUse advisory hint for the seo-aeo-geo plugin.

Matcher: Write|Edit (set in hooks.json). Claude Code pipes the tool-call
payload as JSON on stdin -- {"tool_name": ..., "tool_input": {...}, ...} --
NOT via a $TOOL_INPUT environment variable. The previous version of this hook
read $TOOL_INPUT (always unset), so json.load(sys.stdin) on stdin was in fact
what it should have parsed all along; the bug was in wiring, not intent. This
version reads real stdin and looks under tool_input for file_path.

Fast path: exits silently (no output, exit 0) unless the target file matches
an SEO-related pattern. Advisory only -- never blocks (T3, exit 0 always).
"""
import json
import sys

SEO_PATH_PATTERNS = (
    "metadata", "meta", "sitemap", "robots", "json-ld", "jsonld",
    "structured-data", "schema-markup", "seo",
)
SEO_FILENAMES = ("sitemap.xml", "sitemap.ts", "robots.txt", "robots.ts")

MESSAGE = (
    "SEO-related file detected. Consider: Does this follow structured data "
    "best practices? Use /content-optimize or /code-seo-review to validate."
)


def is_seo_path(path: str) -> bool:
    path_lower = path.lower()
    filename = path_lower.rsplit("/", 1)[-1]
    if any(p in path_lower for p in SEO_PATH_PATTERNS):
        return True
    return any(
        filename == f or filename.startswith(f.split(".")[0]) for f in SEO_FILENAMES
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("filePath") or ""
    if not path or not is_seo_path(path):
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
