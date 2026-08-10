#!/usr/bin/env python3
"""mine_failure_corpus.py — Eval 4 instrument: harvests failing Bash outputs
from local session transcripts for remediation-pattern precision/recall.

Per docs/superpowers/specs/2026-08-10-skill-graph-evals-design.md, eval #4:
"corpus curation is manual once. Failing Bash outputs are harvested from local
transcripts (machine-local dataset, same privacy rule), labeled with
correct-fixer/no-fixer." This script does the harvesting + provisional
auto-labeling; a human does the "correct-fixer/no-fixer" pass afterward by
editing the `label` field directly in the output file.

TRANSCRIPT SHAPE (verified against real ~/.claude/projects/*/*.jsonl on this
machine 2026-08-10): a Bash tool_use is
`{"type":"tool_use","name":"Bash","id":<id>,"input":{"command":...}}` inside an
assistant message; its result is a later `{"type":"user","message":{"content":
[{"type":"tool_result","tool_use_id":<id>,"content":<str>,"is_error":<bool>}]}}`
entry (`content` is sometimes a list of text blocks instead of a plain string;
both are handled). `is_error: true` is the failure ground-truth signal used
here — note this is a transcript-only field: the LIVE PostToolUse hook payload
that remediation-suggester.js actually receives carries no such field (see
that file's FAILURE DETECTION comment), which is exactly why the hook instead
regex-matches known failure text. `is_error: true` entries whose content is a
user tool-use rejection ("The user doesn't want to proceed...") are excluded —
that's a human declining the tool, not a command failure.

SNIPPET LENGTH: remediation-suggester.js matches its condition patterns
against the FULL, untruncated `${stdout}\n${stderr}` text (no truncation in
the hook itself). This miner still caps stored snippets at SNIPPET_MAX_CHARS
purely to keep the (gitignored, machine-local) corpus file a sane size — this
truncation is a corpus-storage choice, not a replication of hook behavior; the
eval script re-derives failure snippets with the same cap so scoring stays
consistent with what's stored.

AUTO-LABELING: catalog/tags.json's condition patterns are compiled exactly as
remediation-suggester.js compiles them (see `compile_pattern` below, mirroring
that file's `compilePattern`). A corpus entry gets a provisional
`"auto:<slug>"` label when EXACTLY ONE condition's patterns match the snippet
(unambiguous); zero or multiple matches leave `label: ""` for manual review.
"""
from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEXES_PATH = REPO_ROOT / "generated" / "skill-map.indexes.json"
PROJECTS_GLOB = os.path.expanduser("~/.claude/projects/*/*.jsonl")
OUT_PATH = Path(__file__).resolve().parent / "data" / "failure-corpus.jsonl"

SNIPPET_MAX_CHARS = 2000
REJECTION_PREFIX = "The user doesn't want to proceed"


def compile_pattern(source):
    """Mirrors remediation-suggester.js's compilePattern(): catalog patterns
    are Python `re` syntax with an optional leading `(?i)` inline flag, which
    JS RegExp can't parse natively (the hook strips it and maps to the 'i'
    flag). Python's `re` handles `(?i)` natively, so no stripping is needed
    here — this function exists to make the mirroring explicit and to fail
    the same way (skip a malformed pattern) rather than raising.
    """
    try:
        return re.compile(source)
    except re.error:
        return None


def load_conditions():
    doc = json.loads(INDEXES_PATH.read_text())
    remediation = doc.get("remediation", {})
    conditions = []
    for slug, entry in remediation.items():
        patterns = [compile_pattern(p) for p in entry.get("patterns", [])]
        patterns = [p for p in patterns if p is not None]
        conditions.append((slug, patterns))
    return conditions


def auto_label(snippet, conditions):
    matched_slugs = [slug for slug, patterns in conditions if any(p.search(snippet) for p in patterns)]
    if len(matched_slugs) == 1:
        return f"auto:{matched_slugs[0]}"
    return ""


def extract_result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def mine_file(path, conditions):
    try:
        with open(path, "r", errors="ignore") as fh:
            raw_lines = fh.readlines()
    except OSError:
        return []

    lines = []
    for raw in raw_lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            lines.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    if not lines:
        return []

    session_id = next((l["sessionId"] for l in lines if isinstance(l.get("sessionId"), str)), None)

    bash_commands = {}  # tool_use_id -> command string
    for entry in lines:
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash":
                bash_commands[block.get("id")] = (block.get("input") or {}).get("command", "")

    if not bash_commands:
        return []

    rows = []
    for entry in lines:
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                continue
            tool_use_id = block.get("tool_use_id")
            if tool_use_id not in bash_commands:
                continue
            if block.get("is_error") is not True:
                continue  # only mining genuine failures
            text = extract_result_text(block.get("content"))
            if not text or text.startswith(REJECTION_PREFIX):
                continue  # a human declining the tool call is not a command failure
            snippet = text[:SNIPPET_MAX_CHARS]
            rows.append(
                {
                    "snippet": snippet,
                    "command": bash_commands[tool_use_id][:500],
                    "label": auto_label(snippet, conditions),
                    "session_id": session_id,
                    "ts": entry.get("timestamp"),
                }
            )
    return rows


def main():
    if not INDEXES_PATH.exists():
        print(f"error: {INDEXES_PATH} not found — run scripts/build_skill_map.py first")
        return

    conditions = load_conditions()
    files = sorted(glob.glob(PROJECTS_GLOB))

    all_rows = []
    for f in files:
        all_rows.extend(mine_file(f, conditions))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as out:
        for row in all_rows:
            out.write(json.dumps(row) + "\n")

    n_auto = sum(1 for r in all_rows if r["label"].startswith("auto:"))
    n_unlabeled = sum(1 for r in all_rows if not r["label"])
    print(f"scanned {len(files)} session transcripts")
    print(f"failing Bash outputs harvested: {len(all_rows)}")
    print(f"  auto-labeled (exactly 1 condition matched): {n_auto}")
    print(f"  unlabeled (0 or >1 condition matched, needs manual review): {n_unlabeled}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
