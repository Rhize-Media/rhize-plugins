#!/usr/bin/env python3
"""baseline_upstreams.py — record/refresh the reviewed-upstream baseline hash.

Implements the "baseline" half of
docs/superpowers/specs/2026-08-10-three-way-drift-design.md: the deliberate,
human-triggered "I reviewed upstream, accept its state" action. It is NEVER
run by scripts/build_skill_map.py (the compiler stays offline and
deterministic) — only by a human (or this repo's audit routine, on request)
after actually reviewing an upstream change.

For every non-retired entry in a plugin's `skills/SOURCES.md` whose `Source`
field is an http(s) URL, this script:
  1. Fetches the upstream file.
  2. Computes its sha256 hex digest.
  3. Writes/updates the entry's
     `- **Upstream baseline:** sha256:<hex> (recorded YYYY-MM-DD)` bullet,
     inserted before the entry's `- **Notes:**` bullet (or appended at the
     end of the entry block if there is no Notes bullet).

Idempotent: if the freshly fetched hash already matches the recorded
baseline hash, the file is left byte-for-byte untouched (no date bump) — two
consecutive runs against an unchanged upstream produce no diff.

Non-URL (local marketplace-path) `Source` entries are skipped with a report
line — a local path is not a "reviewed upstream state" this script can
fetch and hash; that fork's drift stays whatever `upstream-unreachable`/
`local-missing` state build_skill_map.py already reports for it.

Usage:
  python3 scripts/baseline_upstreams.py
  python3 scripts/baseline_upstreams.py --skill context-fundamentals
  python3 scripts/baseline_upstreams.py --sources <path-to-SOURCES.md>

SECURITY: this script parses SOURCES.md with plain string/regex operations
only (reusing scripts/build_skill_map.py's parser) and never executes
anything read from it. The only network call is a plain HTTP(S) GET of each
entry's own recorded Source URL.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import build_skill_map as bsm  # noqa: E402

DEFAULT_SOURCES_PATH = REPO_ROOT / "rhize-context-manager" / "skills" / "SOURCES.md"
_BASELINE_LINE_RE = bsm._BASELINE_HASH_RE  # sha256:<hex> at start of the field value
FETCH_TIMEOUT_SECS = 20


class BaselineError(Exception):
    """Raised for conditions that should abort the whole run (bad --skill, etc)."""


def fetch_url(url: str) -> bytes:
    """Default fetcher: a plain HTTP(S) GET. Overridable by tests/callers."""
    request = urllib.request.Request(url, headers={"User-Agent": "rhize-plugins-baseline-upstreams"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECS) as response:  # noqa: S310
        return response.read()


def split_into_blocks(text: str) -> tuple[list[str], list[dict]]:
    """Split raw SOURCES.md text into line-indexed blocks.

    Returns (lines, blocks) where each block is
    {"skill_name", "retired", "fields", "start", "end"} — "start"/"end" are
    line indices into `lines` spanning the block's heading through (but not
    including) the next heading or EOF. This mirrors
    build_skill_map.parse_sources_md()'s field extraction but additionally
    keeps line-span bookkeeping so we can rewrite the file with a minimal,
    surgical diff instead of re-serializing the whole document.
    """
    lines = text.split("\n")
    blocks: list[dict] = []
    current: dict | None = None
    for i, line in enumerate(lines):
        heading = bsm._HEADING_RE.match(line)
        if heading:
            if current is not None:
                current["end"] = i
                blocks.append(current)
            current = {
                "skill_name": heading.group(1).strip(),
                "retired": False,
                "fields": {},
                "start": i,
            }
            continue
        if current is None:
            continue
        bullet = bsm._BULLET_RE.match(line.strip())
        if bullet:
            field, value = bullet.group(1).strip(), bullet.group(2).strip()
            if field.upper().startswith("RETIRED"):
                current["retired"] = True
            else:
                current["fields"][field] = value
    if current is not None:
        current["end"] = len(lines)
        blocks.append(current)
    return lines, blocks


def _find_bullet_line_index(lines: list[str], start: int, end: int, field: str) -> int | None:
    prefix = f"- **{field}:**"
    for i in range(start, end):
        if lines[i].strip().startswith(prefix):
            return i
    return None


def apply_baseline_update(
    lines: list[str], block: dict, new_hash: str, today: date
) -> tuple[list[str], bool]:
    """Insert/replace the block's '- **Upstream baseline:**' bullet.

    Returns (new_lines, changed). `changed` is False when the recorded
    baseline hash already equals `new_hash` (idempotent no-op — the date is
    NOT bumped just because the script ran again).
    """
    start, end = block["start"], block["end"]
    existing_value = block["fields"].get("Upstream baseline", "")
    existing_match = _BASELINE_LINE_RE.match(existing_value)
    if existing_match and existing_match.group(1) == new_hash:
        return lines, False

    new_line = f"- **Upstream baseline:** sha256:{new_hash} (recorded {today.isoformat()})"
    existing_idx = _find_bullet_line_index(lines, start, end, "Upstream baseline")
    if existing_idx is not None:
        new_lines = lines[:existing_idx] + [new_line] + lines[existing_idx + 1 :]
        return new_lines, True

    notes_idx = _find_bullet_line_index(lines, start, end, "Notes")
    if notes_idx is not None:
        new_lines = lines[:notes_idx] + [new_line] + lines[notes_idx:]
        return new_lines, True

    # No Notes bullet: append just before the block's trailing blank line(s)/
    # next heading, i.e. at the end of the block's own content.
    insert_at = end
    while insert_at > start and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    new_lines = lines[:insert_at] + [new_line] + lines[insert_at:]
    return new_lines, True


def run(sources_path: Path, skill_filter: str | None, fetcher=fetch_url) -> int:
    if not sources_path.is_file():
        print(f"FAIL: no SOURCES.md found at {sources_path}")
        return 1

    text = sources_path.read_text()
    lines, blocks = split_into_blocks(text)

    if skill_filter is not None:
        if not any(b["skill_name"] == skill_filter for b in blocks):
            print(f"FAIL: no SOURCES.md entry named {skill_filter!r} in {sources_path}")
            return 1

    today = date.today()
    updated = 0
    unchanged = 0
    skipped_non_url = []
    skipped_retired = []
    failed = []

    # Recompute blocks after each mutation since line offsets shift; iterate
    # by skill name (stable identity) rather than by stale index.
    remaining_names = [
        b["skill_name"]
        for b in blocks
        if not b["retired"] and (skill_filter is None or b["skill_name"] == skill_filter)
    ]

    for skill_name in remaining_names:
        _, blocks = split_into_blocks("\n".join(lines))
        block = next(b for b in blocks if b["skill_name"] == skill_name)
        if block["retired"]:
            skipped_retired.append(skill_name)
            continue
        source_value = block["fields"].get("Source", "")
        if not bsm._URL_SCHEME_RE.match(source_value):
            skipped_non_url.append(skill_name)
            continue
        try:
            body = fetcher(source_value)
        except (urllib.error.URLError, OSError) as exc:
            failed.append((skill_name, str(exc)))
            continue
        new_hash = hashlib.sha256(body).hexdigest()
        lines, changed = apply_baseline_update(lines, block, new_hash, today)
        if changed:
            updated += 1
        else:
            unchanged += 1

    sources_path.write_text("\n".join(lines))

    try:
        display_path = sources_path.relative_to(REPO_ROOT)
    except ValueError:
        display_path = sources_path
    print(f"Baselined against {display_path}:")
    print(f"  updated:   {updated}")
    print(f"  unchanged: {unchanged} (baseline already matches upstream)")
    if skipped_non_url:
        print(f"  skipped (non-URL Source, cannot baseline): {', '.join(skipped_non_url)}")
    if skipped_retired:
        print(f"  skipped (retired): {', '.join(skipped_retired)}")
    if failed:
        print("  FAILED to fetch:")
        for name, err in failed:
            print(f"    {name}: {err}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", default=None, help="Only baseline this SOURCES.md entry.")
    parser.add_argument(
        "--sources",
        type=Path,
        default=DEFAULT_SOURCES_PATH,
        help="Path to the SOURCES.md file to baseline (default: rhize-context-manager's).",
    )
    args = parser.parse_args(argv)
    return run(args.sources, args.skill)


if __name__ == "__main__":
    sys.exit(main())
