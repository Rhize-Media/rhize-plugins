#!/usr/bin/env python3
"""baseline_upstreams.py — record/refresh the reviewed-upstream baseline hash.

Implements the "baseline" half of
docs/superpowers/specs/2026-08-10-three-way-drift-design.md: the deliberate,
human-triggered "I reviewed upstream, accept its state" action. It is NEVER
run by scripts/build_skill_map.py (the compiler stays offline and
deterministic) — only by a human (or this repo's audit routine, on request)
after actually reviewing an upstream change.

For every non-retired entry in a SOURCES.md whose `Source` field is an
http(s) URL, this script:
  1. Fetches the upstream file.
  2. Computes its sha256 hex digest.
  3. Writes/updates the entry's
     `- **Upstream baseline:** sha256:<hex> (recorded YYYY-MM-DD)` bullet,
     inserted before the entry's `- **Notes:**` bullet (or appended at the
     end of the entry block if there is no Notes bullet).

Idempotent: if the freshly fetched hash already matches the recorded
baseline hash, the file is left byte-for-byte untouched — not just
byte-identical content, the file is never even re-written, so its mtime is
untouched too. Two consecutive runs against an unchanged upstream produce no
diff and no touch.

Non-URL (local marketplace-path) `Source` entries are skipped with a report
line — a local path is not a "reviewed upstream state" this script can
fetch and hash; that fork's drift stays whatever `upstream-unreachable`/
`local-missing` state build_skill_map.py already reports for it.

Default scope: every plugin's `skills/SOURCES.md`, discovered via the same
`.claude-plugin/marketplace.json`-driven plugin list build_skill_map.py
uses. `--sources` narrows to one file; `--skill` narrows to one entry
(within whichever file(s) are in scope).

Usage:
  python3 scripts/baseline_upstreams.py
  python3 scripts/baseline_upstreams.py --skill context-fundamentals
  python3 scripts/baseline_upstreams.py --sources <path-to-SOURCES.md>

SECURITY: this script parses SOURCES.md with plain string/regex operations
only (via scripts/sources_md.py, the single grammar owner shared with
scripts/build_skill_map.py) and never executes anything read from it. The
only network call is a plain HTTP(S) GET of each entry's own recorded
Source URL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import sources_md  # noqa: E402

MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"
FETCH_TIMEOUT_SECS = 20


class BaselineError(Exception):
    """Raised for conditions that should abort the whole run (bad --skill, etc)."""


def fetch_url(url: str) -> bytes:
    """Default fetcher: a plain HTTP(S) GET. Overridable by tests/callers."""
    request = urllib.request.Request(url, headers={"User-Agent": "rhize-plugins-baseline-upstreams"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECS) as response:  # noqa: S310
        return response.read()


def discover_sources_files() -> list[Path]:
    """Every plugin's skills/SOURCES.md, using the same marketplace.json-
    driven plugin list scripts/build_skill_map.py uses to enumerate plugins."""
    marketplace = json.loads(MARKETPLACE_PATH.read_text())
    paths = []
    for entry in marketplace["plugins"]:
        source = entry["source"]
        plugin_dir_name = source[2:] if source.startswith("./") else source
        sources_path = REPO_ROOT / plugin_dir_name / "skills" / "SOURCES.md"
        if sources_path.is_file():
            paths.append(sources_path)
    return sorted(paths)


def _find_bullet_line_index(lines: list[str], start: int, end: int, field: str) -> int | None:
    prefix = f"- **{field}:**"
    for i in range(start, end):
        if lines[i].strip().startswith(prefix):
            return i
    return None


def _insert_baseline_bullet(lines: list[str], entry: dict, new_hash: str, today: date) -> list[str]:
    """Insert/replace the entry's '- **Upstream baseline:**' bullet.

    Caller has already established this entry needs an update (its recorded
    hash, if any, differs from `new_hash`) — this only performs the line
    surgery, it doesn't re-check idempotency.
    """
    start, end = entry["start"], entry["end"]
    new_line = f"- **Upstream baseline:** sha256:{new_hash} (recorded {today.isoformat()})"
    existing_idx = _find_bullet_line_index(lines, start, end, "Upstream baseline")
    if existing_idx is not None:
        return lines[:existing_idx] + [new_line] + lines[existing_idx + 1 :]

    notes_idx = _find_bullet_line_index(lines, start, end, "Notes")
    if notes_idx is not None:
        return lines[:notes_idx] + [new_line] + lines[notes_idx:]

    # No Notes bullet: append just before the block's trailing blank line(s)/
    # next heading, i.e. at the end of the block's own content.
    insert_at = end
    while insert_at > start and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    return lines[:insert_at] + [new_line] + lines[insert_at:]


def run(sources_path: Path, skill_filter: str | None, fetcher=fetch_url) -> int:
    if not sources_path.is_file():
        print(f"FAIL: no SOURCES.md found at {sources_path}")
        return 1

    text = sources_path.read_text()
    try:
        entries = sources_md.parse_sources_text(text)
    except sources_md.SourcesMdError as exc:
        print(f"FAIL: {exc}")
        return 1

    if skill_filter is not None:
        if not any(e["skill_name"] == skill_filter for e in entries):
            print(f"FAIL: no SOURCES.md entry named {skill_filter!r} in {sources_path}")
            return 1

    today = date.today()
    unchanged = 0
    skipped_non_url = []
    failed = []
    # (entry, new_hash) pairs for entries whose baseline actually needs
    # updating — collected in one pass over the parsed entries, before any
    # line surgery, so entries' recorded start/end spans never go stale.
    to_apply: list[tuple[dict, str]] = []

    for entry in entries:
        if entry["retired"]:
            continue
        if skill_filter is not None and entry["skill_name"] != skill_filter:
            continue
        source_value = entry["fields"].get("Source", "")
        if not sources_md._URL_SCHEME_RE.match(source_value):
            skipped_non_url.append(entry["skill_name"])
            continue
        try:
            body = fetcher(source_value)
        except (urllib.error.URLError, OSError) as exc:
            failed.append((entry["skill_name"], str(exc)))
            continue
        new_hash = hashlib.sha256(body).hexdigest()
        existing_match = sources_md._BASELINE_HASH_RE.match(entry["fields"].get("Upstream baseline", ""))
        if existing_match and existing_match.group(1) == new_hash:
            unchanged += 1
            continue
        to_apply.append((entry, new_hash))

    # Apply updates in a single pass, in reverse line order, so inserting a
    # bullet for one entry never shifts the recorded start/end of an entry
    # further down the file that's still waiting to be applied.
    lines = text.split("\n")
    for entry, new_hash in sorted(to_apply, key=lambda pair: pair[0]["start"], reverse=True):
        lines = _insert_baseline_bullet(lines, entry, new_hash, today)

    if to_apply:
        sources_path.write_text("\n".join(lines))

    try:
        display_path = sources_path.relative_to(REPO_ROOT)
    except ValueError:
        display_path = sources_path
    print(f"Baselined against {display_path}:")
    print(f"  updated:   {len(to_apply)}")
    print(f"  unchanged: {unchanged} (baseline already matches upstream)")
    if skipped_non_url:
        print(f"  skipped (non-URL Source, cannot baseline): {', '.join(skipped_non_url)}")
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
        default=None,
        help=(
            "Path to a single SOURCES.md file to baseline. Default: every "
            "plugin's skills/SOURCES.md, discovered from marketplace.json."
        ),
    )
    args = parser.parse_args(argv)

    explicit_single_file = args.sources is not None
    sources_paths = [args.sources] if explicit_single_file else discover_sources_files()
    if not sources_paths:
        print("FAIL: no SOURCES.md files found")
        return 1

    if args.skill is not None and not explicit_single_file:
        # Scanning every plugin's SOURCES.md: only run against files that
        # actually contain the named entry, and fail only if it's in none of
        # them (an explicit --sources still fails loudly on a miss, via
        # run()'s own check, since there's no other file it could mean).
        matching = [
            p
            for p in sources_paths
            if any(e["skill_name"] == args.skill for e in sources_md.parse_sources_text(p.read_text()))
        ]
        if not matching:
            print(f"FAIL: no SOURCES.md entry named {args.skill!r} in any discovered SOURCES.md")
            return 1
        sources_paths = matching

    rc = 0
    for sources_path in sources_paths:
        rc = run(sources_path, args.skill) or rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
