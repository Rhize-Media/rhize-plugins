#!/usr/bin/env python3
"""plugin_prune.py — report-first advisor over a skill-forge plugin audit.

Reads a `@rhize/skill-forge` `audit --claude-plugins`/`routine --claude-plugins`
JSON report (schemaVersion 1, a `plugins` array — see the skill-forge CLAUDE.md's
"MCP gating"/"audit" sections for the producing side) and, optionally, the last N
`rhize-skill-monitor` usage snapshots, and prints a per-plugin table: recommendation,
active HIGH/CRITICAL findings, and how many of the last N *exhaustive* snapshots never
observed the plugin's skills fire.

The audit report is untrusted input (it may describe attacker-influenced plugin ids,
reasons, or other fields), so every string anywhere in it is control-character-stripped
once, at the moment it's parsed (load_audit) — never per call site — so a field this
script doesn't yet know about is safe by default too.

This script NEVER writes `~/.claude/settings.json`. The only mutating path is
`--apply --disable <id>...`, which requires an interactive terminal, requires every
`--disable` id to already be present in the audit AND enabled in settings, and only
after a per-id typed "yes" runs `claude plugin disable <id> --scope user` as an argv
list (no shell). Everything else is read-only.

Usage:
  plugin_prune.py --audit <file> [--settings <path>] [--json]
  plugin_prune.py --audit <file> --snapshots <dir> --weeks <N> [--json]
  plugin_prune.py --audit <file> --apply --disable <id> [--disable <id> ...]

Exit codes:
  0  clean report — no plugin recommended `review` or `unobserved`
  1  at least one plugin is `review` or `unobserved` (so a cron job can alert)
  2  usage/input error (bad audit file, bad flag combination, --apply refused)

`--apply` returns 0 once every requested id has been prompted for, even if an
individual `claude plugin disable` invocation failed (that failure is printed to
stderr and the next id is still attempted) — the confirmation flow itself is the
safety gate, not the exit code.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "rhize-plugin-prune-v1"
DEFAULT_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
CRON_ALERT_RECOMMENDATIONS = {"review", "unobserved"}

# C0/C1 control characters plus zero-width and bidi-override characters (a
# RIGHT-TO-LEFT OVERRIDE in a `reasons` string could visually reverse the table
# a human reads before typing `yes`).
_CONTROL_CHARS_RE = re.compile("[\\x00-\\x1f\\x7f-\\x9f\\u200b-\\u200f\\u202a-\\u202e\\u2066-\\u2069]")


class UsageError(ValueError):
    pass


def strip_control_chars(value: str) -> str:
    return _CONTROL_CHARS_RE.sub("", value)


def sanitize_json_value(value: Any) -> Any:
    """Recursively strip C0/C1 control characters from every string inside a
    parsed JSON value (dict/list/str), leaving other types untouched. Applied
    once in load_audit(), at the untrusted-input boundary."""
    if isinstance(value, str):
        return strip_control_chars(value)
    if isinstance(value, list):
        return [sanitize_json_value(v) for v in value]
    if isinstance(value, dict):
        return {k: sanitize_json_value(v) for k, v in value.items()}
    return value


def load_audit(path: Path) -> list[Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot read --audit file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--audit file {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise UsageError(f"--audit file {path} must contain a JSON object")
    if data.get("schemaVersion") != 1:
        raise UsageError(
            f"--audit file {path} has unsupported schemaVersion "
            f"{data.get('schemaVersion')!r} (expected 1)"
        )
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        raise UsageError(
            f"--audit file {path} has no \"plugins\" array — produce it with "
            "skill-forge >= 0.17: `skill-forge audit --yes --claude-plugins --json`"
        )
    return sanitize_json_value(plugins)


def load_settings(path: Path) -> dict[str, Any]:
    """`enabledPlugins` from the user-scope settings file only — the scope
    `--apply` disables at (`claude plugin disable --scope user`). Project-local
    `.claude/settings.local.json` overrides are deliberately not merged."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    enabled = data.get("enabledPlugins")
    return enabled if isinstance(enabled, dict) else {}


def settings_status(plugin_id: str, enabled_plugins: dict[str, Any]) -> str:
    if plugin_id not in enabled_plugins:
        return "unknown"
    return "enabled" if enabled_plugins[plugin_id] is True else "disabled"


# ---------------------------------------------------------------------------
# Snapshots / weeks-unobserved
#
# A snapshot is "exhaustive" only when it carries every skill's count, not
# just the top-50 `top_skills` cap `monitor.py` writes (rhize-skill-monitor's
# `skill_totals` field, added alongside `top_skills` for exactly this reason —
# see rhize-skill-monitor CLAUDE.md's "Data shape" section). Absent that, a
# snapshot whose `top_skills` length equals `unique_skills_used` is also
# exhaustive by construction (nothing was capped) — `unique_skills_used` is
# `len(totals)` over the FULL counter in monitor.py, independent of the
# `top_skills` cap, so this inference is sound even for pre-`skill_totals`
# snapshots. The audit JSON never lists skill names, only plugin ids, so a
# plugin counts as "observed" in a snapshot when any usage key starts with
# "<bare-plugin-name>:" — skill-monitor keys invocations by the exact string
# passed to the Skill tool, which is "<plugin>:<skill>" for a plugin-scoped
# skill.
# ---------------------------------------------------------------------------


def bare_plugin_name(plugin_id: str) -> str:
    return plugin_id.split("@", 1)[0]


def parse_generated_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # A naive timestamp (no offset) would raise on comparison against an aware
    # one during sort — treat it as UTC rather than crash on a mixed batch.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def snapshot_usage_keys(report: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (exhaustive, usage_keys) for one snapshot's `report` object."""
    skill_totals = report.get("skill_totals")
    if isinstance(skill_totals, dict):
        return True, [k for k in skill_totals if isinstance(k, str)]

    top_skills = report.get("top_skills")
    keys: list[str] = []
    if isinstance(top_skills, list):
        for entry in top_skills:
            if isinstance(entry, (list, tuple)) and entry and isinstance(entry[0], str):
                keys.append(entry[0])

    unique = report.get("unique_skills_used")
    exhaustive = isinstance(top_skills, list) and isinstance(unique, int) and len(top_skills) == unique
    return exhaustive, keys


def load_snapshots(snapshots_dir: Path, weeks: int) -> tuple[list[dict[str, Any]], int]:
    """Return (selected reports newest-first, count of unreadable/malformed files).

    Selection is by each snapshot's own `report.generated_at`, never file mtime.
    `sorted()` over the glob gives ties (identical `generated_at`) a deterministic,
    filename-based order before the stable sort below breaks ties by recency —
    without it, ties would fall back to arbitrary directory-iteration order.
    """
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    unreadable = 0
    for path in sorted(snapshots_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            unreadable += 1
            continue
        report = data.get("report") if isinstance(data, dict) else None
        if not isinstance(report, dict):
            unreadable += 1
            continue
        generated_at = parse_generated_at(report.get("generated_at"))
        if generated_at is None:
            unreadable += 1
            continue
        candidates.append((generated_at, report))

    candidates.sort(key=lambda c: c[0], reverse=True)
    selected = [report for _generated_at, report in candidates[:weeks]]
    return selected, unreadable


def compute_weeks(
    selected_reports: list[dict[str, Any]], plugin_ids: list[str]
) -> tuple[dict[str, int], int, int]:
    """Return ({pluginId: weeksUnobserved}, weeksTotal, skippedNonExhaustive).

    `weeksTotal` (the count of exhaustive snapshots among `selected_reports`) is
    the single source of truth for that number — every caller reads it from here
    rather than re-deriving it.
    """
    observed_prefixes_per_snapshot: list[set[str]] = []
    skipped_non_exhaustive = 0
    for report in selected_reports:
        exhaustive, keys = snapshot_usage_keys(report)
        if not exhaustive:
            skipped_non_exhaustive += 1
            continue
        observed_prefixes_per_snapshot.append({k.split(":", 1)[0] for k in keys if ":" in k})

    weeks_total = len(observed_prefixes_per_snapshot)
    weeks_unobserved_by_plugin = {
        plugin_id: sum(
            1
            for observed_prefixes in observed_prefixes_per_snapshot
            if bare_plugin_name(plugin_id) not in observed_prefixes
        )
        for plugin_id in plugin_ids
    }
    return weeks_unobserved_by_plugin, weeks_total, skipped_non_exhaustive


# ---------------------------------------------------------------------------
# Rows / rendering
# ---------------------------------------------------------------------------


def build_rows(plugins_raw: list[Any], enabled_plugins: dict[str, Any]) -> list[dict[str, Any]]:
    """Build one row per plugin entry. `plugins_raw` is assumed already
    control-character-sanitized (load_audit's job, not this function's).
    `weeksUnobserved`/`weeksTotal` start as None; main() fills them in when
    snapshots were requested."""
    rows: list[dict[str, Any]] = []
    for entry in plugins_raw:
        if not isinstance(entry, dict):
            continue
        plugin_id = str(entry.get("pluginId", ""))
        version = str(entry.get("version", "")) or "-"
        skill_count = entry.get("skillCount")
        finding_counts = entry.get("findingCounts")
        finding_counts = finding_counts if isinstance(finding_counts, dict) else {}
        recommendation = str(entry.get("recommendation", "unknown"))
        reasons_raw = entry.get("reasons")
        reasons = [r for r in reasons_raw if isinstance(r, str)] if isinstance(reasons_raw, list) else []

        # `notes` are this script's OWN observations (settings cross-reference),
        # kept separate from `reasons` (skill-forge's audit reasoning) so --json
        # output never blends the two provenances; `settingsStatus` is the
        # structured form of the same fact ("enabled" is the only actionable value).
        status = settings_status(plugin_id, enabled_plugins)
        notes: list[str] = []
        if status == "unknown":
            notes.append("plugin id not found in user-scope settings.json enabledPlugins (not actionable)")
        elif status == "disabled":
            notes.append("already disabled in user-scope settings.json")

        rows.append(
            {
                "pluginId": plugin_id,
                "version": version,
                "skillCount": skill_count,
                "findingsHigh": finding_counts.get("HIGH", 0),
                "findingsCritical": finding_counts.get("CRITICAL", 0),
                "recommendation": recommendation,
                "reasons": reasons,
                "notes": notes,
                "settingsStatus": status,
                "weeksUnobserved": None,
                "weeksTotal": None,
            }
        )
    rows.sort(key=lambda r: r["pluginId"])
    return rows


def render_table(rows: list[dict[str, Any]]) -> str:
    headers = ["pluginId", "version", "skills", "H/C", "recommendation", "weeks", "reasons"]
    lines = [" | ".join(headers), "-" * 100]
    for row in rows:
        weeks = "-" if row["weeksTotal"] is None else f"{row['weeksUnobserved']}/{row['weeksTotal']}"
        hc = f"{row['findingsHigh']}/{row['findingsCritical']}"
        combined_reasons = row["reasons"] + row["notes"]
        reasons_cell = "; ".join(combined_reasons) if combined_reasons else "-"
        lines.append(
            " | ".join(
                [
                    row["pluginId"],
                    row["version"],
                    str(row["skillCount"]),
                    hc,
                    row["recommendation"],
                    weeks,
                    reasons_cell,
                ]
            )
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# --apply --disable
# ---------------------------------------------------------------------------


def apply_disable(ids: list[str], rows_by_id: dict[str, dict[str, Any]]) -> int:
    if not sys.stdin.isatty():
        print("error: refusing: --apply needs an interactive terminal", file=sys.stderr)
        return 2

    invalid: list[str] = []
    for plugin_id in ids:
        row = rows_by_id.get(plugin_id)
        if plugin_id.startswith("-"):
            # Never let an id shaped like a flag reach the `claude` argv as a positional.
            invalid.append(f"{plugin_id}: not a valid plugin id")
        elif row is None:
            invalid.append(f"{plugin_id}: not present in the --audit report")
        elif row["settingsStatus"] != "enabled":
            invalid.append(
                f"{plugin_id}: not enabled in settings.json (status: {row['settingsStatus']})"
            )
    if invalid:
        print(
            "error: --disable requires ids present in the audit and enabled in settings:",
            file=sys.stderr,
        )
        for message in invalid:
            print(f"  {message}", file=sys.stderr)
        return 2

    claude_bin = os.environ.get("PLUGIN_PRUNE_CLAUDE_BIN") or "claude"
    for plugin_id in ids:
        answer = input(f"Disable {plugin_id}? type yes to confirm: ")
        if answer.strip() != "yes":
            print(f"skipped {plugin_id} (not confirmed)")
            continue
        argv = [claude_bin, "plugin", "disable", plugin_id, "--scope", "user"]
        try:
            result = subprocess.run(argv, capture_output=True, text=True)
        except OSError as exc:
            print(f"error: could not run {claude_bin!r}: {exc}", file=sys.stderr)
            continue
        if result.returncode != 0:
            print(
                f"error: disabling {plugin_id} failed (exit {result.returncode}): "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
        else:
            print(f"disabled {plugin_id}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--audit", required=True, type=Path, help="skill-forge audit/routine JSON report")
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH, help="Claude Code settings.json (default: ~/.claude/settings.json)")
    parser.add_argument("--snapshots", type=Path, default=None, help="directory of rhize-skill-monitor snapshot *.json files")
    parser.add_argument("--weeks", type=int, default=None, help="number of latest snapshots to consider (required with --snapshots)")
    parser.add_argument("--json", action="store_true", help="print one JSON document instead of a table")
    parser.add_argument("--apply", action="store_true", help="disable the ids named by --disable (requires a TTY + typed confirmation)")
    parser.add_argument("--disable", action="append", default=[], metavar="ID", help="plugin id (plugin@marketplace) to disable; repeatable")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_arg_parser().parse_args(argv)

    if args.apply and not args.disable:
        print("error: --apply requires at least one --disable <id>", file=sys.stderr)
        return 2
    if (args.snapshots is None) != (args.weeks is None):
        print("error: --snapshots and --weeks must be given together", file=sys.stderr)
        return 2
    if args.weeks is not None and args.weeks < 1:
        print("error: --weeks must be a positive integer", file=sys.stderr)
        return 2

    try:
        plugins_raw = load_audit(args.audit)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    enabled_plugins = load_settings(args.settings)

    rows = build_rows(plugins_raw, enabled_plugins)

    snapshots_summary: dict[str, Any] | None = None
    if args.snapshots is not None:
        if not args.snapshots.is_dir():
            print(f"error: --snapshots path is not a directory: {args.snapshots}", file=sys.stderr)
            return 2
        selected_reports, unreadable = load_snapshots(args.snapshots, args.weeks)
        weeks_unobserved_by_plugin, weeks_total, skipped_non_exhaustive = compute_weeks(
            selected_reports, [row["pluginId"] for row in rows]
        )
        for row in rows:
            row["weeksUnobserved"] = weeks_unobserved_by_plugin.get(row["pluginId"])
            row["weeksTotal"] = weeks_total
        snapshots_summary = {
            "dir": str(args.snapshots),
            "weeksRequested": args.weeks,
            "selected": len(selected_reports),
            "weeksConsidered": weeks_total,
            "skippedNonExhaustive": skipped_non_exhaustive,
            "unreadable": unreadable,
        }

    rows_by_id = {row["pluginId"]: row for row in rows}

    if args.apply:
        return apply_disable(args.disable, rows_by_id)

    exit_code = 1 if any(row["recommendation"] in CRON_ALERT_RECOMMENDATIONS for row in rows) else 0

    if args.json:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "auditPath": str(args.audit),
            "settingsPath": str(args.settings),
            "plugins": rows,
        }
        if snapshots_summary is not None:
            payload["snapshots"] = snapshots_summary
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_table(rows))
        if snapshots_summary is not None:
            print(
                f"\n{snapshots_summary['selected']} snapshot(s) selected "
                f"(by generated_at); {snapshots_summary['weeksConsidered']} exhaustive, "
                f"{snapshots_summary['skippedNonExhaustive']} skipped as non-exhaustive, "
                f"{snapshots_summary['unreadable']} unreadable."
            )
        print(
            "\nRecommendations are advisory: dormancy is only reported from exhaustive "
            "snapshots, and skill telemetry says nothing about a plugin's hooks, commands, "
            "or MCP servers."
        )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
