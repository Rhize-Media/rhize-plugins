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
- **Additional source (2026-09-27):** https://github.com/paperclipai/paperclip @ `0f14d26`, MIT (repo-root LICENSE, "Copyright (c) 2025 Paperclip AI"). Pattern taken: goal ancestry → task-graph v2 (required `objective` with `done_signal`, plus per-lane `purpose`). No Paperclip code, prompts or skill bodies vendored.
- **Paperclip decision (2026-09-27, human-authorized):**
  - ABSORB here and into two targets outside this marketplace: claude-routines `scheduled/codex/run_guard.py` (slot-idempotent admission, coalesce-if-active lease, skip-missed, owner record, invocation budget) and the rhize-infra Sentry triage spend breaker.
  - WATCH the platform: CLI adapters bypass permissions and send telemetry by default, and it overlaps claude-routines, Puppetmaster and rhize-bridge.
  - REJECT 31 shippable skills.
  - DEFER `simplified-english` into `~/.agents/skills` (ledger: agents-skills `skills/SOURCES.md`).
  - Gate evidence: skill-forge 0.21.0 scanned all 32 SKILL.md files plus the MCP server; skill-map overlap < 0.2 everywhere (control self-match 0.982); independent Codex reviews on rhize-bridge jobs `6f1c2a8e` and `9a4d7c21`.
  - Revisit the WATCH if permission bypass or telemetry becomes opt-in.
  - Vault: "Forge decision - paperclip (2026-09-27)".
