#!/usr/bin/env python3
"""
benchmark_status.py — procedural-memory benchmark watchdog.

Answers a question that used to require opening four Obsidian notes by hand:
did each benchmark-instrumented routine's capture step actually land a row this
run, or did it silently no-op? The capture pipeline (`bench-append`) has already
failed silently at least once — this module exists to turn "did it land?" into a
queryable JSON snapshot instead of something discovered by eyeballing a table.

Four read-only data sources:
  1. The four benchmark notes' `## Metrics log` markdown tables (vault paths
     below). The four notes have DIFFERENT column sets — this module does not
     assume a shared schema; it reports each note's own header verbatim.
  2. `~/.rhize/procedural-memory/runs/*.jsonl` run telemetry (streamed, never
     loaded wholesale).
  3. `~/dev-local/RHIZE/procedural-memory/registry/.health/**/*.json` health
     sidecars — the OFFLINE-AUTHORITATIVE health record. Deliberately does NOT
     read `health` out of `*.provenance.json` (that field is stale there by
     design — health is excluded from the digest-hashed provenance document).
  4. Scheduler state: `~/.claude/scheduled-tasks/*/` (Claude Code CLI scheduler
     — existence only, no run-time log) and the Desktop app's registry JSON at
     `~/Library/Application Support/Claude/local-agent-mode-sessions/*/*/
     scheduled-tasks.json` (has real `lastRunAt` timestamps keyed by task id).

The `liveness` section is the actual point of this module: per routine, did the
routine run (per the scheduler) more recently than the newest row logged in its
note? If so, a run happened and produced no row — `row_missing`. That is the
finding this module exists to surface, made unmissable in both JSON and the
human-readable report. Rows carry only a DATE, never a time, so a run and the
newest row sharing a calendar date is genuinely indeterminate, not `ok` — see
`classify_liveness()`'s `indeterminate_same_day` status. Scheduler instants are
converted to the benchmark program's America/New_York calendar before that
date-only comparison.

System python3 here is 3.14 and has no `jsonschema` — this module deliberately
imports nothing beyond the standard library.

Run as: python3 benchmark_status.py [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

HOME = Path.home()
BENCHMARK_TIMEZONE = ZoneInfo("America/New_York")

# --- Data source locations -------------------------------------------------

_VAULT_ROOT = (
    HOME
    / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault"
    / "Projects/Rhize Media/Rhize Tools"
)
_SCHEDULED_ROUTINES_DIR = _VAULT_ROOT / "Scheduled Agent Routines & Automations"

BENCHMARK_NOTES: dict[str, Path] = {
    "Vault Inbox Processor": _SCHEDULED_ROUTINES_DIR
    / "Vault Inbox Processor"
    / "Procedural Memory Benchmark.md",
    "AI-Stack-Version-Drift": _SCHEDULED_ROUTINES_DIR
    / "AI-Stack-Version-Drift"
    / "Procedural Memory Benchmark.md",
    "Daily Completed Summary": _SCHEDULED_ROUTINES_DIR
    / "Daily Completed Summary"
    / "Procedural Memory Benchmark.md",
    "Content Engine": _VAULT_ROOT / "Content Engine" / "Procedural Memory Benchmark.md",
}

RUNS_DIR = HOME / ".rhize" / "procedural-memory" / "runs"
HEALTH_DIR = HOME / "dev-local" / "RHIZE" / "procedural-memory" / "registry" / ".health"
SCHEDULED_TASKS_DIR = HOME / ".claude" / "scheduled-tasks"
DESKTOP_SESSIONS_ROOT = HOME / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"

DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_PATH = DATA_DIR / "benchmark-status.json"

# Substrings (case-insensitive) matched against Desktop scheduler task `id`s to
# find the entry(ies) that correspond to each benchmark-instrumented routine.
# "Content Engine" is deliberately on-demand (see its own note's prose) and has
# no scheduler entry by design — an empty list means "don't guess."
ROUTINE_SCHEDULER_KEYS: dict[str, list[str]] = {
    "Vault Inbox Processor": ["vault-inbox-processor"],
    "AI-Stack-Version-Drift": ["ai-stack-version-drift", "drift-benchmark"],
    "Daily Completed Summary": ["daily-completed-summary", "daily-summary-benchmark"],
    "Content Engine": [],
}


# --- 1. Benchmark note parsing ---------------------------------------------

_SECTION_RE = re.compile(r"^#{1,6}\s*Metrics log\s*$", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"^\|?[\s\-:|]+\|?$")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")


def _split_table_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip().replace("\\|", "|") for c in _CELL_SPLIT_RE.split(s)]


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _find_col(columns: list[str], name: str) -> str | None:
    for c in columns:
        if c.strip().lower() == name:
            return c
    return None


def parse_metrics_table(text: str) -> dict[str, Any]:
    """Parse the '## Metrics log' markdown table out of a benchmark note's text.

    Returns a dict with: error (str|None), columns (list[str]), raw_rows
    (list[dict[str,str]]), malformed_rows (list[dict]).
    """
    lines = text.splitlines()

    start = None
    for i, line in enumerate(lines):
        if _SECTION_RE.match(line.strip()):
            start = i
            break
    if start is None:
        return {
            "error": "no '## Metrics log' section found",
            "columns": [],
            "raw_rows": [],
            "malformed_rows": [],
        }

    # Don't let a table from a LATER section bleed in.
    section_end = len(lines)
    for k in range(start + 1, len(lines)):
        if lines[k].strip().startswith("#"):
            section_end = k
            break

    header_idx = None
    for k in range(start + 1, section_end):
        if lines[k].strip().startswith("|"):
            header_idx = k
            break
    if header_idx is None:
        return {
            "error": "'## Metrics log' section found but no table under it",
            "columns": [],
            "raw_rows": [],
            "malformed_rows": [],
        }

    columns = _split_table_row(lines[header_idx])

    data_start = header_idx + 1
    if data_start < section_end and _SEPARATOR_RE.match(lines[data_start].strip()) and "-" in lines[data_start]:
        data_start += 1  # skip the |---|---| separator row

    raw_rows: list[dict[str, str]] = []
    malformed_rows: list[dict[str, Any]] = []
    k = data_start
    while k < section_end:
        line = lines[k]
        stripped = line.strip()
        if not stripped or not stripped.startswith("|"):
            break
        cells = _split_table_row(line)
        if len(cells) != len(columns):
            malformed_rows.append(
                {
                    "line_no": k + 1,
                    "raw": line,
                    "reason": f"expected {len(columns)} columns, got {len(cells)}",
                }
            )
        else:
            raw_rows.append(dict(zip(columns, cells)))
        k += 1

    return {"error": None, "columns": columns, "raw_rows": raw_rows, "malformed_rows": malformed_rows}


def summarize_note(text: str) -> dict[str, Any]:
    """Turn parse_metrics_table()'s output into the per-note summary this module reports:
    total rows, rows by arm, newest row date (overall + per arm), column schema.
    """
    parsed = parse_metrics_table(text)
    if parsed["error"]:
        return {
            "error": parsed["error"],
            "columns": [],
            "total_rows": 0,
            "rows_by_arm": {},
            "newest_row_date": None,
            "newest_row_date_by_arm": {},
            "malformed_rows": parsed["malformed_rows"],
            "unparseable_dates": [],
        }

    columns = parsed["columns"]
    date_col = _find_col(columns, "date")
    arm_col = _find_col(columns, "arm")

    rows_by_arm: dict[str, int] = {}
    newest_by_arm: dict[str, date] = {}
    newest_overall: date | None = None
    unparseable_dates: list[dict[str, Any]] = []

    for idx, rec in enumerate(parsed["raw_rows"]):
        arm_key = (rec.get(arm_col, "").strip() if arm_col else "") or "<unknown>"
        rows_by_arm[arm_key] = rows_by_arm.get(arm_key, 0) + 1

        if date_col is None:
            continue
        d = _parse_date(rec.get(date_col, ""))
        if d is None:
            unparseable_dates.append({"row_index": idx, "date_raw": rec.get(date_col, "")})
            continue
        if arm_key not in newest_by_arm or d > newest_by_arm[arm_key]:
            newest_by_arm[arm_key] = d
        if newest_overall is None or d > newest_overall:
            newest_overall = d

    return {
        "error": None,
        "columns": columns,
        "total_rows": len(parsed["raw_rows"]),
        "rows_by_arm": rows_by_arm,
        "newest_row_date": newest_overall,
        "newest_row_date_by_arm": newest_by_arm,
        "malformed_rows": parsed["malformed_rows"],
        "unparseable_dates": unparseable_dates,
    }


def load_note_summary(path: Path) -> dict[str, Any]:
    """Read + summarize one benchmark note. Never raises — a missing/unreadable
    file becomes exists=False + an error string."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "exists": False,
            "error": f"file not found: {path}",
            "columns": [],
            "total_rows": 0,
            "rows_by_arm": {},
            "newest_row_date": None,
            "newest_row_date_by_arm": {},
            "malformed_rows": [],
            "unparseable_dates": [],
        }
    except OSError as e:
        return {
            "exists": False,
            "error": f"could not read {path}: {e}",
            "columns": [],
            "total_rows": 0,
            "rows_by_arm": {},
            "newest_row_date": None,
            "newest_row_date_by_arm": {},
            "malformed_rows": [],
            "unparseable_dates": [],
        }
    summary = summarize_note(text)
    summary["exists"] = True
    return summary


def load_all_note_summaries(notes: dict[str, Path] = BENCHMARK_NOTES) -> dict[str, dict[str, Any]]:
    return {name: load_note_summary(path) for name, path in notes.items()}


# --- 2. Run telemetry --------------------------------------------------------


def load_run_telemetry(runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    """Stream every runs_dir/*.jsonl line-by-line, aggregate per-artifact counts.
    Never loads a file wholesale; never raises on a missing dir or a bad line."""
    result: dict[str, Any] = {
        "available": True,
        "error": None,
        "files_read": 0,
        "files_error": [],
        "artifacts": {},
    }
    if not runs_dir.exists():
        result["available"] = False
        result["error"] = f"runs dir not found: {runs_dir}"
        return result

    for fp in sorted(runs_dir.glob("*.jsonl")):
        try:
            with fp.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # skip a corrupt telemetry line, don't crash
                    name = rec.get("name") or "<unknown>"
                    entry = result["artifacts"].setdefault(
                        name, {"runs": 0, "ok": 0, "fail": 0, "newest_started_at": None}
                    )
                    entry["runs"] += 1
                    if rec.get("ok"):
                        entry["ok"] += 1
                    else:
                        entry["fail"] += 1
                    started = rec.get("started_at")
                    if started and (
                        entry["newest_started_at"] is None or started > entry["newest_started_at"]
                    ):
                        entry["newest_started_at"] = started
            result["files_read"] += 1
        except OSError as e:
            result["files_error"].append({"file": str(fp), "error": str(e)})

    return result


# --- 3. Health sidecars -------------------------------------------------------


def load_health_sidecars(health_dir: Path = HEALTH_DIR) -> dict[str, Any]:
    """Read every health_dir/**/*.json sidecar. This is the offline-authoritative
    health record — deliberately NOT the (stale) health field inside
    *.provenance.json."""
    result: dict[str, Any] = {"available": True, "error": None, "artifacts": {}}
    if not health_dir.exists():
        result["available"] = False
        result["error"] = f"health dir not found: {health_dir}"
        return result

    for fp in sorted(health_dir.rglob("*.json")):
        artifact_id = str(fp.relative_to(health_dir).with_suffix(""))
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            result["artifacts"][artifact_id] = {
                "health": data.get("health"),
                "last_verified": data.get("last_verified"),
            }
        except (OSError, json.JSONDecodeError) as e:
            result["artifacts"][artifact_id] = {"error": str(e)}

    return result


# --- 4. Scheduler state -------------------------------------------------------


def load_scheduler_status(
    scheduled_tasks_dir: Path = SCHEDULED_TASKS_DIR,
    sessions_root: Path = DESKTOP_SESSIONS_ROOT,
) -> dict[str, Any]:
    """Best-effort scheduler reader. Never raises — an unresolvable path or an
    unreadable/malformed JSON file is recorded as an error, not a crash."""
    result: dict[str, Any] = {
        "cli_scheduled_tasks": [],
        "cli_scheduled_tasks_error": None,
        "desktop_tasks": [],
        "desktop_registry_error": None,
    }

    try:
        if scheduled_tasks_dir.exists():
            result["cli_scheduled_tasks"] = sorted(
                p.name for p in scheduled_tasks_dir.iterdir() if p.is_dir()
            )
        else:
            result["cli_scheduled_tasks_error"] = f"not found: {scheduled_tasks_dir}"
    except OSError as e:
        result["cli_scheduled_tasks_error"] = str(e)

    try:
        if sessions_root.exists():
            found_any = False
            for fp in sorted(sessions_root.glob("*/*/scheduled-tasks.json")):
                found_any = True
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as e:
                    result["desktop_tasks"].append({"source_file": str(fp), "error": str(e)})
                    continue
                for t in data.get("scheduledTasks", []):
                    result["desktop_tasks"].append(
                        {
                            "id": t.get("id"),
                            "enabled": t.get("enabled"),
                            "lastRunAt": t.get("lastRunAt"),
                            "cronExpression": t.get("cronExpression"),
                            "source_file": str(fp),
                        }
                    )
            if not found_any:
                result["desktop_registry_error"] = f"no scheduled-tasks.json found under {sessions_root}"
        else:
            result["desktop_registry_error"] = f"not found: {sessions_root}"
    except OSError as e:
        result["desktop_registry_error"] = str(e)

    return result


def find_scheduler_last_run(routine_name: str, scheduler_status: dict[str, Any]) -> dict[str, Any]:
    """Match a routine's known id-substrings against the Desktop registry's task
    ids, and return the MOST RECENT lastRunAt among all matches."""
    keys = ROUTINE_SCHEDULER_KEYS.get(routine_name, [])
    if not keys:
        return {
            "matched": False,
            "last_run_at": None,
            "matched_ids": [],
            "reason": f"no scheduler keys configured for '{routine_name}' (on-demand routine by design)",
        }

    matches = [
        t
        for t in scheduler_status["desktop_tasks"]
        if t.get("id") and any(key in t["id"].lower() for key in keys)
    ]
    if not matches:
        return {
            "matched": False,
            "last_run_at": None,
            "matched_ids": [],
            "reason": f"no desktop scheduler entry matched keys {keys}",
        }

    parsed: list[tuple[datetime, dict]] = []
    for m in matches:
        lra = m.get("lastRunAt")
        if not lra:
            continue
        try:
            parsed.append((datetime.fromisoformat(lra.replace("Z", "+00:00")), m))
        except ValueError:
            continue

    matched_ids = [m.get("id") for m in matches]
    if not parsed:
        return {"matched": True, "last_run_at": None, "matched_ids": matched_ids, "reason": None}

    parsed.sort(key=lambda x: x[0])
    newest_dt, _ = parsed[-1]
    return {"matched": True, "last_run_at": newest_dt, "matched_ids": matched_ids, "reason": None}


# --- 5. Liveness classification ----------------------------------------------

LIVENESS_STATUSES = ("ok", "indeterminate_same_day", "row_missing", "never_run", "unknown")


def classify_liveness(note_summary: dict[str, Any], scheduler_lookup: dict[str, Any]) -> dict[str, Any]:
    """The watchdog's actual verdict: did the routine run, and did a row land?

    ok                     — newest logged row is dated strictly AFTER the
                             scheduler's last known run — the row demonstrably
                             postdates the run, so it can only have landed
                             because of (or after) that run or a later one.
    indeterminate_same_day — the newest row and the scheduler's last run share
                             a calendar date. Rows carry only a DATE, not a
                             time, so whether that row was written before or
                             after that day's run cannot be determined either
                             way from this data. Reporting this as `ok` was
                             the exact false-negative this module used to
                             produce: a run that landed no row still reads as
                             covered as long as some earlier row exists from
                             the same day. Never fabricate a time to resolve
                             this — report the genuine indeterminacy instead.
    row_missing            — scheduler shows a run that postdates the newest
                             row (or the note has zero rows despite a recorded
                             run). THE finding this module exists to surface.
    never_run              — scheduler entry exists but has no recorded run,
                             and the note has zero rows.
    unknown                — can't determine; `reason` names the missing
                             input.
    """
    if note_summary.get("error"):
        return {"status": "unknown", "reason": f"could not read/parse note: {note_summary['error']}"}

    if not scheduler_lookup["matched"]:
        return {"status": "unknown", "reason": scheduler_lookup["reason"]}

    last_run_at = scheduler_lookup.get("last_run_at")
    newest_row_date = note_summary.get("newest_row_date")
    total_rows = note_summary.get("total_rows", 0)

    if last_run_at is None:
        if total_rows == 0:
            return {
                "status": "never_run",
                "reason": "scheduler entry found but has no recorded run, and the note has zero rows",
            }
        return {
            "status": "unknown",
            "reason": "scheduler entry found but lastRunAt is missing; note has rows so recency can't be verified",
        }

    if last_run_at.tzinfo is not None:
        last_run_at = last_run_at.astimezone(BENCHMARK_TIMEZONE)
    last_run_date = last_run_at.date()
    if newest_row_date is None:
        return {
            "status": "row_missing",
            "reason": f"scheduler last ran {last_run_date.isoformat()} but the note has zero rows",
        }
    if last_run_date > newest_row_date:
        return {
            "status": "row_missing",
            "reason": (
                f"scheduler last ran {last_run_date.isoformat()}, "
                f"newest row is {newest_row_date.isoformat()} — a run happened and no row landed"
            ),
        }
    if last_run_date == newest_row_date:
        return {
            "status": "indeterminate_same_day",
            "reason": (
                f"scheduler last ran {last_run_date.isoformat()} and the newest row is "
                f"also dated {newest_row_date.isoformat()} — rows carry only a date, not "
                "a time, so whether this row postdates the run cannot be determined"
            ),
        }
    return {
        "status": "ok",
        "reason": f"newest row {newest_row_date.isoformat()} covers scheduler's last run {last_run_date.isoformat()}",
    }


# --- Orchestration -------------------------------------------------------------


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def build_snapshot(
    notes: dict[str, Path] = BENCHMARK_NOTES,
    runs_dir: Path = RUNS_DIR,
    health_dir: Path = HEALTH_DIR,
    scheduled_tasks_dir: Path = SCHEDULED_TASKS_DIR,
    sessions_root: Path = DESKTOP_SESSIONS_ROOT,
) -> dict[str, Any]:
    note_summaries = load_all_note_summaries(notes)
    run_telemetry = load_run_telemetry(runs_dir)
    health = load_health_sidecars(health_dir)
    scheduler_status = load_scheduler_status(scheduled_tasks_dir, sessions_root)

    liveness: dict[str, Any] = {}
    for routine_name in notes:
        lookup = find_scheduler_last_run(routine_name, scheduler_status)
        verdict = classify_liveness(note_summaries[routine_name], lookup)
        liveness[routine_name] = {
            "status": verdict["status"],
            "reason": verdict["reason"],
            "scheduler_matched_ids": lookup.get("matched_ids", []),
            "scheduler_last_run_at": lookup.get("last_run_at"),
        }

    snapshot = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "notes": note_summaries,
        "run_telemetry": run_telemetry,
        "health": health,
        "scheduler": scheduler_status,
        "liveness": liveness,
    }
    return _jsonable(snapshot)


def render_human(snapshot: dict[str, Any]) -> str:
    lines: list[str] = []
    row_missing = [name for name, v in snapshot["liveness"].items() if v["status"] == "row_missing"]

    if row_missing:
        lines.append("!!! ROW_MISSING — capture ran but no row landed !!!")
        for name in row_missing:
            lines.append(f"  - {name}: {snapshot['liveness'][name]['reason']}")
        lines.append("")

    lines.append("Liveness by routine:")
    for name, v in snapshot["liveness"].items():
        lines.append(f"  [{v['status']:>11}] {name} — {v['reason']}")
    lines.append("")

    lines.append("Benchmark notes:")
    for name, s in snapshot["notes"].items():
        if s.get("error"):
            lines.append(f"  - {name}: ERROR — {s['error']}")
            continue
        by_arm = ", ".join(f"{arm}={n}" for arm, n in sorted(s["rows_by_arm"].items())) or "none"
        lines.append(
            f"  - {name}: {s['total_rows']} rows ({by_arm}), newest row {s['newest_row_date'] or 'n/a'}, "
            f"{len(s['columns'])} columns"
        )
        if s.get("malformed_rows"):
            lines.append(f"      malformed rows: {len(s['malformed_rows'])}")

    lines.append("")
    lines.append("Run telemetry (~/.rhize/procedural-memory/runs/*.jsonl):")
    if snapshot["run_telemetry"]["available"]:
        for artifact, counts in sorted(snapshot["run_telemetry"]["artifacts"].items()):
            lines.append(
                f"  - {artifact}: {counts['runs']} runs (ok={counts['ok']}, fail={counts['fail']}), "
                f"newest {counts['newest_started_at']}"
            )
    else:
        lines.append(f"  UNAVAILABLE — {snapshot['run_telemetry']['error']}")

    lines.append("")
    lines.append("Health sidecars:")
    if snapshot["health"]["available"]:
        for artifact, info in sorted(snapshot["health"]["artifacts"].items()):
            lines.append(f"  - {artifact}: {info}")
    else:
        lines.append(f"  UNAVAILABLE — {snapshot['health']['error']}")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="print the full JSON snapshot to stdout")
    ap.add_argument("--output", default=str(OUTPUT_PATH), help="where to write the JSON snapshot")
    args = ap.parse_args()

    snapshot = build_snapshot()

    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(snapshot, indent=2))
    else:
        print(render_human(snapshot))
        print(f"\n→ JSON snapshot written to {output_path}")

    any_row_missing = any(v["status"] == "row_missing" for v in snapshot["liveness"].values())
    return 2 if any_row_missing else 0


if __name__ == "__main__":
    sys.exit(main())
