#!/usr/bin/env python3
"""
skill-monitor — Track which Claude skills actually get invoked on this Mac.

Walks  ~/.claude/projects/**/*.jsonl AND
       ~/Library/Application Support/Claude/local-agent-mode-sessions/**/*.jsonl
extracts Skill `tool_use` events,
aggregates by skill / week / direct-vs-indirect / project / entrypoint,
and writes:
  - JSON raw + aggregated data (for downstream analysis)
  - Markdown report into the Obsidian vault weekly-reports folder
  - Session-level skill co-occurrence snapshot (data/skill-cooccurrence.json)
    — counts only (no prompt text, no project paths, no per-event
    timestamps); consumed by scripts/build_local_skill_map.py to build the
    skill-map's usage-cooccurs edges (skill-map-graph-substrate plan, Phase 3)

The signal being measured:
  A skill invocation is any `tool_use` block where `name == "Skill"` and
  `input.skill == "<skill-name>"`. These appear in:
    ~/.claude/projects/<encoded-proj>/<sessionId>.jsonl              (main, host CLI)
    ~/.claude/projects/<encoded-proj>/<sessionId>/subagents/*.jsonl  (indirect, host CLI)
  And, for the desktop ("Cowork") app:
    .../local-agent-mode-sessions/<root>/<user>/local_<id>/.claude/projects/...
    .../local-agent-mode-sessions/<root>/<user>/local_<id>/audit.jsonl  (alt schema)

Usage:
  python3 monitor.py                     # last 7 days, write MD into vault
  python3 monitor.py --days 0            # all-time
  python3 monitor.py --days 28
  python3 monitor.py --report-dir ./out  # override vault path (for testing)
  python3 monitor.py --cowork-dir ""     # disable Cowork scanning (debug)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

import git_sync
import paths

HOME = Path.home()
CLAUDE_PROJECTS = HOME / ".claude" / "projects"
COWORK_SESSIONS_ROOT = (
    HOME / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
)
COWORK_SESSION_META = (
    HOME / "Library" / "Application Support" / "Claude" / "claude-code-sessions"
)
# None when no single vault could be resolved (see paths.vault_root()) — the
# --report-dir flag then has no usable default and main() skips the vault
# write with a clear message instead of crashing.
DEFAULT_VAULT_REPORT_DIR = paths.vault_report_dir("weekly-reports")
DEFAULT_JSON_OUT = paths.data_dir() / "skill-usage.json"
SNAPSHOTS_DIR = paths.snapshots_dir()

# Skill-map Phase 3 (local overlay) consumer: scripts/build_local_skill_map.py
# reads this snapshot to derive `usage-cooccurs` edges. Counts only — no
# prompt text, no project paths, no per-event timestamps (see
# build_cooccurrence()'s docstring for the privacy contract).
DEFAULT_COOCCURRENCE_OUT = paths.data_dir() / "skill-cooccurrence.json"

# The canonical weekly cadence. Reports for this window keep the plain
# `YYYY-MM-DD-skill-usage.md` filename; all other windows are suffixed with
# their window tag (e.g. `-28d`, `-0d`) to avoid same-day clobbering.
WEEKLY_WINDOW_DAYS = 7

# A skill is invoked through one of two channels (see
# .claude/plans/capture-slash-command-skill-invocations.md):
#   - "skill_tool"    : a `tool_use` block with name == "Skill"
#   - "slash_command" : a `type:"user"` turn typing `/<name>` (often fires no
#                       Skill tool_use, so it is otherwise invisible)
CHANNEL_SKILL_TOOL = "skill_tool"
CHANNEL_SLASH_COMMAND = "slash_command"

# Built-in / framework slash commands that are NOT skills. Typed as `/<name>`
# but represent CLI control, not skill usage — excluded from the audit. Bare
# names only; anything namespaced (contains ':') is always a real plugin
# command and is never in this list. Unknown bare names default to COUNTED
# (under-pruning is safer than silently dropping real usage). Revisit quarterly.
COMMAND_BUILTINS = frozenset({
    "clear", "compact", "model", "effort", "goal", "loop", "batch", "resume",
    "help", "init", "config", "cost", "login", "logout", "status", "agents",
    "plugin", "usage-credits", "mcp", "export", "doctor", "memory", "vim",
    "terminal-setup", "bug", "pr-comments", "add-dir", "exit", "quit",
})

# Live slash-command envelope. MUST only be matched against a live
# `message.content` *string* on a `type:"user"` line — never against
# `attachment` payloads, which embed prior-session summaries that also contain
# `<command-name>` tags (historical echoes, not live invocations).
_COMMAND_NAME_RE = re.compile(r"<command-name>\s*/?([^<]+?)\s*</command-name>")


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def iso_to_week(iso_ts: str) -> str:
    """Convert an ISO-8601 timestamp to YYYY-Www (ISO week)."""
    dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def decode_project_path(encoded: str) -> str:
    """DEPRECATED fallback. Approx-decodes ~/.claude/projects/ folder names back to
    a filesystem path. Lossy because the CLI escapes '/' as '-' but real '-' in
    directory names collide. Every JSONL line carries a real `cwd`; prefer that.
    Kept only as a last-resort fallback when `cwd` is missing.
    """
    if encoded.startswith("-"):
        return "/" + encoded[1:].replace("-", "/")
    return encoded


def _cowork_local_id_from_path(jsonl_path: Path) -> str | None:
    """Walk path parents looking for the `local_<UUID>` directory that names a
    Cowork session. Returns the directory name or None if not on a Cowork path."""
    for p in jsonl_path.parents:
        if p.name.startswith("local_"):
            return p.name
    return None


def extract_skill_events(
    jsonl_path: Path, source_type: str
) -> Iterator[dict]:
    """Yield a dict for every Skill `tool_use` in `jsonl_path` (main/subagent schema)."""
    try:
        fp = jsonl_path.open("r", encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"  ! cannot open {jsonl_path}: {e}", file=sys.stderr)
        return
    cowork_local_id = _cowork_local_id_from_path(jsonl_path)
    with fp:
        for line_no, raw in enumerate(fp, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg = obj.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                if block.get("name") != "Skill":
                    continue

                inp = block.get("input") or {}
                skill = inp.get("skill")
                if not skill:
                    continue

                if source_type == "main":
                    project_dir = jsonl_path.parent.name
                else:  # subagent: .../<proj>/<session>/subagents/<agent>.jsonl
                    project_dir = jsonl_path.parents[2].name

                yield {
                    "skill": skill,
                    "args": inp.get("args"),
                    "channel": CHANNEL_SKILL_TOOL,
                    "source_type": source_type,          # 'main' | 'subagent'
                    "uuid": obj.get("uuid"),
                    "session_id": obj.get("sessionId"),
                    "agent_id": obj.get("agentId"),
                    "agent_slug": None,                  # resolved post-hoc from main toolUseResults
                    "entrypoint": obj.get("entrypoint"),
                    "cwd": obj.get("cwd"),
                    "git_branch": obj.get("gitBranch"),
                    "model": msg.get("model"),
                    "timestamp": obj.get("timestamp"),
                    "project_dir_encoded": project_dir,
                    "project_dir_decoded": decode_project_path(project_dir),
                    "cowork_local_id": cowork_local_id,
                    "transcript_file": str(jsonl_path),
                    "transcript_line": line_no,
                }


def extract_command_events(
    jsonl_path: Path, source_type: str
) -> Iterator[dict]:
    """Yield a dict for every *live* slash-command invocation in `jsonl_path`.

    A live slash command is a `type:"user"` line whose `message.content` is a
    STRING containing a `<command-name>/foo</command-name>` envelope. We deliberately
    ignore the tag when it appears anywhere else (attachment payloads, assistant
    echoes), because SessionStart hook summaries embed prior-session text that
    also contains `<command-name>` tags — those are historical, not live.

    Built-in CLI commands (see COMMAND_BUILTINS) are skipped; everything else,
    including all namespaced (`plugin:name`) commands, counts as a skill use on
    the `slash_command` channel.
    """
    try:
        fp = jsonl_path.open("r", encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"  ! cannot open {jsonl_path}: {e}", file=sys.stderr)
        return
    cowork_local_id = _cowork_local_id_from_path(jsonl_path)
    with fp:
        for line_no, raw in enumerate(fp, 1):
            raw = raw.strip()
            if not raw or "<command-name>" not in raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if obj.get("type") != "user":
                continue
            msg = obj.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, str):     # live command turns carry a str
                continue
            m = _COMMAND_NAME_RE.search(content)
            if not m:
                continue
            name = m.group(1).strip().lstrip("/")
            if not name or name in COMMAND_BUILTINS:
                continue

            args_m = re.search(r"<command-args>([^<]*)</command-args>", content)

            if source_type == "main":
                project_dir = jsonl_path.parent.name
            else:  # subagent: .../<proj>/<session>/subagents/<agent>.jsonl
                project_dir = jsonl_path.parents[2].name

            yield {
                "skill": name,
                "args": (args_m.group(1).strip() if args_m else None) or None,
                "channel": CHANNEL_SLASH_COMMAND,
                "source_type": source_type,
                "uuid": obj.get("uuid"),
                "session_id": obj.get("sessionId"),
                "agent_id": obj.get("agentId"),
                "agent_slug": None,
                "entrypoint": obj.get("entrypoint"),
                "cwd": obj.get("cwd"),
                "git_branch": obj.get("gitBranch"),
                "model": msg.get("model"),
                "timestamp": obj.get("timestamp"),
                "project_dir_encoded": project_dir,
                "project_dir_decoded": decode_project_path(project_dir),
                "cowork_local_id": cowork_local_id,
                "transcript_file": str(jsonl_path),
                "transcript_line": line_no,
            }


_DEVFLOW_DOCTOR_CMD_RE = re.compile(r"devflow\.py[^\n]*\bdoctor\b")


def extract_devflow_doctor_events(jsonl_path: Path, source_type: str) -> Iterator[dict]:
    """Yield one dict per `devflow.py doctor` invocation found in `jsonl_path`,
    carrying only a redacted healthy/degraded/unknown flag — never the
    command's full text, the inspected plugin/repo path, or any other file
    content (Task 9: "doctor degradation events ... without ... client
    paths").

    Correlates a Bash `tool_use` block whose `command` input mentions
    `devflow.py ... doctor` with the `tool_result` block that answers it
    (matched by `tool_use_id`, the standard Anthropic Messages tool_result
    schema). Looks for the literal `"healthy": true`/`"healthy": false`
    substring that `devflow.py doctor --json`'s `json.dumps(..., indent=2)`
    always emits (schemas/devflow-evidence-v1.schema.json documents the
    `evidence` contract; `doctor`'s own JSON shape is documented in
    devflow.py's module docstring) — deliberately a substring check, not a
    JSON parse, so this can never fail on unrelated tool output.

    Fails closed throughout: any parse error, missing field, or unrecognized
    shape is skipped rather than raised, so transcript-format drift can't
    break the wider scan this function is called from.
    """
    try:
        fp = jsonl_path.open("r", encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"  ! cannot open {jsonl_path}: {e}", file=sys.stderr)
        return

    cowork_local_id = _cowork_local_id_from_path(jsonl_path)
    pending: dict[str, dict] = {}  # tool_use_id -> partial event (outcome not yet known)
    with fp:
        for line_no, raw in enumerate(fp, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg = obj.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue

                if block.get("type") == "tool_use" and block.get("name") == "Bash":
                    inp = block.get("input") or {}
                    command = inp.get("command")
                    tool_use_id = block.get("id")
                    if not (isinstance(command, str) and tool_use_id):
                        continue
                    if not _DEVFLOW_DOCTOR_CMD_RE.search(command):
                        continue
                    if source_type == "main":
                        project_dir = jsonl_path.parent.name
                    else:  # subagent: .../<proj>/<session>/subagents/<agent>.jsonl
                        project_dir = jsonl_path.parents[2].name
                    pending[tool_use_id] = {
                        "channel": "devflow_doctor",
                        "source_type": source_type,
                        "session_id": obj.get("sessionId"),
                        "timestamp": obj.get("timestamp"),
                        "project_dir_encoded": project_dir,
                        "project_dir_decoded": decode_project_path(project_dir),
                        "cowork_local_id": cowork_local_id,
                        "transcript_file": str(jsonl_path),
                        "transcript_line": line_no,
                        "healthy": None,  # filled in below once its tool_result lands
                    }

                elif block.get("type") == "tool_result":
                    tool_use_id = block.get("tool_use_id")
                    event = pending.pop(tool_use_id, None) if tool_use_id else None
                    if event is None:
                        continue
                    result_content = block.get("content")
                    text = ""
                    if isinstance(result_content, str):
                        text = result_content
                    elif isinstance(result_content, list):
                        text = " ".join(
                            part.get("text", "")
                            for part in result_content
                            if isinstance(part, dict) and part.get("type") == "text"
                        )
                    if '"healthy": true' in text:
                        event["healthy"] = True
                    elif '"healthy": false' in text:
                        event["healthy"] = False
                    yield event

    # Any tool_use left pending (no matching tool_result observed in this
    # file, e.g. a transcript truncated mid-call) is reported as an
    # invocation with unknown outcome — never silently dropped or counted as
    # healthy.
    for event in pending.values():
        yield event


def extract_skill_events_from_audit(jsonl_path: Path) -> Iterator[dict]:
    """Cowork audit.jsonl uses a snake_case schema (session_id, parent_tool_use_id)
    and `system`-typed lines have content at the top level rather than under
    `message`. For Skill detection we only care about lines with `message.content`
    arrays containing tool_use blocks — same logic as main, but key names differ.
    Treat all events as source_type='audit' so we can debug overlap with main.
    """
    try:
        fp = jsonl_path.open("r", encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"  ! cannot open {jsonl_path}: {e}", file=sys.stderr)
        return
    cowork_local_id = _cowork_local_id_from_path(jsonl_path)
    # First pass: capture session-level cwd from any `system` line (audit assistant
    # lines themselves don't carry cwd).
    audit_cwd: str | None = None
    audit_entrypoint: str | None = None
    with fp:
        lines = fp.readlines()
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "system":
            audit_cwd = audit_cwd or obj.get("cwd")
            audit_entrypoint = audit_entrypoint or obj.get("entrypoint")
            if audit_cwd:
                break
    for line_no, raw in enumerate(lines, 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue

        msg = obj.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            if block.get("name") != "Skill":
                continue

            inp = block.get("input") or {}
            skill = inp.get("skill")
            if not skill:
                continue

            yield {
                "skill": skill,
                "args": inp.get("args"),
                "channel": CHANNEL_SKILL_TOOL,
                "source_type": "audit",
                "uuid": obj.get("uuid"),
                "session_id": obj.get("session_id"),  # snake_case
                "agent_id": obj.get("agent_id") or obj.get("agentId"),
                "agent_slug": None,
                "entrypoint": audit_entrypoint or "local-agent",
                "cwd": audit_cwd,
                "git_branch": None,
                "model": msg.get("model"),
                "timestamp": obj.get("timestamp") or obj.get("_audit_timestamp"),
                "project_dir_encoded": None,
                "project_dir_decoded": None,
                "cowork_local_id": cowork_local_id,
                "transcript_file": str(jsonl_path),
                "transcript_line": line_no,
            }


def extract_agent_type_map(jsonl_path: Path) -> Iterator[tuple[str, str]]:
    """Yield (agent_id, agent_type) from any `toolUseResult` blocks in a main jsonl.

    Cowork desktop and host CLI both record subagent-completion data here;
    the inner `agent_id` matches the agentId field on the corresponding
    subagent transcript, and `agent_type` is the canonical subagent slug
    (e.g. 'code-reviewer', 'general-purpose'). This is the only reliable
    source of agent-type attribution — the subagent transcripts themselves
    carry only the session slug, not the agent type.
    """
    try:
        fp = jsonl_path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with fp:
        for raw in fp:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            tur = obj.get("toolUseResult")
            if not isinstance(tur, dict):
                continue
            agent_id = tur.get("agentId")
            agent_type = tur.get("agentType")
            if agent_id and agent_type:
                yield agent_id, agent_type


def _is_excluded(jsonl_path: Path) -> bool:
    """Skip plugin marketplaces / test fixtures that ship inside Cowork sandboxes."""
    s = str(jsonl_path)
    return "/plugins/" in s or "/marketplaces/" in s


def walk_projects(
    projects_root: Path, mtime_cutoff: float | None = None
) -> Iterator[tuple[Path, str]]:
    """Yield (jsonl_path, source_type) for every session/subagent transcript under
    a host-style ~/.claude/projects/ tree."""
    if not projects_root.exists():
        return
    for project_dir in projects_root.iterdir():
        if not project_dir.is_dir():
            continue
        # main session transcripts: project_dir/<sessionId>.jsonl
        for f in project_dir.glob("*.jsonl"):
            if _is_excluded(f):
                continue
            if mtime_cutoff is not None:
                try:
                    if f.stat().st_mtime < mtime_cutoff:
                        continue
                except OSError:
                    continue
            yield f, "main"
        # subagent transcripts: project_dir/<sessionId>/subagents/*.jsonl
        for sess_dir in project_dir.iterdir():
            if not sess_dir.is_dir():
                continue
            subagents_dir = sess_dir / "subagents"
            if subagents_dir.is_dir():
                for f in subagents_dir.glob("*.jsonl"):
                    if _is_excluded(f):
                        continue
                    if mtime_cutoff is not None:
                        try:
                            if f.stat().st_mtime < mtime_cutoff:
                                continue
                        except OSError:
                            continue
                    yield f, "subagent"


def walk_cowork_projects(
    cowork_root: Path, mtime_cutoff: float | None = None
) -> Iterator[tuple[Path, str]]:
    """Yield (jsonl_path, source_type) for transcripts in the Cowork desktop tree.

    Each Cowork session lives at:
        <cowork_root>/<rootId>/<userId>/local_<sessId>/

    Inside that directory:
        .claude/projects/<encoded-proj>/<sess>.jsonl              -> 'main'
        .claude/projects/<encoded-proj>/<sess>/subagents/*.jsonl  -> 'subagent'
        audit.jsonl                                               -> 'audit'

    Filter out plugin/marketplace test fixtures that Cowork bundles inside
    each session sandbox — those are not real user activity.
    """
    if not cowork_root.exists():
        return
    # Yield every <local_*> dir's interior projects tree.
    for local_dir in cowork_root.glob("*/*/local_*"):
        if not local_dir.is_dir():
            continue
        projects_dir = local_dir / ".claude" / "projects"
        if projects_dir.is_dir():
            yield from walk_projects(projects_dir, mtime_cutoff=mtime_cutoff)
        # NOTE: audit.jsonl scanning is intentionally disabled.
        # Verified 2026-05-08: 100% of Skill events in Cowork audit.jsonl
        # files share (uuid, session_id) with the main session transcript,
        # i.e. they are fully redundant. Keeping the parser
        # (extract_skill_events_from_audit) available for future use, but the
        # walk does not yield them by default — otherwise the defensive
        # dedup guard fires loudly on every run for noise-only duplicates.


def load_cowork_origin_map() -> dict[str, str]:
    """Build {local_<id> -> originCwd} from Cowork session metadata files.

    The metadata file's `sessionId` is identical to the Cowork session
    directory name (`local_<UUID>`). Used to attribute Cowork events
    (whose `cwd` is a sandbox path like `/sessions/...`) back to the
    user-side project they originated from.
    """
    out: dict[str, str] = {}
    if not COWORK_SESSION_META.exists():
        return out
    for f in COWORK_SESSION_META.rglob("local_*.json"):
        try:
            with f.open("r", encoding="utf-8", errors="replace") as fp:
                d = json.load(fp)
        except (OSError, json.JSONDecodeError):
            continue
        sid = d.get("sessionId")
        origin = d.get("originCwd")
        if sid and origin:
            out[sid] = origin
    return out


# ---------------------------------------------------------------------------
# Skill-name canonicalization
# ---------------------------------------------------------------------------
# Some skills surface under multiple names because different runtimes sanitize
# the SKILL.md `name:` field differently. The clearest case: the delegation
# skill historically carried `name: rhize:delegate-to-tom` (a colon in a
# standalone skill name), which the host CLI kept verbatim, the Cowork harness
# flattened to `rhizedelegate-to-tom`, and the bundled copy re-namespaced to
# `anthropic-skills:rhizedelegate-to-tom`. It then moved into the `rhize-ops`
# plugin as a plain `delegate-to-tom` slug → `rhize-ops:delegate-to-tom`, and
# was later generalized/renamed again to `rhize-ops:delegate-to-teammate`
# (2026-07-16, to remove a hardcoded person's name from the skill itself).
# This map rolls every historical variant up to the current canonical name so
# week-over-week ranking isn't fragmented. Add new variant→canonical pairs
# here as they are discovered.
CANONICAL_ALIASES: dict[str, str] = {
    "rhize:delegate-to-tom": "rhize-ops:delegate-to-teammate",
    "rhizedelegate-to-tom": "rhize-ops:delegate-to-teammate",
    "anthropic-skills:rhizedelegate-to-tom": "rhize-ops:delegate-to-teammate",
    "delegate-to-tom": "rhize-ops:delegate-to-teammate",
    "rhize-ops:delegate-to-tom": "rhize-ops:delegate-to-teammate",
    "delegate-to-teammate": "rhize-ops:delegate-to-teammate",
}


def canonical_skill(name: str) -> str:
    """Map a raw skill name to its canonical form (see CANONICAL_ALIASES)."""
    return CANONICAL_ALIASES.get(name, name)


# ---------------------------------------------------------------------------
# Dev Flow control-plane observability (Task 9,
# .claude/plans/rhize-devflow-v3-engineering-control-plane.md). Deprecated ->
# canonical command mapping for the 2.12.0 compatibility window's six browser/
# mutation adapters plus the Context Manager impact-map adapter. Used only to
# LABEL already-counted invocations as canonical vs. deprecated in the report
# — it does not change how events are extracted or counted.
# ---------------------------------------------------------------------------
DEVFLOW_DEPRECATED_TO_CANONICAL: dict[str, str] = {
    "rhize-devflow:browser-debug": "rhize-devflow:browser-qa",
    "rhize-devflow:browser-help": "rhize-devflow:browser-qa",
    "rhize-devflow:browser-perf": "rhize-devflow:browser-qa",
    "rhize-devflow:browser-test": "rhize-devflow:browser-qa",
    "rhize-devflow:mutation-analyze": "rhize-devflow:mutation-check --all",
    "rhize-devflow:mutation-fix": "rhize-devflow:mutation-check --fix-plan",
    "rhize-context-manager:impact-map": "rhize-devflow:impact-map",
}


def build_devflow_control_plane_section(
    totals: "Counter", doctor_events: list[dict] | None = None
) -> dict:
    """Dev Flow 2.12.0 compatibility-window observability (Task 9): label each
    already-counted command invocation as canonical or deprecated, and
    summarize `devflow.py doctor` degradation from `doctor_events` (see
    `extract_devflow_doctor_events`). A name this run's transcripts never
    mentioned is reported as "no data", never as zero usage — the plan's
    explicit requirement (Observation window: "do not interpret missing
    telemetry as zero usage").
    """
    doctor_events = doctor_events or []

    deprecated: dict[str, dict] = {}
    for old_name, canonical_name in DEVFLOW_DEPRECATED_TO_CANONICAL.items():
        count = totals.get(old_name)
        deprecated[old_name] = {
            "canonical": canonical_name,
            "invocations": count if count is not None else "no data",
        }

    canonical: dict[str, "int | str"] = {}
    canonical_names = sorted(set(DEVFLOW_DEPRECATED_TO_CANONICAL.values()) | {"rhize-devflow:doctor"})
    for full_name in canonical_names:
        base_name = full_name.split(" ", 1)[0]  # strip a "--all"/"--fix-plan" flag suffix
        count = totals.get(base_name)
        canonical[full_name] = count if count is not None else "no data"

    healthy = sum(1 for e in doctor_events if e.get("healthy") is True)
    degraded = sum(1 for e in doctor_events if e.get("healthy") is False)
    unknown = sum(1 for e in doctor_events if e.get("healthy") is None)
    doctor_summary = {
        "invocations": len(doctor_events) if doctor_events else "no data",
        "healthy": healthy,
        "degraded": degraded,
        "unknown_outcome": unknown,
    }

    return {"deprecated": deprecated, "canonical": canonical, "doctor": doctor_summary}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def build_report(
    events: list[dict],
    since_days: int | None = None,
    cowork_origin_map: dict[str, str] | None = None,
    doctor_events: list[dict] | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=since_days) if since_days else None
    cowork_origin_map = cowork_origin_map or {}

    filtered: list[dict] = []
    for e in events:
        ts = e.get("timestamp")
        if cutoff is not None and ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except ValueError:
                pass
        e["skill"] = canonical_skill(e["skill"])
        filtered.append(e)

    # --- Channel reconciliation (avoid cross-channel double counting) -------
    # If a (session, skill) pair was recorded on the skill_tool channel, drop any
    # overlapping slash_command events for that same pair — the tool_use already
    # counts it. Keep slash_command events that are the ONLY signal: those are
    # the real blind spot the channel was added to capture. Within-channel
    # multiplicity is preserved (3 tool_use calls still count as 3).
    skill_tool_keys = {
        (e.get("session_id"), e["skill"])
        for e in filtered
        if e.get("channel") == CHANNEL_SKILL_TOOL
    }
    raw_total = len(filtered)
    reconciled = [
        e for e in filtered
        if e.get("channel") == CHANNEL_SKILL_TOOL
        or (e.get("session_id"), e["skill"]) not in skill_tool_keys
    ]
    overlap_deduped = raw_total - len(reconciled)
    by_channel: Counter = Counter(
        e.get("channel", CHANNEL_SKILL_TOOL) for e in reconciled
    )
    top_by_channel: dict[str, list] = {}
    for ch in (CHANNEL_SKILL_TOOL, CHANNEL_SLASH_COMMAND):
        ch_counts = Counter(e["skill"] for e in reconciled if e.get("channel") == ch)
        top_by_channel[ch] = ch_counts.most_common(15)

    totals: Counter = Counter(e["skill"] for e in reconciled)
    by_week: dict[str, Counter] = defaultdict(Counter)
    direct: Counter = Counter()
    indirect_real: Counter = Counter()        # subagent work, excluding compaction
    indirect_compaction: Counter = Counter()  # acompact-* background agents
    by_project: dict[str, Counter] = defaultdict(Counter)
    by_entrypoint: Counter = Counter()
    by_source_type: Counter = Counter()
    indirect_by_slug: dict[str, Counter] = defaultdict(Counter)

    for e in reconciled:
        ts = e.get("timestamp")
        if ts:
            try:
                by_week[iso_to_week(ts)][e["skill"]] += 1
            except Exception:
                pass

        # The cleanest direct/indirect signal is the file location:
        # a skill invocation inside a subagent transcript is always indirect.
        # Audit events roll into 'direct' for the headline numbers but keep
        # source_type for downstream debugging.
        if e["source_type"] == "subagent":
            agent_id = e.get("agent_id") or ""
            if agent_id.startswith("acompact-"):
                indirect_compaction[e["skill"]] += 1
            else:
                indirect_real[e["skill"]] += 1
                slug = e.get("agent_slug") or "unknown"
                indirect_by_slug[slug][e["skill"]] += 1
        else:
            direct[e["skill"]] += 1

        by_source_type[e["source_type"]] += 1

        # Project rollup: prefer real cwd over the lossy decoded folder name.
        # For Cowork sandbox cwds, swap in the metadata-derived originCwd.
        cwd = e.get("cwd") or ""
        if cwd.startswith("/sessions/"):
            local_id = e.get("cowork_local_id")
            real = cowork_origin_map.get(local_id) if local_id else None
            if real:
                cwd = real
            else:
                cwd = f"[Cowork: {cwd}]"
        bucket = cwd or e.get("project_dir_decoded") or "unknown"
        by_project[bucket][e["skill"]] += 1
        if e.get("entrypoint"):
            by_entrypoint[e["entrypoint"]] += 1

    return {
        "generated_at": now.isoformat(),
        "window_days": since_days,
        "total_invocations": sum(totals.values()),
        "total_raw_invocations": raw_total,
        "overlap_deduped": overlap_deduped,
        "by_channel": dict(by_channel.most_common()),
        "top_by_channel": top_by_channel,
        "unique_skills_used": len(totals),
        "top_skills": totals.most_common(50),
        "direct_top": direct.most_common(50),
        "indirect_top": indirect_real.most_common(50),
        "indirect_compaction_top": indirect_compaction.most_common(20),
        "by_week": {
            w: dict(c.most_common(25)) for w, c in sorted(by_week.items())
        },
        "by_project": {
            p: dict(c.most_common(15)) for p, c in by_project.items()
        },
        "by_entrypoint": dict(by_entrypoint.most_common()),
        "by_source_type": dict(by_source_type.most_common()),
        "indirect_by_slug": {
            slug: dict(c.most_common(10))
            for slug, c in sorted(
                indirect_by_slug.items(),
                key=lambda kv: -sum(kv[1].values()),
            )
        },
        "devflow_control_plane": build_devflow_control_plane_section(totals, doctor_events),
    }


#  minimum distinct sessions an ordered (A then B) adjacency must appear in
# before it's considered a real "follows" signal rather than noise — same
# threshold the skill-map-relationships-v2 design pins for the `follows`
# edge (skill-map-relationships-v2 design doc, decision 1).
MIN_FOLLOWS_SESSIONS = 2


def build_cooccurrence(events: list[dict], since_days: int | None = None) -> dict:
    """Aggregate session-level skill co-occurrence for the skill-map local
    overlay (skill-map-graph-substrate plan, Phase 3), plus ordered
    time-adjacent pairs for the `follows` edge (skill-map-relationships-v2
    design, decision 1).

    A skill "co-occurs" with another when both were invoked (Skill tool_use
    or slash command, main or subagent — same channel reconciliation the
    rest of this module already does) within the same session_id. Verified
    empirically (2026-08-09) that subagent transcripts share their parent's
    session_id, so this genuinely captures cross-invocation co-occurrence,
    not just same-transcript co-occurrence.

    "Follows" mining: within each session, skill invocations are sorted by
    timestamp and walked in order; each time-adjacent (A, B) pair of
    DISTINCT skills (immediate neighbors only, not every later skill) is
    recorded once per session. A pair is only emitted in `orderedPairs` once
    it has occurred in at least MIN_FOLLOWS_SESSIONS distinct sessions —
    below that it's noise, not a real "commonly invoked after" signal.

    PRIVACY CONTRACT — this function's output must never carry:
      - prompt text
      - project paths / cwd
      - per-event timestamps (only the coarse `windowDays` label survives)
    Only skill names and integer counts leave this function. `session_id`
    (an opaque UUID, carrying no path/prompt information) is used solely as
    an internal grouping key and is discarded before returning.

    Returns {windowDays, totalSessions, pairs, totals, orderedPairs} — see
    scripts/build_local_skill_map.py for how this snapshot is consumed.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=since_days) if since_days else None

    sessions: dict[str, set[str]] = defaultdict(set)
    session_seq: dict[str, list[tuple[str, str]]] = defaultdict(list)  # sid -> [(ts, skill), ...]
    for e in events:
        ts = e.get("timestamp")
        if cutoff is not None and ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except ValueError:
                pass
        sid = e.get("session_id")
        skill = canonical_skill(e["skill"]) if e.get("skill") else None
        if not sid or not skill:
            continue
        sessions[sid].add(skill)
        session_seq[sid].append((ts or "", skill))

    totals: Counter = Counter()
    pair_counts: Counter = Counter()
    for skills in sessions.values():
        ordered = sorted(skills)
        for s in ordered:
            totals[s] += 1
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pair_counts[(ordered[i], ordered[j])] += 1

    pairs = [
        {"a": a, "b": b, "sessions": n}
        for (a, b), n in sorted(
            pair_counts.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])
        )
    ]

    follows_session_counts: Counter = Counter()  # (a, b) ordered -> distinct session count
    for seq in session_seq.values():
        seq_sorted = sorted(seq, key=lambda t: t[0])
        seen_this_session: set[tuple[str, str]] = set()
        prev_skill = None
        for _ts, skill in seq_sorted:
            if prev_skill is not None and skill != prev_skill:
                seen_this_session.add((prev_skill, skill))
            prev_skill = skill
        for pair in seen_this_session:
            follows_session_counts[pair] += 1

    ordered_pairs = [
        {"a": a, "b": b, "sessions": n}
        for (a, b), n in sorted(
            follows_session_counts.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])
        )
        if n >= MIN_FOLLOWS_SESSIONS
    ]

    return {
        "windowDays": since_days or 0,
        "totalSessions": len(sessions),
        "pairs": pairs,
        "totals": dict(sorted(totals.items())),
        "orderedPairs": ordered_pairs,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(report: dict, files_scanned: int) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    window = report["window_days"]
    window_label = f"last {window} days" if window else "all-time"
    total = report["total_invocations"]
    unique = report["unique_skills_used"]

    lines: list[str] = []
    lines.append("---")
    lines.append("type: weekly-skill-report")
    lines.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"window: {window_label}")
    lines.append(f"total-invocations: {total}")
    lines.append(f"unique-skills: {unique}")
    lines.append("tags:")
    lines.append("  - skill-audit")
    lines.append("  - claude-code")
    lines.append("  - monitoring")
    lines.append("---")
    lines.append("")
    lines.append(f"# Skill Usage Report — {now_str}")
    lines.append("")
    lines.append(
        f"> **{files_scanned}** transcripts scanned • "
        f"**{total}** skill invocations ({window_label}, reconciled across the "
        f"Skill-tool and slash-command channels) • "
        f"**{unique}** unique skills used."
    )
    lines.append("")
    lines.append(
        "> Related: [[Anthropic Runs Hundreds of Skills - Only 12 Run Weekly]] • "
        "[[Skill Audit and Monitoring System]]"
    )
    lines.append("")

    # Top skills
    lines.append("## Top skills")
    lines.append("")
    lines.append("| Rank | Skill | Count |")
    lines.append("| ---: | --- | ---: |")
    for i, (s, c) in enumerate(report["top_skills"][:25], 1):
        lines.append(f"| {i} | `{s}` | {c} |")
    lines.append("")

    # By invocation channel
    by_channel = report.get("by_channel") or {}
    if by_channel:
        lines.append("## By invocation channel")
        lines.append("")
        lines.append(
            "*Two ways a skill gets invoked: the **Skill tool** (`tool_use`) and "
            "**slash commands** (`/name`). Slash commands often fire no Skill "
            "tool_use, so they were historically invisible. Counts below are "
            "post-reconciliation: a `(session, skill)` pair recorded on both "
            "channels is counted once (under skill_tool).*"
        )
        lines.append("")
        st = by_channel.get(CHANNEL_SKILL_TOOL, 0)
        sc = by_channel.get(CHANNEL_SLASH_COMMAND, 0)
        deduped = report.get("overlap_deduped", 0)
        raw = report.get("total_raw_invocations", st + sc)
        lines.append(f"- `skill_tool` — {st}")
        lines.append(f"- `slash_command` — {sc}")
        lines.append(
            f"- *raw events before reconciliation: {raw}; "
            f"cross-channel overlaps deduped: {deduped}*"
        )
        lines.append("")
        top_ch = report.get("top_by_channel") or {}
        sc_top = top_ch.get(CHANNEL_SLASH_COMMAND) or []
        if sc_top:
            lines.append("Top slash-command-channel skills (the recovered blind spot):")
            lines.append("")
            lines.append("| Skill | Count |")
            lines.append("| --- | ---: |")
            for s, c in sc_top[:10]:
                lines.append(f"| `{s}` | {c} |")
            lines.append("")

    # Direct vs indirect
    lines.append("## Direct vs. indirect")
    lines.append("")
    lines.append(
        "*Direct* = invoked in the main session. "
        "*Indirect* = invoked by a subagent (Task-delegated work)."
    )
    lines.append("")
    lines.append("### Top 15 direct")
    lines.append("")
    lines.append("| Skill | Count |")
    lines.append("| --- | ---: |")
    for s, c in report["direct_top"][:15]:
        lines.append(f"| `{s}` | {c} |")
    lines.append("")
    lines.append("### Top 15 indirect (real subagent work)")
    lines.append("")
    lines.append("| Skill | Count |")
    lines.append("| --- | ---: |")
    for s, c in report["indirect_top"][:15]:
        lines.append(f"| `{s}` | {c} |")
    lines.append("")
    if report["indirect_compaction_top"]:
        lines.append("### Top 5 indirect (auto-compaction)")
        lines.append("")
        lines.append(
            "*Background context-compaction agents (`agentId` starts with `acompact-`). "
            "Bucketed separately so they don't crowd real subagent-delegation signal.*"
        )
        lines.append("")
        lines.append("| Skill | Count |")
        lines.append("| --- | ---: |")
        for s, c in report["indirect_compaction_top"][:5]:
            lines.append(f"| `{s}` | {c} |")
        lines.append("")

    # By project
    lines.append("## By project")
    lines.append("")
    for proj, skills in sorted(
        report["by_project"].items(),
        key=lambda kv: -sum(kv[1].values()),
    ):
        if not skills:
            continue
        total_p = sum(skills.values())
        lines.append(f"### `{proj}` — {total_p} invocations")
        lines.append("")
        for s, c in list(skills.items())[:8]:
            lines.append(f"- `{s}` — {c}")
        lines.append("")

    # By entrypoint
    lines.append("## By entrypoint")
    lines.append("")
    for ep, c in report["by_entrypoint"].items():
        lines.append(f"- `{ep}` — {c}")
    lines.append("")

    # Week-by-week
    lines.append("## Week-by-week")
    lines.append("")
    for w, skills in report["by_week"].items():
        top3 = ", ".join(
            f"`{s}` ({n})" for s, n in list(skills.items())[:3]
        )
        lines.append(
            f"- **{w}** — {sum(skills.values())} total; top: {top3}"
        )
    lines.append("")

    # Action items
    lines.append("## Action items")
    lines.append("")
    lines.append(
        "- [ ] Any skill with **0 invocations in the last 28 days** and "
        "not on a keep-list → candidate to disable."
    )
    lines.append(
        "- [ ] Any skill with **high indirect but low direct** usage → "
        "consider elevating its trigger description."
    )
    lines.append(
        "- [ ] Any **project with unexpected skill dominance** → inspect "
        "for quality (may indicate a runaway prompt pattern)."
    )
    lines.append("")

    # NEW: Indirect skill use by subagent type (added at bottom; positional-parser-safe)
    if report.get("indirect_by_slug"):
        lines.append("## Indirect skill use by subagent type")
        lines.append("")
        lines.append(
            "*Subagent-delegated skill invocations grouped by the parent's "
            "`subagent_type`. Resolved from each main session's "
            "`toolUseResult.agentType`. Auto-compaction agents excluded.*"
        )
        lines.append("")
        lines.append("| Agent type | Top skill | Count |")
        lines.append("| --- | --- | ---: |")
        for slug, skills in report["indirect_by_slug"].items():
            if not skills:
                continue
            top_skill, top_count = next(iter(skills.items()))
            lines.append(f"| `{slug}` | `{top_skill}` | {top_count} |")
        lines.append("")

    # NEW: Limitations footer
    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- **Slash commands are now counted** (as of 2026-06) via the "
        "`slash_command` channel — see *By invocation channel*. Residual gaps: "
        "built-in CLI commands are filtered by a maintained denylist (a new "
        "built-in could be miscounted until added), and **hook-triggered skills "
        "are out of scope** (measured as effectively non-existent: of ~380k hook "
        "attachments in a 28-day window only ~38 referenced a skill, all embedded "
        "prior-session echoes, not live runs)."
    )
    lines.append(
        "- **No surface-level breakdown for terminals vs. IDEs.** Both log as "
        "`entrypoint: cli`. Cowork desktop-app sessions log as `entrypoint: local-agent`."
    )
    lines.append(
        "- **Compaction agents are bucketed separately.** Subagents whose "
        "`agentId` starts with `acompact-` are background context-compaction "
        "agents, not user-delegated work; their skill use is reported in a "
        "dedicated subsection of \"Direct vs. indirect\"."
    )
    lines.append("")

    devflow = report.get("devflow_control_plane")
    if devflow:
        lines.append("## Dev Flow Control-Plane Usage")
        lines.append("")
        lines.append(
            "Compatibility-window observability for the rhize-devflow 2.12.0 release "
            "(Task 9, `.claude/plans/rhize-devflow-v3-engineering-control-plane.md`). "
            "`no data` means this window's transcripts never mentioned the name — "
            "**not** zero usage; see that plan's Observation window section."
        )
        lines.append("")
        lines.append("### Deprecated adapters (2.12.0 compatibility window)")
        lines.append("")
        lines.append("| Deprecated command | Canonical replacement | Invocations |")
        lines.append("|---|---|---|")
        for old_name, info in sorted(devflow["deprecated"].items()):
            lines.append(f"| `{old_name}` | `{info['canonical']}` | {info['invocations']} |")
        lines.append("")
        lines.append("### Canonical commands")
        lines.append("")
        lines.append("| Canonical command | Invocations |")
        lines.append("|---|---|")
        for name, count in sorted(devflow["canonical"].items()):
            lines.append(f"| `{name}` | {count} |")
        lines.append("")
        doctor = devflow["doctor"]
        lines.append(
            f"### `devflow.py doctor` outcomes — invocations: {doctor['invocations']}, "
            f"healthy: {doctor['healthy']}, degraded: {doctor['degraded']}, "
            f"unknown outcome: {doctor['unknown_outcome']}"
        )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Monitor Claude skill invocations across session transcripts.",
    )
    ap.add_argument("--projects-dir", default=str(CLAUDE_PROJECTS),
                    help=f"default: {CLAUDE_PROJECTS}")
    ap.add_argument("--cowork-dir", default=str(COWORK_SESSIONS_ROOT),
                    help=("Cowork desktop-app sessions root. "
                          "Pass empty string to disable. "
                          f"default: {COWORK_SESSIONS_ROOT}"))
    ap.add_argument("--report-dir",
                    default=str(DEFAULT_VAULT_REPORT_DIR) if DEFAULT_VAULT_REPORT_DIR else None,
                    help=("where to write the markdown report (default: the "
                          "Obsidian vault, if exactly one is configured — see "
                          "paths.vault_root(); omit or pass --report-dir to "
                          "write elsewhere)"))
    ap.add_argument("--json-out", default=str(DEFAULT_JSON_OUT),
                    help=f"default: {DEFAULT_JSON_OUT}")
    ap.add_argument("--cooccurrence-out", default=str(DEFAULT_COOCCURRENCE_OUT),
                    help=("skill-map local-overlay input: session-level skill "
                          "co-occurrence counts (no prompt text/paths/timestamps). "
                          f"default: {DEFAULT_COOCCURRENCE_OUT}"))
    ap.add_argument("--days", type=int, default=7,
                    help="window in days (0 or negative = all-time; default 7)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress per-file progress")
    args = ap.parse_args()

    # Self-sync: the scheduled task runs from this working tree, so pull any
    # commits made since the last run before scanning (never leaves a rebase
    # in progress — see git_sync.py).
    git_sync.pull_rebase()

    projects_root = Path(args.projects_dir).expanduser()
    cowork_root = Path(args.cowork_dir).expanduser() if args.cowork_dir else None
    report_dir = Path(args.report_dir).expanduser() if args.report_dir else None
    json_out = Path(args.json_out).expanduser()
    since = args.days if args.days and args.days > 0 else None

    # mtime prefilter: skip files clearly outside the window. 1-day grace because
    # mtime can lag the last write inside a long-running session.
    if since is not None:
        mtime_cutoff = (datetime.now() - timedelta(days=since + 1)).timestamp()
    else:
        mtime_cutoff = None

    print(f"→ Scanning {projects_root} (window = {since or 'all-time'} days)")
    if cowork_root:
        print(f"→ Scanning {cowork_root} (Cowork desktop-app)")

    # Collect (file, source_type) pairs from both trees.
    walks: list[Iterable[tuple[Path, str]]] = [
        walk_projects(projects_root, mtime_cutoff=mtime_cutoff),
    ]
    if cowork_root:
        walks.append(walk_cowork_projects(cowork_root, mtime_cutoff=mtime_cutoff))

    all_events: list[dict] = []
    doctor_events: list[dict] = []
    agent_type_map: dict[str, str] = {}
    files_scanned = 0
    for walk in walks:
        for jsonl_path, source_type in walk:
            files_scanned += 1
            if source_type == "audit":
                for ev in extract_skill_events_from_audit(jsonl_path):
                    all_events.append(ev)
            else:
                for ev in extract_skill_events(jsonl_path, source_type):
                    all_events.append(ev)
                # Same files also carry slash-command invocations (a separate
                # channel that usually fires no Skill tool_use).
                for ev in extract_command_events(jsonl_path, source_type):
                    all_events.append(ev)
                # Dev Flow control-plane observability (Task 9): a fully
                # separate collection, never merged into all_events — it
                # carries only a redacted healthy/degraded flag, never
                # command text or paths, and cannot affect the dedup/report
                # pipeline above.
                for ev in extract_devflow_doctor_events(jsonl_path, source_type):
                    doctor_events.append(ev)
                # Main jsonls additionally contribute (agentId -> agentType)
                # mappings via toolUseResult — only useful source of subagent
                # type attribution.
                if source_type == "main":
                    for agent_id, agent_type in extract_agent_type_map(jsonl_path):
                        agent_type_map.setdefault(agent_id, agent_type)

    # Resolve subagent attribution.
    for ev in all_events:
        if ev.get("source_type") == "subagent" and ev.get("agent_id"):
            ev["agent_slug"] = agent_type_map.get(ev["agent_id"])

    # Defensive dedup on (uuid, session_id).
    #
    # Three dedup cases are known and EXPECTED (all harness replay, not an
    # ingestion bug):
    #   (a) main + subagent overlap within one session. Subagent transcripts
    #       (especially `acompact-*` context-compaction agents) re-embed
    #       parent main events so the subagent has continuity. The same
    #       (uuid, session_id) appears in both the main jsonl and a subagent
    #       jsonl. Dropping the subagent copy is correct.
    #   (b) acompact-* subagents replaying each other. When the main jsonl
    #       has been rotated/deleted, multiple compaction snapshots for one
    #       session can each independently preserve the same parent event.
    #       All compaction copies are dropped except one.
    #   (c) main + main replay from the Claude Desktop (Cowork) app. Verified
    #       2026-08-09: for `entrypoint == "claude-desktop"`, an assistant
    #       turn recorded early in a session's main jsonl can reappear later
    #       in the SAME file, byte-identical on uuid/requestId/parentUuid/
    #       timestamp/message content, differing only in `cwd` (resolved
    #       against whatever root the desktop app has active at replay time)
    #       and sometimes gaining a `slug` field once the session is
    #       auto-named. This is the desktop app re-serializing session state
    #       into the transcript, not a reader double-counting a file — 22/22
    #       inspected instances on 2026-08-09 shared this exact shape. Kept
    #       as its own category (rather than folded into "any main+main is
    #       fine") so a same-source_type duplicate from the CLI, which has no
    #       known replay mechanism, still trips the loud warning below.
    #
    # Anything else (e.g. two host-CLI main events sharing a key, a
    # host/Cowork uuid collision, an audit-file double-walk) is UNEXPECTED
    # and warned on loudly so it can't go unnoticed.
    def _is_compaction(ev: dict) -> bool:
        return (ev.get("agent_id") or "").startswith("acompact-")

    def _is_desktop_main_replay(prior: dict, ev: dict) -> bool:
        return (
            prior.get("source_type") == "main"
            and ev.get("source_type") == "main"
            and prior.get("entrypoint") == "claude-desktop"
            and ev.get("entrypoint") == "claude-desktop"
        )

    seen: dict = {}  # key -> first event seen (for category check)
    deduped: list[dict] = []
    unexpected_dups = 0
    desktop_replay_dups = 0
    for ev in all_events:
        uuid = ev.get("uuid")
        if uuid is None:
            deduped.append(ev)
            continue
        key = (uuid, ev.get("session_id"))
        if key in seen:
            prior = seen[key]
            this_src = ev.get("source_type")
            prior_src = prior.get("source_type")
            if {prior_src, this_src} == {"main", "subagent"} or (
                prior_src == "subagent" and this_src == "subagent"
                and (_is_compaction(prior) or _is_compaction(ev))
            ):
                pass  # (a)/(b) — expected, silent
            elif _is_desktop_main_replay(prior, ev):
                desktop_replay_dups += 1  # (c) — expected, informational
            else:
                unexpected_dups += 1
            continue
        seen[key] = ev
        deduped.append(ev)
    if desktop_replay_dups:
        print(
            f"  · collapsed {desktop_replay_dups} duplicate events from Claude "
            f"Desktop session-transcript replay (expected; see dedup comment "
            f"in monitor.py)",
        )
    if unexpected_dups:
        print(
            f"  ! warning: dropped {unexpected_dups} unexpected duplicate events "
            f"(same source_type sharing uuid+session_id) — investigate",
            file=sys.stderr,
        )
    all_events = deduped

    cowork_origin_map = load_cowork_origin_map() if cowork_root else {}

    report = build_report(
        all_events,
        since_days=since,
        cowork_origin_map=cowork_origin_map,
        doctor_events=doctor_events,
    )
    md = render_markdown(report, files_scanned=files_scanned)

    cooccurrence = build_cooccurrence(all_events, since_days=since)
    cooccurrence_out = Path(args.cooccurrence_out).expanduser()
    cooccurrence_out.parent.mkdir(parents=True, exist_ok=True)
    cooccurrence_out.write_text(json.dumps(cooccurrence, indent=2, sort_keys=True) + "\n")

    json_out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"events": all_events, "report": report},
        indent=2,
        default=str,
    )
    json_out.write_text(payload)

    # Per-run snapshot for the live dashboard. The rolling json_out above is
    # overwritten every run; the snapshot is immutable per-window-per-day
    # history. Same payload, different filename. Cheap (~500KB/snapshot).
    #
    # The filename encodes both the date and the window so a same-day
    # `--days 28` rerun does NOT overwrite the canonical weekly `--days 7`
    # snapshot — that would break trend-chart comparability in the dashboard.
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    window_tag = f"{since}d" if since else "0d"
    snap_path = (
        SNAPSHOTS_DIR
        / f"{datetime.now().strftime('%Y-%m-%d')}-skill-usage-{window_tag}.json"
    )
    snap_path.write_text(payload)

    # The 7-day window is the canonical weekly report and keeps the plain
    # filename that the dashboard, week-over-week diff, and scheduled task all
    # reference. Any other window (28d, all-time, custom) gets the same
    # -{window_tag} suffix the snapshot uses, so a same-day rerun (e.g. the
    # 4th-Monday `--days 28` pass) can't clobber the weekly report.
    md_path = None
    if report_dir is None:
        print(
            "  ! no --report-dir given and no single Obsidian vault could be "
            "resolved (see paths.vault_root()) — skipping the markdown report "
            "write.",
            file=sys.stderr,
        )
    else:
        report_dir.mkdir(parents=True, exist_ok=True)
        report_stem = f"{datetime.now().strftime('%Y-%m-%d')}-skill-usage"
        if since != WEEKLY_WINDOW_DAYS:
            report_stem += f"-{window_tag}"
        md_path = report_dir / f"{report_stem}.md"
        md_path.write_text(md)

    # Self-sync: commit + push the new snapshot so the tree can't drift again.
    git_sync.commit_and_push_snapshots()

    print(f"  ✓ JSON written  → {json_out}")
    print(f"  ✓ Snapshot      → {snap_path}")
    if md_path is not None:
        print(f"  ✓ Markdown report → {md_path}")
    print(
        f"  ✓ Co-occurrence  → {cooccurrence_out} "
        f"({len(cooccurrence['pairs'])} pairs, "
        f"{len(cooccurrence['orderedPairs'])} follows-candidates, "
        f"{cooccurrence['totalSessions']} sessions)"
    )
    print(
        f"\nSummary: {files_scanned} files scanned, "
        f"{len(all_events)} events, "
        f"{report['unique_skills_used']} unique skills."
    )
    if report.get("by_source_type"):
        srcs = ", ".join(f"{k}={v}" for k, v in report["by_source_type"].items())
        print(f"By source: {srcs}")
    print("\nTop 10 skills in window:")
    for s, c in report["top_skills"][:10]:
        print(f"  {c:>5}  {s}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
