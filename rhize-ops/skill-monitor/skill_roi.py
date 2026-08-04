#!/usr/bin/env python3
"""
skill_roi.py — Cost-per-skill ROI join.

Joins skill-monitor's data/skill-usage.json events (they carry session_id) to
~/.claude/metrics/costs.jsonl (latest row per session_id — see cost_metrics.py)
to produce: skill | invocations (7d/28d) | sessions | total session cost those
sessions | cost-share heuristic.

IMPORTANT — this is attribution context, not exact skill cost. A session's cost
covers everything that happened in it (every tool call, every other skill used),
not just the one skill being reported on. Two numbers are reported per skill:

  - "total session cost" — the full cost of every session that invoked this
    skill at least once (sessions can and do overlap across skills; this is
    NOT additive across the whole table).
  - "cost-share heuristic" — that same session cost divided evenly across the
    distinct skills invoked in it, summed across the skill's sessions. Still a
    heuristic (skills aren't equally expensive within a session), but it at
    least avoids charging one skill for 100% of a session five other skills
    also touched.

Also cross-references keep-list.yaml:
  - keep-listed skills with 0 invocations in the current data window
  - skills whose sessions are expensive but rarely invoked (<=2 invocations,
    cost-share above the median of skills that have invocations)

CAVEAT: invocation/session counts are bounded by whatever window
data/skill-usage.json was last generated with (see monitor.py --days). If that
snapshot's window is narrower than 28 days, the "28d" column here can't show
data monitor.py never captured — this script flags that explicitly rather than
silently under-reporting.

Usage:
  python3 skill_roi.py                       # uses data/skill-usage.json as-is
  python3 skill_roi.py --report-dir ./out
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cost_metrics

SCRIPT_DIR = Path(__file__).resolve().parent
HOME = Path.home()

DEFAULT_SKILL_USAGE_JSON = SCRIPT_DIR / "data" / "skill-usage.json"
DEFAULT_KEEP_LIST = SCRIPT_DIR / "keep-list.yaml"

# Mirrors savings_scorecard.py's cost-reports folder — "alongside the
# scorecard" per the task spec.
DEFAULT_VAULT_REPORT_DIR = (
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
    / "cost-reports"
)


def parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_keep_list(path: Path) -> set[str]:
    """Same tiny stdlib parser convention as dashboard.py: one skill per line,
    optionally prefixed with '- '; # comments and blank lines ignored."""
    out: set[str] = set()
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        if line:
            out.add(line)
    return out


def load_skill_usage(path: Path) -> dict:
    if not path.exists():
        return {"available": False, "error": f"not found: {path}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as e:
        return {"available": False, "error": str(e)}
    events = data.get("events", [])
    report = data.get("report", {})
    return {
        "available": True,
        "error": None,
        "events": events,
        "window_days": report.get("window_days"),
        "generated_at": report.get("generated_at"),
    }


def build_join(events: list[dict], cost_days: int | None) -> dict:
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_28d = now - timedelta(days=28)

    # skill -> set(session_id), skill -> invocation counters
    skill_sessions: dict[str, set[str]] = {}
    skill_inv_total: dict[str, int] = {}
    skill_inv_7d: dict[str, int] = {}
    skill_inv_28d: dict[str, int] = {}
    # session_id -> set(skill) — needed for the even-split cost-share heuristic
    session_skills: dict[str, set[str]] = {}

    for e in events:
        skill = e.get("skill")
        sid = e.get("session_id")
        if not skill or not sid:
            continue
        skill_sessions.setdefault(skill, set()).add(sid)
        skill_inv_total[skill] = skill_inv_total.get(skill, 0) + 1
        session_skills.setdefault(sid, set()).add(skill)

        ts = e.get("timestamp")
        if ts:
            try:
                dt = parse_iso(ts)
                if dt >= cutoff_7d:
                    skill_inv_7d[skill] = skill_inv_7d.get(skill, 0) + 1
                if dt >= cutoff_28d:
                    skill_inv_28d[skill] = skill_inv_28d.get(skill, 0) + 1
            except ValueError:
                pass

    all_session_ids = set(session_skills.keys())
    cost_result = cost_metrics.load_latest_costs_per_session(
        days=cost_days, session_ids=all_session_ids
    )
    session_cost: dict[str, float] = {
        sid: cost_metrics.session_cost_usd(row)
        for sid, row in cost_result.get("sessions", {}).items()
    }

    rows = []
    for skill, sids in skill_sessions.items():
        total_session_cost = sum(session_cost.get(sid, 0.0) for sid in sids)
        cost_share = sum(
            session_cost.get(sid, 0.0) / max(len(session_skills.get(sid, {skill})), 1)
            for sid in sids
        )
        matched_sessions = sum(1 for sid in sids if sid in session_cost)
        rows.append(
            {
                "skill": skill,
                "invocations_total": skill_inv_total.get(skill, 0),
                "invocations_7d": skill_inv_7d.get(skill, 0),
                "invocations_28d": skill_inv_28d.get(skill, 0),
                "session_count": len(sids),
                "sessions_with_cost_data": matched_sessions,
                "total_session_cost_usd": total_session_cost,
                "cost_share_usd": cost_share,
            }
        )

    return {
        "rows": rows,
        "cost_lookup_available": cost_result.get("available", False),
        "cost_lookup_error": cost_result.get("error"),
        "sessions_looked_up": len(all_session_ids),
        "sessions_matched": len(session_cost),
    }


def compute_prune_flags(rows: list[dict], keep_list: set[str], all_seen_skills: set[str]) -> dict:
    keep_zero_invocation = sorted(k for k in keep_list if k not in all_seen_skills)

    invoked_rows = [r for r in rows if r["invocations_total"] > 0]
    cost_shares = [r["cost_share_usd"] for r in invoked_rows if r["cost_share_usd"] > 0]
    median_cost_share = statistics.median(cost_shares) if cost_shares else 0.0

    expensive_rarely_invoked = sorted(
        (
            r
            for r in invoked_rows
            if r["invocations_total"] <= 2 and r["cost_share_usd"] > median_cost_share
        ),
        key=lambda r: -r["cost_share_usd"],
    )

    return {
        "keep_listed_zero_invocations": keep_zero_invocation,
        "median_cost_share_usd": median_cost_share,
        "expensive_but_rarely_invoked": expensive_rarely_invoked,
    }


def _fmt_usd(n) -> str:
    return f"${float(n):,.4f}"


def render_markdown(days_note: str, join: dict, flags: dict, keep_list: set[str]) -> str:
    now = datetime.now()
    rows = sorted(join["rows"], key=lambda r: -r["invocations_total"])

    lines: list[str] = []
    lines.append("---")
    lines.append("type: skill-roi")
    lines.append(f"date: {now.strftime('%Y-%m-%d')}")
    lines.append("tags:")
    lines.append("  - skill-audit")
    lines.append("  - cost-tracking")
    lines.append("---")
    lines.append("")
    lines.append(f"# Skill Cost-ROI — {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append(f"> {days_note}")
    lines.append("")
    lines.append(
        "> **Attribution, not measurement.** \"Total session cost\" is the full cost of "
        "every session that used a skill — sessions overlap across skills and this "
        "column is NOT additive down the table. \"Cost-share heuristic\" divides each "
        "session's cost evenly across the distinct skills it invoked, which spreads the "
        "blame more fairly but is still a heuristic, not the skill's real marginal cost."
    )
    lines.append("")
    if not join["cost_lookup_available"]:
        lines.append(f"> ⚠️ Cost lookup unavailable: {join['cost_lookup_error']}")
        lines.append("")
    else:
        lines.append(
            f"> Cost data matched for {join['sessions_matched']}/{join['sessions_looked_up']} "
            "sessions referenced by skill events (unmatched sessions predate costs.jsonl's "
            "retention or never wrote a cost row)."
        )
        lines.append("")

    lines.append("## Skill | invocations | sessions | cost")
    lines.append("")
    lines.append(
        "| Skill | Inv. (7d) | Inv. (28d) | Inv. (total in data) | Sessions | "
        "Total session cost | Cost-share heuristic |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in rows:
        lines.append(
            f"| `{r['skill']}` | {r['invocations_7d']} | {r['invocations_28d']} | "
            f"{r['invocations_total']} | {r['session_count']} | "
            f"{_fmt_usd(r['total_session_cost_usd'])} | {_fmt_usd(r['cost_share_usd'])} |"
        )
    lines.append("")

    lines.append("## Prune / attention candidates")
    lines.append("")
    lines.append(
        f"### Keep-listed skills with 0 invocations this window ({len(flags['keep_listed_zero_invocations'])})"
    )
    lines.append("")
    if flags["keep_listed_zero_invocations"]:
        for s in flags["keep_listed_zero_invocations"]:
            lines.append(f"- `{s}` — on `keep-list.yaml` but not in the current data window")
    else:
        lines.append(
            "- None. Every keep-listed skill has at least one invocation in the current data."
            if keep_list
            else "- `keep-list.yaml` is empty — nothing to cross-reference."
        )
    lines.append("")

    lines.append(
        f"### Expensive but rarely invoked ({len(flags['expensive_but_rarely_invoked'])})"
    )
    lines.append("")
    lines.append(
        f"*Threshold: ≤2 invocations AND cost-share above the median "
        f"({_fmt_usd(flags['median_cost_share_usd'])}) among skills with any invocation.*"
    )
    lines.append("")
    if flags["expensive_but_rarely_invoked"]:
        lines.append("| Skill | Invocations | Cost-share heuristic |")
        lines.append("| --- | ---: | ---: |")
        for r in flags["expensive_but_rarely_invoked"]:
            lines.append(
                f"| `{r['skill']}` | {r['invocations_total']} | {_fmt_usd(r['cost_share_usd'])} |"
            )
    else:
        lines.append("- None matched the threshold.")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--skill-usage-json",
        default=str(DEFAULT_SKILL_USAGE_JSON),
        help="path to skill-monitor's data/skill-usage.json",
    )
    ap.add_argument(
        "--keep-list",
        default=str(DEFAULT_KEEP_LIST),
        help="path to keep-list.yaml",
    )
    ap.add_argument(
        "--report-dir",
        default=str(DEFAULT_VAULT_REPORT_DIR),
        help="where to write the markdown report",
    )
    ap.add_argument(
        "--cost-days",
        type=int,
        default=None,
        help="restrict cost lookup to the last N days (default: no limit — "
        "look up whatever session_ids appear in the skill-usage data)",
    )
    args = ap.parse_args()

    usage = load_skill_usage(Path(args.skill_usage_json).expanduser())
    if not usage["available"]:
        print(f"ERROR: {usage['error']}", file=sys.stderr)
        return 1

    window_days = usage.get("window_days")
    days_note = (
        f"Invocation counts are drawn from `data/skill-usage.json`, generated "
        f"{usage.get('generated_at', 'unknown time')} with a "
        f"{window_days if window_days else 'all-time'}-day window."
    )
    if window_days is not None and window_days < 28:
        days_note += (
            f" ⚠️ That window is narrower than 28 days — the 28d column below can only "
            f"reflect events actually present in this snapshot (≤{window_days}d of real "
            f"coverage); re-run `monitor.py --days 28` for accurate 28d numbers."
        )

    join = build_join(usage["events"], cost_days=args.cost_days)
    keep_list = load_keep_list(Path(args.keep_list).expanduser())
    all_seen_skills = {r["skill"] for r in join["rows"]}
    flags = compute_prune_flags(join["rows"], keep_list, all_seen_skills)

    md = render_markdown(days_note, join, flags, keep_list)

    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{window_days}d" if window_days else "0d"
    md_path = report_dir / f"{datetime.now().strftime('%Y-%m-%d')}-skill-roi-{tag}.md"
    md_path.write_text(md)

    print(f"→ Skill ROI: {len(join['rows'])} skills joined against costs.jsonl")
    print(f"  ✓ Markdown report → {md_path}")
    print("")
    print(md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
