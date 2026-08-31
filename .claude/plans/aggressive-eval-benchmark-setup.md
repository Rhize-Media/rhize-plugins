# Aggressive Eval Coverage and Benchmark Establishment

Status: implementation in progress; deterministic coverage and centralized setup foundation built
Owner: `rhize-ops` central setup, with component-owned eval adapters
Scope: every published custom Rhize plugin skill plus `@rhize/skill-forge`
Evidence rule: observational data may guide investigation, but product-benefit claims require a matched controlled Arm A/Arm B cohort.

## Current behavior and evidence

- The repository ships 56 custom Rhize skills across nine plugin surfaces. Coverage was uneven:
  some components had broad heuristic cases, some had deep deterministic tests without benefit
  benchmarks, and some had no explicit eval surface.
- The generic live harness auto-discovered only its house-format directories, while Context
  Manager and Rhize Ops already had stricter component-specific evidence contracts that must not be
  weakened or pooled with incompatible rows.
- All seven current setup manifests catalog dependencies/hooks only; none establishes an incumbent
  benchmark, runs an immediate deterministic baseline, or enables opportunity capture.
- SkillForge's source checkout has a large deterministic test suite but lacked a labeled safety
  precision/recall corpus, a performance benchmark, and pre/post-evolve non-inferiority evidence.

## Intended semantic delta

- Add immediate local/free routing, collision, and static quality coverage for every published
  Rhize skill, with exact benchmark applicability and honest pending state where live evidence has
  not run.
- Add separate, isolated comparison machinery for the Superpowers and Rhize parallel-agent guides
  without changing the canonical baseline-versus-Rhize v2 readiness cohort.
- Define the centralized setup-wizard migration that establishes a confirmed existing
  implementation as Arm A, runs deterministic seed evidence at setup, and offers privacy-safe
  per-opportunity capture for Arm B.

## Invariants and must-not-change boundaries

- Never fabricate receipts, performance rows, or successful benchmark results.
- Keep observational, controlled, vendor-gated, and deterministic evidence classes visibly
  separate.
- Preserve the canonical Rhize v2 readiness contract and existing Context Manager receipt safety.
- No paid/network/live mutation, plugin installation, external write, or SkillForge adoption is
  authorized by this work.
- Shared schemas, setup manifests/wizards, versions, generated files, and release integration stay
  coordinator-owned.

## Acceptance tests

- Every discovered plugin skill maps to local runnable coverage and one benchmark applicability
  record; trigger-capable skills have one positive and two collision/near-miss negatives.
- Component runners and repository tests pass from the joined branch.
- Guide-comparison reservations bind exact guide snapshots, counterbalanced order, actual variants,
  agent overlap/collisions, and never feed canonical readiness.
- SkillForge version drift is explicit, safety precision/recall and local latency are measurable,
  and evolve candidates cannot pass when safety/correctness regress.
- All checked-in live benchmark results remain empty/pending unless a real run occurred.

## Implementation order

1. Add isolated component eval suites and benchmark contracts.
2. Join and run repository-wide deterministic verification.
3. Add shared documentation, release metadata, and the centralized setup-wizard implementation
   plan.
4. Reconcile the final diff against this map before commit, push, or merge.

## Joined implementation impact map

The implementation attached to this plan also touches these coordinator and integration files;
they are listed explicitly so the final diff can be reconciled without treating directory-level
ownership as sufficient:

- `CHANGELOG.md`, `README.md`, and `evals/README.md` document the complete coverage inventory,
  evidence boundaries, runner commands, and release metadata.
- `evals/parallel-agent-skills/README.md`,
  `evals/parallel-agent-skills/scripts/evaluate_ops_skills.py`,
  `evals/parallel-agent-skills/scripts/prepare_guide_comparison.py`, and
  `evals/parallel-agent-skills/scripts/validate_guide_receipts.py` own Ops coverage plus the
  isolated baseline/Superpowers/Rhize comparison contract.
- `evals/rhize-tasks/README.md` and `evals/rhize-tasks/run_evals.py` own the Tasks local gate and
  benefit-protocol entry point.
- `evals/skill-forge/README.md`, `evals/skill-forge/evolve_contract.py`, and
  `evals/skill-forge/integration_eval.py` own SkillForge version, isolated safety/latency, and
  full-cohort evolve validation.
- `tests/rhize-ops/test_eval_coverage.py`, `tests/rhize-tasks/test_eval_contract.py`, and
  `tests/skill-forge/test_integration_eval.py` enforce those contracts and failure boundaries.

## Objective

Make eval coverage complete, immediate, and continuously useful:

1. Every published skill is explicitly `evaluated`, `benchmarkable`, or `not_applicable` with a reviewed reason.
2. Installation establishes a deterministic baseline immediately instead of waiting for organic usage.
3. The setup wizard helps the user identify and confirm the exact existing implementation as Arm A before enabling the new Rhize path as Arm B.
4. Every eligible natural execution records a privacy-safe pending and terminal receipt, so opportunities are not silently lost.
5. Deterministic regression suites run on relevant changes; daily work checks capture health; weekly work aggregates already-captured evidence rather than waiting a week to start collecting it.
6. Performance, context-efficiency, accuracy, token-savings, or workflow-benefit claims are made only from comparable evidence.

## Current-state findings to preserve

| Component | Current useful evidence | Gap this program must close |
| --- | --- | --- |
| `seo-aeo-geo` | Generic trigger and quality cases | Immediate local coverage must not depend on paid DataForSEO calls; baseline identity and natural receipts are absent. |
| `obsidian-second-brain` | Generic self-contained trigger and quality cases | Command/setup behavior and real-vault benefit comparisons are incomplete. |
| `project-launcher` | Existing deterministic plugin tests | Both skills need explicit eval and benefit-benchmark coverage. |
| `rhize-cowork` | Plugin structure only | No eval or benchmark contract. |
| `rhize-devflow` | Broad heuristic triggers and text contracts | Outcomes, rework, latency, and context-cost deltas are not established. |
| `rhize-context-manager` | Strongest real Arm A/Arm B capture and receipt health | Coverage is uneven across the full skill inventory; strict cohort comparability must remain visible. |
| `rhize-ops` | Privacy-safe v2 baseline/Rhize routing harness | Current complete repeated cohort is missing; delegation and dashboard outcomes are unmeasured. |
| `rhize-tasks` | Deep deterministic test suite | No workflow-benefit or existing-implementation benchmark. |
| `procedural-memory` | Five authored portable eval cases | `functionize` is uncovered and vendor execution can be organization-gated. |
| `@rhize/skill-forge` | Large deterministic package suite | No safety precision/recall corpus, performance benchmark, or pre/post-evolve non-inferiority gate. |

## Non-negotiable evidence contract

### Coverage inventory

The release validator discovers skills from plugin manifests and requires one coverage entry per skill:

- `evaluated`: one or more runnable deterministic suites exist;
- `benchmarkable`: an Arm A/Arm B benchmark and capture adapter exist;
- `not_applicable`: a non-empty reason and review owner exist;
- `blocked`: setup attempted but a dependency, permission, host counter, or user choice prevents execution. `blocked` is visible setup state, never a release exemption.

A trigger-capable skill must have at least:

- one realistic positive case;
- two meaningful near-miss or collision negatives;
- precision, recall, and F1 aggregation.

An operational skill must also have at least one deterministic behavior/quality contract where its output can be checked locally. Missing live credentials cannot excuse the deterministic layer.

### Benchmark arms

- **Arm A:** the exact user-confirmed existing implementation, version, configuration, and entry point. “Without plugin” is not sufficient when the real incumbent is a script, manual checklist, another skill, or another tool.
- **Arm B:** the exact Rhize plugin or SkillForge path under evaluation, including version/commit and configuration.
- Every reservation and result records `variant`; aggregation rejects rows where the executed variant is absent or ambiguous.
- Controlled pairs use the same normalized fixture/task, environment class, model, input fingerprint, validation contract, and counterbalanced order.
- Required controlled readiness is three matched repetitions per deterministic task class unless a component predeclares a stronger threshold.
- Natural Arm A and Arm B observations remain observational unless strict matching and ordering are proven. Same-day timestamps alone are not ordering evidence.

### Common metrics

Every adapter declares which common metrics it can measure and why any metric is unavailable:

- correctness/accuracy and verification completion;
- routing true/false positives, precision, recall, and F1 when routing applies;
- input, output, cache-read, and cache-write tokens when the host exposes them authoritatively;
- elapsed latency and, where meaningful, step timing;
- tool calls and agent count;
- follow-up reads or retrieval turns;
- corrections, retries, rework, and human overrides;
- failures, timeouts, refusals, and degraded-mode use;
- component-specific outcome metrics declared before execution.

Never estimate unavailable token/tool counters. Never treat lower token use as a win when correctness or safety regresses.

### Privacy and integrity

- Raw local state lives under `~/.rhize/evals/` with directories mode `0700` and files mode `0600`.
- Receipts contain no prompts, response bodies, code, commands, paths, URLs, names, user/project/session identifiers, or credentials.
- When pairing requires input identity, use a local-secret HMAC fingerprint; never store a reversible or unsalted prompt hash.
- Each run reserves before execution and terminates as `completed`, `failed`, or `incomplete`. Stale pending reservations are a daily health failure.
- Store exact component/plugin version, baseline version or SHA, schema version, model identifier when exposed, fixture ID, and verification-contract digest.
- Append-only raw receipts are never rewritten to improve a cohort. Corrections are new records linked by random local IDs.
- Redacted summaries may be projected to the vault; raw receipts remain local unless the user explicitly authorizes another destination.

## Central setup-manifest contract

The implementation uses one centralized, versioned catalog instead of duplicating runner and
benchmark paths in every plugin manifest. `rhize-ops` owns the catalog, JSON Schemas, validator,
local state, and receipt lifecycle; component repositories continue to own the eval runners and
protocols referenced by the catalog.

Schema 2 preserves `items` and `dependencies` and adds a strict catalog binding:

```jsonc
{
  "schema": 2,
  "plugin": "rhize-context-manager",
  "items": [],
  "dependencies": [],
  "evaluations": {
    "catalog": "rhize-evaluations-v1",
    "component": "rhize-context-manager"
  }
}
```

All nine current plugin surfaces now have schema-2 manifests, including the newly cataloged
Procedural Memory and Rhize Cowork manifests. Schema 1 remains readable by the dependency/hook
wizard during migration, but reports `evaluation catalog missing` and cannot pass the central
evaluation validator. The central catalog also covers the SkillForge package as an explicit-input
component without pretending that it is a plugin or automatically selecting an executable from
`PATH`.

Security constraints:

- formalize the currently used `runtime` and `platform` dependency kinds alongside `plugin`, `cli`, `mcp`, and `data`, and give the wizard deterministic probes for each rather than accepting undocumented values;
- `path` is a repository-relative file path, not an arbitrary shell command;
- the validator rejects traversal, absolute paths, symlinks escaping the repository root, unknown runner kinds, and unbounded timeouts;
- `args` is an array passed without shell interpolation;
- network and cost are explicit enums, and anything non-free or networked requires literal effect-specific authorization at run time;
- setup never installs a dependency, schedules a job, wires a hook, or runs a live benchmark merely because a manifest declares it.

## Central `/rhize-setup` experience

Retain the existing dependency and hook flow, then add a first-class evaluation phase.

### Phase A: inventory and validate

1. Discover enabled plugins and every published skill.
2. Validate schema, runner path containment, coverage completeness, and dependencies.
3. Display one row per skill: deterministic suite, benchmark status, incumbent baseline, capture status, and blocker.
4. Refuse to call the inventory complete when any skill is omitted; do not block unrelated setup when a runner is merely unavailable.

### Phase B: establish the existing implementation

For every benchmarkable component, present discovered Arm A candidates and require confirmation:

- current manual workflow or checklist;
- current script/command/skill/tool;
- no existing implementation.

Show the exact label, version/SHA when available, and validation method. If no incumbent exists, record `greenfield`; do not manufacture an Arm A. A future pre/post release comparison can use the first production version as a frozen baseline.

### Phase C: run the immediate baseline

Recommended by default, but still user-controlled:

1. Run manifest and deterministic-case validation.
2. Run one free/offline smoke repetition for each enabled component.
3. If a replayable incumbent exists, offer a three-pair controlled seed now.
4. Before any networked, paid, credentialed, or externally mutating work, show estimated effects and ask for literal authorization.
5. Persist passing and failing terminal receipts. A failed trial remains evidence and is never silently retried or reclassified.

The wizard finishes with concrete statuses: `baseline established`, `deterministic only`, `blocked`, `declined`, or `greenfield`.

### Phase D: enable opportunity capture

Offer capture as a separate explicit choice from running the seed benchmark:

- **Aggressive local capture — recommended:** reserve a receipt on every eligible execution and finalize it immediately; no raw content is stored.
- **Deterministic gates only:** run change gates but do not observe natural executions.
- **Disabled:** record the user's choice so future setup runs can offer it again without pretending capture is healthy.

Component adapters, not the central wizard, define eligible start/finish events. The central engine validates and stores receipts uniformly. If a host has no reliable lifecycle hook, the adapter reports `host_lifecycle_unavailable`; it must not infer execution from file dates.

### Phase E: report and repair

Print complete tables for dependencies, hooks, eval coverage, established baselines, capture modes, and failed smoke tests. Include exact repair commands only for local/free actions; seek authorization separately for other effects.

Setup is idempotent: reruns inspect effective state, preserve valid baseline IDs and local secrets, never duplicate hooks/schedules, and offer refresh when component versions or incumbent SHAs drift.

## Aggressive cadence

| Trigger | Work | Blocking behavior |
| --- | --- | --- |
| First setup / plugin enable | Validate coverage; run free deterministic smoke; offer three-pair seed | Cannot claim setup complete for omitted skills; live/paid work remains opt-in. |
| Every eligible natural execution | Pending receipt before; terminal receipt after | Capture failure is visible but must not break the user's primary workflow. |
| Pull request touching a skill/eval/adapter | Deterministic routing + quality + schema suites | Block regressions and uncovered new skills. |
| Plugin release or model/host change | Full deterministic suite; controlled refresh for affected claims | Existing claims become stale until the affected cohort is refreshed. |
| Daily | Audit pending/stale receipts, adapter health, missing opportunities, version drift | Alert/record health failure; do not fabricate benchmark rows. |
| Weekly | Aggregate evidence already captured; show coverage, freshness, and claim readiness | Aggregation only; collection started at setup and continued per opportunity. |

Use a local cost budget for optional controlled refreshes. Exhausting the budget pauses paid/networked runs and records `budget_paused`; it never reduces deterministic coverage.

## Existing plugin setup-wizard integration

The component wizards must delegate to one central implementation rather than each creating its own receipt format:

| Wizard | Required integration |
| --- | --- |
| `obsidian-second-brain:vault-setup` | After vault/interface verification, call the central evaluation subflow for `obsidian-second-brain`; establish the current vault-search/manual retrieval Arm A before enabling natural retrieval receipts. |
| `rhize-context-manager:context-setup` | Register the existing context workflow and frozen baseline SHA; preserve the current strict comparability and natural-capture contracts. |
| `rhize-devflow:devflow-setup` | Establish the current review/test/debug workflow as Arm A; measure rework and correctness before token or latency savings. |
| `rhize-ops:delegate-setup` | Offer a delegation outcome baseline only after recipient/integration setup succeeds; never send Jira/Slack traffic solely to seed a benchmark. |
| `rhize-tasks:setup` | Establish the incumbent task capture/today workflow and validate the service locally before capture is enabled. |
| `rhize-ops:rhize-setup` | Own fleet inventory, common schema, local storage, baseline interview, deterministic seed, capture settings, and final report. |
| Plugins without their own wizard | Participate through schema 2 whenever central setup runs; README installation instructions must make central setup the final step. |

Expose a component-scoped entry point conceptually equivalent to:

```text
/rhize-ops:rhize-setup --plugin <name> --evaluations
```

Host adapters may present questions differently, but Claude and Codex must write the same host-neutral `~/.rhize/evals/config.json` and receipt schemas.

## SkillForge-specific plan

Implement in the SkillForge repository after the central registration schema is stable:

1. Add a labeled safety corpus with allowed and disallowed transformations; report precision, recall, F1, false-positive categories, and false-negative categories.
2. Add a deterministic performance benchmark for analysis/evolution stages, separating input/output/cache tokens, elapsed time, tool calls, and output correctness when exposed.
3. Make `skillforge init` offer central Rhize eval registration and incumbent-baseline establishment. It must also work standalone when Rhize Ops is absent.
4. Make `skillforge evolve` run the original skill as Arm A and candidate skill as Arm B on the same frozen eval corpus before promotion.
5. Gate promotion on non-inferiority for safety and correctness; efficiency wins cannot compensate for safety/correctness regressions.
6. Persist the original skill hash, candidate hash, corpus digest, tool version, executed arm, and terminal status in privacy-safe receipts.
7. Add compatibility tests for source package and installed CLI version drift; setup reports the mismatch and does not silently benchmark a different binary.

## Implementation sequence and ownership

### Phase 1 — contract and validators (sequential dependency)

Coordinator-owned shared files:

- add the setup schema and eval coverage/protocol/receipt schemas under `rhize-ops/schemas/`;
- add strict stdlib validators and adversarial path/privacy fixtures;
- define `~/.rhize/evals/config.json`, secret creation, reservations, finalization, and audit lifecycle;
- document migration and failure states.

Verify: schema tests, path-escape tests, exact-key/privacy tests, file modes, idempotent config migration, and real CLI interface runs.

Implemented foundation impact map (exact coordinator-owned paths):

- contracts and runtime: `rhize-ops/setup/evaluation-catalog.json`,
  `rhize-ops/schemas/evaluation-catalog-v1.schema.json`,
  `rhize-ops/schemas/evaluation-config-v1.schema.json`,
  `rhize-ops/schemas/evaluation-receipt-v1.schema.json`,
  `rhize-ops/schemas/setup-manifest-v2.schema.json`, and
  `rhize-ops/scripts/evaluation_setup.py`;
- central wizard/docs/security: `rhize-ops/commands/rhize-setup.md`, `rhize-ops/README.md`,
  `rhize-ops/GUIDE.md`, `CHANGELOG.md`, `SECURITY.md`, `scripts/build_skill_map.py`, and the required
  regenerated artifact `generated/skill-map.static.json`;
- schema-2 manifests: `obsidian-second-brain/setup/manifest.json`,
  `project-launcher/setup/manifest.json`, `procedural-memory/setup/manifest.json`,
  `rhize-context-manager/setup/manifest.json`, `rhize-cowork/setup/manifest.json`,
  `rhize-devflow/setup/manifest.json`, `rhize-ops/setup/manifest.json`,
  `rhize-tasks/setup/manifest.json`, and `seo-aeo-geo/setup/manifest.json`;
- component wizard handoffs: `obsidian-second-brain/commands/vault-setup.md`,
  `rhize-context-manager/commands/context-setup.md`, `rhize-devflow/commands/devflow-setup.md`,
  `rhize-ops/commands/delegate-setup.md`, and
  `rhize-tasks/skills/rhize-tasks-setup/SKILL.md`;
- benchmark/tests/plan: `evals/procedural-memory/benchmark_spec.json`,
  `tests/rhize-ops/test_evaluation_setup.py`, and this plan.
- release metadata: `.claude-plugin/marketplace.json` plus both
  `<plugin>/.claude-plugin/plugin.json` and `<plugin>/.codex-plugin/plugin.json` for
  `obsidian-second-brain`, `procedural-memory`, `project-launcher`, `rhize-context-manager`,
  `rhize-cowork`, `rhize-devflow`, `rhize-ops`, `rhize-tasks`, and `seo-aeo-geo`, plus the
  Rhize Tasks runtime mirrors `rhize-tasks/package.json` and
  `rhize-tasks/native/reminders-helper/Resources/Info.plist`.

### Phase 2 — component adapters (parallel after Phase 1)

Assign one owner per non-overlapping component territory. Each owner migrates its manifest, coverage file, deterministic runner, benchmark protocol, capture adapter, and narrow tests. Shared schemas and central runner stay coordinator-owned.

Verify: every discovered skill maps exactly once; each runner executes offline; benchmark arms and metrics validate; unavailable live dependencies remain explicit.

### Phase 3 — wizard and component handoff (sequential integration)

- extend `/rhize-setup` with evaluation phases A-E;
- add component-scoped invocation;
- update each component wizard to call the central subflow only after its own prerequisites pass;
- add dry-run, non-interactive validation, and structured report output so setup behavior is testable without a model guessing from Markdown.

Verify: clean first install, rerun/idempotency, disabled plugin, missing dependency, declined capture, greenfield baseline, existing incumbent, stale version, offline host, paid-run refusal, and partial smoke failure.

### Phase 4 — continuous gates and health (parallel adapters, sequential policy merge)

- run deterministic coverage validation on relevant PRs;
- add daily local capture-health audit through the user's chosen scheduler, without silently creating one;
- aggregate weekly local summaries;
- invalidate stale claims on plugin/model/baseline drift;
- render coverage and readiness in the skill dashboard.

`.github/workflows/*` is protected: review and authorize workflow changes separately at the merge boundary.

### Phase 5 — SkillForge integration and pilot

- implement the SkillForge-specific plan;
- pilot on Context Manager plus one no-network plugin and one operational plugin;
- run the interfaces end to end, inspect actual receipts, and repair schema/UX gaps;
- migrate remaining plugins only after the pilot passes.

## Verification and release gates

Required before merge:

- all existing repository suites remain green;
- every published skill is present in validated coverage inventory;
- all deterministic eval runners pass from a clean checkout without credentials unless explicitly marked otherwise;
- setup manifests and runner paths survive malicious/traversal fixtures;
- wizard tests prove no paid, networked, scheduled, or external action occurs without exact authorization;
- baseline identity and executed variant appear in every benchmark receipt;
- stale pending receipt audit works;
- same-day/unmatched natural rows remain non-comparable;
- Superpowers and Rhize parallel-routing comparison uses a separate isolated protocol and does not contaminate the canonical baseline-vs-Rhize readiness cohort;
- cold diff review confirms component wizards delegate to the central engine rather than forking schemas;
- affected docs and durable project state are updated before commit.

Required before making a benefit claim:

- complete matched cohort at the predeclared repetition threshold;
- 100% required correctness and verification completion;
- routing and safety thresholds pass;
- zero collisions for isolated routing benchmarks;
- no increase in rework or failures;
- efficiency delta is reported with metric availability and cohort freshness;
- observational evidence is labeled observational.

## Executor routing

- Contract/schema, central wizard, receipt engine, migrations, and SkillForge evolve gate: Terra-class implementation; Sol-class plan/security/final review.
- Mechanical per-plugin manifest and case additions after contracts freeze: Luna-class implementation with explicit acceptance tests.
- Protected workflow changes and final release gate: Sol-class review.

## Completion definition

This program is complete only when a clean installation can discover all custom Rhize skills, establish or explicitly classify every baseline, run an immediate deterministic seed, enable privacy-safe per-opportunity capture when chosen, show health the next day without waiting for weekly data, and reject unsupported benefit claims. Documentation-only declarations do not satisfy completion; the setup interface and receipt lifecycle must be run and verified.
