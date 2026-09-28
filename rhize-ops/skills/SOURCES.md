# Rhize Skill Forge — Provenance Ledger

One entry per external-skill ingestion decision.

## parallel-agent-optimization — 2026-08-30
- **Source:** https://github.com/affaan-m/ECC/tree/main/skills/parallel-execution-optimizer
- **Additional source:** https://github.com/obra/superpowers/tree/main/skills/dispatching-parallel-agents
- **Upstream ref:** ECC 2.2.0; Superpowers 6.3.0
- **Upstream skill digests:** ECC `b44def0f7c24ab2505bd2eee10ceb777d591724dbe32dfdf5220354385e1e3ab`; Superpowers `1968923066f3b707eb01d1992cdf4c42284c3855f70253b9cd5000ff45fca13c`
- **License:** MIT (both upstream plugins)
- **Verb:** CONSOLIDATE (human-authorized)
- **Graph relation:** provenance-only
- **Target:** rhize-ops:parallel-agent-optimization
- **Took:** high-level dependency/lane planning, deliberate polling, focused self-contained agent briefs, and coordinator integration review; no examples or source bodies vendored
- **Verified:** exact installed source and MIT license inspection; focused lifecycle/privacy/readiness tests; legacy v1 compatibility
- **Drift check:** `use existing ai-stack-version-drift review to compare the recorded installed versions and skill digests; human-review changes without altering runtime automatically`
- **Notes:** Runtime is self-contained. Sources are attribution/update references only. The 2026-08-27 four-arm smoke remains archived non-comparable screening evidence; new comparisons are baseline versus Rhize.

## paperclip (paperclipai/paperclip) — 2026-09-27
- **Source:** https://github.com/paperclipai/paperclip
- **Upstream ref:** `0f14d26` (2026-09-27); latest stable release v2026.916.1
- **License:** MIT (repo-root LICENSE, "Copyright (c) 2025 Paperclip AI")
- **Verb:** WATCH (platform) · ABSORB (three design patterns) · REJECT (31 shippable skills) · DEFER (`simplified-english`), all human-authorized by Jim
- **Graph relation:** provenance-only
- **Target:** rhize-ops:parallel-agent-optimization (goal ancestry: task-graph v2 `objective` plus per-lane `purpose`). The other ABSORB targets are outside this marketplace: claude-routines `scheduled/codex/run_guard.py` (slot-idempotent admission, coalesce-if-active lease, skip-missed, owner record, invocation budget) and the rhize-infra Sentry triage spend breaker (per-run `--max-budget-usd` and a monthly reserve/reconcile cap). `simplified-english` was installed as-is into `~/.agents/skills` (ledger: agents-skills `skills/SOURCES.md`).
- **Took:** design patterns only, re-implemented from the published design. No Paperclip code, prompts or skill bodies were vendored into rhize-plugins.
- **Verified:**
  - skill-forge 0.21.0 gate scan of all 32 shippable SKILL.md files plus `@paperclipai/mcp-server`.
  - Skill-map overlap < 0.2 for every file (control self-match 0.982).
  - Independent Codex review (rhize-bridge jobs `6f1c2a8e`, `9a4d7c21`).
  - task-graph v2 tests: 339 passed (tests/rhize-ops + tests/config-lint).
- **Drift check:** `git -C <paperclip clone> fetch && git log --oneline 0f14d26..origin/master -- packages/adapters/claude-local/src/server/permissions.ts packages/shared/src/telemetry doc/plugins/PLUGIN_SPEC.md`. The WATCH revisit triggers are permission bypass becoming opt-in, telemetry becoming opt-in, and the plugin spec leaving "early runtime".
- **Notes:**
  - Platform not adopted: CLI adapters bypass permissions by default (Claude `--dangerously-skip-permissions`, Codex `--dangerously-bypass-approvals-and-sandbox`), telemetry is on by default, and it overlaps claude-routines, Puppetmaster and rhize-bridge.
  - Vault: "Forge decision - paperclip (2026-09-27)" and "Paperclip — Forge Assessment (2026-09-27)".
