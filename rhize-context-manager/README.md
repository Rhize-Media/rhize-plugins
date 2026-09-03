# rhize-context-manager

Long AI coding sessions get messy: context fills up, background tooling starts repeating
itself, and nobody remembers where a decision or a lesson learned was supposed to be
recorded. This plugin gives a session one place that watches for that, tells you when
something's off, and keeps a running memory of decisions so they survive between sessions.
In practice that's a handful of commands — check session health, open/close a session
cleanly, capture what was learned — plus a quiet background layer that keeps the tools
already installed for your stack from stepping on each other. Start with `/context-doctor`
to see how your current setup is doing, or `/start` to begin a session with full context of
where you left off.

Under the hood, this is a context engineering and optimization plugin covering
**compression, management, retrieval, and storage**. It orchestrates the external context
tools already in the Rhize stack (rather than forking them) and ships a curated,
safety-gated skill library.

## Design: orchestrate, don't vendor

Headroom, claude-mem, Serena, OpenWolf, RTK, and CodeGraph are living external
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
| `context-pack` | Build or verify a private, deterministic source-bound code context preview for a specific implementation, diagnosis, impact-analysis, or re… | context-engineering, search |
| `context-stack` | Routing and coexistence brain for the Rhize context stack. | context-engineering, obsidian, workflow-patterns |
| `graph-memory` | Govern Graphify graph.json artifacts for a Rhize Neo4j projection. | knowledge-graph, memory-systems, neo4j, security |
| `graphify` | Use for any question about a codebase, its architecture, file relationships, or project content — especially when graphify-out/ exists, whe… | knowledge-graph, memory-systems, obsidian, search |
| `graphiti-memory` | Historical design reference for Graphiti concepts. | knowledge-graph, memory-systems |
| `learning-curation` | This skill should be used when deciding whether a session learning, correction, or rule deserves persistent storage — and where to put it s… | context-engineering, learning-curation |
| `memory-context` | Assemble, verify, or explicitly purge a private bounded preview across authorized Rhize memory sources while preserving source authority, c… | context-engineering, memory-systems |
| `refinement-pipeline` | Operate and reason about the gated skill-refinement pipeline: headroom learn + claude-mem + skill-monitor signals flow into a human-triaged… | learning-curation, workflow-patterns |
<!-- SKILL-MAP:END -->

### Curated third-party (ingested via skill-forge, safety-gated, provenance in [skills/SOURCES.md](skills/SOURCES.md))

From **muratcankoylan/Agent-Skills-for-Context-Engineering**: `context-fundamentals`,
`context-degradation`, `context-compression`, `context-optimization`, `memory-systems`,
`filesystem-context`, `tool-design`.

Per the marketplace curation rule, context/token budgeting, iterative retrieval, and
strategic compaction are NOT re-shipped here — `ecc@everything-claude-code` owns them.

Coverage per feature goal: compression (context-compression), retrieval/budgeting
(ecc's skills, by design), memory (memory-systems, memory-context), degradation
(context-degradation), refinement (refinement-pipeline, learning-curation).

## Commands

| Command | Purpose |
|---|---|
| `/context-doctor` | Read-only health check of the active stack layers (Headroom proxy, RTK savings, claude-mem dashboard, OpenWolf state, Serena/CodeGraph) + overlap flags. Asserts **capture liveness** and flags credentials expiring before the next scheduled run. |
| `/context-setup` | Repo-level setup wizard: scans the repo (`config_generator.py`), probes which stack layers are actually active, proposes a tailored per-repo enable/disable list with reasons, and on confirmation writes `~/.claude/rhize-context-manager/stack.config.json`. Owns stack **config** only — hook wiring is `/rhize-core:setup` (rhize-core). |
| `/start` | Session bookend — resume from `STATE.md` with real memory (moved from rhize-devflow) |
| `/done` | Session bookend — delegates code-change review to `/rhize-devflow:review` when Dev Flow is available, else runs a disclosed local fallback checklist, then updates `STATE.md` before commit (moved from rhize-devflow) |
| `/context-hygiene` | Mid-session context cleanup when a session gets heavy (moved from rhize-devflow) |
| `/impact-map` | **Deprecated adapter** — use `/rhize-devflow:impact-map`. The executable workflow (CodeGraph-first discovery plus a semantic change/invariant map, synced and reconciled after implementation) moved to Dev Flow; this adapter remains only for the 2.12.0 compatibility window |
| `/learn-harvest` | Harvest refinement signals (headroom learn dry-run, claude-mem, skill-monitor) into the pending queue — never writes skills or CLAUDE.md. Step 7 runs `scripts/harvest_noise_filter.py` so rephrased-but-known facts don't accumulate |
| `/skill-refine` | `review`: human triage of queued signals · `run`: gated skill-forge evolve pass with auto-promote for SKILL.md-only ALLOW verdicts |
| `/context-experiment` | Disabled-by-default local retrieval, mgrep, and compiled-context control: backward-compatible one-shot canaries or continuous allowlisted local mode, provider health, evidence-backed terminal receipts, and Arm A/B reports. |
| `/context-pack` | Build and inspect a deterministic private pack. Native v2 supports parser-backed Python/JavaScript/TypeScript contracts, mixed targets, healthy-CodeGraph-first discovery, deterministic `rg` fallback, optional hash-only impact-map hints, FULL/INTERFACE roles, and stale-pack verification; preview mode never arms or injects. |
| `/memory-context` | Assemble and verify a private scoped preview over explicit supported memory adapters. Reuse requires an explicit current source-ID/revision map; conflicts, authority, TTL, purge, and unavailable states remain visible; automatic injection and write-back are disabled. |
| `/graph-memory` | Thin Claude adapter to the shared `graph-memory` CLI (`scripts/graph_memory/cli.py`). Defaults to `validate`, then offers a private `preview`. Never invokes `graphify export neo4j`, arbitrary Cypher, a Neo4j driver, or a live database this release; a live canary and restore rehearsal are deferred to a future release (tracked internally as RT-159). |
| `/graph-memory-review` | Thin Claude adapter to the shared `graph-memory hygiene` capability CLI. In-process contracts enforce actor-effective ACL lanes (`review ∩ actor`) so broader actor grants cannot widen a narrow review; every stateful operation remains structured `unavailable` until the hygiene domain owns a private-state adapter. |
| `/graph-decision` | Thin Claude adapter to the shared `graph-memory decision` CLI. Offline preview is available; durable record/query/correction remains explicitly unavailable until a future release (tracked internally as RT-161). |
| `/suggestion-report` | Read-only acceptance-rate report over the shared suggestion log: per-hook suggested/accepted/ignored/ext-unjoin counts and accept%, router silence samples, and the agent-dispatch named-rate/candidate-miss-rate section (with a `by_agent_type` breakdown). Thin adapter over `scripts/suggestion_log_report.py`. |

`/start`, `/done`, `/context-hygiene`, and `/impact-map` are registered only under
`commands/` — the `skills/context-engineering/commands/` copies were removed
2026-08-04 (they had drifted behind: `commands/` had gained frontmatter, a verifier-
subagent step in `/done`, and a `STATE.md` update step that the skill-side copies
lacked). `skills/context-engineering/SKILL.md` now links to the `commands/` originals.

### Scripts shipped with the plugin (`rhize-context-manager/scripts/`)

Three scripts ship with the plugin instead of depending on a dev checkout (the first two moved
in from the repo root on 2026-09-02, R3 task 8 of the portability-readiness plan; the third
replaced a prose step the same day):

- **`harvest_headroom.py`** — the `/learn-harvest` collector for captured `headroom learn`
  reports. Parses every `###`/`####` block into one refinement-queue entry with the pattern
  stored **verbatim** (title, savings estimate, full body), ids as `sha1-12(source + pattern)`,
  and duplicate-safe re-runs; `--audit` lists pending entries that still look truncated. Written
  after the 2026-08-26 run cut seven entries at exactly 550 characters mid-word.
- **`suggestion_log_report.py`** — the acceptance-rate report behind `/suggestion-report`
  above; also runnable directly (`python3 rhize-context-manager/scripts/
  suggestion_log_report.py`).
- **`build_local_skill_map.py`** — builds the machine-local overlay and resolved skill
  map (`skill-map.local.json`, `skill-map.resolved.json`, `skill-map.indexes.resolved.json`
  under `~/.claude/context-manager/`) from the committed static artifact plus optional
  machine-local inputs (enabled plugins, stack config, skill-monitor co-occurrence data,
  third-party plugin inventory). `/rhize-core:setup` installs the compiled skill map
  for this machine via `setup_orchestrator.py install-skill-map`, which calls this script
  to build the overlay whenever it's available at the discovered source root (a dev
  checkout; reported as unavailable from an installed marketplace clone); see
  `docs/skill-map.md` for the artifact shapes.

Both scripts keep a two-line compatibility shim at their old repo-root `scripts/` path,
so `python3 scripts/suggestion_log_report.py` and `python3 scripts/
build_local_skill_map.py` still work — the shims forward to these copies unchanged.

### Harvest noise filter (`scripts/harvest_noise_filter.py`, repo root)

Step 7 of `/learn-harvest` runs a content-based dedupe filter before anything reaches the
queue, so a reworded restatement of an already-known fact doesn't count as a new signal —
on 2026-08-14 this caught 3 of 5 candidate entries that were just rephrasings of facts
already in CLAUDE.md. It scores each candidate against existing queue/CLAUDE.md content
and either suppresses it, flags it for human triage, or keeps it; every decision is logged
to `~/.claude/context-manager/harvest-logs/<date>-filter.txt` so a quiet harvest is never
ambiguous. See [docs/harvest-noise-filter.md](docs/harvest-noise-filter.md) for the scoring
algorithm, thresholds, and calibration data.

## Hooks

| Hook | Event | Purpose |
|---|---|---|
| `context-window-monitor.js` | `PreToolUse` (`Edit\|Write`) | Warns once per 10% band past 75% of the **real** context window |
| `session-disclosure.js` | `SessionStart` | Fingerprints the CWD against a small set of cheap file/dir checks (`next.config.*` → nextjs, `sanity.config.*` → sanity, `vercel.json` → vercel, `.obsidian/` → obsidian), maps any detected stack to its stack-tag edges in the compiled skill-map artifact, and surfaces up to 8 relevant skills. Silent when no stack is detected. |
| `remediation-suggester.js` | `PostToolUse` (`Bash`) | On a failing Bash command, matches `stdout`+`stderr` against the compiled skill-map's remediation-condition patterns (`build-failure`, `type-error`, `test-failure`, `lint-failure`, `merge-conflict`) and suggests the top remediating skill/agent via `additionalContext`. Silent when nothing matches. |
| `next-step-suggester.js` | `PostToolUse` (`Skill`) | After a skill invocation, looks up the invoked skill's succession entry and suggests exactly one next step — the declared `precedes` successor, or the mined `follows` successor if no `precedes` exists. Silent when there's no successor. |
| `context-experiment-selector.js` | `UserPromptSubmit` | Fail-silent Claude Code selector. Strict disabled-by-default config, allowlist, task, clean-repository, provider, snapshot, duration, and single-flight gates decide whether to emit an accepted local pack/evidence command. |
| `context-experiment-finalizer.js` | `Stop` | Writes one evidence-backed terminal receipt. Completed continuous attempts remain enabled; failed, incomplete, stale, or malformed evidence freezes further claims. |

All six hooks are auto-wired for Claude Code in `hooks/hooks.json`. Codex does not consume this
Claude hook manifest; it discovers the same canonical skills and must invoke the host-neutral
context pack or experiment runner explicitly. Both paths remain behaviorally inert until strict
configuration explicitly enables a capability for an allowlisted repository.

The five map-reading hooks above (`session-disclosure`, `remediation-suggester`,
`next-step-suggester`, plus opt-in `skill-router` and `agent-brief-router`) all resolve the same
compiled skill-map artifact and fail silently on any missing/corrupt input, and the first four
also write a privacy-preserving suggestion log (ids/hashes only, never prompt text) so
acceptance/ignore rates are measurable. Beyond the auto-wired six, nine more hooks are declared
in `setup/manifest.json` for opt-in per-repo use and Claude-plugin migration bookkeeping —
`/rhize-core:setup` wires them for you if that plugin is installed, otherwise see the
snippet in [rhize-core/README.md § Setup manifest schema](../rhize-core/README.md#setup-manifest-schema).
Two of those nine are refinement-pipeline hooks that detect "this skill doesn't work" style
phrasing or a substantial session ending, and suggest capturing it via `/learn-harvest` →
`/skill-refine review`.

The `context-window-monitor.js` hook exists because ECC's equivalent hook sizes the context
window by sniffing the model id for a literal `[1m]` marker — Opus 5 has a 1M window and no such
marker, so ECC's hook reported 97% usage when the real figure was 20% (verified 2026-07-28).
This hook instead resolves in strongest-signal-first order (env override → `[1m]` marker →
verified known-model table → observed-usage evidence → 200k default). **Both hooks will fire
unless you disable ECC's** — add to `~/.claude/settings.json`:

```json
"env": { "ECC_DISABLED_HOOKS": "pre:edit-write:suggest-compact" }
```

See [docs/hooks-reference.md](docs/hooks-reference.md) for the full hook catalog (including the
nine `setup/manifest.json` entries and the refinement-pipeline hooks with their wiring snippet),
skill-map resolution order, suggestion-log schema, and how to extend the known-model table. See
[docs/context-experiment-internals.md](docs/context-experiment-internals.md) for what the
context-experiment selector/finalizer hooks actually gate: the dogfood retrieval providers, the
live P4 selection gate, and how evidence receipts are recorded and verified.

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
| `dependsOn` | Runtime dependencies, e.g. `["mcp:codegraph"]` — mints an `mcp-server` node in the compiled map. |

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
| Neo4j | governed semantic projection | ontology, fake-adapter, and in-process identity-review contracts available; shared review state and the credentialed live canary/restore remain deferred to a future release (tracked internally as RT-159) |

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
