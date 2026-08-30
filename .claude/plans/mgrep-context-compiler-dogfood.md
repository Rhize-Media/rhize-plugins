# mgrep and Compiled Context Dogfood Plan

| Field | Value |
|---|---|
| Status | Phase 8 native-pack v2 and dual-host hardening implemented; live measurement remains gated |
| Created | 2026-08-27 |
| Primary owner | Rhize Tools |
| Implementation home | `rhize-context-manager` |
| Evaluation home | `evals/context-tools` |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for cross-cutting integration; Luna only for bounded fixtures, tests, and documentation |
| Cross-host surface | Canonical `rhize-context-manager:context-pack` skill/CLI; thin Claude command; Codex skill discovery |
| Jira tracking | RT-128 remains authoritative for host-stratified live measurement and promotion evidence |

## 1. Objective

Dogfood two related ideas in normal Rhize engineering work, measure whether either one improves outcomes, and bundle only the pieces that earn their place:

1. **mgrep** as an optional semantic candidate-finding provider.
2. **Compiled context** as a provider-neutral way to construct a compact, dependency-aware context pack for an agent task.

The program must answer four questions with evidence:

1. Does mgrep find the right files faster or with fewer tokens than the current routing stack?
2. Does a compiled context pack reduce context consumption without hiding dependencies that affect correctness?
3. Do the two provide independent value, complementary value, or no material value?
4. If value is demonstrated, what is the smallest safe capability to ship in the Rhize plugin suite?

This is a staged evaluation, not a commitment to make either dependency part of the default stack.

### 1.1 Implementation checkpoint — 2026-08-27

- Jira tracking lives in Rhize Tools at `RT-128`; the misplaced `RHIZE-181` is closed with a
  redirect.
- mgrep 0.1.13 is installed, but the authenticated vendor dry-run and repository upload have
  not happened. The latest independent reviewed inventory contains 652 eligible files
  (5,494,819 bytes), excludes 39, and reports that mgrep's unconditional hidden-path policy
  omits `.claude-plugin`/`.codex-plugin` metadata. Upload remains blocked on device login plus
  approval for the exact `rhize-plugins` manifest and `rhize-dogfood-rhize-plugins` store.
- The pinned upstream Context Compiler now runs a nine-case Phase 3 corpus through the real
  provider. All nine cases passed the versioned `context-compiler-phase-3-v1` behavior gate:
  static aliases were accepted; duplicate names widened with an explicit collision warning;
  dynamic dispatch, event decorators, and callback registration failed closed; the upstream
  self-case was rejected for dynamic dispatch; and the Rhize runner case was rejected for
  breadth, token budget, collisions, and dynamic edges. Independent processes produced the same
  source-bound pack IDs and prompt content. The gate permits Phase 4 design only, not injection.
- `/context-pack` is now an explicit, non-injecting preview. Its first real invocation on the
  Rhize runner produced 92,783 estimated Arm B tokens versus 394,372 for Arm A (76.5% smaller)
  but rejected the pack because it selected 110/162 Python files and exposed 66 name collisions
  plus dynamic, decorator, and callback risks. This confirms that reduction alone is not an
  adoption signal.
- No mock, synthetic, or fake provider output is retained as dogfood evidence. Test-local
  doubles may still cover failure/concurrency branches, but benchmark rows must name and verify
  the real provider revision.

### 1.2 Provider economics and data-handling checkpoint — 2026-08-27

**Decision:** do not create a Mixedbread account, authenticate mgrep, create a remote store, or
upload repository content until Phase 1.5 passes. The local mgrep CLI installation is inert and
may remain only for source/behavior inspection.

Current vendor facts, captured from the published pages on 2026-08-27:

- Mixedbread Starter is a no-card plan with **$5 in one-time credits**, 3 users, and 10 stores.
  Scale is **$20/month** with $20/month in included credits. Usage is priced separately for
  indexing, searching, and storage.
- Text is estimated by Mixedbread at roughly 1.4 content tokens per word. The reviewed
  `rhize-plugins` upload manifest contains 592,253 whitespace-delimited words, or approximately
  829,154 billable content tokens under that approximation. That implies about **$1.24** for a
  Fast initial index, **$2.49** for High Quality, and **$0.41/month** for storage before searches.
  These are planning estimates; the vendor receipt is authoritative if a managed pilot runs.
- The pricing page currently renders both launch and regular semantic-search/rerank rates. Until
  billing output removes the ambiguity, budget the upper advertised combination rather than the
  promotional rate and record actual per-query charges in receipts.
- The published Privacy Policy says free-tier native queries and model logs are retained
  indefinitely, used for service improvement/analytics/research, and not used for model training.
  The published Terms separately say free-tier usage data may be retained indefinitely and used
  for model training. This contradiction makes the free tier unacceptable for proprietary source
  until Mixedbread resolves it in writing. Paid-tier language is materially safer, but still
  requires the normal repository upload approval and verified purge procedure.
- mgrep is Apache-2.0, but its supported runtime pushes every indexed file to a cloud-backed
  Mixedbread Store. It does not expose a supported pluggable local store/embedding backend, so
  “self-hosting mgrep” would mean maintaining a fork or replacement rather than changing config.

The first no-signup alternative is **grepai with local Ollama embeddings and its file-based GOB
store**. grepai is MIT-licensed, exposes CLI/JSON/MCP surfaces, respects Git ignore rules, and can
run without source leaving the machine. Its costs are local model download, disk/RAM/CPU, indexing
time, watcher reliability, version maintenance, and single-machine limitations. Team sharing would
add PostgreSQL/pgvector or Qdrant operations and is explicitly outside the first spike.

### 1.3 Local retrieval checkpoint — 2026-08-27

Phase 1.5 produced real negative evidence, so the local semantic path is **not approved for an
automatic live task** yet:

- Installed and checksum-verified grepai `0.35.0` and Ollama `0.33.1`; pulled
  `nomic-embed-text:v1.5` and verified its full manifest digest
  `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`.
- grepai has no one-shot index command. Its foreground watcher also discovers registered Git
  worktrees every three seconds, auto-initializes their `.grepai` stores, and modifies their
  `.gitignore` files. A real main-worktree smoke exposed this behavior; it was stopped, the two
  affected worktrees were restored, and their indexes were quarantined. Direct main-worktree
  indexing is now prohibited. The benchmark used a detached, single-worktree disposable clone.
- The isolated scan indexed 530 real repository files into 2,945 chunks in 91.543 seconds. The GOB
  index was 18,872,969 bytes and the symbol index was 1,655,309 bytes. The foreground watcher was
  terminated after readiness; no grepai daemon remains.
- On the reviewed six-case retrieval smoke corpus, Arm A ripgrep achieved mean recall@5 `1.0`,
  mean precision@5 `0.466667`, and zero critical misses. Arm B-local grepai achieved mean recall@5
  `0.166667`, mean precision@5 `0.1`, and five critical misses. Median end-to-end query time was
  41.444 ms for the multi-call ripgrep baseline and 534.875 ms for the guarded grepai adapter,
  including its provider and snapshot checks.
- The versioned evaluator gate records `pause` for critical misses and recall below baseline. Keep
  the adapter, strict snapshot/provider checks, and
  evaluator as repeatable evidence infrastructure, but leave `localRetrieval` disabled and unarmed.
  Do not count this as an automatic live experiment. Reconsider only with a materially different
  model/configuration or an upstream release that provides safe single-checkout indexing.

### 1.4 Native compiled-context and final decision checkpoint — 2026-08-27

- Added `rhize-native-context-pack-v1`, a local-only Python/JavaScript/TypeScript provider with
  explicit or query-based target discovery, CodeGraph-first behavior when `.codegraph/` exists,
  FULL/INTERFACE roles, source-free v2 manifests, visible selection reasons, and `verify-pack`
  snapshot/source-hash invalidation.
- The real native corpus passed 5/5 cases with zero critical misses. Four accepted cases had a
  39.02% median estimated reduction; a dynamic JavaScript import failed closed. Together with the
  nine upstream cases, compiled context has 14 paired offline cases.
- Real repository dogfood accepted the provider-target pack at 8,759 versus 680,703 estimated
  tokens and correctly rejected the runner-target pack despite more than 94% reduction because of
  a dynamic edge. The one-shot hook then built an accepted query-discovered pack with Arm B live
  at 10,907 versus 682,821 estimated tokens; a subsequent edit made verification fail on snapshot
  drift and forced a fresh accepted pack.
- Final disposition: native compiled context is an advanced opt-in capability; the upstream
  compiler remains an eval/reference provider; current managed mgrep and local grepai paths are
  rejected; the combined 2x2 is skipped because retrieval did not pass its independent gate.
  The decision record is `evals/context-tools/NATIVE_CONTEXT_DECISION.md`.

### 1.5 Additional Context Compiler article review — 2026-08-30

The published article and its Obsidian Inbox clipping were independently compared with the upstream
repository, pinned adapter, Rhize native pack, fourteen-case corpus, and real-repository receipts.
This is not a new plugin domain: it is the source already evaluated by this plan and tracked in
RT-128. Creating another context-compiler plan or provider would duplicate `rhize-context-manager`.

Adopted insights are partially present and remain the target contract: explicit reachability before
prompt assembly, FULL/INTERFACE/EXCLUDED classification, deterministic interface rendering, visible
dynamic/collision warnings, source-bound invalidation, and fail-closed fallback. Native v1 does not
yet prove complete multiline interfaces or non-relative JS/TS dependency expansion, so Phase 8 fixes
those gaps before making a stronger claim. Rhize deliberately improves on the article by using an
existing healthy CodeGraph index for target discovery and, in v2, dependency expansion; supporting
Python/JavaScript/TypeScript plus tests/configuration; and treating critical-dependency recall and
task correctness as gates ahead of token savings.

Do not adopt the upstream compiler as a required runtime. Its evidence covers two small Python
repositories, uses `characters // 4` token estimates, begins from a known target, is not type-aware,
and does not measure coding outcomes. The headline “70% waste,” reported context-window change, and
69–74% reductions are source-specific observations, not Rhize baselines or architectural premises.
The upstream revision remains a pinned eval/reference provider.

The net-new follow-up is correctness hardening before delivery parity. Native v1's line-prefix
interface renderer must be replaced with parser-backed contract extraction that preserves multiline
signatures, overloads/generics/decorators, exported types, and the complete callable contract. Its
JavaScript/TypeScript resolver must resolve configured path aliases, package/workspace imports, and
package exports—or reject/fall back with a visible unresolved-import reason instead of silently
ignoring non-relative imports. Phase 8 then exposes the hardened native pack as one canonical skill
and host-neutral CLI for both Claude Code and Codex. Claude may retain an explicitly armed hook only
where its supported hook contract is verified; Codex uses explicit preview/build/verify until a
supported bounded injection surface exists. Host differences are recorded, never hidden behind a
claimed identical execution path.

Sources: Mixedbread [pricing](https://www.mixedbread.com/pricing),
[Privacy Policy](https://www.mixedbread.com/pages/privacy),
[Terms](https://www.mixedbread.com/pages/terms), and
[mgrep repository](https://github.com/mixedbread-ai/mgrep); grepai
[repository](https://github.com/yoanbernabeu/grepai),
[embedders](https://yoanbernabeu.github.io/grepai/backends/embedders/), and
[stores](https://yoanbernabeu.github.io/grepai/backends/stores/).

## 2. Findings that govern the design

### 2.1 mgrep

mgrep may be useful when the agent knows the intent of the code it wants but not the exact symbol, filename, or wording. It is not a safe global replacement for deterministic search.

Constraints that shape the pilot:

- Indexing sends selected files to a Mixedbread-backed store. The initial pilot therefore uses only an explicitly allowlisted, non-sensitive internal repository after a dry-run inventory.
- The official plugin's broad instruction to replace grep, glob, and web search conflicts with Rhize's CodeGraph-first policy and with the need to verify exact claims. Rhize will call the CLI through its own provider adapter instead of installing that instruction layer.
- Results are candidates, not evidence. Exact claims must be verified with CodeGraph, `rg`, or direct source reads.
- Automatic background synchronization is unnecessary for the first phase. The pilot starts with explicit, one-shot indexing against a fixed Git snapshot.
- mgrep 0.1.13 is installed on the evaluation machine but is not authenticated. Authentication,
  account/store creation, upload, and deletion remain explicit gated actions.

### 2.2 Context Compiler

The referenced Context Compiler implementation is a useful proof of concept, but it is not sufficient as the production abstraction:

- It is Python-only and AST-based.
- It begins from a known target file rather than solving target discovery.
- Its name-based call matching can miss dynamic dispatch, event wiring, aliases, and name collisions.
- Its published examples demonstrate prompt-size reduction on small repositories, not improved coding outcomes.

Rhize should dogfood the upstream implementation on controlled Python fixtures, while building the lasting feature as a provider-neutral **compiled context pack**. Target discovery may come from CodeGraph, mgrep, Serena, or `rg`; compilation then selects full sources, interfaces, tests, configuration, and warnings under a budget.

### 2.3 Ownership decision

`rhize-context-manager` owns:

- provider routing and capability detection;
- experiment eligibility and assignment;
- read-only shadow execution;
- context-pack construction and provenance;
- metrics receipts and aggregation;
- opt-in setup, diagnostics, and rollback.

`rhize-devflow` may later consume a compiled pack for planning, impact mapping, or review. It must not own a second search/index/context stack.

External tools remain external dependencies. Rhize adapters pin, validate, and orchestrate them; the plugin suite does not vendor a fork during the evidence phase.

## 3. Success criteria and decision gates

Correctness is a non-inferiority gate. Token or latency savings do not compensate for a missed critical dependency, a failed task, or a privacy violation.

The thresholds below are **proposed program gates**, not vendor claims. Phase 0 may tighten them before any live arm is enabled, but later changes must be versioned in the experiment manifest rather than edited retroactively.

| Capability | Continue to broader pilot | Bundle candidate | Pause or reject |
|---|---|---|---|
| Local semantic retrieval | No critical relevant-file misses, no source egress, and acceptable local resource use in the paired offline corpus and first 5 eligible tasks | At least 20% median reduction in retrieval tokens or time-to-first-relevant-file over at least 20 eligible tasks, with relevant-file recall no worse than baseline | Critical dependency miss, repeated stale-index failure, unacceptable host impact, or no material efficiency gain after 20 eligible tasks |
| Managed mgrep retrieval | Phase 1.5 legal/pricing gates pass; no critical relevant-file misses or security event in the first 5 eligible tasks | Beats baseline by the retrieval gate and either materially beats the local candidate or demonstrates lower measured total cost of ownership | Unresolved free-tier terms, unapproved recurring cost/upload, unauthorized upload, critical miss, repeated stale index, or no material advantage over baseline/local candidate |
| Compiled context | Packs are reproducible, warnings are visible, and no supported task performs worse in the first 5 eligible tasks | At least 25% median reduction in context input tokens on supported tasks, no correctness regression, and zero silent stale-pack use over at least 20 eligible tasks | A critical dependency is omitted without a warning, stale content is injected, or savings remain immaterial after 20 eligible tasks |
| Combined path | Both independent experiments have passed their continue gates | A later 2x2 test shows additive value or a simpler combined workflow without correctness loss | Interaction makes results less reliable or increases total cost/latency beyond either independent winner |

Required review points:

- **First-run review:** after the first completed receipt for each capability.
- **Safety/calibration review:** after 5 eligible live tasks or 14 calendar days, whichever comes first.
- **Adoption decision:** after 20 eligible tasks with at least 8 live executions per arm, plus the paired offline corpus.
- **Post-bundle review:** 30 days after any opt-in bundle release.

Small samples will be reported as medians, ranges, and paired differences. The report must not claim statistical significance from an underpowered run. Bootstrap confidence intervals may be added once the sample is large enough to make them informative.

## 4. Scope and non-goals

### In scope

- An opt-in mgrep CLI adapter with explicit repository allowlisting.
- A bounded local semantic-retrieval adapter/spike that can be measured independently from mgrep.
- An adapter around a pinned upstream Context Compiler revision for Python fixture evaluation.
- A native, provider-neutral compiled-context contract suitable for mixed-language Rhize work.
- Automatic selection of the next eligible engineering task once an experiment is armed.
- Arm A/Arm B execution receipts that state exactly which variants ran.
- Read-only shadow measurements during live work.
- Paired offline benchmarks against fixed repository snapshots.
- Aggregated, sanitized reports and review gates.
- A bundle, refinement, or rejection decision supported by retained evidence.

### Out of scope during the evidence phase

- Replacing CodeGraph, Serena, `rg`, globbing, or direct source reads globally.
- Installing the official mgrep prompt/plugin as a default instruction layer.
- Uploading client repositories, credentials, customer exports, logs, or production data.
- Running two write-capable agents against the same live working tree.
- Using prompt-size reduction alone as proof of improved engineering performance.
- Counting a mock, synthetic, or fake provider run as dogfood or benchmark evidence.
- Vendoring or forking either upstream project before its value is demonstrated.
- Enabling a network provider silently through an automatic hook.
- Bundling setup in all Rhize plugins before the decision gate.

## 5. Experiment model

The two capabilities are evaluated independently first. This prevents a positive or negative result from being incorrectly attributed to the combination.

### 5.1 mgrep experiment

**Arm A — current retrieval baseline**

- If `.codegraph/` exists, use CodeGraph first.
- Otherwise use the existing context-stack route: focused `rg`, targeted file reads, and Serena where available and appropriate.
- Record search queries, files considered, files read, tool calls, tokens, timings, and final relevant-file judgment.

**Arm B — mgrep candidate retrieval with deterministic verification**

- Query the repository's dedicated mgrep store using the normalized task intent.
- Treat results only as candidates.
- Verify selected files and exact claims with CodeGraph, `rg`, or direct source reads.
- Fall back to Arm A immediately when mgrep is unavailable, stale, outside budget, or returns insufficient evidence.
- Record both the semantic result set and the verification route.

### 5.2 Compiled-context experiment

**Arm A — current targeted-read baseline**

- Follow the normal context-stack route and let the agent request files as needed.
- Capture the actual context supplied during discovery and implementation.

**Arm B — compiled context pack**

- Discover likely targets with the current routing stack.
- Build a dependency-aware pack under a declared token budget.
- Include target implementations in full, relevant interfaces or signatures for dependencies, nearby tests and configuration, provenance, and explicit uncertainty warnings.
- Allow the agent to retrieve more context. Such retrieval is measured as a pack miss, not prohibited.
- Recompile or invalidate the pack after any source edit that affects its hashes.

### 5.3 Combined experiment

Only after both independent experiments pass the adoption gate, run a 2x2 comparison:

| Cell | Retrieval | Context construction |
|---|---|---|
| 1 | Baseline | Targeted reads |
| 2 | mgrep + verification | Targeted reads |
| 3 | Baseline | Compiled pack |
| 4 | mgrep + verification | Compiled pack |

The combined test determines whether semantic retrieval improves target discovery for compilation or merely duplicates the existing stack.

## 6. What “automatically run on the next viable task” means

Automatic execution is **one-shot, opt-in, and eligibility-gated**. An operator explicitly arms a capability for a bounded number of runs. The selector then claims the next eligible task without requiring the operator to remember to start the experiment.

### 6.1 Arming configuration

Add an opt-in setup item that writes local, gitignored configuration under the context manager's existing user configuration directory. A proposed configuration shape is:

```json
{
  "schemaVersion": 1,
  "experiments": {
    "localRetrieval": {
      "enabled": false,
      "armedRuns": 0,
      "eligibleRepos": ["/absolute/path/to/rhize-plugins"],
      "liveAssignment": "alternate",
      "shadow": true,
      "networkApproved": false,
      "smokeApproved": false
    },
    "mgrep": {
      "enabled": true,
      "armedRuns": 1,
      "eligibleRepos": ["/absolute/path/to/rhize-plugins"],
      "liveAssignment": "alternate",
      "shadow": true,
      "networkApproved": true,
      "store": "rhize-dogfood-rhize-plugins"
    },
    "compiledContext": {
      "enabled": true,
      "armedRuns": 1,
      "eligibleRepos": ["/absolute/path/to/rhize-plugins"],
      "liveAssignment": "alternate",
      "shadow": true
    }
  }
}
```

The schema must reject unknown fields, relative repository paths, an mgrep arm without `networkApproved`, and an `armedRuns` value outside the configured safety maximum.

### 6.2 Eligibility checks

A task is eligible only when all of the following are true:

- The current directory is inside an explicitly allowlisted Git repository.
- The repository snapshot can be identified with commit plus dirty-state hashes.
- The task includes code discovery, impact analysis, implementation, diagnosis, or review where retrieval affects the outcome.
- The discovery portion can begin read-only.
- The relevant provider is installed, healthy, and current enough for the snapshot.
- The task has a normalized query with sufficient meaning for semantic retrieval or a discoverable target for compilation.
- No other process holds the repository/capability experiment lease.
- The configured run, time, token, and network budgets have not been exhausted.

A task is ineligible when it is:

- a production incident, release, merge, credential operation, database mutation, or other time-sensitive operational action;
- a one-line deterministic lookup, trivial documentation edit, or task where semantic retrieval cannot plausibly matter;
- in a non-allowlisted client or private repository;
- working with `.env*`, keys, auth exports, customer data, production logs, backups, generated bundles, or binary-heavy material;
- dependent on an index whose snapshot cannot be proven current;
- already partway through discovery before the selector runs;
- likely to exceed configured data, file-count, token, or duration limits.

### 6.3 Claim and assignment

The selector uses an atomic lease scoped to repository, snapshot, capability, and task ID. This prevents concurrent sessions from claiming the same “next” run.

Assignment rules:

1. Create a stable task ID from repository, snapshot, normalized task class, and session ID.
2. Evaluate and record every eligibility rule.
3. Atomically claim an armed run.
4. Assign the live arm using a deterministic alternating sequence stratified by task class and repository.
5. Run the other arm as a read-only shadow when budgets and provider policy permit.
6. Decrement `armedRuns` only after a receipt is durably written. A skipped or preflight-failed task does not consume the run.
7. Release the lease on completion or timeout.

The very first mgrep dogfood run should use **Arm B live and Arm A shadow** so the new path is genuinely exercised. The first compiled-context run should be an explicit `/context-pack` invocation before automatic injection is enabled; after that smoke test, the next eligible armed task may use Arm B live.

### 6.4 Live and shadow boundary

- Exactly one arm may influence the live task's retrieval/context decisions.
- The shadow arm is read-only and may not edit files, run mutating commands, send messages, or alter the agent's live prompt.
- The shadow may inspect the same immutable snapshot and emit candidates, a pack, timings, and token estimates.
- If a shadow arm would require unapproved network access, it is skipped with a recorded reason.
- A receipt must never imply that an unexecuted arm ran.

Every receipt includes:

```json
{
  "armsRequested": ["A", "B"],
  "armsExecuted": ["A", "B"],
  "armsSkipped": [],
  "liveVariant": "B",
  "shadowVariant": "A",
  "fallbackUsed": false
}
```

If only one arm ran, `armsExecuted` contains only that arm and `armsSkipped` contains the other arm plus a reason code.

## 7. Technical architecture

### 7.1 Planned file layout

The implementation should follow existing plugin conventions after inspecting neighboring scripts and tests. The intended ownership boundaries are:

```text
rhize-context-manager/
  commands/
    context-experiment.md
    context-pack.md
  hooks/
    context-experiment-selector.js
    context-experiment-finalizer.js
  schemas/
    context-experiment-v1.schema.json
    context-pack-v1.schema.json
  scripts/context_experiments/
    __init__.py
    aggregate.py
    eligibility.py
    metrics.py
    models.py
    receipt_store.py
    runner.py
    security.py
    providers/
      __init__.py
      base.py
      baseline.py
      mgrep.py
      upstream_context_compiler.py
      compiled_context.py
  skills/
    context-tools-dogfood/
      SKILL.md
  setup/
    manifest.json

evals/context-tools/
  README.md
  cases.json
  run_context_evals.py
  fixtures/
    python-static/
    python-dynamic/
    typescript-static/
    mixed-plugin/
  tests/
    test_aggregation.py
    test_compiled_context.py
    test_eligibility.py
    test_mgrep_provider.py
    test_receipts.py
    test_security.py
    test_selector_hooks.py
```

Keep hook files thin. The core selector, policy, provider, metrics, and aggregation logic belongs in testable standard-library Python unless an existing context-manager runtime convention requires otherwise.

Raw local receipts belong outside Git under the context manager's local data directory. Only redacted aggregate reports and deliberately constructed fixtures may enter `evals/results/context-tools/`.

### 7.2 Provider contract

All retrieval providers implement the same conceptual request:

```json
{
  "schemaVersion": 1,
  "experimentId": "uuid",
  "repoRoot": "/absolute/allowlisted/repo",
  "snapshot": {
    "commit": "git-sha",
    "dirtyTreeHash": "sha256-or-null"
  },
  "query": "normalized task intent",
  "limits": {
    "maxResults": 20,
    "maxDurationMs": 30000,
    "maxInputBytes": 1048576
  }
}
```

And return candidates without asserting they are correct:

```json
{
  "provider": "mgrep",
  "providerVersion": "pinned-version",
  "snapshotVerified": true,
  "results": [
    {
      "path": "relative/path.py",
      "lineStart": 10,
      "lineEnd": 42,
      "score": 0.84,
      "contentHash": "sha256",
      "reason": "semantic candidate"
    }
  ],
  "warnings": [],
  "metrics": {
    "elapsedMs": 1234,
    "queryCount": 1,
    "bytesUploadedThisRun": 0
  }
}
```

Paths must remain repository-relative in stored receipts. Source text, queries containing secrets, absolute user paths, and code excerpts are redacted from aggregate artifacts.

### 7.3 Compiled-context contract

A context pack is a versioned artifact tied to a repository snapshot and task query. Each entry has one of three inclusion levels:

- `FULL`: complete source for target implementations and other code whose body is necessary.
- `INTERFACE`: signatures, types, public contract, or bounded excerpts for supporting dependencies.
- `EXCLUDED`: considered but omitted, with reason and risk.

Each pack includes:

- repository snapshot and dirty-tree hash;
- normalized task and selected targets;
- source provider and selection reason for every entry;
- content hash, language, line range, and estimated tokens;
- relevant tests and configuration;
- unresolved dynamic edges and ambiguity warnings;
- total budget, consumed budget, and truncation decisions;
- compiler implementation and version;
- an invalidation check that runs before use and after source edits.

The pack must never silently collapse two same-named symbols or claim a dynamic edge is complete. Unsupported or ambiguous analysis produces a warning and widens the context or falls back to targeted reads.

### 7.4 Upstream Context Compiler adapter

Use the upstream implementation only in the controlled Python phase:

- Pin an exact revision and record its license and checksum.
- Install it through explicit setup; never download code during a live agent task.
- Execute it in an isolated environment against fixture or approved repositories.
- Translate its output into the Rhize context-pack schema.
- Add regression cases for aliased imports, duplicate function names, decorators, callbacks, event registration, and dynamic dispatch.
- Mark unsupported cases as warnings or fallbacks rather than treating the output as complete.

The native provider-neutral compiler may reuse useful algorithms only where licensing permits and tests show the behavior is sound. Do not make the upstream Python package a mandatory runtime for non-Python repositories.

### 7.5 mgrep adapter

The adapter must:

- detect the CLI and capture its version;
- require an approved dedicated store per repository;
- verify the indexed snapshot or require explicit re-indexing;
- run manual one-shot sync during the pilot;
- enforce `.mgrepignore` plus Rhize's denylist before indexing;
- parse structured output rather than scraping display text where the CLI supports it;
- impose result, duration, byte, and retry limits;
- fall back cleanly to baseline retrieval;
- provide a doctor command showing installation, authentication, store, snapshot, ignore rules, and deletion instructions;
- never adopt upstream instructions that globally replace deterministic tools.

If an API key is required, store it in macOS Keychain with an on-demand retrieval helper. Do not export it automatically into all shell sessions. If mgrep uses its own device-auth credential store, document and validate that behavior without copying the credential into receipts.

## 8. Privacy and security gates

The first mgrep pilot repository should be this internal `rhize-plugins` repository, subject to a successful dry-run inventory. Client repositories remain excluded until a separate data-handling approval exists.

Before the first upload:

1. Enumerate every path, extension, file count, and total byte count that would be indexed.
2. Apply repository `.gitignore`, `.mgrepignore`, and the hard Rhize denylist.
3. Fail closed if any denied pattern survives.
4. Present or retain a redacted manifest with counts and hashes, not contents.
5. Create a dedicated store whose name includes repository and pilot identity.
6. Record the deletion/purge procedure and verify access before upload.
7. Index an immutable snapshot and record the provider receipt.

Hard-deny at minimum:

- `.env`, `.env.*`, credential files, keys, certificates, auth caches, cookies, and tokens;
- `.git`, `.vercel`, local tool state, package caches, build outputs, and dependencies;
- database dumps, backups, exports, production logs, recordings, screenshots, and binary media;
- customer datasets and any file matched by repository-specific protected-data rules;
- files over the configured size limit and unsupported binary types.

The security layer must inspect resolved paths to prevent symlink escape and must never rely only on filename patterns. Network access is denied unless both the repository and capability are explicitly approved.

Any unauthorized upload, path escape, credential exposure, or incorrect repository selection immediately disables the experiment and triggers the rollback procedure. Efficiency metrics are irrelevant after a privacy gate failure.

## 9. Measurement and receipts

### 9.1 Correctness metrics

- Task result: completed, partially completed, failed, or abandoned.
- Repository validation: targeted tests, broader tests, typecheck, lint, and build where applicable.
- Relevant-file precision and recall against a reviewed ground-truth set.
- Critical dependency misses, including files discovered only after the initial route or pack.
- Incorrect-file distraction count.
- Human reviewer verdict on completeness and unsupported claims.
- Regression severity and whether retrieval/context construction contributed.
- Fallback use and whether fallback recovered correctness.

Changed files and passing tests are evidence, but they are not sufficient ground truth by themselves. Offline cases require a reviewed list of relevant files, critical symbols, expected warnings, and validation commands.

### 9.2 Efficiency metrics

- Input, cache-read, cache-write, and output tokens when the host exposes them.
- Estimated tokens in candidate excerpts and compiled packs.
- Number of search calls, direct reads, tool calls, and agent turns.
- Time to first relevant file.
- Time to sufficient context, first correct plan, first edit, and completion.
- Total task duration and provider-only duration.
- Context-window compaction or overflow events.
- Additional retrieval after the pack, treated as pack misses.
- Bytes indexed/uploaded, store size, sync duration, query count, and provider cost when available.

Self-reported provider savings are retained as diagnostics only; they are not decision metrics.

### 9.3 Reliability and governance metrics

- Provider version, model, host, plugin revision, and experiment schema version.
- Commit, dirty-tree hash, index snapshot, pack hashes, and staleness checks.
- Warnings, retries, timeouts, fallbacks, skipped arms, and reason codes.
- Eligibility decisions and lease collisions.
- Privacy preflight result, denied-file counts, and network approval state.
- Manual interventions and reviewer overrides.

### 9.4 Receipt integrity

Each run writes an append-only JSON receipt before aggregate reporting. The receipt must:

- identify `armsRequested`, `armsExecuted`, `armsSkipped`, `liveVariant`, and `shadowVariant`;
- distinguish measured facts from estimates and human judgments;
- contain no source code, secrets, raw prompts, or unredacted absolute user paths;
- hash the schema, configuration, provider versions, and relevant artifacts;
- survive an interrupted task and finalize later as incomplete;
- reject edits after finalization or retain a visible amendment trail;
- support aggregation by capability, arm, repository class, language, task class, and snapshot.

## 10. Offline benchmark design

Live results are ecologically useful but confounded by different tasks, models, and repository states. The adoption gate therefore also requires paired offline evaluation.

### 10.1 Corpus

Build at least 12 reviewed cases before the adoption decision:

- 3 Python static-call cases supported by the upstream compiler.
- 2 Python dynamic/ambiguous cases expected to warn or fall back.
- 3 TypeScript/JavaScript static cases.
- 2 mixed plugin/configuration cases from sanitized repository fixtures.
- 2 exact-lookup or trivial cases where the selector should decline the experiment.

Cases should include bug diagnosis, feature impact mapping, targeted implementation, and code review. Each case pins a repository snapshot and supplies:

- task prompt;
- ground-truth relevant files and critical symbols;
- expected dynamic-edge warnings;
- validation commands;
- protected and irrelevant files;
- maximum budgets;
- rubric for correctness and reviewer scoring.

### 10.2 Execution

- Run paired arms against the same immutable snapshot in isolated worktrees or copied fixtures.
- Use the same model, reasoning effort, system instructions, tool availability, token limits, and validation commands.
- Randomize arm order to reduce warm-cache/order effects.
- Clear or separately label provider and model caches.
- Prevent any write-capable arms from sharing a working tree.
- Run one smoke repetition while developing; use at least three repetitions for decision candidates.
- Retain failures and timeouts rather than silently rerunning only bad results.
- Record environment and dependency versions for reproducibility.

### 10.3 Analysis

Report:

- per-case paired differences;
- medians and interquartile ranges by arm and task class;
- relevant-file recall and critical-miss counts;
- correctness/validation pass rates;
- time, tokens, turns, reads, and provider cost;
- fallbacks, warnings, and stale-artifact events;
- live observational results separately from offline paired results.

Do not pool a Python-only compiler win into a mixed-language claim. Do not combine skipped, fallback, and successful Arm B runs without labeling them.

## 11. Implementation phases

### Phase 0 — Freeze policy and baseline

**Goal:** make the experiment auditable before introducing either dependency.

Tasks:

- Add this plan's decisions to a short architecture decision record in `rhize-context-manager`.
- Define the versioned experiment, receipt, provider, and context-pack schemas.
- Define the repository allowlist, hard denylist, budgets, and proposed thresholds.
- Select and review the first offline cases.
- Capture current-stack baseline runs with the existing eval harness where possible.
- Document why mgrep and the upstream compiler are optional providers, not replacements.

Verify:

- Schema tests reject missing arm fields, unknown variants, relative paths, and unapproved network use.
- A dry receipt clearly reports one executed baseline arm and one skipped experimental arm.
- Security review signs off on the first repository dry-run policy.

- Dependencies: none.
- Executor: Terra; Sol review.

### Phase 1 — Build the experiment spine

**Goal:** reliably select, claim, execute, and measure an experiment without either external provider.

Tasks:

- Implement typed models, eligibility, atomic leases, arm assignment, budgets, receipts, and aggregation.
- Add minimal in-test provider doubles for failure/concurrency coverage and a read-only
  shadow runner. Test doubles must not ship as a user-facing simulator or contribute
  benchmark evidence.
- Add thin selector/finalizer hooks through opt-in `setup/manifest.json` entries.
- Add `/context-experiment status|arm|disarm|doctor|report` documentation and command handling.
- Make the hook a no-op unless explicitly armed.
- Add interrupted-run finalization and stale-lease recovery.

Verify:

- Unit tests cover every eligibility and exclusion rule.
- Concurrency tests prove only one session claims a run.
- Arm A and Arm B receipts never misstate which variant ran.
- Hook tests cover supported Claude/Codex payload shapes and malformed input.
- An isolated contract test proves live/shadow accounting, followed by a real-provider
  smoke run in Phase 2 or 3 before this work is released.

- Dependencies: Phase 0 schemas and policy.
- Executor: Terra; Sol cold review.

### Phase 1.5 — Retrieval provider economics, privacy, and local-first spike

**Goal:** determine whether a managed account is justified before sending source to a vendor.

**Current disposition (2026-08-27):** implementation and the real offline spike are complete.
Arm B-local failed correctness non-inferiority and is paused before live-task arming. Arm B-managed
remains blocked by the contradictory free-tier data-use terms and requires a separate paid-tier
decision; no Mixedbread account, store, authentication, or upload was created.

Run three separately identified paths against the same reviewed retrieval corpus; never aggregate
the two candidate providers into one Arm B result:

- **Arm A:** the current CodeGraph/`rg`/direct-read routing stack;
- **Arm B-local:** pinned grepai + pinned local Ollama embedding model + local GOB store;
- **Arm B-managed:** pinned mgrep + Mixedbread Store, permitted only after its legal, cost, and
  upload gates pass.

Tasks:

- Freeze a dated pricing, terms, and privacy snapshot with source links and note any ambiguity.
- Add a provider-specific cost model: initial and incremental indexing, storage, query/rerank,
  subscription minimum, host resource use, setup/maintenance interventions, and failure recovery.
- Pin and checksum-review grepai and one local embedding model before installation. Start with the
  zero-service GOB backend; do not add Qdrant/PostgreSQL or an automatic watcher to the first run.
- Reuse the independent Rhize manifest/denylist. Treat `.grepaiignore` as additive only: its
  negation support must never re-include a hard-denied path.
- Run the paired offline retrieval corpus with provider, model, snapshot, and arm recorded in every
  row. Then use the winning eligible path as Arm B for the next explicitly armed live task.
- Measure relevant-file recall/precision, time to first relevant file, search/read calls, result
  tokens, index/query latency, peak resident memory, model/index disk bytes, and manual
  interventions. Record local resource use even when direct vendor cost is zero.
- Before any Mixedbread signup, obtain written clarification of the conflicting free-tier data-use
  language, confirm current rates/credit behavior, approve any recurring commitment, and verify a
  complete store purge path. If those gates fail, mark Arm B-managed skipped with reason rather
  than weakening them.

Decision rules:

- Prefer the local candidate when it passes correctness/non-inferiority and meets the existing
  efficiency gate without unacceptable host or maintenance cost.
- Pay for managed mgrep only if it passes data handling and demonstrates incremental value over the
  local candidate or a lower measured total cost of ownership. A small API bill alone is not proof
  of lower total cost.
- Reject both candidates if deterministic routing remains as accurate and the semantic paths do not
  recover enough task time/token cost to cover their measured burden.

Verify:

- No account, token, remote store, or source upload exists before the managed gate is signed off.
- Offline reports keep baseline, local, and managed providers separate and identify which arm ran.
- The local candidate can be removed completely by deleting its tool/model/index artifacts, and no
  repository source appears in network receipts.
- The chosen next-task provider has a reviewed install, ignore, staleness, and rollback procedure.

- Dependencies: Phase 1; independent of the Context Compiler Phase 3 smoke path.
- Executor: Terra; Sol economics, privacy, and decision review.

### Phase 2 — mgrep provider and first automatic live run

**Goal:** exercise mgrep on the next eligible task safely and retain a complete comparison.

Tasks:

- Pin a tested mgrep CLI version and document explicit install/uninstall steps.
- Implement installation/version/auth/store/snapshot health checks.
- Implement the dry-run inventory, resolved-path denylist, `.mgrepignore`, and size limits.
- Create a dedicated pilot store for `rhize-plugins` only after preflight passes.
- Perform one-shot indexing of a recorded snapshot; do not start background sync.
- Implement semantic query, structured result parsing, deterministic verification, budgets, and fallback.
- Arm exactly one mgrep run with Arm B live and Arm A read-only shadow.
- Let the selector claim the next eligible task automatically.
- Finalize the receipt and conduct the first-run review before rearming.

Verify:

- Security tests prove ignored, denied, oversized, binary, and symlink-escape files cannot be indexed.
- Fake-CLI tests cover missing binary, auth failure, stale store, timeout, malformed output, and zero results.
- The live receipt proves Arm B ran, records Arm A shadow or the exact skip reason, and links task validation evidence.
- Exact claims from mgrep candidates are backed by CodeGraph, `rg`, or direct reads.
- Store deletion instructions are tested before broader rollout.

- Dependencies: Phase 1.5 must approve managed mgrep; explicit network/data and recurring-cost
  approval at arming time.
- Executor: Terra; Sol security and first-run review.

### Phase 3 — Upstream Context Compiler dogfood

**Goal:** establish where the upstream library works and where it fails before designing around it.

**Current disposition (2026-08-27):** complete. The real pinned provider passed all nine
behavior cases and the versioned gate records `continue_to_phase_4`. This means the adapter is
reproducible and conservative enough to inform Phase 4; it does not demonstrate better coding
outcomes and remains ineligible for automatic injection.

Tasks:

- Pin the upstream source revision, checksum, license, Python version, and dependencies.
- Wrap it behind the provider contract and translate output to context-pack v1.
- Add static Python fixtures resembling the upstream supported case.
- Add adversarial fixtures for aliases, duplicate names, decorators, callbacks, event wiring, and dynamic dispatch.
- Add an explicit `/context-pack --provider upstream-python` command.
- Run paired offline Arm A/Arm B cases; do not inject it automatically into mixed-language tasks.

Verify:

- Supported static cases produce reproducible packs.
- Unsupported cases warn, widen, or fall back; none silently claim completeness.
- Pack hashes invalidate when source changes.
- Paired benchmark receipts separate prompt-size savings from outcome correctness.

- Dependencies: Phase 1; independent of Phase 2 after the shared spine exists.
- Executor: Terra; Luna may build fixtures after contracts are fixed; Sol review.

### Phase 4 — Native provider-neutral compiled context

**Goal:** create the Rhize-owned abstraction that can serve mixed-language work without duplicating the context stack.

**Disposition (2026-08-27):** complete. Native v1 passed the fixed mixed-language gate and its
actual-repository explicit/query smoke paths; unsafe dynamic targets reject use.

Tasks:

- Implement target discovery adapters for baseline routing and CodeGraph where `.codegraph/` exists.
- Treat mgrep as an optional target-discovery adapter only after Phase 2 evidence.
- Implement FULL/INTERFACE/EXCLUDED selection under a budget.
- Include relevant tests, types, schemas, configuration, and call/dependency evidence.
- Surface unresolved dynamic edges and collision risk.
- Implement incremental invalidation and recompilation after edits.
- Add `/context-pack` inspection output showing why every entry was selected.

Verify:

- Golden fixtures produce stable manifests across repeated runs.
- Source edits invalidate only affected artifacts without allowing stale content.
- Dynamic and ambiguous fixtures warn or fall back.
- Pack construction never bypasses CodeGraph-first routing when CodeGraph exists.
- Pack inspection is understandable without exposing source in receipts.

- Dependencies: Phase 3 findings; Phase 2 only if adding mgrep discovery at this point.
- Executor: Terra; Sol architecture review.

### Phase 5 — Compiled-context live pilot

**Goal:** measure compiled packs in real, eligible tasks without forcing the workflow globally.

**Disposition (2026-08-27):** first-run complete. The one-shot selector built a real accepted
native pack before the next implementation slice and recorded Arm B live/Arm A shadow. The receipt
retains human-review warnings for correctness and follow-up reads. Broader rollout stops at
advanced opt-in and moves to the scheduled 5-task/14-day review rather than claiming adoption.

Tasks:

- First use `/context-pack` explicitly on an approved task and review the artifact.
- Arm one automatic compiled-context run after the smoke review.
- Alternate live arms for later runs and run the other arm as read-only shadow.
- Permit follow-up reads and record each as a pack miss.
- Revalidate/recompile after edits before the pack is reused.
- Stop at 5 tasks for the safety/calibration review.

Verify:

- Every live pack matches the repository snapshot at injection time.
- The receipt identifies the live arm, shadow arm, warnings, and follow-up reads.
- No correctness issue is hidden by a lower token count.
- The calibration report recommends continue, change thresholds, narrow eligibility, or stop.

- Dependencies: Phase 4; Phase 1 selector.
- Executor: Terra; Sol first-run and five-run reviews.

### Phase 6 — Decision corpus and combined test

**Goal:** produce enough controlled and live evidence for a bundle decision.

**Disposition (2026-08-27):** complete at the documented stop/decision boundary. Fourteen paired
compiled-context cases and six paired retrieval cases reconcile to their source reports. The 2x2
combined run was not executed because both semantic-retrieval candidates failed prerequisites.

Tasks:

- Complete at least 12 paired offline cases and the required live-task sample.
- Aggregate mgrep and compiled-context results independently.
- If both pass, run the 2x2 combined comparison.
- Analyze results by repository class, language, task class, and fallback status.
- Document negative results and operational cost as prominently as savings.
- Produce an adoption decision: bundle, revise and rerun, retain as advanced opt-in, or reject.

Verify:

- Raw receipts reconcile to every aggregate count.
- Executed, skipped, fallback, live, and shadow variants remain distinguishable.
- A skeptical review reproduces sampled metrics from raw receipts.
- Conclusions do not exceed the language/repository/task coverage of the corpus.

- Dependencies: Phases 2 and 5.
- Executor: Terra analysis; Sol final decision review.

### Phase 7 — Bundle or retire

**Disposition (2026-08-27):** complete. Bundle the native pack as disabled-by-default advanced
opt-in; retain upstream/retrieval adapters only as evidence infrastructure; do not add a
`rhize-devflow` consumer or managed provider setup. See
`evals/context-tools/NATIVE_CONTEXT_DECISION.md`.

**If evidence supports adoption:**

- Package the smallest winning capability inside `rhize-context-manager`.
- Keep mgrep installation and network indexing opt-in with explicit setup and doctor output.
- Preserve provider-neutral routing and deterministic verification.
- Update `context-stack`, README/GUIDE, setup manifest, changelog, tests, and marketplace version.
- Add consumption points to `rhize-devflow` only where an eval demonstrated value.
- Release as opt-in first and schedule a 30-day post-bundle review.

**If evidence does not support adoption:**

- Disable and remove automatic hooks and provider setup.
- Stop any watcher, purge pilot stores through the provider's documented process, and remove local credentials if no longer used.
- Retain redacted schemas, fixtures, receipts, and the rejection decision so the experiment is not repeated without new evidence.
- Keep any independently valuable generic eval infrastructure only if it has a clear owner and maintenance value.

Verify:

- Full plugin validation passes.
- Documentation matches actual defaults and data movement.
- Rollback is exercised in a clean environment.
- The final Jira update links the decision and retained evidence.

- Dependencies: Phase 6 decision.
- Executor: Terra; Sol production/release gate.

### Phase 8 — Native pack v2, Claude Code/Codex packaging, and host-stratified evidence

**Disposition (2026-08-30):** proposed; implementation is blocked until RT-128 is updated with the
accepted scope and measurement matrix.

Tasks:

- Replace line-prefix INTERFACE rendering with parser-backed language adapters that preserve complete
  multiline Python/JavaScript/TypeScript public contracts. Unsupported/ambiguous parsing widens to
  full source or rejects the pack; it never emits a confidently incomplete interface.
- Use CodeGraph for dependency expansion when an existing healthy `.codegraph/` index is present.
  Otherwise resolve JS/TS relative imports plus `tsconfig`/`jsconfig` path aliases, package/workspace
  imports and package exports, and Python configured source roots within the verified snapshot. Any
  unresolved internal import is recorded with source location and triggers the predeclared widen/
  fallback decision; never initialize or sync CodeGraph automatically.
- Add critical-symbol/contract-fidelity fixtures that assert rendered signatures, types, decorators,
  overloads/generics, alias targets, workspace packages, and negative dynamic/unsupported cases—not
  only selected roles and paths.
- Create `rhize-context-manager/skills/context-pack/SKILL.md` as the canonical workflow and
  `skills/context-pack/agents/openai.yaml` for Codex routing metadata.
- Make `commands/context-pack.md` a thin Claude adapter over the existing host-neutral runner.
- Register the skill in the `.codex-plugin/plugin.json` created by the unified-memory foundation;
  synchronize Claude/Codex/marketplace manifests, root CHANGELOG/ROADMAP, README/GUIDE, setup
  metadata, and generated skill maps.
- Resolve source/install roots portably rather than depending only on Claude-specific environment
  variables or home-directory layout.
- Preserve CodeGraph-first behavior only when `.codegraph/` already exists; never initialize or sync
  CodeGraph automatically. Fall back to the current native/`rg` path with an explicit reason.
- Add calibrated eligibility for projected benefit and scan/index budget. Single-file/small,
  alias-heavy, highly dynamic, and bounded large-repository fixtures return explicit reasons such as
  `insufficient_compilation_benefit` or `repository_scan_budget_exceeded`; thresholds are measured and
  versioned rather than copied from the article.
- Reconcile the v2 artifact model: pack entries remain `FULL` or `INTERFACE`, while excluded files are
  represented by a bounded source-free reason-count ledger plus private inspection output. Do not
  claim one manifest entry per excluded file when the schema stores only an aggregate.
- Keep context-pack content private and explicit. No host may scrape private transcripts or silently
  inject a pack; any later injection is a separate Jira decision.

Verify:

- Fresh installed Claude Code and Codex sessions discover the canonical skill and produce
  byte-equivalent deterministic manifests, hashes, roles, warnings, and fallback decisions for fixed
  fixtures; live model/task outcomes are evaluated separately by host/model.
- Static, dynamic, collision, event/callback, mixed-language, missing-CodeGraph, stale snapshot,
  multiline-interface, path-alias/workspace, unsupported-host, and budget/coverage cases preserve
  complete critical contracts or fail closed.
- Single-file/small, alias-heavy, dynamic, and bounded large-repository cases prove eligibility and
  scan-budget decisions without inventing universal thresholds.
- Run two separately labeled comparisons that are never pooled: native-v1 versus native-v2 isolates
  correctness/regression changes, while the current CodeGraph/`rg`/targeted-read workflow versus
  native-v2 measures product value. A complete supported-source dump remains a diagnostic upper bound,
  not the claimed production baseline. Host/model/tool availability and repository state are matched,
  and actual host input tokens are preferred when exposed while estimates remain labeled.
- RT-128 records frozen repo/query/source fingerprints, baseline/candidate/release SHAs, host/model/
  plugin versions, critical symbol/file misses, rendered-contract completeness, correctness,
  follow-up reads, context tokens, latency, operator burden, and explicit promote/hold outcome. Raw
  packs/prompts/paths remain local.
- Native packs remain advanced opt-in until the predeclared live sample is reviewed; token reduction
  alone cannot promote the capability.

- Dependencies: unified-memory Phase 0 owns the context-manager Codex manifest; existing Phase 7
  native-pack decision and RT-128 evidence remain authoritative.
- Executor: Terra; Sol cross-host and release review.

## 12. Test and validation matrix

| Area | Required cases |
|---|---|
| Eligibility | eligible implementation, trivial/single-file/small repo, alias-heavy/dynamic repo, bounded large repo, projected-benefit/scan-budget decline, production incident, protected task, wrong repo, exhausted budget, already-in-progress discovery |
| Assignment | first B-live run, alternation, deterministic stratification, skipped arm, fallback, no shadow network approval |
| Concurrency | atomic claim, competing sessions, stale lease, interrupted finalization |
| Security | `.env*`, nested secrets, symlink escape, ignored paths, oversized file, binary, customer export, wrong store/repository |
| mgrep | missing CLI, version mismatch, auth failure, store absent, stale snapshot, zero result, malformed result, timeout, fallback, deterministic verification |
| Upstream compiler | static imports/calls, aliases, duplicate names, decorators, callbacks, event registration, dynamic dispatch, unsupported syntax |
| Native pack | FULL/INTERFACE selection, multiline contract fidelity, path-alias/workspace import resolution, test/config inclusion, budget truncation, ambiguity warning, stale hash, post-edit invalidation, critical-symbol recall, follow-up read |
| Receipts | exact executed arms, skipped reasons, redaction, interrupted run, amendment trail, schema/version hash, aggregate reconciliation |
| Hooks | valid payloads, malformed payload, unarmed no-op, unsupported host, provider unavailable, finalizer after failure |
| Cross-host | fresh Claude Code/Codex discovery, portable roots, equivalent deterministic artifacts, explicit capability differences, no unsupported injection |
| E2E | isolated Python, TypeScript, dynamic, and mixed-plugin fixtures with fixed validation commands |

Current executable interfaces:

```bash
python3 -m pytest evals/context-tools/tests
python3 evals/context-tools/run_retrieval_evals.py --output /private/report.json
python3 evals/context-tools/run_context_evals.py --checkout /path/to/context-compiler --output /private/report.json
python3 rhize-context-manager/scripts/context_experiments/runner.py doctor
python3 rhize-context-manager/scripts/context_experiments/runner.py pack --provider upstream-python --repo /absolute/repo --target /absolute/repo/file.py
python3 rhize-context-manager/scripts/context_experiments/runner.py report
```

Implementation must also run the repository's existing validation suite and plugin checks before each commit or release gate.

## 13. Rollout and rollback controls

Rollout controls:

- off by default;
- explicit opt-in setup item;
- absolute repository allowlist;
- separate `enabled`, `armedRuns`, `networkApproved`, `shadow`, and budget settings;
- maximum one automatic run before first-run review;
- health check and snapshot verification before claim;
- immediate fallback to current routing;
- no background mgrep synchronization in the initial pilot;
- provider/version visible in every receipt and report.

Rollback sequence:

1. Disarm the experiment and disable the setup hook.
2. Finalize or mark any open receipt incomplete.
3. Stop mgrep synchronization if it was enabled in a later phase.
4. Revoke or remove local authentication if the capability is being retired.
5. Purge the dedicated remote store using a verified, explicit provider operation.
6. Remove local indexes/configuration without touching source repositories.
7. Confirm the existing CodeGraph/Serena/`rg` route remains operational.
8. Retain only redacted metrics and the decision record.

Deletion must never be implemented as an unresolved wildcard or broad recursive command. The doctor output must identify exact local and remote resources before a rollback action is offered.

## 14. Jira tracking and review cadence

Create one Rhize Tools Task that links this plan and tracks the internal program. Keep implementation detail in this versioned plan rather than duplicating a brittle wall of prose in Jira.

The Jira Task should contain these milestones as checkboxes:

- Phase 0 policy, schemas, and baseline complete.
- Phase 1 experiment spine complete.
- Phase 1.5 provider economics/privacy review and local semantic-retrieval report complete.
- First mgrep preflight/index and automatic live receipt reviewed if the managed gate passes;
  otherwise the exact legal/economic stop reason is recorded.
- Upstream Context Compiler fixture benchmark complete.
- Native compiled-context pack complete.
- First compiled-context live receipt reviewed.
- Five-task/14-day calibration review complete.
- Twenty-task paired/live decision review complete.
- Bundle/revise/reject decision recorded.
- Thirty-day post-bundle review complete, if applicable.

Required Jira updates:

- Comment at the Phase 1.5 gate with the pricing date, repository-specific estimate, privacy/terms
  disposition, and local-first decision.
- Comment after each first live run with receipt/report link and outcome.
- Comment at the 5-task/14-day gate with continue/change/stop decision.
- Comment at the 20-task adoption gate with mgrep, compiled-context, and any combined results separated.
- Final comment links the release or rejection record and rollback status.

Jira is the coordination surface; raw experiment data stays in the controlled local receipt store, and sanitized reports live in the repository.

## 15. Definition of done

The program is complete only when:

- The next-viable-task selector has automatically executed each capability that passed its offline
  safety/correctness gate after explicit arming. A capability that fails the gate instead requires
  a documented stop decision and real retained evidence. Managed mgrep must either have a real
  receipt or a documented stop decision at the economics/privacy gate; a simulated run cannot
  satisfy this condition.
- Receipts prove exactly which live and shadow arms ran.
- Privacy, eligibility, snapshot, and concurrency gates are covered by automated tests.
- The offline paired corpus and minimum live sample are complete or a stop condition has been reached and documented.
- Correctness, retrieval quality, context usage, latency, tool calls, cost, reliability, and operational burden are reported.
- A skeptical review has reconciled aggregate claims against sampled raw receipts.
- Rhize has recorded one of four decisions for each capability: bundle, revise and rerun, advanced opt-in only, or reject.
- Any bundled feature is documented, tested, reversible, and owned by `rhize-context-manager` without duplicating existing context layers.
- Any rejected feature is disabled and its remote/local data is purged according to the verified rollback process.
- The Rhize Tools Jira task links the final evidence and decision.

## 16. Immediate implementation sequence

The first implementation session should establish a reviewable Phase 0/1 slice and then
continue to at least one real-provider smoke path before releasing or presenting dogfood
results:

1. Add the schemas and redaction-safe receipt model.
2. Add eligibility, atomic claim, deterministic arm assignment, and test-local provider doubles.
3. Add unit tests proving Arm A/Arm B accounting and unarmed no-op behavior.
4. Add the opt-in setup entries and doctor/status surfaces without authenticating mgrep.
5. Implement a real mgrep or upstream Context Compiler adapter, run its non-destructive
   preflight/smoke path, then run the existing plugin validations and a cold scope/security
   review.
6. Run Phase 1.5 before any Mixedbread signup: add the local provider spike, execute the paired
   offline retrieval cases, and publish the managed-vs-local economics/privacy decision.

The current session may keep the inert mgrep CLI for inspection, but no later session may
authenticate, create a Mixedbread store, or upload source until Phase 1.5 is approved. Context
Compiler work proceeds independently once the shared receipt/provider contracts are stable.

## 17. Source references

- mgrep: <https://www.mgrep.dev/>
- Mixedbread pricing: <https://www.mixedbread.com/pricing>
- Mixedbread Privacy Policy: <https://www.mixedbread.com/pages/privacy>
- Mixedbread Terms: <https://www.mixedbread.com/pages/terms>
- Local comparison candidate: <https://github.com/yoanbernabeu/grepai>
- Context Compiler article: <https://towardsdatascience.com/coding-agents-dont-need-bigger-context-windows-they-need-a-context-compiler/>

The referenced article's Markdown clipping in the Obsidian Vault was reviewed during planning. Published reduction figures are treated as hypotheses to reproduce, not as Rhize performance evidence.
