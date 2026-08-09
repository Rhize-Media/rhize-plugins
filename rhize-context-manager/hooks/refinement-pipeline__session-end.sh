#!/usr/bin/python3
#
# session-end.sh - Prompt for refinements after significant sessions
#
# This hook runs on the Stop event and prompts the user to capture any skill
# refinements if the session was substantial.
#
# BUG FIXED (2026-08-04): the previous version read SESSION_TOOL_CALLS /
# SESSION_ERRORS / SESSION_DURATION / SESSION_FILES_TOUCHED from the
# environment, commented "set by Claude Code" -- Claude Code does not set
# those. It delivers a Stop-hook payload as JSON on stdin containing
# session_id/transcript_path/cwd, same as every other hook event. Those four
# env vars were always unset, so SHOULD_PROMPT was always false and this
# hook never fired. This version computes the same four stats itself by
# reading the transcript JSONL Claude Code already points to.
#
# Thresholds for prompting:
#   - > 20 tool calls
#   - > 0 tool-result errors
#   - > 1 hour session duration (first to last transcript timestamp)
#   - > 10 distinct files touched (Write/Edit/MultiEdit file_path args)
#
# Installation:
#   Wire into .claude/settings.json as a Stop hook (see this plugin's
#   README.md Hooks section for the exact command path/entry — this file
#   moved here from rhize-devflow/hooks/ on 2026-08-09).
#
# Note (updated 2026-08-09): skill refinement is now the gated pipeline in the
# `refinement-pipeline` skill (this plugin) — signals go through
# `/rhize-context-manager:learn-harvest` (collect) and `/skill-refine`
# (triage/run), which drives `@rhize/skill-forge evolve` under a safety re-gate.
# A bare `npx @rhize/skill-forge refine` skips that queue and re-gate.
#
# Always exits 0 -- advisory only, never blocks Stop.

import json
import sys
from datetime import datetime

TOOL_THRESHOLD = 20
ERROR_THRESHOLD = 0
DURATION_THRESHOLD_SEC = 3600
FILES_THRESHOLD = 10

WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


def parse_ts(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def gather_stats(transcript_path):
    tool_calls = 0
    errors = 0
    files_touched = set()
    timestamps = []

    with open(transcript_path, "r", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue

            ts = parse_ts(record.get("timestamp", ""))
            if ts:
                timestamps.append(ts)

            content = ((record.get("message") or {}).get("content"))
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    tool_calls += 1
                    name = block.get("name")
                    path = (block.get("input") or {}).get("file_path")
                    if name in WRITE_TOOLS and path:
                        files_touched.add(path)
                if block.get("type") == "tool_result" and block.get("is_error"):
                    errors += 1

    duration_sec = 0
    if len(timestamps) >= 2:
        duration_sec = int((max(timestamps) - min(timestamps)).total_seconds())

    return tool_calls, errors, len(files_touched), duration_sec


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        sys.exit(0)

    try:
        tool_calls, errors, files_touched, duration_sec = gather_stats(transcript_path)
    except Exception:
        sys.exit(0)

    reasons = []
    if tool_calls > TOOL_THRESHOLD:
        reasons.append("  • %d tool calls (threshold: %d)" % (tool_calls, TOOL_THRESHOLD))
    if errors > ERROR_THRESHOLD:
        reasons.append("  • %d errors encountered" % errors)
    if duration_sec > DURATION_THRESHOLD_SEC:
        reasons.append("  • %d minute session (threshold: 60)" % (duration_sec // 60))
    if files_touched > FILES_THRESHOLD:
        reasons.append("  • %d files modified (threshold: %d)" % (files_touched, FILES_THRESHOLD))

    if not reasons:
        sys.exit(0)

    bar = "━" * 57
    print(bar)
    print("\U0001F4DD Session Complete")
    print(bar)
    print()
    print("This was a substantial session:")
    print("\n".join(reasons))
    print()
    print("\U0001F4CA Session Stats:")
    print("  • Tool calls: %d" % tool_calls)
    print("  • Errors: %d" % errors)
    print("  • Files touched: %d" % files_touched)
    print("  • Duration: %d minutes" % (duration_sec // 60))
    print()
    print("Any skill refinements to capture from this session?")
    print("  → Run: /rhize-context-manager:learn-harvest, then /skill-refine review")
    print("  → Or say \"no refinements\" to skip")
    print()
    print(bar)


if __name__ == "__main__":
    main()
    sys.exit(0)
