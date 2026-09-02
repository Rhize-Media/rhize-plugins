---
description: Show which skill/next-step suggestions the plugin's hooks made and how often, from the suggestion log
model: sonnet
---

# /suggestion-report [options]

Report the skill-map hooks' suggestion-to-acceptance rate from the shared, local,
machine-only suggestion log (`~/.claude/context-manager/suggestion-log.jsonl`). This
command is read-only — it never writes to the log, the skill map, or any config.

## Step 1 — Run the report

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/suggestion_log_report.py" $ARGUMENTS
```

Forward `$ARGUMENTS` verbatim. Useful flags (see the script's `--help` for the full
list): `--json` for machine-readable output instead of the table; `--log-path` /
`--usage-path` to point at a different log or skill-usage snapshot (e.g. investigating
an exported copy from another machine). With no arguments the script prints the
human-readable table described below and exits 0 even when the log doesn't exist yet
(a missing log is not an error — it's append-only and may not have been written to on
a fresh install).

## Step 2 — Summarize the output

The report has two independent sections — present both, and do not conflate them:

1. **Per-hook table** (`router`, `disclosure`, `remediation`, `next-step`): suggested /
   accepted / ignored / ext-unjoin counts and an accept% for each hook, plus the
   router's silence-sample count. Note in your summary that **acceptance is a
   same-session proxy** (a suggested skill's bare name appearing anywhere in that
   session's skill-usage record) — it cannot confirm the invocation happened *after*
   the suggestion, and `remediation-suggester` can suggest a third-party agent id
   (`external:<slug>`) that has no skill-usage.json counterpart, so those are reported
   separately as "ext-unjoin" rather than folded into the ignore rate.
2. **Agent-dispatch section** (`agent-brief-router`'s `source: "agent-dispatch"` rows —
   no session-usage join, a different measurement entirely): total dispatches logged,
   named-rate (brief named >=1 skill), candidate-present count, candidate-miss rate,
   top unnamed-but-suggested skill ids, and a `by_agent_type` breakdown. **Do not
   compare miss-rates across agentTypes as if they measure the same thing** —
   Skill-capable rosters (e.g. `executor`) are briefed to *name* a skill, while
   Skill-less rosters (`verifier`, `Explore`, `Plan`) are briefed to *inline* the
   operative content instead and never name one, so a high miss-rate there reflects a
   policy-compliant inlined brief, not non-compliance.

## Output

The script's own table (or `--json` output) followed by a short prose summary calling
out: the hook(s) with the lowest accept%, the router's silence-sample count as context
for how often it stays quiet, the agent-dispatch named-rate and candidate-miss rate,
and any `by_agent_type` split worth flagging (per the caveat above). If the log doesn't
exist yet, say so plainly rather than reporting empty numbers as a finding.
