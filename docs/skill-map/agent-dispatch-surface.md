# Agent-Dispatch Surface (2026-08-26)

Deep reference for the "Agent-dispatch surface" section summarized in
[`docs/skill-map.md`](../skill-map.md).

The Agent tool has no skills parameter, so a dispatching orchestrator's only levers are picking a
skill-shaped agent type, naming a skill in the brief ("Invoke `<plugin:skill>` first"), or inlining
its content — and in practice neither happens on its own: a Skill-capable subagent inherits the
same skill roster but none of the parent transcript (every dispatch is a cold start), and zero of
~15 observed subagent reports in the originating session invoked a skill unprompted. Because a
PreToolUse hook fires only after the brief is already written, it cannot fix the dispatch it
observes — it can only measure, across sessions, whether outgoing briefs already name the skill the
router index would otherwise suggest for their content.

**Spike verdicts** (`.claude/plans/subagent-skill-injection.md`, Task 3 Step 5, 2026-08-26):

```
V1 fired: yes · tool_name(s) observed: Agent  → SPIKE_MATCHER = "^(Agent)$"
V2 additionalContext reached model: yes (result=True, stderr-clean=True, control-clean=True)
Consequence for Task 5: log + flag-gated advisory (V2 yes)
```

**What it measures:** `rhize-context-manager/hooks/agent-brief-router.js` (PreToolUse, matcher
`^(Agent)$`, tier T3, opt-in via `setup/manifest.json`, `default: false`) is a **measurement
instrument, not a router** — default behavior is log-only. Each Agent-tool dispatch that reaches
it (non-empty brief, usable map/index data) logs one `source: "agent-dispatch"` row to the shared
suggestion log: which skills the brief named via the directive `Invoke <plugin:skill> first`
(Task 1's convention) versus the single best-scoring candidate the router index would suggest for
the brief's content. `rhize-context-manager/scripts/suggestion_log_report.py`'s `agent_dispatch` section reports the
named-rate, candidate-present count, and candidate-miss rate computed from that log, plus the
same four numbers broken out per `agentType`. A one-line advisory
(`hookSpecificOutput.additionalContext`, next-dispatch guidance only — it cannot retract the
dispatch already in flight) exists behind `RHIZE_AGENT_BRIEF_ADVISORY=1` and stays off until the
logged data has been reviewed; briefs are long, multi-paragraph documents and over-match the
prompt-calibrated thresholds `skill-router.js` uses for short user prompts.

**Reading the per-agentType breakdown:** Skill-capable rosters are briefed to NAME a skill
("Invoke `<plugin:skill>` first"), while Skill-less rosters (verifier, Explore, Plan) are
briefed to INLINE the skill's operative content instead, without naming it — so a high
candidate-miss rate for a Skill-less `agentType` reflects a policy-compliant inlined brief
whose content still matches a topic-scoring candidate, not non-compliance. Do not compare
miss-rates across the two roster kinds as if they measured the same behavior.

**Known limitations:** Workflow `agent()` calls and scheduled-task sessions bypass the Agent-tool
hook entirely — they're spawned by other runtimes, so PreToolUse on `Agent` never fires for them.
For those paths, the CLAUDE.md skill-explicit dispatch rule (Task 1, `~/.claude/CLAUDE.md`) is the
only enforcement, by design; no hook will be built for them.

## Forward contract: graph-node skill declarations (deferred to the graph-determinism plan)

When workflow graphs land (graph-based determinism direction, 2026-08-26), each
node that dispatches an agent declares its skills in the node schema:

    skills: ["skill:<plugin>/<name>", ...]   # canonical skill-map node ids (docs/skill-map.md's id form), validated against the map at graph-build time

The brief compiler — not the executor — resolves the declaration at dispatch:
for a Skill-capable agent roster it emits one `Invoke <plugin>:<name> first.`
line per entry; for a Skill-less roster it inlines the skill's operative
content (never the whole SKILL.md). Unresolvable ids are graph-BUILD errors,
not runtime warnings — same stance as the compiler's dangling-edge rule. This
replaces per-brief manual injection (the CLAUDE.md dispatch rule) with a
declared, validated, compounding structure: the declaration lives in the graph,
not in an orchestrator's context window.

---

Back to [`docs/skill-map.md`](../skill-map.md).
