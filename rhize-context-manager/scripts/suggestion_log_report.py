#!/usr/bin/env python3
"""suggestion_log_report.py — acceptance-rate report for the skill-map hooks'
suggestion log.

Five map-driven hooks append to a shared, local, machine-only suggestion log
(default ~/.claude/context-manager/suggestion-log.jsonl; NEVER committed to
the repo), but they write TWO different row shapes:

  - The four legacy hooks (rhize-context-manager/hooks/{skill-router,
    session-disclosure,remediation-suggester,next-step-suggester}.js) each
    append one JSON line per suggestion fired, keyed by `hook`. This script
    joins those rows against the standalone rhize-skill-monitor tool's usage
    data (skill-usage.json, under skill_monitor_data_dir() — see that
    function below) to answer the previously unmeasurable question: of the
    suggestions the hooks fired, how many were actually acted on
    ("suggested-but-ignored", the routing-miss metric)?

  - The fifth hook (agent-brief-router.js) appends one JSON line per Agent-tool
    dispatch, keyed by `source: "agent-dispatch"` — a different shape (see
    AGENT-DISPATCH SCHEMA below), with no session-usage join: it measures
    skill-map coverage of the outgoing brief text itself, not downstream
    acceptance.

PINNED LEGACY LOG SCHEMA (one JSON object per line):
    {
      "ts": "<ISO8601>",
      "session_id": "<str|null>",
      "hook": "router" | "disclosure" | "remediation" | "next-step",
      "suggested": "<skill/agent id>" | ["<id>", ...] | null,
      "context_hash": "<16 hex chars>"
    }
`suggested` is `null` only for the router's sampled (~1-in-20) no-suggestion
lines — everything else logged is a real suggestion. `suggested` is an array
only for the disclosure hook (its multi-skill surface); every other hook logs
a single id string.

AGENT-DISPATCH LOG SCHEMA (one JSON object per line, no `hook` key):
    {
      "ts": "<ISO8601>",
      "source": "agent-dispatch",
      "agentType": "<subagent_type str>",
      "briefHash": "<16 hex chars>",
      "briefLength": <int>,
      "namedSkills": ["<skill id>", ...],
      "suggestedSkills": ["<skill id>"] | [],
      "advisoryEmitted": <bool>
    }
`namedSkills` are ids the brief explicitly named via the "Invoke <plugin:skill>
first" directive (Task 1's convention); `suggestedSkills` is the (at most one)
id route-core's scoring would suggest for the brief's content. This script
routes these rows to a separate `agent_dispatch` report section — they carry
no `hook` field and are never counted by the legacy per-hook logic.

CAVEAT ON THE PER-AGENTTYPE BREAKDOWN: Skill-capable agent rosters are briefed
to NAME a skill ("Invoke <plugin:skill> first"), while Skill-less rosters
(verifier, Explore, Plan) are briefed to INLINE the skill's operative content
instead, without naming it. A high candidate-miss rate for a Skill-less
agentType therefore reflects a policy-compliant inlined brief whose content
still matches a topic-scoring candidate — not non-compliance — so the two
roster kinds' miss-rates must not be conflated when reading `by_agent_type`.

JOIN METHODOLOGY AND ITS LIMITATION (read before trusting the LEGACY
acceptance numbers — does not apply to the agent-dispatch section, which has
no session-usage join):
    skill-monitor's skill-usage.json records one event per Skill-tool
    invocation, each carrying a bare `skill` name (e.g. "graphify") and a
    `session_id` — it does NOT record plugin-qualified ids, ordering relative
    to a suggestion, or agent invocations at all. This script can therefore
    only compute a PROXY for acceptance:

        accepted (proxy) := the suggested skill's bare name appears ANYWHERE
        in skill-usage.json's per-session skill set for that session_id.

    This is NOT true acceptance tracking: it cannot tell whether the matching
    invocation happened before or after the suggestion fired within the
    session, and it will count a coincidental match (the user was already
    going to invoke that skill) as an "acceptance". Treat the acceptance rate
    as an upper bound / rough signal, not ground truth, until skill-usage.json
    grows a per-event ordering key the log's own timestamp can be compared
    against.

    A further gap: `remediation-suggester.js` can suggest an `external:<slug>`
    id naming a third-party AGENT (e.g. an ecc build-resolver), not a
    skill-map skill. skill-usage.json only tracks Skill-tool invocations, so
    external suggestions have no possible match and are reported separately
    as "external (unjoinable)" rather than folded into the ignore rate, which
    would otherwise be inflated by a metric this data source cannot answer.

Dependency-free stdlib only — this becomes a weekly-audit input later.

SHIPS WITH THE PLUGIN (moved from repo-root `scripts/` 2026-09-02, R3 task 8 of the
portability-readiness plan): this file now lives at
`rhize-context-manager/scripts/suggestion_log_report.py`. A two-line compatibility
shim remains at the old `scripts/suggestion_log_report.py` path.

The skill-usage.json it joins against no longer ships bundled in this marketplace
either — skill-monitor is the standalone Rhize-Media/rhize-skill-monitor repo,
cloned by default at `~/dev-local/RHIZE/rhize-skill-monitor` and overridable with
`RHIZE_SKILL_MONITOR_ROOT`. `skill_monitor_data_dir()` below resolves its data
directory by that tool's own precedence, without importing across the plugin
boundary (a discovered path with a documented degraded mode, per this repo's
cross-plugin sharing rule).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_LOG_PATH = Path.home() / ".claude" / "context-manager" / "suggestion-log.jsonl"


def skill_monitor_data_dir() -> Path:
    """Resolve the standalone rhize-skill-monitor tool's data directory on
    this machine (Rhize-Media/rhize-skill-monitor — not bundled with this
    plugin; reached only by this discovered-path resolver, never a
    cross-plugin import). Mirrors that tool's own paths.py precedence:
      1. RHIZE_SKILL_MONITOR_HOME set -> <home>/data
      2. else RHIZE_SKILL_MONITOR_ROOT, or the default checkout
         (~/dev-local/RHIZE/rhize-skill-monitor); if its data/ is a
         directory -> that data/
      3. else ~/.rhize/skill-monitor/data (fresh-install default)
    """
    home_override = os.environ.get("RHIZE_SKILL_MONITOR_HOME", "").strip()
    if home_override:
        return Path(home_override).expanduser() / "data"
    root_override = os.environ.get("RHIZE_SKILL_MONITOR_ROOT", "").strip()
    root = (
        Path(root_override).expanduser()
        if root_override
        else Path.home() / "dev-local" / "RHIZE" / "rhize-skill-monitor"
    )
    checkout_data = root / "data"
    if checkout_data.is_dir():
        return checkout_data
    return Path.home() / ".rhize" / "skill-monitor" / "data"


def _default_usage_path() -> Path:
    """Where skill-monitor's skill-usage.json lives on this machine. See
    skill_monitor_data_dir() for the precedence. Missing files degrade to
    "no usage data" in load_session_skills(), never an error.
    """
    return skill_monitor_data_dir() / "skill-usage.json"

HOOKS = ("router", "disclosure", "remediation", "next-step")

AGENT_DISPATCH_SOURCE = "agent-dispatch"

_ID_PATTERN = re.compile(r"^(skill|command):(?:([^/]+)/)?(.+)$")


def short_skill_name(suggested_id: str) -> str | None:
    """Extracts the bare skill name skill-usage.json would record for a
    skill-map node id (`skill:<plugin>/<name>` or bare `<name>`). Returns
    None for an `external:` agent id — those have no skill-usage.json
    counterpart (see module docstring's JOIN METHODOLOGY note)."""
    if not isinstance(suggested_id, str):
        return None
    if suggested_id.startswith("external:"):
        return None
    match = _ID_PATTERN.match(suggested_id)
    if match:
        return match.group(3)
    return suggested_id  # unknown shape — treat the raw string as the name


def load_log(log_path: Path) -> list[dict]:
    """Reads the suggestion log. A missing file is not an error — the log is
    append-only and may not exist yet on a fresh install."""
    if not log_path.exists():
        return []
    entries = []
    with log_path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(
                    f"warning: skipping malformed log line {line_no}: {exc}",
                    file=sys.stderr,
                )
    return entries


def load_session_skills(usage_path: Path) -> dict[str, set[str]]:
    """Builds session_id -> set(bare skill names invoked in that session)
    from skill-usage.json. Missing/unreadable/malformed usage data degrades
    to an empty mapping (every suggestion then reports as not-accepted)
    rather than raising, since the log report must still run standalone."""
    if not usage_path.exists():
        return {}
    try:
        data = json.loads(usage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    events = data.get("events", []) if isinstance(data, dict) else []
    by_session: dict[str, set[str]] = defaultdict(set)
    for event in events:
        if not isinstance(event, dict):
            continue
        session_id = event.get("session_id")
        skill = event.get("skill")
        if isinstance(session_id, str) and isinstance(skill, str):
            by_session[session_id].add(skill)
    return dict(by_session)


def compute_agent_dispatch_report(entries: list[dict]) -> dict:
    """Computes the agent-dispatch coverage stats from `source: "agent-dispatch"`
    rows (see module docstring's AGENT-DISPATCH LOG SCHEMA). No session-usage
    join here — this measures whether the outgoing brief named a skill the
    router would have suggested for it, not downstream acceptance.

    - named_rate: share of dispatches whose brief named >=1 skill.
    - candidate_present: count of dispatches with a non-empty suggestion.
    - candidate_miss_rate: of the candidate-present dispatches, the share
      whose suggestion was fully disjoint from the named skills — i.e. a
      dispatch with no candidate can't miss, so it's excluded from the
      denominator.
    - top_unnamed_suggested: the suggested skill ids from miss rows, ranked
      by how often they were suggested-but-not-named.
    - by_agent_type: the same four counters (dispatches/named_rate/
      candidate_present/candidate_miss_rate), grouped by the logged
      `agentType` field. See the module docstring's CAVEAT ON THE
      PER-AGENTTYPE BREAKDOWN — a high miss-rate for a Skill-less agentType
      (verifier, Explore, Plan) is not evidence of non-compliance, since those
      rosters are briefed to inline content rather than name a skill.
    """
    total = 0
    named_count = 0
    candidate_present = 0
    candidate_miss = 0
    unnamed_but_suggested_counts: dict[str, int] = defaultdict(int)
    by_type_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "named_count": 0, "candidate_present": 0, "candidate_miss": 0}
    )

    for entry in entries:
        total += 1
        agent_type = entry.get("agentType")
        agent_type = agent_type if isinstance(agent_type, str) and agent_type else "(unknown)"
        named_skills = entry.get("namedSkills")
        suggested_skills = entry.get("suggestedSkills")
        named_skills = named_skills if isinstance(named_skills, list) else []
        suggested_skills = suggested_skills if isinstance(suggested_skills, list) else []
        type_stats = by_type_totals[agent_type]
        type_stats["total"] += 1

        if named_skills:
            named_count += 1
            type_stats["named_count"] += 1

        if suggested_skills:
            candidate_present += 1
            type_stats["candidate_present"] += 1
            if set(suggested_skills).isdisjoint(named_skills):
                candidate_miss += 1
                type_stats["candidate_miss"] += 1
                for skill_id in suggested_skills:
                    unnamed_but_suggested_counts[skill_id] += 1

    named_rate = (named_count / total) if total else 0.0
    candidate_miss_rate = (candidate_miss / candidate_present) if candidate_present else 0.0
    top_unnamed_suggested = [
        {"skill_id": skill_id, "count": count}
        for skill_id, count in sorted(
            unnamed_but_suggested_counts.items(), key=lambda kv: (-kv[1], kv[0])
        )[:5]
    ]

    by_agent_type = {}
    for agent_type, stats in by_type_totals.items():
        t = stats["total"]
        cp = stats["candidate_present"]
        by_agent_type[agent_type] = {
            "total": t,
            "named_rate": (stats["named_count"] / t) if t else 0.0,
            "candidate_present": cp,
            "candidate_miss_rate": (stats["candidate_miss"] / cp) if cp else 0.0,
        }

    return {
        "total": total,
        "named_rate": named_rate,
        "candidate_present": candidate_present,
        "candidate_miss_rate": candidate_miss_rate,
        "top_unnamed_suggested": top_unnamed_suggested,
        "by_agent_type": by_agent_type,
    }


def compute_report(entries: list[dict], session_skills: dict[str, set[str]]) -> dict:
    """Computes per-hook suggestion/acceptance/ignore counts plus the
    router's silence-sample counts, and the agent-dispatch coverage section.
    See module docstring for the acceptance proxy's methodology and
    limitation, and compute_agent_dispatch_report for the agent-dispatch
    metrics' definitions.

    Branches on `entry.get("source")` FIRST: agent-dispatch rows carry no
    `hook` key and are routed to their own section below; every other row
    flows through the legacy per-hook logic byte-for-byte unchanged."""
    per_hook = {
        hook: {
            "suggestions": 0,
            "accepted": 0,
            "ignored": 0,
            "external_unjoinable": 0,
        }
        for hook in HOOKS
    }
    router_silence_samples = 0
    agent_dispatch_entries: list[dict] = []

    for entry in entries:
        if entry.get("source") == AGENT_DISPATCH_SOURCE:
            agent_dispatch_entries.append(entry)
            continue

        hook = entry.get("hook")
        if hook not in per_hook:
            continue  # unknown hook value — ignore rather than crash
        suggested = entry.get("suggested")

        if suggested is None:
            if hook == "router":
                router_silence_samples += 1
            continue  # a null suggestion is not a suggestion to score

        session_id = entry.get("session_id")
        invoked = session_skills.get(session_id, set()) if isinstance(session_id, str) else set()

        suggested_ids = suggested if isinstance(suggested, list) else [suggested]
        per_hook[hook]["suggestions"] += 1

        names = [short_skill_name(sid) for sid in suggested_ids]
        joinable_names = [n for n in names if n is not None]
        all_external = suggested_ids and all(n is None for n in names)

        if all_external:
            per_hook[hook]["external_unjoinable"] += 1
            continue

        if any(name in invoked for name in joinable_names):
            per_hook[hook]["accepted"] += 1
        else:
            per_hook[hook]["ignored"] += 1

    return {
        "per_hook": per_hook,
        "router_silence_samples": router_silence_samples,
        "agent_dispatch": compute_agent_dispatch_report(agent_dispatch_entries),
    }


def format_table(report: dict) -> str:
    lines = []
    header = f"{'hook':<12} {'suggested':>9} {'accepted':>8} {'ignored':>7} {'ext-unjoin':>10} {'accept%':>8}"
    lines.append(header)
    lines.append("-" * len(header))
    for hook in HOOKS:
        stats = report["per_hook"][hook]
        scoreable = stats["accepted"] + stats["ignored"]
        pct = f"{(100 * stats['accepted'] / scoreable):.1f}%" if scoreable else "n/a"
        lines.append(
            f"{hook:<12} {stats['suggestions']:>9} {stats['accepted']:>8} "
            f"{stats['ignored']:>7} {stats['external_unjoinable']:>10} {pct:>8}"
        )
    lines.append("")
    lines.append(f"router silence samples (suggested:null, ~1-in-20 sampled): {report['router_silence_samples']}")
    lines.append("")
    lines.append(
        "NOTE: acceptance is a same-session proxy (see script docstring's JOIN\n"
        "METHODOLOGY note) — it cannot confirm the invocation happened after the\n"
        "suggestion, and 'ext-unjoin' suggestions (agent ids) are excluded from\n"
        "accept% because skill-usage.json has no record of agent invocations."
    )
    lines.append("")
    lines.append("agent-dispatch (source: \"agent-dispatch\" rows — no session-usage join)")
    lines.append("-" * 72)
    ad = report["agent_dispatch"]
    lines.append(f"total dispatches logged: {ad['total']}")
    named_pct = f"{(100 * ad['named_rate']):.1f}%" if ad["total"] else "n/a"
    lines.append(f"named-rate (brief named >=1 skill): {named_pct}")
    lines.append(f"candidate-present (router had a suggestion): {ad['candidate_present']}")
    miss_pct = f"{(100 * ad['candidate_miss_rate']):.1f}%" if ad["candidate_present"] else "n/a"
    lines.append(f"candidate-miss rate (of candidate-present): {miss_pct}")
    if ad["top_unnamed_suggested"]:
        lines.append("top unnamed-but-suggested skill ids:")
        for row in ad["top_unnamed_suggested"]:
            lines.append(f"  {row['skill_id']}: {row['count']}")
    else:
        lines.append("top unnamed-but-suggested skill ids: (none)")
    if ad["by_agent_type"]:
        lines.append("")
        lines.append("by agentType:")
        type_header = (
            f"{'agentType':<20} {'dispatches':>10} {'named-rate':>10} "
            f"{'cand-present':>12} {'miss-rate':>9}"
        )
        lines.append(type_header)
        lines.append("-" * len(type_header))
        for agent_type in sorted(ad["by_agent_type"]):
            stats = ad["by_agent_type"][agent_type]
            t_named_pct = f"{(100 * stats['named_rate']):.1f}%" if stats["total"] else "n/a"
            t_miss_pct = (
                f"{(100 * stats['candidate_miss_rate']):.1f}%" if stats["candidate_present"] else "n/a"
            )
            lines.append(
                f"{agent_type:<20} {stats['total']:>10} {t_named_pct:>10} "
                f"{stats['candidate_present']:>12} {t_miss_pct:>9}"
            )
    lines.append("")
    lines.append(
        "CAVEAT: Skill-capable agentTypes (e.g. executor) are briefed to NAME a\n"
        "skill (\"Invoke <plugin:skill> first\"); Skill-less agentTypes (verifier,\n"
        "Explore, Plan) are briefed to INLINE the operative content instead and\n"
        "never name one. A high miss-rate for a Skill-less agentType therefore\n"
        "reflects a policy-compliant inlined brief, not non-compliance — do not\n"
        "compare miss-rates across the two roster kinds as if they measured the\n"
        "same behavior."
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help=f"path to suggestion-log.jsonl (default: {DEFAULT_LOG_PATH})",
    )
    parser.add_argument(
        "--usage-path",
        type=Path,
        default=None,
        help="path to skill-usage.json (default: skill-monitor data dir's "
             "skill-usage.json — see skill_monitor_data_dir())",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    entries = load_log(args.log_path)
    usage_path = args.usage_path if args.usage_path else _default_usage_path()
    session_skills = load_session_skills(usage_path)
    report = compute_report(entries, session_skills)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_table(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
