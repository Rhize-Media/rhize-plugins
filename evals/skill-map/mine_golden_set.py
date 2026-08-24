#!/usr/bin/env python3
"""mine_golden_set.py — Eval 1 instrument: mines a golden routing set from local
Claude Code session transcripts (~/.claude/projects/*/*.jsonl).

Per docs/superpowers/specs/2026-08-10-skill-graph-evals-design.md ("Golden routing
set"): a user prompt followed within the same session by a Skill invocation is a
positive example (label = the invoked skill's map node id); prompts with no
subsequent skill use are sampled as negatives (label = null).

HARD CONSTRAINTS (both load-bearing, per spec):
  - Output is gitignored (evals/skill-map/data/) — prompts are raw user text.
  - Contamination guard: the map router went live 2026-08-09. Only sessions whose
    start timestamp is strictly BEFORE that date are mined, so the router is never
    graded on ground truth it helped create.

TRANSCRIPT SHAPE (verified against real ~/.claude/projects/*/*.jsonl on this
machine 2026-08-10): each line is a JSON object. A human prompt is a
`{"type": "user", "message": {"role": "user", "content": <str> | <list>}}` entry
whose content is either a plain string, or a list of blocks none of which is a
`tool_result` (a tool_result-carrying "user" entry is a tool reply, not a human
prompt). A Skill invocation is an assistant entry with
`message.content[].{type: "tool_use", name: "Skill", input: {skill: "<name>"}}`.
Entries chain via `parentUuid`; to find the prompt that led to a Skill call, walk
parentUuid ancestors until the first entry that is a plain-text user prompt.
Session start timestamp is taken as the minimum `timestamp` field across all
lines in the file (some early lines, e.g. `queue-operation`/`attachment`, carry a
timestamp before the first `type: "user"` line).

Skill invocations in `input.skill` come in two shapes: "plugin:name" (unambiguous)
or a bare "name" (e.g. "simplify") when invoked without a plugin prefix. Per spec
("drop invocations that don't resolve to first-party map skills"), only
invocations that resolve — via the plugin-qualified id, or an unambiguous bare
name — to a `skill:<plugin>/<name>` node in generated/skill-map.static.json are
kept as positives; everything else (including the many invocations of skills this
repo's map does not track, e.g. user-level `~/.claude/skills/*`) is dropped.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_MAP_PATH = REPO_ROOT / "generated" / "skill-map.static.json"
PROJECTS_GLOB = os.path.expanduser("~/.claude/projects/*/*.jsonl")
OUT_PATH = Path(__file__).resolve().parent / "data" / "golden-routing.jsonl"

# The map router (rhize-context-manager/hooks/skill-router.js) went live on this
# date — mining is restricted to sessions that started strictly before it.
CUTOFF = datetime(2026, 8, 9, tzinfo=timezone.utc)

# Deterministic 1-in-20 sample of no-skill prompts as negatives, matching the
# suggestion log's stated sampling rate for the same purpose (spec: "a
# deterministic 1-in-20 sample of no-suggestion prompts").
NEG_SAMPLE_MOD = 20


def load_skill_ids():
    doc = json.loads(STATIC_MAP_PATH.read_text())
    by_qualified = {}
    by_bare = {}
    for node in doc.get("nodes", []):
        if node.get("kind") != "skill":
            continue
        m = re.match(r"^skill:([^/]+)/(.+)$", node.get("id", ""))
        if not m:
            continue
        plugin, name = m.groups()
        by_qualified[(plugin, name)] = node["id"]
        by_bare.setdefault(name, set()).add(node["id"])
    return by_qualified, by_bare


def resolve_skill_id(invoked, by_qualified, by_bare):
    if not isinstance(invoked, str) or not invoked:
        return None
    if ":" in invoked:
        plugin, name = invoked.split(":", 1)
        return by_qualified.get((plugin, name))
    ids = by_bare.get(invoked)
    if ids and len(ids) == 1:
        return next(iter(ids))
    return None  # bare name absent or ambiguous — drop per spec


def parse_ts(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_text_prompt(entry):
    """Return the human-authored prompt text if `entry` is a plain-text user
    turn (not a tool_result reply), else None."""
    if entry.get("type") != "user":
        return None
    msg = entry.get("message")
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return None
    content = msg.get("content")
    if isinstance(content, str):
        text = content.strip()
        return text or None
    if isinstance(content, list):
        if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
            return None  # a tool reply, not a human prompt
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        text = "\n".join(t for t in texts if t).strip()
        return text or None
    return None


def find_prompt_ancestor(entry, by_uuid, max_depth=40):
    cur = entry
    depth = 0
    while depth < max_depth:
        parent_uuid = cur.get("parentUuid")
        if not parent_uuid:
            return None
        cur = by_uuid.get(parent_uuid)
        if cur is None:
            return None
        text = extract_text_prompt(cur)
        if text is not None:
            return cur.get("uuid"), text
        depth += 1
    return None


def mine_file(path, by_qualified, by_bare):
    try:
        with open(path, "r", errors="ignore") as fh:
            raw_lines = fh.readlines()
    except OSError:
        return [], []

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
        return [], []

    timestamps = [t for t in (parse_ts(l.get("timestamp")) for l in lines) if t is not None]
    if not timestamps:
        return [], []
    session_start = min(timestamps)
    if session_start >= CUTOFF:
        return [], []  # contamination guard: router went live 2026-08-09

    session_id = next((l["sessionId"] for l in lines if isinstance(l.get("sessionId"), str)), None)
    by_uuid = {l["uuid"]: l for l in lines if "uuid" in l}

    positive_uuids = set()
    positives = []
    for entry in lines:
        msg = entry.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill"):
                continue
            skill_input = block.get("input") or {}
            skill_id = resolve_skill_id(skill_input.get("skill"), by_qualified, by_bare)
            if not skill_id:
                continue
            ancestor = find_prompt_ancestor(entry, by_uuid)
            if not ancestor:
                continue
            prompt_uuid, prompt_text = ancestor
            if prompt_uuid in positive_uuids:
                continue  # same prompt already credited (e.g. two Skill calls off one prompt)
            positive_uuids.add(prompt_uuid)
            positives.append(
                {
                    "prompt": prompt_text,
                    "label": skill_id,
                    "session_id": session_id,
                    "ts": entry.get("timestamp"),
                }
            )

    negatives = []
    for entry in lines:
        if entry.get("type") != "user":
            continue
        uuid = entry.get("uuid")
        if uuid in positive_uuids:
            continue
        text = extract_text_prompt(entry)
        if not text:
            continue
        digest = hashlib.sha256(f"{session_id}:{uuid}".encode("utf-8")).hexdigest()
        if int(digest[:8], 16) % NEG_SAMPLE_MOD != 0:
            continue
        negatives.append(
            {
                "prompt": text,
                "label": None,
                "session_id": session_id,
                "ts": entry.get("timestamp"),
            }
        )

    return positives, negatives


def main():
    if not STATIC_MAP_PATH.exists():
        print(f"error: {STATIC_MAP_PATH} not found — run scripts/build_skill_map.py first", file=sys.stderr)
        sys.exit(1)

    by_qualified, by_bare = load_skill_ids()
    files = sorted(glob.glob(PROJECTS_GLOB))

    all_positives = []
    all_negatives = []
    scanned = 0
    skipped_after_cutoff = 0
    for f in files:
        pos, neg = mine_file(f, by_qualified, by_bare)
        scanned += 1
        if not pos and not neg:
            skipped_after_cutoff += 1
        all_positives.extend(pos)
        all_negatives.extend(neg)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as out:
        for row in all_positives + all_negatives:
            out.write(json.dumps(row) + "\n")

    print(f"scanned {scanned} session transcripts under {PROJECTS_GLOB}")
    print(f"cutoff: sessions must start before {CUTOFF.isoformat()}")
    print(f"positives: {len(all_positives)}")
    print(f"negatives (sampled 1-in-{NEG_SAMPLE_MOD}): {len(all_negatives)}")
    print(f"total golden examples: {len(all_positives) + len(all_negatives)}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
