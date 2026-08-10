#!/usr/bin/env python3
"""suggestion_log_report.py — acceptance-rate report for the skill-map hooks'
suggestion log.

The four map-driven hooks (rhize-context-manager/hooks/{skill-router,
session-disclosure,remediation-suggester,next-step-suggester}.js) each append
one JSON line per suggestion fired to a local, machine-only log (default
~/.claude/context-manager/suggestion-log.jsonl; NEVER committed to the repo).
This script joins that log against skill-monitor's usage data
(rhize-ops/skill-monitor/data/skill-usage.json) to answer the previously
unmeasurable question: of the suggestions the hooks fired, how many were
actually acted on ("suggested-but-ignored", the routing-miss metric)?

PINNED LOG SCHEMA (one JSON object per line):
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

JOIN METHODOLOGY AND ITS LIMITATION (read before trusting the acceptance
numbers):
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
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_LOG_PATH = Path.home() / ".claude" / "context-manager" / "suggestion-log.jsonl"
DEFAULT_USAGE_PATH = (
    Path(__file__).resolve().parent.parent
    / "rhize-ops"
    / "skill-monitor"
    / "data"
    / "skill-usage.json"
)

HOOKS = ("router", "disclosure", "remediation", "next-step")

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


def compute_report(entries: list[dict], session_skills: dict[str, set[str]]) -> dict:
    """Computes per-hook suggestion/acceptance/ignore counts plus the
    router's silence-sample counts. See module docstring for the acceptance
    proxy's methodology and limitation."""
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

    for entry in entries:
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

    return {"per_hook": per_hook, "router_silence_samples": router_silence_samples}


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
        default=DEFAULT_USAGE_PATH,
        help=f"path to skill-usage.json (default: {DEFAULT_USAGE_PATH})",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    entries = load_log(args.log_path)
    session_skills = load_session_skills(args.usage_path)
    report = compute_report(entries, session_skills)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_table(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
