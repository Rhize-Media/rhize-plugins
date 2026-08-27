# rhize-context-manager

Context engineering and optimization plugin: **compression, management, retrieval, and
storage**. It orchestrates the external context tools already in the Rhize stack (rather
than forking them) and ships a curated, safety-gated skill library.

## Design: orchestrate, don't vendor

Headroom, claude-mem, Serena, OpenWolf, RTK, CodeGraph, and Graphiti are living external
tools with their own release cycles. This plugin owns the *decision layer* — which tool
to use when, how they coexist, and how to health-check the stack — while the binaries
and their own hook plugins stay externally installed and updated.

## Install

Install `rhize-devflow` alongside this plugin. Dev Flow owns the executable `/impact-map` command
(`/rhize-devflow:impact-map`); this plugin keeps a deprecation adapter at `/impact-map` for the
2.12.0 compatibility window only.

**Claude Code / Cowork:**

```text
/plugin marketplace add https://github.com/Rhize-Media/rhize-plugins
/plugin install rhize-devflow@rhize-plugins
/plugin install rhize-context-manager@rhize-plugins
```

**Codex:**

```bash
codex plugin marketplace add https://github.com/Rhize-Media/rhize-plugins
codex plugin add rhize-devflow@rhize-plugins
codex plugin add rhize-context-manager@rhize-plugins
```

Start a new session after an install or update. CodeGraph itself remains optional:
`/rhize-devflow:impact-map` uses an existing healthy index when available and otherwise falls
back to `rg`.

## Skills

### Rhize-authored (orchestration layer)

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `context-engineering` | Systematic context, session, and memory management for Claude Code development sessions: start/resume/close a working session, preserve and… | context-engineering, project-planning, workflow-patterns |
| `context-stack` | Routing and coexistence brain for the Rhize context stack. | context-engineering, obsidian, workflow-patterns |
| `graphify` | Use for any question about a codebase, its architecture, file relationships, or project content — especially when graphify-out/ exists, whe… | knowledge-graph, memory-systems, obsidian, search |
| `graphiti-memory` | Adoption and usage guide for Graphiti — Zep's temporal knowledge-graph memory layer for agents. | knowledge-graph, memory-systems |
| `learning-curation` | This skill should be used when deciding whether a session learning, correction, or rule deserves persistent storage — and where to put it s… | context-engineering, learning-curation |
| `refinement-pipeline` | Operate and reason about the gated skill-refinement pipeline: headroom learn + claude-mem + skill-monitor signals flow into a human-triaged… | learning-curation, workflow-patterns |
<!-- SKILL-MAP:END -->

### Curated third-party (ingested via skill-forge, safety-gated, provenance in [skills/SOURCES.md](skills/SOURCES.md))

From **muratcankoylan/Agent-Skills-for-Context-Engineering**: `context-fundamentals`,
`context-degradation`, `context-compression`, `context-optimization`, `memory-systems`,
`filesystem-context`, `tool-design`.

Per the marketplace curation rule, context/token budgeting, iterative retrieval, and
strategic compaction are NOT re-shipped here — `ecc@everything-claude-code` owns them.

Coverage per feature goal: compression (context-compression), retrieval/budgeting
(ecc's skills, by design), memory (memory-systems, graphiti-memory), degradation
(context-degradation), refinement (refinement-pipeline, learning-curation).

## Commands

| Command | Purpose |
|---|---|
| `/context-doctor` | Read-only health check of every layer (Headroom proxy, RTK savings, claude-mem dashboard, OpenWolf state, Serena/CodeGraph, Graphiti) + overlap flags. Persists each run to `~/.claude/context-manager/doctor/<YYYY-MM-DD-HHMM>.json`, prints a delta against the previous run, and — if the `ecc` plugin's `harness-audit` skill is available — chains into it as a final deeper pass (graceful one-line skip otherwise). |
| `/context-setup` | Repo-level setup wizard: scans the repo (`config_generator.py`), probes which stack layers are actually active, proposes a tailored per-repo enable/disable list with reasons, and on confirmation writes `~/.claude/rhize-context-manager/stack.config.json`. Owns stack **config** only — hook wiring is `/rhize-setup` (rhize-ops). |
| `/start` | Session bookend — resume from `STATE.md` with real memory (moved from rhize-devflow) |
| `/done` | Session bookend — delegates code-change review to `/rhize-devflow:review` when Dev Flow is available, else runs a disclosed local fallback checklist, then updates `STATE.md` before commit (moved from rhize-devflow) |
| `/context-hygiene` | Mid-session context cleanup when a session gets heavy (moved from rhize-devflow) |
| `/impact-map` | **Deprecated adapter** — use `/rhize-devflow:impact-map`. The executable workflow (CodeGraph-first discovery plus a semantic change/invariant map, synced and reconciled after implementation) moved to Dev Flow; this adapter remains only for the 2.12.0 compatibility window |
| `/learn-harvest` | Harvest refinement signals (headroom learn dry-run, claude-mem, skill-monitor) into the pending queue — never writes skills or CLAUDE.md. Step 7 runs `scripts/harvest_noise_filter.py` so rephrased-but-known facts don't accumulate |
| `/skill-refine` | `review`: human triage of queued signals · `run`: gated skill-forge evolve pass with auto-promote for SKILL.md-only ALLOW verdicts |
| `/context-experiment` | Opt-in local retrieval, mgrep, and Context Compiler dogfood control: provider health, bounded arming, real dry-run/eval/compile execution, redaction-safe receipts, and Arm A/B reports. No provider is enabled by default. |

`/start`, `/done`, `/context-hygiene`, and `/impact-map` are registered only under
`commands/` — the `skills/context-engineering/commands/` copies were removed
2026-08-04 (they had drifted behind: `commands/` had gained frontmatter, a verifier-
subagent step in `/done`, and a `STATE.md` update step that the skill-side copies
lacked). `skills/context-engineering/SKILL.md` now links to the `commands/` originals.

### Harvest noise filter (`scripts/harvest_noise_filter.py`)

Queue entry ids are `sha1-12(source + pattern)`, so **a rephrasing of an already-known
fact produces a new id and walks past id-dedupe**. Measured on 2026-08-14: 3 of 5
headroom entries restated facts folded into CLAUDE.md on 2026-08-12, and the two largest
`est_savings` claims (235k, 45k) were the two most duplicative — roughly 30% of a day's
yield spent re-litigating settled facts.

Step 7 of `/learn-harvest` runs this filter, which matches on content instead of hash.
Each candidate is scored by greedy set-cover: what fraction of its normalized content
tokens are covered by up to `--max-blocks` (default 3) reference blocks, drawn from
existing queue patterns (**any** status) and the CLAUDE.md files passed via `--reference`.

| Outcome | Coverage | Action |
|---|---|---|
| `suppressed` | ≥ `--threshold` (0.75) | dropped — a restatement |
| `flagged` | ≥ `--flag-threshold` (0.45) | **kept**, tagged with `filter_note` for triage |
| `thin` | < 6 content tokens | dropped — a bare heading is not a signal |
| `kept` | otherwise | appended normally |

Thresholds are calibrated against the 44 human-labeled dispositions of 2026-08-14, where
the populations separated as: real signals ≤ 0.70, fully-covered restatements ≥ 0.80.
Reproduce with `--self-audit`. Composite entries (`Topic — Fact1. Fact2. Fact3.`) sit in
the 0.46–0.56 band — each fact known, the bundle still part-novel — which is why that band
flags for a human rather than auto-suppressing; no threshold separates them from genuine
signals, so the filter declines to guess.

Stdlib only (system `python3` has no `jsonschema`), deterministic, no network. The report
is teed to `~/.claude/context-manager/harvest-logs/<date>-filter.txt`: suppression must
leave a disk artifact, or "few new entries" becomes indistinguishable from a collector
that never ran.

## Hooks

| Hook | Event | Purpose |
|---|---|---|
| `context-window-monitor.js` | `PreToolUse` (`Edit\|Write`) | Warns once per 10% band past 75% of the **real** context window |
| `session-disclosure.js` | `SessionStart` | Fingerprints the CWD against a small set of cheap file/dir checks (`next.config.*` → nextjs, `sanity.config.*` → sanity, `vercel.json` → vercel, `.obsidian/` → obsidian), maps any detected stack to its stack-tag edges in the compiled skill-map artifact, and surfaces up to 8 relevant skills. Silent when no stack is detected. |
| `remediation-suggester.js` | `PostToolUse` (`Bash`) | On a failing Bash command, matches `stdout`+`stderr` against the compiled skill-map's remediation-condition patterns (`build-failure`, `type-error`, `test-failure`, `lint-failure`, `merge-conflict`) and suggests the top remediating skill/agent via `additionalContext`. Silent when nothing matches. |
| `next-step-suggester.js` | `PostToolUse` (`Skill`) | After a skill invocation, looks up the invoked skill's succession entry and suggests exactly one next step — the declared `precedes` successor, or the mined `follows` successor if no `precedes` exists. Silent when there's no successor. |

All four hooks are auto-wired in `hooks/hooks.json` — they ship active by default.
`session-disclosure.js` replaced the four per-plugin SessionStart banners (seo-aeo-geo,
obsidian-second-brain, project-launcher, rhize-devflow) on 2026-08-09 — Phase 3 of
`.claude/plans/skill-map-graph-substrate.md`. `remediation-suggester.js` and
`next-step-suggester.js` were added 2026-08-09 as the runtime consumers for relationships v2
(`docs/superpowers/specs/2026-08-09-skill-map-relationships-v2-design.md` section 7) — the
first runtime consumer of `precedes`, and the first consumer of the `remediates`/`condition`
data. All five resolve the compiled skill-map artifact the same way: the materialized indexes
first (`~/.claude/context-manager/skill-map.indexes.resolved.json`, falling back to
`skill-map.indexes.json`), and — for `skill-router.js`/`session-disclosure.js`/
`agent-brief-router.js` only — a further fallback to the older
`skill-map.resolved.json`/`skill-map.static.json` map-scan path when no indexes file exists at
all. All five fail silently (exit 0, no output) on any missing or corrupt input. See
`docs/skill-map.md` for the artifact/tagging conventions they depend on.

`session-disclosure.js`, `remediation-suggester.js`, and `next-step-suggester.js` — plus
`skill-router.js` and `agent-brief-router.js` below, both opt-in — also write a **suggestion
log**, one JSON line per fired event, appended fail-silent to
`~/.claude/context-manager/suggestion-log.jsonl`. Two row shapes share that file: the legacy
`{"ts", "session_id", "hook", "suggested", "context_hash"}` shape the first four of these hooks write, and
`agent-brief-router.js`'s `{"ts", "source": "agent-dispatch", "agentType", "briefHash",
"briefLength", "namedSkills", "suggestedSkills", "advisoryEmitted"}` shape (no `hook` key —
see below). No prompt/brief text, paths, or tool output is ever logged — ids, lengths, and
truncated sha256 hashes only, matching skill-monitor's privacy precedent. `skill-router.js`
additionally logs a 1-in-20 sample of no-suggestion prompts (`"suggested": null`) so silence
precision has a denominator. `scripts/suggestion_log_report.py` (repo root) joins the legacy
rows against skill-monitor usage data to report per-hook acceptance and ignore rates, and
reports the agent-dispatch rows' named-rate/candidate-present/candidate-miss-rate in a
separate section. Two env overrides exist for tests/evals: `RHIZE_SUGGESTION_LOG` (log file
path) and `RHIZE_CONTEXT_MANAGER_DIR` (where the hooks look for the compiled map/indexes).

### Opt-in hooks (`setup/manifest.json`)

Nine hooks are declared in `setup/manifest.json` as opt-in items (`default: false`) for
`/rhize-setup` (rhize-ops) to wire per-repo — none of the nine are in `hooks/hooks.json`
and none do anything until enabled. Three generalized hooks live under
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
| `context-experiment-selector` | `UserPromptSubmit` | T3 (advisory) | Claims the next eligible, explicitly armed local-retrieval, mgrep, or compiled-context experiment only when the pinned real provider and snapshot are healthy. |
| `context-experiment-finalizer` | `Stop` | T3 (advisory) | Finalizes durable execution evidence; interrupted runs receive an incomplete receipt and do not consume the armed run. |

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

`setup/manifest.json` also declares a `dependencies` array (`@rhize/skill-forge`, `headroom`,
`ecc:harness-audit`, and the orchestrated stack tools) that the wizard's dependency check reads.

**Fleet setup:** `/rhize-ops:rhize-setup` is what actually wires these opt-in items and checks
`dependencies` for you — it requires the `rhize-ops` plugin. Without it, wire an item manually
per the snippet in [rhize-ops/README.md § Setup manifest
schema](../rhize-ops/README.md#setup-manifest-schema).

### Context-tool dogfood providers

The experiment selector does not install the official mgrep agent instructions or replace
CodeGraph/`rg`. The tested CLI is pinned to `@mixedbread/mgrep@0.1.13`; install and remove it
explicitly with `npm install -g @mixedbread/mgrep@0.1.13` and
`npm uninstall -g @mixedbread/mgrep`. `mgrep login` uses the vendor's device flow and writes
its token to `~/.mgrep/token.json`; `/context-experiment doctor` refuses that login when the
file is broader than mode `0600`. A dry-run may create or retrieve the named remote store but
does not upload files. Actual repository indexing always requires a separately reviewed local
manifest and explicit approval for the exact repository and `rhize-dogfood-*` store.

The current dogfood gate is stricter: do not create a Mixedbread account, run `mgrep login`, or
create a store until the dated provider-economics/privacy review in
[`mgrep-context-compiler-dogfood.md`](../.claude/plans/mgrep-context-compiler-dogfood.md)
passes. Mixedbread's published free-tier data-use language is contradictory, so the plan tests a
pinned local semantic-retrieval candidate first and keeps managed mgrep as a separately measured,
explicitly approved arm.

The local comparison path pins grepai `0.35.0`, Ollama `0.33.1`, and
`nomic-embed-text:v1.5`. It runs only with loopback Ollama, cloud features disabled, a reviewed
configuration checksum, a GOB store, and a current independently generated snapshot marker.
Direct `grepai watch` execution in a real main worktree is prohibited: 0.35.0 automatically
discovers and initializes linked worktrees and has no supported opt-out. The first real isolated
six-case benchmark also failed correctness non-inferiority (five critical misses versus zero for
ripgrep), so `localRetrieval` remains disabled and unarmed pending a materially improved provider
or configuration. See [`evals/context-tools`](../evals/context-tools/README.md).

The Context Compiler adapter runs an unmodified checkout pinned to revision
`4edb163911f9a6bc869f35970fa77acb3dd88b8f`, verifies the MIT license and source-file
checksums, and emits repository-relative private prompt packs. Its 40,000-token, 50%-coverage,
and 10-name-collision limits are preliminary injection guardrails, not evidence that a pack
improves a coding task. The default checkout is
`~/.claude/rhize-context-manager/providers/context-compiler`; override it with
`RHIZE_CONTEXT_COMPILER_CHECKOUT`. See
[`evals/context-tools`](../evals/context-tools/README.md).

### Refinement-pipeline hooks (also in `setup/manifest.json`)

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

### Why this replaces ECC's `suggest-compact`

ECC's hook sizes the window by sniffing the model id for a literal `[1m]`
marker, defaulting to 200k. Opus 5 has a 1M window and carries no marker, so it
divided ~195k by 200k and reported **97% when the true figure was 20%** —
verified against the client's own context readout on 2026-07-28. It self-corrects
only above 200k (its `tokens > 200_000 → assume 1M` fallback), so it is wrong for
the entire run below that and the error is invisible from the message alone.

A marker sniff can only detect windows a model id happens to advertise. This
hook resolves in strongest-signal-first order — env override → `[1m]` marker →
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

## Skill-map frontmatter conventions

Every Rhize-authored skill in `skills/*/SKILL.md` declares its skill-map identity under a
`metadata.rhize` block in frontmatter, e.g.:

```yaml
metadata:
  rhize:
    topics: [context-compression, context-engineering]
    stacks: []
    extends: [context-fundamentals]
```

| Field | Meaning |
|---|---|
| `topics` | Topic tags — what the skill is about; drives `skill-router.js`/`session-disclosure.js` topic-tag matching. |
| `stacks` | Stack tags — which detected project stack (nextjs, sanity, vercel, obsidian, …) the skill is relevant to; drives `session-disclosure.js`'s stack fingerprint match. |
| `extends` | Names an existing skill this one deliberately deepens/specializes (chains capped at depth 2 by the compiler). Also the declaration `skill-forge`'s `--skill-map` overlap gate checks for its exemption. |
| `augments` | Names a topic (not a skill) this skill should run alongside/after — a cross-cutting modifier, distinct from `extends`. |
| `remediates` | Names a `tag:condition/<slug>` this skill fixes when detected in failed tool output — feeds `remediation-suggester.js`. |
| `dependsOn` | Runtime dependencies, e.g. `["mcp:graphiti"]` — mints an `mcp-server` node in the compiled map. |

`docs/skill-map.md` (repo root) is the authoritative schema/tagging reference; this table
is the quick-lookup version for anyone editing a `SKILL.md` here.

## Querying the compiled map

`python3 scripts/query_skill_map.py --list` (run from the `rhize-plugins` repo root)
prints the named, declarative queries available over `catalog/queries.json` — the
second tier of the two-tier query layer (the first tier is the materialized
`generated/skill-map.indexes.json` the hooks above read directly). Use it instead of
hand-writing a traversal when you need something the hooks don't already answer, e.g.
`python3 scripts/query_skill_map.py what-follows context-engineering --resolved` (the
`--resolved` flag reads the installed, third-party-merged
`~/.claude/context-manager/skill-map.resolved.json` instead of the repo-local static
artifact — required for anything touching `follows` edges or third-party nodes).

## The stack this plugin orchestrates

| Tool | Layer | Install (external) |
|---|---|---|
| Headroom | wire compression proxy (:8787) | github.com/chopratejas/headroom (own hooks plugin) |
| RTK | CLI output compression | `brew`-installed `rtk` |
| claude-mem | global session memory (:37777) | github.com/thedotmack/claude-mem (own plugin) |
| OpenWolf | per-repo file intel (`.wolf/`) | `openwolf` binary, per-repo opt-in |
| Serena | semantic code navigation | MCP server (user scope) |
| CodeGraph | code knowledge graph | `codegraph` CLI + MCP, `codegraph init` per repo |
| graphify | vault knowledge graphs | skill (vendored here) |
| Graphiti | temporal KG memory | opt-in — see `graphiti-memory` skill |

### Per-repo stack config

`skills/context-stack/references/stack.config.schema.json` (`schemaVersion: 2`) is the
schema for `$HOME/.claude/rhize-context-manager/stack.config.json` — read by the
`context-stack` skill's routing logic, written by `/context-setup`. v2 added
`repoOverrides` (per-repo enable/disable decisions with reasons) alongside the original
`layers` catalog, so one repo's setup run never has to mutate the shared inventory other
repos also read. `skills/context-engineering/scripts/config_generator.py --scan <path>`
(used by `/context-setup` Step 1 to infer project type) had a bug where scanning `.`
produced an empty project name (`Path(".").name == ""`); fixed 2026-08-04 to resolve the
path first.

## Maintenance

- Third-party skill drift: `npx @rhize/skill-forge watch` reads [skills/SOURCES.md](skills/SOURCES.md)
  and reports upstream movement.
- New intake: always via `npx @rhize/skill-forge add -y -t rhize-context-manager/skills <source>`
  so the gate + provenance ledger stay authoritative.
