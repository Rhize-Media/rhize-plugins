#!/usr/bin/env python3
"""harvest_headroom.py — turn a captured `headroom learn` report into refinement-queue entries.

Replaces the prose step in `commands/learn-harvest.md` that used to say "parse each
recommendation/pattern block into one queue entry". Left to a model, that step produced
entries whose `pattern` was cut at exactly 550 characters mid-word (seven of them on
2026-08-26), which lost the actionable half of each finding. This script stores every
pattern verbatim and never truncates.

Input format (what `headroom learn --dry-run` prints and the harvest step captures to
`~/.claude/context-manager/harvest-logs/<date>-headroom.txt`):

    ### <title>
    *~12,345 tokens/session saved*        (optional)
    <body lines, usually indented>
    ...
    ────────────────────────────          (section separator, optional)

`##`/`###`/`####` headings, separator rules, and blank lines end a block. A block with no
body is ignored.

Queue entry shape (matches `commands/learn-harvest.md` exactly):

    {"id": sha1-12(source + pattern), "ts": ISO8601, "source": "headroom-learn",
     "repo": <--repo>, "pattern": "<title> — <savings> <body>", "est_savings": int|None,
     "target_skill": None, "status": "pending", "harvest_log": "<capture file name>"}

Usage:
    harvest_headroom.py CAPTURE --queue PATH --repo NAME [--dry-run] [--json]
    harvest_headroom.py --audit --queue PATH [--json]

`--audit` lists queue entries that look truncated (pattern exactly 550 characters, or
500+ characters ending without terminal punctuation) so a later review can recover them
from the harvest log the way the 2026-08-26 entries were.

Exit codes: 0 on success (including "nothing new"), 2 on an unreadable input.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SOURCE = "headroom-learn"
HEADING = re.compile(r"^\s*(#{2,4})\s+(.*\S)\s*$")
SAVINGS = re.compile(r"^\*~?([\d,]+)\s+tokens/session saved\*$")
SEPARATOR = re.compile(r"^\s*─{4,}\s*$")
TRUNCATED_LEN = 550
SUSPECT_MIN_LEN = 500
TERMINAL = ".!?)`\"'*]"


def parse_capture(text: str) -> list[dict]:
    """Return [{title, savings, body}] for every `###`/`####` block with a body."""
    blocks: list[dict] = []
    cur: dict | None = None

    def flush() -> None:
        if cur and cur["body"]:
            blocks.append(
                {
                    "title": cur["title"],
                    "savings": cur["savings"],
                    "body": " ".join(cur["body"]),
                }
            )

    for raw in text.splitlines():
        line = raw.strip()
        m = HEADING.match(line)
        if m:
            flush()
            level, title = m.group(1), m.group(2)
            cur = {"title": title, "savings": None, "body": []} if len(level) >= 3 else None
            continue
        if SEPARATOR.match(line):
            flush()
            cur = None
            continue
        if cur is None or not line:
            continue
        s = SAVINGS.match(line)
        if s and cur["savings"] is None and not cur["body"]:
            cur["savings"] = int(s.group(1).replace(",", ""))
            continue
        cur["body"].append(line)
    flush()
    return blocks


def pattern_text(block: dict) -> str:
    savings = f"*~{block['savings']:,} tokens/session saved* " if block["savings"] is not None else ""
    return f"{block['title']} — {savings}{block['body']}"


def entry_id(pattern: str) -> str:
    return hashlib.sha1((SOURCE + pattern).encode("utf-8")).hexdigest()[:12]


def load_queue(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"error: {path}:{n} is not valid JSON ({exc})")
    return rows


def append_entries(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())


def looks_truncated(pattern: str) -> str | None:
    if len(pattern) == TRUNCATED_LEN:
        return f"exactly {TRUNCATED_LEN} characters (the 2026-08-26 collector cut)"
    if len(pattern) >= SUSPECT_MIN_LEN and pattern.rstrip()[-1:] not in TERMINAL:
        return "long pattern ending without terminal punctuation"
    return None


def cmd_audit(queue: Path, as_json: bool) -> int:
    rows = load_queue(queue)
    hits = []
    for r in rows:
        if r.get("status") != "pending":
            continue
        why = looks_truncated(str(r.get("pattern", "")))
        if why:
            hits.append({"id": r.get("id"), "ts": r.get("ts"), "len": len(r.get("pattern", "")), "why": why})
    if as_json:
        print(json.dumps({"queue": str(queue), "pending_checked": sum(r.get("status") == "pending" for r in rows), "suspect": hits}, indent=1))
    else:
        print(f"harvest audit — {len(hits)} suspect pending entr{'y' if len(hits)==1 else 'ies'} in {queue}")
        for h in hits:
            print(f"  {h['id']}  len={h['len']:>5}  {h['why']}")
    return 0


def cmd_ingest(capture: Path, queue: Path, repo: str, dry_run: bool, as_json: bool) -> int:
    try:
        text = capture.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"error: cannot read {capture}: {exc}", file=sys.stderr)
        return 2
    blocks = parse_capture(text)
    queue_rows = load_queue(queue)
    existing_ids = {r.get("id") for r in queue_rows}
    existing_patterns = {r.get("pattern") for r in queue_rows}
    # A row restored from a harvest log keeps the id of its truncated original, so neither
    # its id nor its text matches a fresh parse of the same block; its title does.
    restored_titles = {
        str(r.get("pattern", "")).split(" — ")[0]
        for r in queue_rows
        if r.get("pattern_restored_from")
    }
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new: list[dict] = []
    skipped = 0
    for b in blocks:
        pattern = pattern_text(b)
        eid = entry_id(pattern)
        if eid in existing_ids or pattern in existing_patterns or b["title"].split(" — ")[0] in restored_titles:
            skipped += 1
            continue
        existing_ids.add(eid)
        existing_patterns.add(pattern)
        new.append(
            {
                "id": eid,
                "ts": now,
                "source": SOURCE,
                "repo": repo,
                "pattern": pattern,
                "est_savings": b["savings"],
                "target_skill": None,
                "status": "pending",
                "harvest_log": capture.name,
            }
        )
    if not dry_run and new:
        append_entries(queue, new)
    summary = {
        "capture": str(capture),
        "queue": str(queue),
        "blocks": len(blocks),
        "appended": 0 if dry_run else len(new),
        "would_append": len(new) if dry_run else 0,
        "duplicates_skipped": skipped,
        "longest_pattern": max((len(e["pattern"]) for e in new), default=0),
        "ids": [e["id"] for e in new],
    }
    if as_json:
        print(json.dumps(summary, indent=1))
    else:
        verb = "would append" if dry_run else "appended"
        print(f"harvest_headroom — {len(blocks)} block(s) in {capture.name}; {verb} {len(new)}, skipped {skipped} duplicate(s); longest pattern {summary['longest_pattern']} chars")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("capture", nargs="?", help="captured `headroom learn` report (text)")
    ap.add_argument("--queue", default=str(Path.home() / ".claude" / "context-manager" / "refinement-queue.jsonl"))
    ap.add_argument("--repo", default="global", help="repo label stored on each entry")
    ap.add_argument("--dry-run", action="store_true", help="parse and report; write nothing")
    ap.add_argument("--audit", action="store_true", help="list pending entries that look truncated")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    queue = Path(args.queue).expanduser()
    if args.audit:
        return cmd_audit(queue, args.json)
    if not args.capture:
        ap.error("CAPTURE is required unless --audit is given")
    return cmd_ingest(Path(args.capture).expanduser(), queue, args.repo, args.dry_run, args.json)


if __name__ == "__main__":
    sys.exit(main())
