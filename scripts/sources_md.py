#!/usr/bin/env python3
"""sources_md.py — single-owner grammar for SOURCES.md parsing and the
Rhize-metadata frontmatter normalization used for content-hash comparisons.

Both `scripts/build_skill_map.py` (graph node/edge construction) and
`scripts/baseline_upstreams.py` (in-place SOURCES.md rewriting) import from
here rather than duplicating the grammar or reaching into each other's
private module state.

---------------------------------------------------------------------------
SOURCES.md parse grammar
---------------------------------------------------------------------------
The file is a flat sequence of entries, most-recent-appended-last. Each
entry is:

  ## <skill-name> — <date>
  - **Source:** <absolute path, typically .../marketplaces/<name>/skills/<rest>>
  - **Upstream ref:** <value>
  - **License:** <value>
  - **Verb:** <value>              (FORK | DEFER | ADAPT | ... — free text)
  - **Graph relation:** consumes   (OPTIONAL — DEFER+wrap provenance without a fork edge)
  - **Target:** <value>
  - **Took:** <value>
  - **Verified:** <value>
  - **Drift check:** <value>
  - **Upstream baseline:** sha256:<hex> (recorded YYYY-MM-DD)  (OPTIONAL —
    written/updated by scripts/baseline_upstreams.py, never by
    scripts/build_skill_map.py; the reviewed-upstream-state anchor for the
    three-way drift verdict, see
    docs/superpowers/specs/2026-08-10-three-way-drift-design.md)
  - **Notes:** <value>
  - **RETIRED <date>:** <text>     (OPTIONAL — only present if retired)

Parsing rule: split the file on lines starting with "## ", each block's
first line (after stripping "## ") up to " — " is the skill-name; the rest
of the block is scanned line-by-line for "- **<Field>:** <value>" bullets.
A block containing a bullet whose field name starts with "RETIRED" marks
that entry retired — its skill is expected to no longer exist under the
owning plugin's skills/, and no fork-of edge is emitted for it.
A non-retired entry's "Source" value is expected to contain either:
  (a) a local path: ".../marketplaces/<marketplace-name>/skills/<upstream-path>"
  (b) an http(s) URL to the upstream SKILL.md, e.g.
      "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/skills/<upstream-path>/SKILL.md"
Either form mints a PER-SKILL `external:<marketplace-name>/<upstream-path>`
node — not a single node shared by the whole marketplace — because the
drift checker resolves an upstream file from the node's own `path`/`url`,
and one node-level location can't serve every fork's distinct upstream
file. For form (a) the node carries `path`: the raw "Source" value with
"/SKILL.md" appended and the caller's home directory rewritten to "~"
(portable across machines). For form (b) the node carries `url` instead of
`path` (skill-forge's drift checker — src/gate/skillMapDrift.ts — reads
`node.url ?? node.path` and fetches over HTTPS when the value looks like a
URL): the raw "Source" value verbatim, since it already points at the file.
Either way the fork-of edge's driftCheck.upstreamPath is the parsed
<upstream-path>. If the "Source" value is neither a recognizable local
marketplace path nor an http(s) URL, this is a BuildError (existing
behavior) rather than silently emitting a location-less node — a genuinely
unreachable upstream (e.g. the marketplace was since uninstalled, or a URL
that 404s) is still recorded, just with a `path`/`url` that legitimately
fails to resolve at drift-check time.

Duplicate skill-name headings within one file are a SourcesMdError — a
malformed ledger, not something either caller should silently paper over
(build_skill_map.py wraps this as a BuildError; baseline_upstreams.py fails
the run).

SECURITY: this parser performs ONLY string splitting, regex matching, and
URL parsing (urllib.parse, no network I/O). Nothing read from this file is
ever passed to a shell, eval, or exec, and no request is made here.
---------------------------------------------------------------------------
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

_HEADING_RE = re.compile(r"^##\s+(.+?)\s+—\s+(.+)$")
_BULLET_RE = re.compile(r"^-\s+\*\*([^:*]+):\*\*\s*(.*)$")
_SOURCE_PATH_RE = re.compile(r"/marketplaces/([^/]+)/(?:.+/)?skills/(.+)$")
_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)
_BASELINE_HASH_RE = re.compile(r"^sha256:([a-f0-9]{64})\b")


class SourcesMdError(Exception):
    """Raised for malformed SOURCES.md content (e.g. duplicate headings)."""


def parse_sources_text(text: str) -> list[dict]:
    """Parse SOURCES.md content into entries with line spans.

    Each entry: {"skill_name", "fields", "retired", "start", "end"}.
    "start" is the heading's line index; "end" is one past the entry's last
    line (the next heading's line index, or len(lines) for the last entry).
    This is a superset of both callers' needs: build_skill_map.py only reads
    skill_name/fields/retired; baseline_upstreams.py additionally needs
    start/end to rewrite the file with a minimal, surgical diff instead of
    re-serializing the whole document.
    """
    lines = text.split("\n")
    entries: list[dict] = []
    current: dict | None = None
    for i, line in enumerate(lines):
        heading = _HEADING_RE.match(line)
        if heading:
            if current is not None:
                current["end"] = i
                entries.append(current)
            current = {
                "skill_name": heading.group(1).strip(),
                "fields": {},
                "retired": False,
                "start": i,
            }
            continue
        if current is None:
            continue
        bullet = _BULLET_RE.match(line.strip())
        if bullet:
            field, value = bullet.group(1).strip(), bullet.group(2).strip()
            if field.upper().startswith("RETIRED"):
                current["retired"] = True
            else:
                current["fields"][field] = value
    if current is not None:
        current["end"] = len(lines)
        entries.append(current)

    seen_names: set[str] = set()
    for entry in entries:
        name = entry["skill_name"]
        if name in seen_names:
            raise SourcesMdError(f"duplicate SOURCES.md heading for skill {name!r}")
        seen_names.add(name)

    return entries


def parse_sources_md(path: Path) -> list[dict]:
    """Thin wrapper: parse a SOURCES.md file on disk."""
    return parse_sources_text(path.read_text())


def parse_url_source(source_value: str) -> tuple[str, str]:
    """Derives (marketplace_name, upstream_path) from an http(s) Source URL.

    For a raw.githubusercontent.com URL — the shape produced when repointing
    a marketplace-cache fork upstream to its real remote — marketplace_name is
    "<owner>/<repo>" and upstream_path is the skill's path segment (mirroring
    the <upstream-path> a local marketplace path would yield, e.g.
    "context-fundamentals" from ".../skills/context-fundamentals/SKILL.md").
    Any other https(s) host falls back to using the URL's netloc as
    marketplace_name and its full path as upstream_path — still deterministic,
    just without the GitHub-specific trimming.
    """
    parsed = urlparse(source_value)
    parts = [p for p in parsed.path.split("/") if p]
    if parsed.netloc == "raw.githubusercontent.com" and len(parts) >= 3:
        owner, repo = parts[0], parts[1]
        rest = "/".join(parts[3:])  # drop owner, repo, branch
        skills_match = re.search(r"(?:^|/)skills/(.+?)(?:/SKILL\.md)?$", rest)
        upstream_path = skills_match.group(1) if skills_match else rest
        return f"{owner}/{repo}", upstream_path
    return parsed.netloc, parsed.path.lstrip("/")


def _frontmatter_bounds(lines: list[str]) -> tuple[int, int] | None:
    """Returns (open_idx, close_idx) of the '---' delimiters bounding a
    frontmatter block, or None if `lines[0]` isn't '---' or there's no
    closing delimiter. Line-based only — no YAML parsing. Single definition
    of "where the frontmatter is" for line-surgery purposes; unrelated to
    build_skill_map.py's YAML-parsing `split_frontmatter()`, which stays
    there and is not for this.
    """
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return 0, i
    return None


def strip_rhize_metadata_block(raw: bytes) -> bytes:
    """Textually remove the Rhize-injected `metadata.rhize` frontmatter subtree.

    This is the ONE normalization implementation named by
    docs/superpowers/specs/2026-08-10-three-way-drift-design.md ("the 5-line
    tagging exclusion"): skill-forge compares hashes it is handed and never
    re-implements this stripping itself (the duplicated-validator lesson).

    Precise rule: within the '---'-delimited frontmatter block, find a
    top-level (zero-indent) `metadata:` line.
      - If `rhize` is metadata's ONLY immediate child key, remove the
        `metadata:` line and all of its indented children.
      - Otherwise, remove only the `rhize:` line and its own indented
        children (metadata's other children are untouched).
    Operates on raw text lines only — no YAML parsing, so formatting/comment
    changes elsewhere in the frontmatter are never silently absorbed. Returns
    `raw` unchanged if there is no frontmatter block, no top-level `metadata:`
    key, or no `rhize` child under it (nothing to strip).
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    lines = text.split("\n")
    bounds = _frontmatter_bounds(lines)
    if bounds is None:
        return raw
    _, close_idx = bounds
    fm_lines = lines[1:close_idx]

    def indent_of(s: str) -> int:
        return len(s) - len(s.lstrip(" "))

    meta_idx = None
    for i, line in enumerate(fm_lines):
        if re.match(r"^metadata:\s*$", line):
            meta_idx = i
            break
    if meta_idx is None:
        return raw

    end_idx = len(fm_lines)
    for j in range(meta_idx + 1, len(fm_lines)):
        line = fm_lines[j]
        if line.strip() == "":
            continue
        if indent_of(line) == 0:
            end_idx = j
            break
    children = fm_lines[meta_idx + 1 : end_idx]

    non_blank_children = [(idx, line) for idx, line in enumerate(children) if line.strip() != ""]
    if not non_blank_children:
        return raw
    min_indent = min(indent_of(line) for _, line in non_blank_children)
    immediate_keys = []
    for idx, line in non_blank_children:
        if indent_of(line) == min_indent:
            m = re.match(r"^\s*([A-Za-z0-9_-]+):", line)
            if m:
                immediate_keys.append((idx, m.group(1)))
    rhize_entry = next(((idx, k) for idx, k in immediate_keys if k == "rhize"), None)
    if rhize_entry is None:
        return raw

    if len(immediate_keys) == 1:
        removal_start, removal_end = meta_idx, end_idx
    else:
        rhize_local_idx = rhize_entry[0]
        rhize_indent = indent_of(children[rhize_local_idx])
        subtree_end = len(children)
        for k in range(rhize_local_idx + 1, len(children)):
            line = children[k]
            if line.strip() == "":
                continue
            if indent_of(line) <= rhize_indent:
                subtree_end = k
                break
        removal_start = meta_idx + 1 + rhize_local_idx
        removal_end = meta_idx + 1 + subtree_end

    new_fm_lines = fm_lines[:removal_start] + fm_lines[removal_end:]
    new_lines = [lines[0]] + new_fm_lines + lines[close_idx:]
    return "\n".join(new_lines).encode("utf-8")
