# Drift Boundaries — who detects, who classifies, who propagates

Three systems touch "upstream changed." They are **stages of one pipeline, not competitors.**
This file fixes the boundaries so they never re-collide. Division locked 2026-06-15.

## The three stages

| Stage | System | Owns | Cadence |
|-------|--------|------|---------|
| **Sensor** | `ai-stack-version-drift` (scheduled task, `~/Documents/Claude/Scheduled/ai-stack-version-drift/`) | Detect version movement across the whole stack (AI CLI tools, MCP servers, plugins/skills as installed artifacts); auto-apply **SAFE** bumps (branch-only for repos); flag **RISKY**; report to vault + Slack | Mon/Thu 06:00, unattended |
| **Classifier** | `rhize-skill-forge --check-drift` (`record_provenance.py`) | Of what moved, which sources we **borrowed patterns from** (the `SOURCES.md` ledger) → which need a **re-forge** on the delta | On demand (`/rhize-meta:forge-watch`) or triggered off the sensor's report — **never its own cron** |
| **Propagator** *(Phase 3)* | update-propagation + diff review (not built) | Given a moved resource + the `consumes:` dependency graph, generate per-dependent diffs + a **human-gated** apply | Only once a dependency graph exists and is non-trivial |

## Rules

1. **One scheduler.** The sensor is the only thing on a clock. Forge drift and propagation are *invoked*, not scheduled. Remove any "good candidate for a weekly scheduled task" language from the Forge `SKILL.md` drift section — that would create a second, redundant cron.
2. **One definition of "moved."** The sensor owns version/ref comparison. Forge does **not** re-implement detection; it reads the sensor's output plus its own `SOURCES.md` upstream refs.
3. **Detection ≠ judgment ≠ propagation.** Sensor says *what* moved. Forge says *whether we care* (did we take patterns from it?) and *what to do* (re-forge the delta). The propagator says *how it ripples* to dependents.
4. **Provenance is the join key.** `SOURCES.md` upstream refs map the sensor's "moved" list to "tracked by Forge." `SOURCES.md` must exist first (it currently does not) or the classifier has nothing to classify.

## Handoffs

- **Sensor → Classifier:** the sensor tags any moved item that also appears in `SOURCES.md` as *"tracked — see Forge."* (Future change: add this lookup step to the `ai-stack-version-drift` task SKILL.md. Until then, run `/rhize-meta:forge-watch` after a drift report lands.)
- **Classifier → Propagator (Phase 3):** a re-forged resource whose `consumes:` edges are non-empty hands its changed sections to the propagator for per-dependent diff review.

## Anti-patterns

- **A second cron** that re-checks skill/plugin versions → duplicates the sensor. Don't add one.
- **Forge fetching upstream itself for routine checks** → duplicates detection. Let the sensor detect; Forge classifies.
- **Auto-propagating** a resource change into dependents without review → violates the verify-first doctrine (`dev-flow-foundations`). Propagation is always human-gated, and even then *propose, never silently apply.*

---

*Related: `provenance.md` (the `SOURCES.md` ledger this depends on), `capability-schema.md` (the `consumes:` edges the propagator needs), and the `ai-stack-version-drift` scheduled task (the sensor).*
