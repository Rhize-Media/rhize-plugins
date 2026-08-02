#!/usr/bin/env python3
"""
dashboard.py — Live artifact dashboard renderer for skill-monitor.

Reads every JSON file from data/snapshots/, templates them into either:
  --out html      → a self-contained HTML file (default destination is in
                    the Obsidian vault at Projects/Rhize Media/Rhize Tools/
                    Scheduled Agent Routines & Automations/Skill-Audit-and-Monitoring/
                    dashboard.html)
  --out artifact  → ready-to-paste JSX source for an `application/vnd.ant.react`
                    Claude Artifact, with snapshots and keep-list inlined as
                    module-level constants and a default `App` export. The
                    skill-dashboard skill takes this output and emits it
                    inside an <antArtifact> block in chat.

The React component (SkillDashboard.jsx) is the single source of truth for
the dashboard's layout and computations; this script just inlines snapshots
+ keep-list into one of the two output forms.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import quote
from datetime import datetime
from pathlib import Path

HOME = Path.home()
SCRIPT_DIR = Path(__file__).resolve().parent
SNAPSHOTS_DIR = SCRIPT_DIR / "data" / "snapshots"
COMPONENT_PATH = SCRIPT_DIR / "SkillDashboard.jsx"
TEMPLATE_PATH = SCRIPT_DIR / "dashboard-template.html"
KEEP_LIST_PATH = SCRIPT_DIR / "keep-list.yaml"
CDN_CACHE_DIR = SCRIPT_DIR / "data" / "cdn-cache"

# Cowork live-artifact panel (id "skill-audit-live"). The weekly-skill-audit
# task renders this and calls update_artifact to keep the in-chat panel fresh.
PANEL_TEMPLATE_PATH = SCRIPT_DIR / "panel-template.html"
DEFAULT_PANEL_PATH = SCRIPT_DIR / "data" / "skill-audit-panel.html"
PANEL_DATA_MARKER = "/*__PANEL_DATA__*/"

# Pinned CDN bundles loaded by dashboard-template.html. Versions are baked
# into the URLs, so the cache never needs to expire. Listed in the order
# the template expects them to execute (React → ReactDOM → prop-types →
# Recharts → Babel → Tailwind).
_CDN_BUNDLES: list[str] = [
    "https://unpkg.com/react@18/umd/react.production.min.js",
    "https://unpkg.com/react-dom@18/umd/react-dom.production.min.js",
    "https://unpkg.com/prop-types@15.8.1/prop-types.min.js",
    "https://unpkg.com/recharts@2.12.7/umd/Recharts.js",
    "https://unpkg.com/@babel/standalone@7.24.0/babel.min.js",
    "https://cdn.tailwindcss.com",
]

DEFAULT_HTML_PATH = (
    HOME
    / "Library"
    / "Mobile Documents"
    / "iCloud~md~obsidian"
    / "Documents"
    / "Obsidian Vault"
    / "Projects"
    / "Rhize Media"
    / "Rhize Tools"
    / "Scheduled Agent Routines & Automations"
    / "Skill-Audit-and-Monitoring"
    / "dashboard.html"
)


def _snapshot_sort_key(p: Path) -> tuple[str, int]:
    """Sort snapshots by date primary, window secondary (widest window last).

    Filenames look like `YYYY-MM-DD-skill-usage-{N}d.json`. When the same
    date has multiple snapshots from different `--days` windows, the
    widest window (`0d` = all-time) sorts last so it's treated as the
    "latest" by downstream consumers that pick `snapshots[-1]`. Trend
    aggregations that union by ISO week handle mixed windows gracefully.

    Pre-2026-05-08 snapshots without a `-Nd` suffix are tolerated as
    `-1` priority (sort before any windowed snapshot for the same date).
    """
    name = p.stem  # e.g. "2026-05-08-skill-usage-7d"
    date_part, _, window_part = name.partition("-skill-usage")
    window_part = window_part.lstrip("-").rstrip("d")
    try:
        w = int(window_part)
    except ValueError:
        w = -1
    # 0 = all-time = widest window = highest priority
    priority = 99_999 if w == 0 else w
    return (date_part, priority)


def load_snapshots(snapshots_dir: Path) -> list[dict]:
    """Load one snapshot per date, preferring the widest window when multiple exist.

    Same-date narrower-window snapshots are dropped so the dashboard's
    rank-delta comparison ("vs. previous snapshot") always compares
    different *dates*, not different windows of the same date.
    """
    if not snapshots_dir.exists():
        return []
    by_date: dict[str, tuple[Path, dict]] = {}
    for f in sorted(snapshots_dir.glob("*.json"), key=_snapshot_sort_key):
        date = _snapshot_sort_key(f)[0]
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            print(f"  ! skipping malformed snapshot {f.name}: {e}", file=sys.stderr)
            continue
        # Sort key puts widest window last → later writes win the dedup.
        by_date[date] = (f, data)
    return [data for _date, (_path, data) in sorted(by_date.items())]


def load_keep_list(keep_list_path: Path) -> list[str]:
    """Parse a minimal YAML keep-list.

    Format: one skill name per line, optionally indented under '- '.
    Lines starting with '#' or empty are ignored. We keep the parser
    intentionally tiny to avoid a PyYAML dependency.
    """
    if not keep_list_path.exists():
        return []
    out: list[str] = []
    for raw in keep_list_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        # Strip surrounding quotes if present
        if (line.startswith('"') and line.endswith('"')) or (
            line.startswith("'") and line.endswith("'")
        ):
            line = line[1:-1]
        if line:
            out.append(line)
    return out


def _cache_path_for(url: str) -> Path:
    """Map a CDN URL to a deterministic local cache filename."""
    # Strip protocol, replace '/' so the URL becomes a flat filename.
    flat = re.sub(r"^https?://", "", url).replace("/", "_")
    return CDN_CACHE_DIR / flat


def _fetch_bundle(url: str, timeout: float = 30.0) -> str:
    """Download a CDN bundle, caching by URL. Returns the JS source text."""
    cache = _cache_path_for(url)
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    CDN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "skill-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    # cdn.tailwindcss.com may redirect to a versioned path; that's followed
    # automatically by urllib. Body is the executed JS in either case.
    cache.write_text(body, encoding="utf-8")
    return body


def _inline_cdn(template_html: str) -> str:
    """Replace every <script src="https://..."> tag from _CDN_BUNDLES with an
    inline <script>...</script> containing the bundle source. Order is preserved.

    Falls back to leaving the tag untouched if a bundle fails to fetch (so the
    dashboard still works in a real browser even if the cache is cold offline).
    """
    out = template_html
    for url in _CDN_BUNDLES:
        # Match the full <script ... src="<url>" ...></script> tag.
        # Both the unpkg URLs and cdn.tailwindcss.com are pinned literals in
        # the template, so a literal-URL match is safe.
        pattern = re.compile(
            r'<script[^>]*\bsrc=["\']' + re.escape(url) + r'["\'][^>]*>\s*</script>',
            re.IGNORECASE,
        )
        if not pattern.search(out):
            continue
        try:
            src = _fetch_bundle(url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  ! could not fetch {url} ({e}); leaving as remote <script src>", file=sys.stderr)
            continue
        # Strip any closing </script> sequences inside the body to keep the
        # outer <script> tag balanced. Replace with a Unicode-escaped form
        # that's harmless to the JS parser.
        safe_src = src.replace("</script", "<\\/script")
        replacement = f"<script>\n/* inlined from {url} */\n{safe_src}\n</script>"
        # Replace exactly one occurrence — each URL appears once in the template.
        out = pattern.sub(lambda _m, r=replacement: r, out, count=1)
    return out


def render_html(snapshots: list[dict], keep_list: list[str], offline: bool = True) -> str:
    """Inline snapshots + keep-list + JSX component into the HTML template.

    When `offline=True` (default), also inlines the CDN bundles so the file
    renders in sandboxed previews (e.g. Obsidian's HTML embed) that block
    external <script src> requests. Bundles are cached under data/cdn-cache/.
    """
    template = TEMPLATE_PATH.read_text()
    component_src = COMPONENT_PATH.read_text()

    if offline:
        template = _inline_cdn(template)

    snap_json = json.dumps(snapshots, default=str)
    keep_json = json.dumps(keep_list)

    # Substitution markers are wrapped in JS comments inside the template so
    # the template itself remains valid (and openable for editing) on its own.
    out = template.replace(
        "/*__SNAPSHOTS_PLACEHOLDER__*/[]",
        snap_json,
    ).replace(
        "/*__KEEP_LIST_PLACEHOLDER__*/[]",
        keep_json,
    ).replace(
        "/*__COMPONENT_SOURCE__*/",
        component_src,
    )
    return out


def render_artifact_source(snapshots: list[dict], keep_list: list[str]) -> str:
    """Transform SkillDashboard.jsx into ready-to-paste Claude Artifact source.

    The HTML wrapper relies on React, ReactDOM, and Recharts being globals
    loaded via CDN script tags. Claude Artifact runtime instead expects
    ESM-style imports from 'react' and 'recharts'. This transform:

      1. Adds `import React from 'react'` and `import * as Recharts from 'recharts'`
         at the top. Existing `const { useState, useMemo } = React;` and
         `const { ResponsiveContainer, ... } = Recharts;` destructures keep
         working because `React` and `Recharts` resolve to namespace objects
         with the destructured properties.
      2. Inlines snapshots and keep-list as module-level constants AND on
         `window` so `getSnapshots()` and `props.keepList` paths both work.
      3. Strips the bottom `if (typeof document !== "undefined") { ... }`
         block — the artifact runtime mounts via the default export instead.
      4. Appends `export default function App() { return <SkillDashboard ... /> }`
         so the runtime can mount the dashboard with data already wired in.
    """
    component_src = COMPONENT_PATH.read_text()

    # Strip the manual mount block — artifact runtime uses the default export.
    mount_marker = 'if (typeof document !== "undefined"'
    mount_idx = component_src.find(mount_marker)
    if mount_idx > 0:
        component_src = component_src[:mount_idx].rstrip()

    snapshots_json = json.dumps(snapshots, default=str)
    keep_list_json = json.dumps(keep_list)

    return f"""\
// Auto-generated by dashboard.py from SkillDashboard.jsx + accumulated snapshots.
// Paste inside an <antArtifact type="application/vnd.ant.react"> block.
import React from 'react';
import * as Recharts from 'recharts';

// Inlined data — module-level constants for the default export, plus window
// globals so the legacy `getSnapshots()` fallback in the component still works.
const SNAPSHOTS = {snapshots_json};
const KEEP_LIST = {keep_list_json};
if (typeof window !== 'undefined') {{
  window.React = React;
  window.Recharts = Recharts;
  window.__SNAPSHOTS__ = SNAPSHOTS;
  window.__KEEP_LIST__ = KEEP_LIST;
}}

{component_src}

export default function App() {{
  return <SkillDashboard snapshots={{SNAPSHOTS}} keepList={{KEEP_LIST}} />;
}}
"""


def _newest_window_snapshot(snapshots_dir: Path, window_tag: str) -> Path | None:
    """Return the newest-dated `*-skill-usage-{tag}.json` snapshot, or None.

    Filenames lead with an ISO date, so lexical sort == chronological.
    """
    cands = sorted(snapshots_dir.glob(f"*-skill-usage-{window_tag}.json"))
    return cands[-1] if cands else None


def build_panel_data(snapshots_dir: Path) -> dict:
    """Derive the compact data object the live panel inlines.

    Pulls the newest 7-day snapshot (the weekly headline) and the newest
    28-day snapshot (trend + top skills). If one window is missing, the other
    stands in so the panel still renders.
    """
    def load(tag: str) -> dict | None:
        p = _newest_window_snapshot(snapshots_dir, tag)
        if not p:
            return None
        try:
            return json.loads(p.read_text())["report"]
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    r7 = load("7d")
    r28 = load("28d") or r7
    r7 = r7 or r28
    if not r7 or not r28:
        raise SystemExit("  ! no 7d/28d snapshots found to build the panel.")

    by_week = {
        w: {"_total": sum(c.values())}
        for w, c in (r28.get("by_week") or {}).items()
    }
    top_by_channel = r28.get("top_by_channel") or {}
    return {
        "generated_at": r7.get("generated_at") or r28.get("generated_at") or "",
        "d7": {
            "total": r7["total_invocations"],
            "unique": r7["unique_skills_used"],
            "by_channel": r7.get("by_channel") or {},
            "raw": r7.get("total_raw_invocations", r7["total_invocations"]),
            "dedup": r7.get("overlap_deduped", 0),
            "top": r7["top_skills"][:5],
        },
        "d28": {
            "total": r28["total_invocations"],
            "unique": r28["unique_skills_used"],
            "by_channel": r28.get("by_channel") or {},
            "dedup": r28.get("overlap_deduped", 0),
            "top": r28["top_skills"][:15],
            "by_week": by_week,
            "sc_top": top_by_channel.get("slash_command", [])[:8],
        },
    }


DASH_URL_MARKER = "__DASH_FILE_URL__"


def _user_facing_path(p: Path) -> str:
    """Return the path as the user's macOS filesystem sees it.

    When this script runs inside a Cowork sandbox, paths resolve under
    `/sessions/<id>/mnt/<user>/...`. Rewrite that prefix to the real
    `/Users/<user>/...` home so the emitted file:// link is valid in the
    user's browser. No-op on native runs (where the prefix never matches).
    """
    return re.sub(r"^/sessions/[^/]+/mnt/", "/Users/", str(p))


def _file_url(p: Path) -> str:
    """Build a browser-pasteable file:// URL for a local path (spaces → %20)."""
    return "file://" + quote(_user_facing_path(p))


def render_panel(snapshots_dir: Path) -> str:
    """Inline the panel data object into panel-template.html at its marker."""
    template = PANEL_TEMPLATE_PATH.read_text()
    # Inject the live dashboard.html location as a copyable file:// URL so the
    # panel's "Copy dashboard path" button never goes stale on a vault reorg.
    template = template.replace(DASH_URL_MARKER, _file_url(DEFAULT_HTML_PATH))
    data_json = json.dumps(build_panel_data(snapshots_dir), default=str)
    # Replace `/*__PANEL_DATA__*/<fallback literal>` up to the first `;` after
    # the marker's object. Simplest robust approach: swap the marker plus the
    # immediately-following JSON literal. The template keeps a valid fallback
    # object so it opens standalone; we replace from the marker to just before
    # the line's trailing `;`.
    if PANEL_DATA_MARKER not in template:
        raise SystemExit("  ! panel-template.html is missing the PANEL_DATA marker.")
    head, _, tail = template.partition(PANEL_DATA_MARKER)
    # tail starts with the fallback `{...}`; drop it up to the terminating `;`.
    semi = tail.find(";")
    rest = tail[semi:] if semi != -1 else tail
    return f"{head}{PANEL_DATA_MARKER}{data_json}{rest}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("--out", choices=("html", "artifact", "panel"), default="html",
                    help="output mode (default: html)")
    ap.add_argument("--snapshots-dir", default=str(SNAPSHOTS_DIR),
                    help=f"default: {SNAPSHOTS_DIR}")
    ap.add_argument("--keep-list", default=str(KEEP_LIST_PATH),
                    help=f"default: {KEEP_LIST_PATH}")
    ap.add_argument("--html-path", default=str(DEFAULT_HTML_PATH),
                    help=f"output path for --out html (default: {DEFAULT_HTML_PATH})")
    ap.add_argument("--json-out", default="-",
                    help="output path for --out artifact JSX source ('-' = stdout, default)")
    ap.add_argument("--online", action="store_true",
                    help="HTML mode only: keep CDN <script src> tags as-is "
                         "(default inlines bundles so the file renders in "
                         "Obsidian's HTML preview and other sandboxed iframes)")
    ap.add_argument("--panel-path", default=str(DEFAULT_PANEL_PATH),
                    help=f"output path for --out panel (default: {DEFAULT_PANEL_PATH})")
    args = ap.parse_args()

    snapshots_dir = Path(args.snapshots_dir).expanduser()
    keep_list_path = Path(args.keep_list).expanduser()

    # Panel mode reads the per-window snapshots directly (newest 7d + 28d),
    # not the deduped trend list, so handle it before load_snapshots().
    if args.out == "panel":
        panel_html = render_panel(snapshots_dir)
        out_path = Path(args.panel_path).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(panel_html)
        print(f"  ✓ Live panel → {out_path}")
        print(f"    {len(panel_html) // 1024} KB — feed to update_artifact(id='skill-audit-live')")
        return 0

    snapshots = load_snapshots(snapshots_dir)
    keep_list = load_keep_list(keep_list_path)

    if not snapshots:
        print(
            f"  ! no snapshots found in {snapshots_dir}. Run monitor.py first.",
            file=sys.stderr,
        )
        return 1

    if args.out == "html":
        html = render_html(snapshots, keep_list, offline=not args.online)
        out_path = Path(args.html_path).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html)
        print(f"  ✓ HTML dashboard → {out_path}")
        print(
            f"    {len(snapshots)} snapshot(s), "
            f"{len(keep_list)} keep-list entries, "
            f"{len(html) // 1024} KB"
        )
    else:  # artifact
        source = render_artifact_source(snapshots, keep_list)
        if args.json_out == "-":
            sys.stdout.write(source)
        else:
            out_path = Path(args.json_out).expanduser()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(source)
            print(
                f"  ✓ Artifact source → {out_path}  "
                f"({len(snapshots)} snapshots, {len(source) // 1024} KB)"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
