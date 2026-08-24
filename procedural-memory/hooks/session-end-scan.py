#!/usr/bin/env python3
"""session-end-scan.py — Stop hook.

The heavier half of the two-tier hook design (see
post-bash-candidate-queue.sh for the cheap half). Runs on the Stop event:
looks for candidate-queue entries this session left `pending`, cross-checks
each against the transcript to confirm it really is a completed, non-error
tool call, and prints an advisory naming what passed its test/build command
this session — never claims anything is "verified" (that word is reserved
for `rhize-skill verify` / `/procedural-memory:verify`, the only thing that
ever sets a real `health=ok`).

FAST-EXIT FIRST: Stop fires after every completed assistant turn, not once
per session (same discipline as rhize-context-manager's
refinement-pipeline__session-end.sh) — most Stops in most sessions never
touched a test/build command. Reads the queue and checks for this session's
pending entries via plain string search BEFORE opening or parsing the
(potentially large) transcript JSONL. If nothing is pending for this
session_id, exit immediately.

QUEUE FILE: see post-bash-candidate-queue.sh's header for why this is the
plugin's own file, not rhize-context-manager's refinement-queue.jsonl.

STATUS LIFECYCLE: pending -> surfaced (confirmed non-error, reported to the
user) | pending -> stale (candidate's tool_use_id not found in the
transcript at all — never touched again automatically). Rewritten
atomically via temp-file + os.replace, matching the append tier's use of a
single write(2) rather than in-place edits — a torn rewrite here would be
exactly the "queue that silently drops candidates" failure this project
keeps hitting.

Always exits 0 — advisory only, never blocks Stop.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile


def default_queue_path() -> str:
    override = os.environ.get("PROCEDURAL_MEMORY_CANDIDATE_QUEUE")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "procedural-memory", "candidate-queue.jsonl")


def read_queue(path: str) -> list[dict]:
    entries = []
    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    # A malformed line (e.g. the Tier-1 hook's documented
                    # quote-escaping edge case) is skipped, never fatal —
                    # see post-bash-candidate-queue.sh's EXTRACTION CAVEAT.
                    continue
    except FileNotFoundError:
        return []
    return entries


def write_queue_atomic(path: str, entries: list[dict]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".candidate-queue-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def scan_transcript(transcript_path: str, wanted_tool_use_ids: set[str]) -> tuple[dict[str, bool], set[str]]:
    """Returns (tool_use_id -> is_error, set of Write/Edit file paths touched
    this session) by reading the transcript once. Only bothers building the
    is_error map for ids we actually care about (the pending candidates'
    tool_use_ids) — cheap even on a long transcript.
    """
    is_error_by_id: dict[str, bool] = {}
    files_touched: set[str] = set()

    try:
        with open(transcript_path, "r", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue

                message = record.get("message") or {}
                content = message.get("content")
                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type")

                    if block_type == "tool_use" and block.get("name") in ("Write", "Edit", "MultiEdit"):
                        path = (block.get("input") or {}).get("file_path")
                        if path:
                            files_touched.add(path)

                    if block_type == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id and tool_use_id in wanted_tool_use_ids:
                            is_error_by_id[tool_use_id] = bool(block.get("is_error"))
    except FileNotFoundError:
        pass

    return is_error_by_id, files_touched


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session_id = payload.get("session_id")
    transcript_path = payload.get("transcript_path")
    if not session_id or not transcript_path:
        sys.exit(0)

    queue_path = default_queue_path()
    entries = read_queue(queue_path)
    if not entries:
        sys.exit(0)

    pending_this_session = [
        e for e in entries
        if e.get("status") == "pending" and e.get("session_id") == session_id
    ]
    if not pending_this_session:
        sys.exit(0)  # fast exit — nothing to scan the transcript for

    wanted_ids = {e.get("id") for e in pending_this_session if e.get("id")}
    is_error_by_id, files_touched = scan_transcript(transcript_path, wanted_ids)

    surfaced = []
    changed = False
    for entry in entries:
        if entry.get("status") != "pending" or entry.get("session_id") != session_id:
            continue
        entry_id = entry.get("id")
        if entry_id not in is_error_by_id:
            # Tool call not found in the transcript at all — leave pending
            # rather than guessing; a future Stop (same session_id resuming,
            # or the transcript catching up) can still resolve it.
            continue
        changed = True
        if is_error_by_id[entry_id]:
            # Shouldn't happen (Tier 1 only fires on success — see its
            # header), but defensive: don't surface something the
            # transcript itself says errored.
            entry["status"] = "rejected"
        else:
            entry["status"] = "surfaced"
            surfaced.append(entry)

    if changed:
        write_queue_atomic(queue_path, entries)

    if not surfaced:
        sys.exit(0)

    bar = "━" * 57
    print(bar)
    print("\U0001F4E6 Procedural-memory promotion candidates this session")
    print(bar)
    print()
    print("These passed their test/build command this session (not the same as")
    print("registry-verified — that only happens via /procedural-memory:verify):")
    print()
    for entry in surfaced:
        print("  • %s (%s)" % (entry.get("command", "?"), entry.get("pattern", "?")))
    if files_touched:
        print()
        print("Files written/edited this session:")
        for path in sorted(files_touched):
            print("  • %s" % path)
    print()
    print("Worth capturing into the procedural-memory registry? Stage it and run:")
    print("  /procedural-memory:promote <path-under-registry>")
    print()
    print(bar)


if __name__ == "__main__":
    main()
    sys.exit(0)
