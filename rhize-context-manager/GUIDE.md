# rhize-context-manager — User Guide

## What problem does this solve?

Long agent sessions degrade: context fills up, the same knowledge gets injected twice by
competing tools, and nobody remembers which memory layer a fact lives in. This plugin
makes the context stack *legible* — one place that knows every layer, routes knowledge to
the right one, and health-checks the whole thing.

## When to reach for what

- **"Which tool should hold this knowledge?" / "set up context tooling for this repo"**
  → the `context-stack` skill answers routing questions.
  *Example: "Where should the client's evolving pricing decisions live — claude-mem, the vault, or Graphiti?"*

- **"Session start feels slow" / "I'm seeing the same context twice"**
  → `/context-doctor` — read-only health check + overlap flags across Headroom, RTK,
  claude-mem, OpenWolf, Serena/CodeGraph. Every run is saved to
  `~/.claude/context-manager/doctor/`, so the next run shows you a delta ("Serena flag
  cleared since last time", "RTK savings dropped to zero") instead of a cold read every
  time. If the `ecc` plugin's `harness-audit` skill is installed, doctor chains into it
  automatically as a final deeper pass.
  *Example: "Run /context-doctor — rhize-salesforce felt sluggish this morning."*

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

- **"Turn this into a knowledge graph"** → `/graphify` (now served from this plugin —
  remove any stale copy at `~/.claude/skills/graphify` to avoid double-loading).

- **"We need queryable long-term memory with relationships and time"**
  → the `graphiti-memory` skill walks through opt-in Graphiti adoption (backend, MCP
  wiring, usage patterns). Nothing is installed automatically.

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
  *Example: "Run /learn-harvest across all projects, then let's review the queue."*

## Tips

- Run `/context-doctor` when adopting a new repo or after installing/removing any stack
  tool — overlap problems appear at those boundaries. Follow up with `/context-setup` to
  act on anything it flags.
- The three generalized hooks under `skills/context-engineering/hooks/`
  (`session-init`, `duplicate-check`, `pre-commit-guard`) are opt-in — listed in
  `setup/manifest.json`, not auto-wired. They need `COMPONENT_REGISTRY.md` /
  `CURRENT_SPRINT.md` to be useful, so they're per-repo, not global-default.
- `skill-router` (`hooks/skill-router.js`, also opt-in via `setup/manifest.json`)
  replaced the keyword-grep `skill-suggester` hook 2026-08-09 — it ranks the prompt
  against the compiled skill-map's topic/stack tags instead of a fixed keyword list, so
  a newly tagged skill routes without a hook edit. It needs `scripts/build_skill_map.py
  --install` to have run at least once (installs the artifact to
  `~/.claude/context-manager/`); with no artifact present it fails silently and suggests
  nothing.
- Two more opt-in hooks landed directly under `hooks/` (2026-08-09, moved from
  `rhize-devflow`): `refinement-pipeline__refinement-detector.sh` (prompt-keyword
  detector) and `refinement-pipeline__session-end.sh` (Stop-hook session-stats prompt).
  Both are now also in `setup/manifest.json` (ids `refinement-detector` /
  `refinement-session-end`), so `/rhize-setup` can wire them the same as the others —
  see README.md's Hooks section for the manual `.claude/settings.json` snippet if you're
  wiring without `rhize-ops`.
- The third-party skills are safety-gated snapshots; `npx @rhize/skill-forge watch`
  tells you when upstreams have moved.
- Graphiti is approved for Rhize adoption but needs its backend stood up first — until
  then `graphiti-memory` is the design reference, not a working integration.

## Troubleshooting

- **/graphify fires twice or behaves oddly** → you still have the old user-level skill;
  delete `~/.claude/skills/graphify`.
- **Doctor says a layer is "dead" that you expect alive** → check the tool's own logs
  first (`~/.headroom/guard.log`, claude-mem dashboard `localhost:37777`, `.wolf/`
  ledgers) before reconfiguring; the doctor is read-only and only reports.
- **Duplicate context injection** → per the coexistence policy, prefer dropping the
  per-repo memory layer (OpenWolf) over the global one (claude-mem) unless the repo
  actively uses OpenWolf's correction hooks.
