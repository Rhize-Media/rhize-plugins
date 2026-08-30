# rhize-context-manager — User Guide

## What problem does this solve?

Long agent sessions degrade: context fills up, the same knowledge gets injected twice by
competing tools, and nobody remembers which memory layer a fact lives in. This plugin
makes the context stack *legible* — one place that knows every layer, routes knowledge to
the right one, and health-checks the whole thing.

## When to reach for what

- **"Which tool should hold this knowledge?" / "set up context tooling for this repo"**
  → the `context-stack` skill answers routing questions.
  *Example: "Where should the client's evolving pricing decisions live, and what may be previewed?"*

- **"Session start feels slow" / "I'm seeing the same context twice"**
  → `/context-doctor` — read-only health check + overlap flags across Headroom, RTK,
  claude-mem, OpenWolf, Serena/CodeGraph. Every run is saved to
  `~/.claude/context-manager/doctor/`, so the next run shows you a delta ("Serena flag
  cleared since last time", "RTK savings dropped to zero") instead of a cold read every
  time. If the `ecc` plugin's `harness-audit` skill is installed, doctor chains into it
  automatically as a final deeper pass.
  *Example: "Run /context-doctor — rhize-salesforce felt sluggish this morning."*

  It will not call a layer healthy just because its port answers: claude-mem has to show
  new observations since the last run, or it is reported `dead`. If no sessions ran at all,
  it says `indeterminate` rather than pretending a quiet week is a healthy one. It also warns
  about credentials due to expire before the next weekly run — the failure mode that silently
  killed memory capture for three days in August 2026.

- **"Set up context tooling for this repo" / "which layers should this repo actually run"**
  → `/context-setup` — scans the repo to infer its type, checks which stack layers are
  actually active (via the same probes as `/context-doctor`), proposes a tailored
  enable/disable list with one-line reasons (e.g. "disable Serena — CodeGraph is already
  indexed here"), and on your confirmation writes the decision to
  `~/.claude/rhize-context-manager/stack.config.json`. It only touches that config file —
  it won't install a tool or wire a hook for you; for hook wiring across plugins, run
  `/rhize-setup` (rhize-ops) once that lands.
  *Example: "Run /context-setup on this repo — I want to know if OpenWolf is worth it here."*

- **"Start / where were we / save context / context is getting heavy"**
  → the `context-engineering` skill (sessions, memory extraction, hygiene). This moved
  here from rhize-devflow; all triggers work as before.

- **"Done / finished / ready to commit / wrap up"**
  → `/done` — the session-closure bookend. If this session changed code **and**
  `rhize-devflow` is installed with its `/review` command available, `/done` delegates to
  the fully qualified `/rhize-devflow:review` (Dev Flow's production merge/release gate,
  which routes to its independent verifier subagent for non-trivial changes) rather than
  grading its own work. Without Dev Flow installed, or when no code changed this session,
  `/done` runs — and explicitly discloses — a minimal local fallback checklist instead; it
  never silently skips review or blocks session closure on Dev Flow's absence. Either path
  ends with a `STATE.md` update before commit.
  *Example: "I'm done with this fix — wrap up the session."*

- **"What will this change affect?" / "map this before implementing"**
  → `/rhize-devflow:impact-map` (Dev Flow owns this command; install `rhize-devflow` alongside
  this plugin) — when the repository already has CodeGraph, it queries that first for current
  symbols, callers, tests, and dependency paths. It then creates a semantic impact map for the
  intended behavior, invariants, planned code, operational effects, acceptance tests, and
  explicitly unaffected paths. After implementation it syncs CodeGraph and reports whether the
  graph, diff, and map are in sync. Without `.codegraph/`, it falls back to `rg`; it never indexes
  a repository without the owner's decision. This plugin's own `/impact-map` is a deprecation
  adapter that points here for the 2.12.0 compatibility window only.
  *Example: "Run /rhize-devflow:impact-map for this sponsor lifecycle change, then reconcile it
  after the fix."*

- **"Build a compact source pack for this task" / "inspect compiled context"**
  → `/context-pack` — a local-only preview for Python, JavaScript, TypeScript, and mixed targets.
  Give it one or more target files, or a task query; it uses CodeGraph first only when an existing
  `.codegraph/` is healthy/current, otherwise uses deterministic `rg`, records why each
  FULL/INTERFACE entry was selected, and fails closed
  on dynamic or stale dependencies. `verify-pack` must pass before reuse after any edit. The
  optional `--impact-map .claude/plans/<name>.md` bridge adds semantic terms and source-file seeds
  while recording only hashes/counts. Claude Code auto-wires the selector/finalizer hooks; Codex
  exposes the same host-neutral runner through the `context-pack` and `context-experiment` skills
  and must invoke it explicitly. Strict config disables all providers by default. Canary mode stays one-shot; explicitly enabled
  continuous local mode stays live only after evidence-backed success and freezes on every
  incomplete/failed/stale/malformed terminal state. No network provider is enabled by this command.
  *Example: "Run /context-pack for the account sync target, inspect the reasons, then verify it
  before using it in review."*

- **"Assemble context from several memory sources" / "show memory conflicts"**
  → `/memory-context` — a private, explicit preview that preserves source authority, scope,
  conflicts, TTL, and unavailable adapters. It never scrapes host transcripts, executes recalled
  procedures, writes back, or injects automatically.

- **"Turn this into a knowledge graph"** → `/graphify` (now served from this plugin —
  remove any stale copy at `~/.claude/skills/graphify` to avoid double-loading).

- **"We need queryable long-term memory with relationships and time"**
  → use the `graph-memory` ontology and bounded offline hygiene contracts; the `graphiti-memory`
  skill is historical design context only. Graphiti was not implemented and must not be installed
  or routed as a fallback. Live Neo4j projection remains behind RT-159.

- **"Review these possible duplicate graph entities" / "reverse this SAME_AS decision"**
  → use `graph-memory` (`/graph-memory-review` in Claude) to inspect capability. The in-process
  lifecycle tests enforce proposal-only consolidation, leases, previews, CAS, enumerated rationale,
  and reversal blockers, but shared state is not configured yet. Claude and Codex therefore receive
  the same structured unavailable response and must not invent a ledger or claim acceptance.

- **"Preview why we approved this release/experiment/task effect"**
  → use `graph-memory` (`/graph-decision` in Claude) with a typed adapter from the owning workflow.
  The offline release validates private, source-bound previews but does not record or publish them.
  Record/explain/impact/precedent/correction operations return `unavailable` until the governed RT-161
  projection canary; do not create a local fallback ledger. Claude and Codex use the same CLI and
  [adapter contract](skills/graph-memory/references/typed-decision-adapters.md).

- **Deep context-engineering questions** (why does quality degrade at 100k tokens? how
  should I compress? where should a learning be stored?) → the curated library:
  `context-fundamentals`, `context-degradation`, `context-compression`,
  `context-optimization`, `memory-systems`, `filesystem-context`, `tool-design`,
  `learning-curation`. (Budgeting/retrieval/compaction live in ecc by design.)

- **"Harvest what we learned" / "refine our skills from real sessions"**
  → the refinement pipeline: `/learn-harvest` collects signals (headroom learn dry-run,
  claude-mem observations, skill-monitor snapshots) into a queue; `/skill-refine review`
  is your triage pass; `/skill-refine run` drains triaged entries through skill-forge
  `evolve` — gate-passing SKILL.md edits auto-promote, anything touching scripts/hooks
  HOLDs. The `refinement-pipeline` skill documents the trust model.
  *Example: "Run /learn-harvest across all sources, then let's review the queue."*
  (The `all` argument means all three **sources** above. Headroom stays scoped to the
  current project — it is never passed `--all`, which would sweep every discovered
  project and take minutes instead of seconds.)

  **Why the queue doesn't fill up with the same lesson twice.** Entries are de-duped by a
  hash of their text, so a fact reworded slightly used to sail through as "new" — on
  2026-08-14, 3 of 5 headroom findings were restatements of things already written into
  CLAUDE.md. `/learn-harvest` now runs a content filter before it appends: anything whose
  substance is already in CLAUDE.md or in an existing queue entry gets dropped, and
  anything that *looks* like a repackaging of known facts is kept but tagged so you see it
  at triage. Every decision it makes is written to
  `~/.claude/context-manager/harvest-logs/<date>-filter.txt`, so a quiet harvest is never
  ambiguous — you can always read back exactly what was dropped and why.
  *Example: "Why was today's harvest only two entries?" → open that day's filter report.*

## Tips

- Run `/context-doctor` when adopting a new repo or after installing/removing any stack
  tool — overlap problems appear at those boundaries. Follow up with `/context-setup` to
  act on anything it flags.
- The three generalized hooks under `skills/context-engineering/hooks/`
  (`session-init`, `duplicate-check`, `pre-commit-guard`) are opt-in — listed in
  `setup/manifest.json`, not auto-wired. They need `COMPONENT_REGISTRY.md` /
  `CURRENT_SPRINT.md` to be useful, so they're per-repo, not global-default.
- `context-experiment-selector.js` and `context-experiment-finalizer.js` are auto-wired for Claude
  Code and no-op while capabilities are disabled. Codex uses the same host-neutral runner through
  explicit skill invocation; it does not consume `hooks/hooks.json`. Remove older manually wired
  Claude entries when updating; duplicate calls are state-safe but waste local provider work.
- `skill-router` (`hooks/skill-router.js`, also opt-in via `setup/manifest.json`)
  replaced the keyword-grep `skill-suggester` hook 2026-08-09 — it ranks the prompt
  against the compiled skill-map's topic/stack tags instead of a fixed keyword list, so
  a newly tagged skill routes without a hook edit. It needs `scripts/build_skill_map.py
  --install` to have run at least once (installs the artifact to
  `~/.claude/context-manager/`); with no artifact present it fails silently and suggests
  nothing.
- `session-disclosure` (`hooks/session-disclosure.js`, auto-wired — not opt-in) replaced
  the four per-plugin SessionStart banners on 2026-08-09: seo-aeo-geo,
  obsidian-second-brain, project-launcher, and rhize-devflow no longer print anything on
  session start. Instead, this one hook fingerprints the repo (a `next.config.*`,
  `sanity.config.*`, `vercel.json`, or `.obsidian/` on disk) and lists up to 8 skills
  tagged for that stack — silent in repos with none of those markers, same map
  dependency as `skill-router`.
- `remediation-suggester` and `next-step-suggester` (`hooks/remediation-suggester.js`,
  `hooks/next-step-suggester.js`, both auto-wired — not opt-in) landed 2026-08-09 as the
  runtime layer for relationships v2. After a failing `Bash` command, the first hook
  matches the output against the skill map's `remediates`/`condition` data and suggests a
  fix (e.g. "the ecc:build-error-resolver agent remediates build-failure"). After any
  `Skill` invocation, the second hook suggests the usual next step from that skill's
  `precedes` (or, absent one, a mined `follows`) edge — e.g. after `write-prd`, "the usual
  next step is grill-prd". Both need `scripts/build_skill_map.py --install` to have run at
  least once, same as `skill-router`; with no artifact present they fail silently.
- All five map hooks (`skill-router`, `session-disclosure`, `remediation-suggester`,
  `next-step-suggester`, `agent-brief-router`) log each fired event (2026-08-10, extended
  2026-08-26) to `~/.claude/context-manager/suggestion-log.jsonl` — ids/hashes/lengths only,
  never prompt or brief text — so "was this suggestion actually followed?" is finally
  measurable. The first four share one row shape (`{hook, suggested, ...}`);
  `agent-brief-router` logs a different one (`source: "agent-dispatch"`, no `hook` key — see
  below). Run `python3 scripts/suggestion_log_report.py` (repo root) for per-hook
  acceptance/ignore rates plus the agent-dispatch section (named-rate, candidate-present,
  candidate-miss rate); the skill-graph eval suite (`evals/skill-map/`) builds on the same log.
- `agent-brief-router` (`hooks/agent-brief-router.js`, opt-in via `setup/manifest.json`,
  matcher `^(Agent)$`) measures, per outgoing subagent dispatch, whether the brief already
  named a skill (via "Invoke `<plugin:skill>` first") that the router index would also have
  suggested for its content. It's a measurement instrument, not a router — a PreToolUse hook
  fires only after the brief is written, so it can't fix the dispatch it's observing, only
  inform the next one. Read the numbers via `suggestion_log_report.py`'s agent-dispatch
  section (above). Enable it the same way as `skill-router`, via `/rhize-setup` or a manual
  `.claude/settings.json` entry keyed `agent-brief-router`; a one-line next-dispatch advisory
  exists behind `RHIZE_AGENT_BRIEF_ADVISORY=1` but stays off until the logged data has been
  reviewed. See `docs/skill-map.md`'s "Agent-dispatch surface" section for the spike verdicts
  and known limitations (Workflow `agent()` calls and scheduled tasks bypass this hook
  entirely — by design, no hook covers them).
- Two more opt-in hooks landed directly under `hooks/` (2026-08-09, moved from
  `rhize-devflow`): `refinement-pipeline__refinement-detector.sh` (prompt-keyword
  detector) and `refinement-pipeline__session-end.sh` (Stop-hook session-stats prompt).
  Both are now also in `setup/manifest.json` (ids `refinement-detector` /
  `refinement-session-end`), so `/rhize-setup` can wire them the same as the others —
  see README.md's Hooks section for the manual `.claude/settings.json` snippet if you're
  wiring without `rhize-ops`.
- The third-party skills are safety-gated snapshots; `npx @rhize/skill-forge watch`
  tells you when upstreams have moved.
- Graphiti was not implemented. Neo4j is available, but its live semantic-memory adapter remains
  blocked on RT-159 even though ontology and private offline hygiene contracts now exist;
  `memory-context` is preview-only in the meantime.

## Troubleshooting

- **`/impact-map` is unknown, or only shows a deprecation notice** → the executable command is
  `/rhize-devflow:impact-map`; install/update the `rhize-devflow` plugin, then start a new session.
  This plugin's own `/impact-map` is a deprecation adapter for the 2.12.0 compatibility window.
- **/graphify fires twice or behaves oddly** → you still have the old user-level skill;
  delete `~/.claude/skills/graphify`.
- **Doctor says a layer is "dead" that you expect alive** → check the tool's own logs
  first (`~/.headroom/guard.log`, claude-mem dashboard `localhost:37777`, `.wolf/`
  ledgers) before reconfiguring; the doctor is read-only and only reports.
- **Duplicate context injection** → per the coexistence policy, prefer dropping the
  per-repo memory layer (OpenWolf) over the global one (claude-mem) unless the repo
  actively uses OpenWolf's correction hooks.
