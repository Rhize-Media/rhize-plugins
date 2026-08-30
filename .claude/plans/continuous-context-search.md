# Impact Map: Continuous local context search

## Current behavior and evidence

- **Evidence:** `rhize-context-manager/scripts/context_experiments/config.py` reserves an accepted canary by disabling the capability and clearing `armedRuns`; even a successful evidence-backed run stays frozen.
- **Evidence:** `runner.py` and the selector/finalizer wrappers already enforce allowlists, eligible task classes, clean Git snapshots, provider health, pack verification, bounded duration, immutable source-free evidence, and repository+capability single-flight.
- **Evidence:** the selector/finalizer are opt-in entries in `setup/manifest.json`, not auto-wired plugin hooks; duplicate manually installed Claude hooks are therefore a migration concern when they move into `hooks/hooks.json`.
- **Evidence:** native query discovery tries CodeGraph whenever `.codegraph/` merely exists, then uses an in-process text scorer. This repository has no `.codegraph/`; the structural fallback for this work is `rg` plus targeted reads, and no index will be created.
- **Evidence:** pack manifests hash the task/query/source selection but have no plan/impact-map provenance, and the fixed native eval corpus does not compare baseline query discovery with plan-assisted discovery.

## Intended semantic delta

- Add a disabled-by-default `continuous` capability mode alongside the backward-compatible `canary` mode. In continuous mode, every explicitly eligible implementation, diagnosis, review, or impact-analysis prompt in an allowlisted clean repository may claim the healthy local provider; a completed evidence-backed attempt increments history, releases single-flight, and remains enabled. Failed, incomplete, stale, or malformed evidence writes a terminal receipt and freezes further claims.
- Auto-wire the fail-silent selector and finalizer through plugin hooks shared by Claude and Codex. Duplicate manual Claude hook entries remain safe/idempotent but must be removed by the coordinator during migration.
- Add source-free receipt completeness fields and stale-pending reconciliation so accepted claims end in completed, failed, or incomplete state without inferring correctness, token use, or unobserved execution.
- Let native discovery accept an optional repository-local impact-map/plan hint. Record only hashes/counts in the manifest, expand the query locally, use structural seeds only after a healthy existing CodeGraph preflight, and otherwise use deterministic `rg` discovery. Unsupported syntax and dynamic edges remain fail-closed.
- Extend deterministic native evals with baseline-versus-impact-assisted recall, critical-miss, fallback, and latency measurements.

## Invariants and must-not-change boundaries

- Configuration remains strict and disabled by default; existing schema-v1 canary documents without `mode` continue to parse identically.
- Allowlists, provider readiness/current-snapshot checks, smoke approval, clean repository state, max-duration refusal, task classification, and production/destructive prompt exclusion remain mandatory.
- mgrep stays disabled; no account, store, upload, query, or network action is added.
- Receipts, pending rows, and pack manifests contain no prompt/source/output text, absolute paths, credentials, or URLs. Impact-map provenance is hash-only.
- No `.codegraph` index is initialized or synchronized. An existing index is trusted only after a healthy read-only status preflight.
- The canonical impact-map remains semantic intent; native discovery is advisory context selection and does not turn planned edges into structural facts.
- Existing one-shot canary arming and legacy receipt parsing remain supported.

## Current structural touchpoints

| Repository | Entry point or symbol | Why affected | Evidence |
|---|---|---|---|
| rhize-plugins | `CapabilityConfig`, config reservation/completion functions | Own mode parsing and enabled/frozen transitions | `rg` definitions and call sites in context experiment models/config/runner tests |
| rhize-plugins | `claim_hook_selection`, `finalize_hook_selection`, capture health | Own accepted-attempt lifecycle and terminal evidence accounting | `rg` runner, receipt store, capture-health, aggregation tests |
| rhize-plugins | `NativeContextPackProvider.compile`, `_discover_targets` | Own local target discovery and manifest provenance | `rg` native provider tests and schema |
| rhize-plugins | `hooks/hooks.json`, selector/finalizer wrappers | Shared plugin hook registration for Claude and Codex | hook manifests and wrapper tests |
| rhize-plugins | `rhize-devflow/commands/impact-map.md` and foundation references | Canonical semantic-map contract that must describe the discovery bridge | canonical command and reference reads |
| rhize-plugins | `evals/context-tools` | Fixed lifecycle, schema, provider, audit, and recall evidence | focused pytest corpus |

## Planned additions and deletions

- Extend the schema-v1 capability object with optional `mode: canary|continuous`.
- Extend receipt-v2 with source-free completeness and terminal-reason fields while keeping legacy receipt-v1/v2 reads valid.
- Add a stale pending audit/finalization path invoked by selector/audit commands.
- Add impact-assisted eval fixtures/cases; no generated reports are committed.
- Do not delete manual setup-manifest entries yet; document the coordinator removal from live settings and keep wrappers duplicate-safe during migration.

## External and operational effects

- None in this lane. Live Claude/Codex configuration, installed plugin caches, provider state, Jira, and network services are out of scope.
- Coordinator must regenerate root marketplace/catalog/skill-map/version artifacts after integration if release policy requires them.
- A future paid mgrep pilot may be economically reasonable only if the local/impact-map hybrid fails and the operator explicitly accepts remote privacy, retention, purge, and paid-tier terms.

## Reuse opportunities

- Reuse the existing strict config parser, append-only stores, immutable evidence model, repository+capability lease, native pack verification, and provider-neutral manifest schema.
- Reuse the impact-map command's evidence/inference/planned distinction and CodeGraph health/fallback contract.

## Acceptance tests

- Continuous completed evidence increments history, releases the lease, and permits the next eligible claim while the capability remains enabled.
- Continuous failed/incomplete/stale/malformed evidence writes exactly one terminal receipt, freezes the capability, and prevents a new claim.
- Stale accepted pending attempts are audited into incomplete receipts rather than reclaimed or silently abandoned.
- Canary behavior remains frozen after a terminal attempt and old config documents round-trip.
- Auto-wired selector/finalizer hook entries parse, resolve to existing wrappers, and remain duplicate-safe.
- Receipt completeness fields are source-free and capture evidence/arm/pack/final-verification presence without correctness or token inference.
- Impact-assisted manifests contain only hint hashes/counts, never plan text/path; healthy existing CodeGraph is tried first, absent/unhealthy graph uses deterministic `rg`, and no index is created.
- Fixed eval cases show impact assistance improves or preserves relevant-file recall, has zero assisted critical misses for supported cases, records both latencies, and rejects/falls back for dynamic or unsupported edges.
- Focused and full `evals/context-tools` tests pass; changed JSON parses; plugin config lint passes.

## Explicitly unaffected paths

- mgrep provider execution, remote provider authorization, Jira, user-level settings, installed caches, root marketplace/catalog, and unrelated plugins.
- Context compiler upstream adapter semantics and non-context devflow release/review workflows.

## Unknowns and confidence

- **Inference:** current Codex plugin loading consumes the same `hooks/hooks.json` contract described by rhize-devflow; repository tests can prove hook shape and wrapper behavior, but only a coordinator-owned fresh installed-session smoke can prove host registration.
- **Known blind spot:** hook shutdown cannot guarantee execution after host termination. Stale-pending reconciliation provides deterministic eventual terminalization on the next selector/audit invocation, not an operating-system durability guarantee.
- **Known blind spot:** CodeGraph output cannot prove dynamic/generated/external edges; those paths remain rejected or explicitly fall back.

## Implementation order

1. Add failing lifecycle/config/receipt/hook tests.
2. Implement continuous reservation, terminalization, and audit transitions.
3. Add failing impact-assisted discovery/eval tests and fixtures.
4. Implement local hint parsing, hash-only provenance, healthy-CodeGraph preflight, and deterministic `rg` fallback.
5. Update canonical impact-map/docs/changelogs and the mgrep decision gate.
6. Run focused tests, then the full context-tools suite; cold-review the exact diff and reconcile this map using `rg` because `.codegraph/` is absent.

## Parallelization

- Lifecycle/schema/hook tests and discovery/eval tests are conceptually independent, but this lane is a single-writer worktree; edits remain sequential to avoid overlapping runner/provider fixtures.
- Focused test groups can run concurrently after implementation; full-suite and cold-review gates are sequential.

## Reconciliation verdict

- `IN_SYNC_WITH_EXCEPTIONS`: implementation, focused/full tests, documentation, and
  the final `rg`-based diff reconciliation agree. A fresh installed Claude/Codex
  session is still required to prove host hook registration; this repository has
  no `.codegraph`, and dynamic/generated/external edges remain fail-closed.
