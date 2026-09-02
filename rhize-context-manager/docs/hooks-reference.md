# Hooks reference

Deep reference for every hook this plugin ships — resolution order, logging, the opt-in
per-repo/migration hooks, and the reasoning behind the context-window monitor. See the
README's Hooks section for the auto-wired table and a short summary of each row.

## How hooks resolve the compiled skill map

`session-disclosure.js` replaced the four per-plugin SessionStart banners (seo-aeo-geo,
obsidian-second-brain, project-launcher, rhize-devflow) on 2026-08-09 — Phase 3 of
`.claude/plans/skill-map-graph-substrate.md`. `remediation-suggester.js` and
`next-step-suggester.js` were added 2026-08-09 as the runtime consumers for relationships v2
(`docs/superpowers/specs/2026-08-09-skill-map-relationships-v2-design.md` section 7) — the
first runtime consumer of `precedes`, and the first consumer of the `remediates`/`condition`
data. All five auto-wired hooks resolve the compiled skill-map artifact the same way: the
materialized indexes first (`~/.claude/context-manager/skill-map.indexes.resolved.json`,
falling back to `skill-map.indexes.json`), and — for `skill-router.js`/`session-disclosure.js`/
`agent-brief-router.js` only — a further fallback to the older
`skill-map.resolved.json`/`skill-map.static.json` map-scan path when no indexes file exists at
all. All five fail silently (exit 0, no output) on any missing or corrupt input. See
`docs/skill-map.md` (repo root) for the artifact/tagging conventions they depend on.

`tier` follows the shared convention: T3 = advisory (never blocks, exits 0, must use
`hookSpecificOutput.additionalContext` to reach Claude on events where plain stdout
isn't auto-added to context), T4 = blocking (`exit 2`, stderr becomes the reason shown
to Claude). Verified 2026-08-04 against `code.claude.com/docs/en/hooks`: `SessionStart`
and `UserPromptSubmit` auto-add plain stdout as context, but `PreToolUse`/`PostToolUse`
advisory hooks do not — plain stdout/stderr on `exit 0` there is invisible to the model.
`pre-commit-guard.sh` and `skill-suggester.sh` were fixed to this contract 2026-08-04:
the former printed warnings to stderr on `exit 0` (never reached Claude), the latter both
read the wrong input field (`user_prompt` instead of `prompt` — a permanent no-op) and
wrote its suggestion to `systemMessage` (user-only, not `hookSpecificOutput.additionalContext`).

Before Claude plugin migration, the coordinator must remove any duplicate manual selector/
finalizer entries; duplicate calls are state-idempotent, but a second selector can waste a
local provider build before the lease rejects it.

## Suggestion log

`session-disclosure.js`, `remediation-suggester.js`, and `next-step-suggester.js` — plus
`skill-router.js` and `agent-brief-router.js` below, both opt-in — write a **suggestion
log**, one JSON line per fired event, appended fail-silent to
`~/.claude/context-manager/suggestion-log.jsonl`. Two row shapes share that file: the legacy
`{"ts", "session_id", "hook", "suggested", "context_hash"}` shape the first four of these hooks write, and
`agent-brief-router.js`'s `{"ts", "source": "agent-dispatch", "agentType", "briefHash",
"briefLength", "namedSkills", "suggestedSkills", "advisoryEmitted"}` shape (no `hook` key). No
prompt/brief text, paths, or tool output is ever logged — ids, lengths, and truncated sha256
hashes only, matching skill-monitor's privacy precedent. `skill-router.js` additionally logs a
1-in-20 sample of no-suggestion prompts (`"suggested": null`) so silence precision has a
denominator. `rhize-context-manager/scripts/suggestion_log_report.py` (also reachable via a
compatibility shim at `scripts/suggestion_log_report.py` in the repo root) joins the legacy rows against
skill-monitor usage data to report per-hook acceptance and ignore rates, and reports the
agent-dispatch rows' named-rate/candidate-present/candidate-miss-rate in a separate section.
Two env overrides exist for tests/evals: `RHIZE_SUGGESTION_LOG` (log file path) and
`RHIZE_CONTEXT_MANAGER_DIR` (where the hooks look for the compiled map/indexes).

## Per-repository and migration hooks (`setup/manifest.json`)

Nine hooks remain declared in `setup/manifest.json` for backward-compatible setup inventory.
Seven are opt-in per-repository items (`default: false`). The selector/finalizer rows are Claude
Code migration metadata now that the scripts are auto-wired in `hooks/hooks.json`; do not wire a
second Claude copy. Codex invokes the shared runner explicitly through its canonical skill.
Three generalized hooks live under
`skills/context-engineering/hooks/` and require project-specific files
(`COMPONENT_REGISTRY.md`, `CURRENT_SPRINT.md`) to be useful, so auto-wiring them for
every repo would be noise:

| id | Event | Tier | Purpose |
|---|---|---|---|
| `session-init` | `SessionStart` | T3 (advisory) | Session banner: project name, sprint/registry freshness, active work item, uncommitted count |
| `duplicate-check` | `PreToolUse` (`Write`) | T4 (blocking, exit 2) | Blocks creating a new component/hook/utility whose name closely matches an existing `COMPONENT_REGISTRY.md` entry |
| `pre-commit-guard` | `PreToolUse` (`Bash`) | T3 (advisory) | On `git commit`, flags unstaged related files via `additionalContext` — never blocks |
| `skill-router` | `UserPromptSubmit` | T3 (advisory) | Ranks the prompt against the compiled skill-map's topic/stack tags and skill names, surfaces at most one suggested skill via `additionalContext` — never blocks |
| `agent-brief-router` | `PreToolUse` (`^(Agent)$`) | T3 (advisory) | Logs which skills an outgoing subagent brief names vs. which the router index would suggest for it (`source: "agent-dispatch"` rows); a flag-gated advisory (`RHIZE_AGENT_BRIEF_ADVISORY=1`) is off by default — never blocks |
| `context-experiment-selector` | `UserPromptSubmit` | T3 (advisory, auto-wired) | Claims one clean-repository attempt under a repository/capability single-flight lease. Canary claims freeze immediately; continuous claims stay enabled but cannot overlap. |
| `context-experiment-finalizer` | `Stop` | T3 (advisory, auto-wired) | Verifies the native pack again and writes receipt v2 with terminal reason and source-free completeness fields. Only valid completion evidence releases a continuous attempt without freezing. |

`skill-router` and `agent-brief-router` (`hooks/skill-router.js` and
`hooks/agent-brief-router.js`, plugin root — not under `skills/context-engineering/hooks/`
like the other three) both read the compiled skill-map artifact rather than a fixed keyword
list. `skill-router` replaced the keyword-grep `skill-suggester.sh` on 2026-08-09 (Phase 2 of
`.claude/plans/skill-map-graph-substrate.md`): it reads
`~/.claude/context-manager/skill-map.resolved.json` (falling back to `skill-map.static.json`
— installed via `scripts/build_skill_map.py --install`), requires 2+ distinct matching
signals (topic/stack tag or skill-name word match) to fire at all, and fails silently — exit
0, no output — if the map is missing or corrupt. `agent-brief-router` (2026-08-26) is a
**measurement instrument, not a router** — a PreToolUse hook fires only after the brief is
already written, so it cannot fix the dispatch it observes; it exists to measure, session over
session, whether outgoing subagent briefs already name the skill route-core's scoring would
suggest for their content. See `docs/skill-map.md`'s "Agent-dispatch surface" section for the
spike verdicts, scoring details, and known limitations (Workflow `agent()` calls and
scheduled-task sessions bypass this hook entirely — the CLAUDE.md dispatch rule is the only
enforcement there, by design).

`setup/manifest.json` also declares a `dependencies` array (`@rhize/skill-forge`, `headroom`,
`ecc:harness-audit`, and the orchestrated stack tools) that the wizard's dependency check reads.

**Fleet setup:** `/rhize-ops:rhize-setup` is what actually wires these opt-in items and checks
`dependencies` for you — it requires the `rhize-ops` plugin. Without it, wire an item manually
per the snippet in [rhize-ops/README.md § Setup manifest
schema](../../rhize-ops/README.md#setup-manifest-schema).

See [context-experiment-internals.md](context-experiment-internals.md) for what the
context-experiment selector/finalizer actually gate — the dogfood providers, the live P4 gate,
and how evidence is recorded and verified.

## Refinement-pipeline hooks (also in `setup/manifest.json`)

Two of the nine live under `hooks/` directly as refinement-pipeline hooks. They arrived on 2026-08-09, moved
here from `rhize-devflow` (they predate this plugin and were stranded there by the 2.5.0
command migration). Like the five above they are **not** wired in `hooks/hooks.json`, but
`/rhize-setup` can now offer them per-repo the same way (ids `refinement-detector` and
`refinement-session-end`) — no manual `.claude/settings.json` edit required unless you're
wiring without `rhize-ops`.

| Script | Event | Tier | Purpose |
|---|---|---|---|
| `refinement-pipeline__refinement-detector.sh` | `UserPromptSubmit` | T3 (advisory) | Detects "skill doesn't work" / "false positive" / "missing trigger" style phrasing and suggests `/rhize-context-manager:learn-harvest` → `/skill-refine review` |
| `refinement-pipeline__session-end.sh` | `Stop` | T3 (advisory) | At session end, if the session was substantial (>20 tool calls, any error, >60min, or >10 files touched — computed from the transcript JSONL), suggests capturing a refinement via the same two commands |

To enable one, add it to your project's `.claude/settings.json`, e.g.:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/refinement-pipeline__refinement-detector.sh"
          }
        ]
      }
    ]
  }
}
```

Both suggest the same next step — `/rhize-context-manager:learn-harvest` to queue the signal,
then `/skill-refine review` to triage it — rather than a bare `npx @rhize/skill-forge refine`,
which would skip the human-gate/machine-gate trust model the `refinement-pipeline` skill
documents.

## Why this replaces ECC's `suggest-compact`

ECC's hook sizes the window by sniffing the model id for a literal `[1m]`
marker, defaulting to 200k. Opus 5 has a 1M window and carries no marker, so it
divided ~195k by 200k and reported **97% when the true figure was 20%** —
verified against the client's own context readout on 2026-07-28. It self-corrects
only above 200k (its `tokens > 200_000 → assume 1M` fallback), so it is wrong for
the entire run below that and the error is invisible from the message alone.

A marker sniff can only detect windows a model id happens to advertise. `context-window-monitor.js`
resolves in strongest-signal-first order — env override → `[1m]` marker →
**verified known-model table** → observed-usage evidence → 200k default — and
the table is the part upstream structurally cannot have.

**Both hooks will fire unless you disable ECC's.** Add to `~/.claude/settings.json`:

```json
"env": { "ECC_DISABLED_HOOKS": "pre:edit-write:suggest-compact" }
```

### Maintaining the known-model table

`KNOWN_WINDOWS` in the hook is deliberately sparse — it holds only entries
confirmed against a client readout or vendor docs. A wrong entry is worse than
no entry, because it outranks the observed-usage evidence beneath it. An
unlisted model degrades to the same heuristics ECC used, which is today's
behaviour, not a regression.

Verify any change with the built-in self-test (9 cases, including the exact
197.3k-on-Opus-5 regression):

```bash
node hooks/context-window-monitor.js --self-test
```
