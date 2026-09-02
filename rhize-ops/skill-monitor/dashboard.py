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
import html
import json
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import quote
from datetime import datetime
from pathlib import Path

import benchmark_status
import paths
import stack_metrics

SCRIPT_DIR = Path(__file__).resolve().parent
SNAPSHOTS_DIR = paths.snapshots_dir()
# Static plugin assets (template/source), not user data — stay repo-relative.
COMPONENT_PATH = SCRIPT_DIR / "SkillDashboard.jsx"
TEMPLATE_PATH = SCRIPT_DIR / "dashboard-template.html"
KEEP_LIST_PATH = SCRIPT_DIR / "keep-list.yaml"
CDN_CACHE_DIR = paths.cdn_cache_dir()

# stack_metrics.py / benchmark_status.py write these pre-computed snapshots;
# dashboard.py reads them (imported path constants, not a re-parse of their
# sources) the same way it already reads data/snapshots/*.json rather than
# re-running monitor.py's own scan.
STACK_METRICS_PATH = stack_metrics.DEFAULT_OUT_PATH
BENCHMARK_STATUS_PATH = benchmark_status.OUTPUT_PATH

# Cowork live-artifact panel (id "skill-audit-live"). The weekly-skill-audit
# task renders this and calls update_artifact to keep the in-chat panel fresh.
PANEL_TEMPLATE_PATH = SCRIPT_DIR / "panel-template.html"
DEFAULT_PANEL_PATH = paths.data_dir() / "skill-audit-panel.html"
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

# None when no single vault could be resolved (see paths.vault_root()) —
# main() then requires an explicit --html-path instead of writing into a
# vault it can't find.
_vault_report_dir = paths.vault_report_dir("dashboard")
DEFAULT_HTML_PATH = (_vault_report_dir / "dashboard.html") if _vault_report_dir else None


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


def _load_json_snapshot(path: Path) -> dict | None:
    """Read a single pre-computed JSON snapshot file. Never raises — a
    missing or malformed snapshot renders as "unavailable" in the Stack
    Trust section rather than crashing the whole dashboard build."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return None


def load_stack_metrics_snapshot(path: Path = STACK_METRICS_PATH) -> dict | None:
    return _load_json_snapshot(path)


def load_benchmark_status_snapshot(path: Path = BENCHMARK_STATUS_PATH) -> dict | None:
    return _load_json_snapshot(path)


_TRUST_BADGE_STYLE = {
    "measured": "background:#dcfce7;color:#166534;",
    "measured_caveated": "background:#fef3c7;color:#92400e;",
    "indicative": "background:#e0e7ff;color:#3730a3;",
    "self_reported": "background:#fee2e2;color:#991b1b;",
}


def _badge(label: str) -> str:
    style = _TRUST_BADGE_STYLE.get(label, "background:#e5e7eb;color:#374151;")
    return (
        f'<span style="display:inline-block;padding:1px 8px;border-radius:9999px;'
        f'font:600 11px ui-monospace,monospace;{style}">{html.escape(label)}</span>'
    )


def render_trust_section_html(
    stack_metrics_snapshot: dict | None,
    benchmark_status_snapshot: dict | None,
) -> str:
    """Server-rendered (no React/Recharts — stdlib string templating only)
    HTML fragment surfacing stack_metrics.py's trust-tagged metrics and
    benchmark_status.py's procedural-memory liveness. Every figure carries
    its trust class as a badge next to the number, not as a legend a reader
    has to scroll to find; a row_missing verdict gets its own banner, not
    just a table cell.

    Deterministic: renders only fields already frozen inside the source
    JSON snapshots, so re-running dashboard.py against unchanged inputs
    reproduces byte-identical output (see CLAUDE.md's idempotency
    expectation).
    """
    parts: list[str] = []
    parts.append('<section style="max-width:1100px;margin:32px auto;padding:0 16px;'
                 'font-family:ui-sans-serif,system-ui,sans-serif;">')
    parts.append('<h2 style="font-size:20px;font-weight:700;margin-bottom:4px;">Stack Trust</h2>')
    parts.append(
        '<p style="color:#6b7280;font-size:13px;margin-top:0;">'
        "Every figure below carries its trust class inline — "
        f"{_badge('measured')} {_badge('measured_caveated')} "
        f"{_badge('indicative')} {_badge('self_reported')} — "
        "so a measured saving is never confused with a self-reported one."
        "</p>"
    )

    # --- Procedural memory liveness (row_missing unmissable) --------------
    if benchmark_status_snapshot is None:
        parts.append(
            '<p style="color:#991b1b;">Procedural memory status unavailable — '
            f"no snapshot at {html.escape(str(BENCHMARK_STATUS_PATH))}.</p>"
        )
    else:
        liveness = benchmark_status_snapshot.get("liveness", {})
        missing = [name for name, v in liveness.items() if v.get("status") == "row_missing"]
        if missing:
            parts.append(
                '<div style="background:#fee2e2;border:2px solid #991b1b;border-radius:8px;'
                'padding:12px 16px;margin:12px 0;">'
                '<strong style="color:#991b1b;">ROW_MISSING — a run happened and no row landed</strong>'
                '<ul style="margin:6px 0 0;padding-left:20px;color:#7f1d1d;">'
            )
            for name in missing:
                reason = html.escape(str(liveness[name].get("reason") or ""))
                parts.append(f"<li><strong>{html.escape(name)}</strong>: {reason}</li>")
            parts.append("</ul></div>")

        parts.append('<h3 style="font-size:15px;font-weight:600;margin:16px 0 6px;">Procedural memory liveness</h3>')
        parts.append(
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            "<thead><tr style=\"text-align:left;border-bottom:1px solid #e5e7eb;\">"
            "<th style=\"padding:4px 8px;\">Routine</th><th style=\"padding:4px 8px;\">Status</th>"
            "<th style=\"padding:4px 8px;\">Reason</th></tr></thead><tbody>"
        )
        for name in sorted(liveness):
            v = liveness[name]
            status = v.get("status", "unknown")
            row_bg = "background:#fee2e2;" if status == "row_missing" else ""
            parts.append(
                f'<tr style="border-bottom:1px solid #f3f4f6;{row_bg}">'
                f'<td style="padding:4px 8px;">{html.escape(name)}</td>'
                f'<td style="padding:4px 8px;">{html.escape(status)}</td>'
                f'<td style="padding:4px 8px;color:#6b7280;">{html.escape(str(v.get("reason") or ""))}</td>'
                "</tr>"
            )
        parts.append("</tbody></table>")

    # --- Trust-tagged metrics -----------------------------------------------
    parts.append('<h3 style="font-size:15px;font-weight:600;margin:20px 0 6px;">Trust-tagged metrics</h3>')
    if stack_metrics_snapshot is None:
        parts.append(
            '<p style="color:#991b1b;">Stack metrics unavailable — '
            f"no snapshot at {html.escape(str(STACK_METRICS_PATH))}.</p>"
        )
    else:
        parts.append(
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            "<thead><tr style=\"text-align:left;border-bottom:1px solid #e5e7eb;\">"
            "<th style=\"padding:4px 8px;\">Metric</th><th style=\"padding:4px 8px;\">Value</th>"
            "<th style=\"padding:4px 8px;\">Trust</th><th style=\"padding:4px 8px;\">Basis</th>"
            "<th style=\"padding:4px 8px;\">Source</th></tr></thead><tbody>"
        )
        for m in stack_metrics_snapshot.get("metrics", []):
            value = m.get("value")
            value_str = f"{value:,}" if isinstance(value, (int, float)) else "n/a"
            basis = m.get("basis") or "—"
            parts.append(
                "<tr style=\"border-bottom:1px solid #f3f4f6;\">"
                f'<td style="padding:4px 8px;"><code>{html.escape(m.get("name", ""))}</code></td>'
                f'<td style="padding:4px 8px;text-align:right;">{html.escape(value_str)} {html.escape(m.get("unit", ""))}</td>'
                f'<td style="padding:4px 8px;">{_badge(m.get("trust", ""))}</td>'
                f'<td style="padding:4px 8px;color:#6b7280;">{html.escape(str(basis))}</td>'
                f'<td style="padding:4px 8px;color:#6b7280;">{html.escape(m.get("source", ""))}</td>'
                "</tr>"
            )
        parts.append("</tbody></table>")

        totals = stack_metrics_snapshot.get("totals") or {}
        if totals:
            parts.append('<h3 style="font-size:15px;font-weight:600;margin:20px 0 6px;">Totals (same-basis only)</h3>')
            parts.append(
                '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
                "<thead><tr style=\"text-align:left;border-bottom:1px solid #e5e7eb;\">"
                "<th style=\"padding:4px 8px;\">Total</th><th style=\"padding:4px 8px;\">Value</th>"
                "<th style=\"padding:4px 8px;\">Basis</th><th style=\"padding:4px 8px;\">From</th></tr></thead><tbody>"
            )
            for name, t in totals.items():
                value = t.get("value")
                value_str = f"{value:,}" if isinstance(value, (int, float)) else "n/a"
                parts.append(
                    "<tr style=\"border-bottom:1px solid #f3f4f6;\">"
                    f'<td style="padding:4px 8px;"><code>{html.escape(name)}</code></td>'
                    f'<td style="padding:4px 8px;text-align:right;">{html.escape(value_str)} {html.escape(t.get("unit", ""))}</td>'
                    f'<td style="padding:4px 8px;color:#6b7280;">{html.escape(str(t.get("basis") or "—"))}</td>'
                    f'<td style="padding:4px 8px;color:#6b7280;">{html.escape(", ".join(t.get("from_metrics", [])))}</td>'
                    "</tr>"
                )
            parts.append("</tbody></table>")

    parts.append("</section>")
    return "".join(parts)


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


def render_html(
    snapshots: list[dict],
    keep_list: list[str],
    offline: bool = True,
    stack_metrics_snapshot: dict | None = None,
    benchmark_status_snapshot: dict | None = None,
) -> str:
    """Inline snapshots + keep-list + JSX component into the HTML template.

    When `offline=True` (default), also inlines the CDN bundles so the file
    renders in sandboxed previews (e.g. Obsidian's HTML embed) that block
    external <script src> requests. Bundles are cached under data/cdn-cache/.

    `stack_metrics_snapshot` / `benchmark_status_snapshot` feed a separate,
    server-rendered "Stack Trust" section (plain HTML, not part of the React
    component tree) — see render_trust_section_html(). Passing None for
    either renders that section as "unavailable" rather than omitting it.
    """
    template = TEMPLATE_PATH.read_text()
    component_src = COMPONENT_PATH.read_text()

    if offline:
        template = _inline_cdn(template)

    snap_json = json.dumps(snapshots, default=str)
    keep_json = json.dumps(keep_list)
    trust_html = render_trust_section_html(stack_metrics_snapshot, benchmark_status_snapshot)

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
    ).replace(
        "<!--__TRUST_SECTION_PLACEHOLDER__-->",
        trust_html,
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
    # No single vault resolved (paths.vault_root()) -> no default location to
    # copy; the button gets a placeholder instead of a bogus "file://None".
    dash_url = _file_url(DEFAULT_HTML_PATH) if DEFAULT_HTML_PATH else "(no vault configured — pass --html-path)"
    template = template.replace(DASH_URL_MARKER, dash_url)
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
    ap.add_argument("--html-path",
                    default=str(DEFAULT_HTML_PATH) if DEFAULT_HTML_PATH else None,
                    help=("output path for --out html (default: the Obsidian "
                          "vault, if exactly one is configured — see "
                          "paths.vault_root(); required otherwise)"))
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
        if not args.html_path:
            print(
                "  ! no --html-path given and no single Obsidian vault could "
                "be resolved (see paths.vault_root()) — pass --html-path "
                "explicitly.",
                file=sys.stderr,
            )
            return 1
        dashboard_html = render_html(
            snapshots,
            keep_list,
            offline=not args.online,
            stack_metrics_snapshot=load_stack_metrics_snapshot(),
            benchmark_status_snapshot=load_benchmark_status_snapshot(),
        )
        out_path = Path(args.html_path).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(dashboard_html)
        print(f"  ✓ HTML dashboard → {out_path}")
        print(
            f"    {len(snapshots)} snapshot(s), "
            f"{len(keep_list)} keep-list entries, "
            f"{len(dashboard_html) // 1024} KB"
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
