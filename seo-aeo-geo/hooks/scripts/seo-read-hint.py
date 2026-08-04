#!/usr/bin/env python3
"""PostToolUse advisory hint for the seo-aeo-geo plugin.

Matcher: Read (set in hooks.json). Same $TOOL_INPUT bug as seo-edit-hint.py --
see that file's docstring. Reads the real PostToolUse payload from stdin and
looks under tool_input for file_path.

Fast path: exits silently (no output, exit 0) unless the file just read
matches an SEO-related pattern. Advisory only -- never blocks (T3, exit 0
always).
"""
import json
import sys

SEO_PATH_SEGMENTS = (
    "metadata", "meta", "sitemap", "robots", "json-ld", "jsonld",
    "structured-data", "schema-markup", "seo",
)
SEO_FILENAMES = ("head.tsx", "head.jsx", "layout.tsx", "layout.jsx")

MESSAGE = (
    "SEO file loaded. Use /code-seo-review to check for issues, or "
    "/content-optimize for on-page improvements."
)


def is_seo_path(path: str) -> bool:
    path_lower = path.lower()
    filename = path_lower.rsplit("/", 1)[-1]
    if any(p in path_lower for p in SEO_PATH_SEGMENTS):
        return True
    return filename in SEO_FILENAMES


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
            "hookEventName": "PostToolUse",
            "additionalContext": MESSAGE,
        }
    }))


if __name__ == "__main__":
    main()
    sys.exit(0)
