# Changelog — rhize-context-manager

## 0.30.0 — 2026-09-06

- Add silent native Claude/Codex opportunity, tool and stop measurement hooks with explicit workspace scope, duplicate suppression, private receipts and bounded paired answer workers.
- Enforce both Arm A and Arm B for every measurement assignment, including legacy shadow=false. Failed, interrupted, unavailable and model-mismatched pairs remain incomplete.
- Add a ten-case personal-work gauntlet, subscription-authenticated isolated answer drivers, actual usage normalization and separate host/model/corpus aggregates. No API fallback or production action replay.
- Keep catalog selection observational and experimental: initial real answer cohorts exposed two source misses despite lower model input usage. Correctness gates remain unmet; no default injection or procedural adoption.
- Correct outdated Codex hook documentation; native trust, configured scope and observed health remain distinct activation states.

## 0.29.0 — 2026-09-06

- Add opt-in source-bound topic catalogs and selected expansion to the existing private memory-context store, with revision/digest/authority checks and combined presentation budgets.
- Add adversarial contracts, an executable pinned Arm A/B component comparison, and a staged live evaluation plan. Synthetic results show short-source overhead as well as long-source savings; automatic host use and procedural runtime integration remain gated.

## 0.28.0 — 2026-09-05

- Bridge human-triaged targeted failures through Skill Forge capture and project activation.
- Keep queue entries pending until the actual host loads the new skill and the failure scenario is verified; document backup and rollback.

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-10-06_ Fix Codex multipart browser-comment context recovery: preserve native text concatenation around image captions so prompt hashes validate. Claude newline separation and exact session/time/redaction/snapshot seals remain unchanged; image bytes stay outside label packets and collection source identity is unchanged.
- _2026-10-06_ version bump — 0.43.1 → 0.43.2 (patch); marketplace 2.100.1 → 2.100.2.
- _2026-10-02_ version bump — 0.43.0 → 0.43.1 (patch); marketplace 2.100.0 → 2.100.1.
- _2026-10-02_ version bump — 0.42.1 → 0.43.0 (minor); marketplace 2.99.0 → 2.100.0.
- Fix the published-main adversarial regex timing failure: suffix guards avoid whitespace restarts and overlong-name backtracking while preserving credential match spans and existing timing limits.
- _2026-10-02_ version bump — 0.42.0 → 0.42.1 (patch); marketplace 2.98.2 → 2.98.3.
- _2026-09-30_ version bump — 0.41.0 → 0.42.0 (minor); marketplace 2.97.0 → 2.98.0.
- _2026-09-29_ version bump — 0.40.1 → 0.41.0 (minor); marketplace 2.95.0 → 2.96.0.
- _2026-09-29_ The cross-origin collision report now also reads skills synced from the user's claude.ai account (`~/.claude/skills/synced/<org>_<user>/*/SKILL.md`, shown by hosts as `anthropic-skills:<name>`). They are used for collision detection only and never reach the resolved map, router indexes or the third-party inventory; resolved outputs are byte-identical with or without them. A `syncedSkills` summary and source note are added. `--synced-skills-root` overrides the folder, and `none` disables the scan. On this host the report went from 0 to 5 collisions (`context-compression`, `context-optimization`, `api-design`, `deep-research`, `rhize-content-engine`).
- Add label supersession to `pilot_labels.py`: with an explicit `--supersede` opt-in, a family-derived AI label may be replaced by an explicitly judged one and any AI label by a human label. The replaced record moves to `pilot/v2/taxonomy-labels-superseded/` with its reason and is never deleted; human labels and directly judged AI labels stay immutable, and the default import behavior is unchanged. `report` counts superseded labels.
- Add `pilot_autolabel.py`, the daily AI labeling step: eligible v2 decisions without an explicit-choice label are classified by two independent no-tools annotators (Claude and Codex, subscription CLIs only, environment allowlist, login checked before any call, no API-key fallback) from redacted, hash-matched local transcript context, agreed cases are settled by a Claude reviewer whose identity comes from Claude's own usage report, and the compiled `rhize-ai-taxonomy-annotations-v1` batch is imported with supersession. Annotator packets never carry Arm A/B choices, consultations, Laya scores, existing labels or the routing request. Includes a hard wall deadline, an attempt ledger that skips unchanged settled packets, a run lock, private run directories, and `--no-import`/`--prepare-only` inspection modes.
- Add the public `docs/workflow-taxonomy.md` (category, phase, area, stratum, risk-flag and routing-choice definitions); the labeler embeds it and records its digest. Both modules stay outside the collection source digest.
- _2026-09-29_ Review fixes for `pilot_autolabel.py` (Codex and Claude security reviews of the first build):
  - Redaction: the whole message is redacted before any truncation and a partial token at the cut is trimmed; added Supabase, GitHub fine-grained, Slack (`xoxc`/`xoxd`, webhooks), Google, npm, Vercel, Sanity, Resend (with `_`), `Authorization: Basic`, `sshpass -p` and phone patterns, a key-name-anywhere credential-line rule and a generic 32-plus character mixed-case-and-digit fallback; all patterns are length-bounded (the e-mail and URL patterns were quadratic on long dotted runs).
  - Prior context is user-typed turns only (no assistant prose, sub-agent or compact-summary records), injected boilerplate is detected anywhere in a turn, and the pilot-artifact filter is wider.
  - Codex runs with a private per-call `CODEX_HOME` holding only `auth.json`, so `~/.codex/AGENTS.md` is not sent; a refreshed login is written back atomically and never logged. The Codex tool lockdown now also disables `unified_exec`, `unified_exec_tty`, `view_image`, `code_mode_host`, `plugins`, `remote_plugin`, `tool_suggest`, `js_repl` and `multi_agent_v2` (names verified against the installed CLI); the removed `apply_patch_freeform` flag is dropped.
  - Import and ledger: `import_batch` reports a disposition per record; the ledger mirrors it, skipped imports are counted and make the run incomplete, and the ledger is written when the import fails. New `import-run <runDir>` imports a saved run.
  - Robustness: lone surrogates, malformed answer types per case, lock errors other than a contended lock, a taxonomy size cap with batching on the full prompt, deadline-caused failures kept `not_attempted`, a SIGTERM handler and a failure summary for unexpected errors.
  - Integrity: supersession archives are pending until the replacement commits and only committed ones are counted; the reviewer identity must come from CLI metadata, differ from both annotator models, and never sees annotator rationales.
  - Round 2 (re-reviews): redaction matches on a normalized view (NFKC, zero-width, Unicode whitespace, homoglyphs, decoded escapes) and redacts the original span; the credential key rule handles space-separated names, values on following lines, YAML blocks and natural language; more token shapes, hex and base64 runs, `-u user:pw`, `mysql -p`, URL secret parameters and webhook secrets; messages are cut at 200K before redaction (the trailing-token trim was quadratic and is now linear). Prior context is bounded structurally by the session's first pilot artifact and omitted when no boundary can be proven. The Codex login is opened without symlinks, guarded by a lock and a key-subset check, counted when skipped, stale private homes are swept, and a tool attempt in Codex's output kills the process at the first line. Import-pending ledger rows no longer use attempts; superseded-archive reconciliation compares the whole replacement; `import-run` validates records, duplicates and the reviewer identity before importing.
  - Retry accounting: import outcomes are split into transient (I/O, lock contention, deadline cut-offs: never counted) and deterministic skips (validation-shaped reasons, unknown reasons included: two tries, then the packet is no longer selected and is reported as `deterministicSkipExhausted`); the model-failure cap of three is unchanged.
  - Round 3: credential names match when concatenated or camelCase (`PGPASSWORD`, `dbPassword`, `_authToken`), name/value and tag shapes, tables, netrc, natural-language and container values below a key are redacted and every bound fails closed; only the head of a message is kept. A Codex refresh may not remove or empty anything in the login (only `last_refresh` and known `tokens` names may be added, rotated values are accepted) and a skipped write-back is loud; Codex output that is not JSON or has an unterminated tool line fails closed; a FIFO named `auth.json` cannot hang the run. `import-run` also checks status, `runId`, model names and the run manifest; an oversized case fails alone. The unused transient-skip constants are gone.
  - Round 4 (canary blocker): Codex `error` items (its own warnings, such as the code-mode notice our lockdown triggers) and top-level reconnect `error` events no longer fail a call; they are recorded as `codexWarnings` / `codexTransientErrors`, an error item never supplies the answer, and only `turn.failed` or a missing `turn.completed` fails. Redaction: `pwd=`/`DB_PWD=`, string-aware containers that fail closed and can be opened by the key line, bounded `ENV` scan, YAML block headers with indicators, npm/pnpm `set` variants and `--otp`, `my pass is v`, the arrow, k8s `valueFrom`, path-shaped runs exempt from the entropy-only base64 rule. A Codex refresh may not change `auth_mode`, null out the API-key null, or store non-strings.
  - Round 5: the path check that exempts paths from the base64 rule is a linear scanner instead of a regex that backtracked exponentially (a real kebab-case + ALLCAPS path took about half a second to sanitize, longer names hung the packet build); ALLCAPS words and trailing capitals (`marketA`, `workerV2`, `PanelUI`) now count as path-like while random base64 with `/` still redacts. A Codex turn that completes without a message fails as `codex_answer_missing` and counts toward the failed-call cap; `error` items with keys beyond `id`/`type`/`message` are tool attempts; call records store sanitized, capped output; `pass is`/`pass was` needs a credential context or one ending token (`the first pass is done` is no longer redacted); npm/pnpm/yarn/bun `c set`, `--location`, `-L` and `--global=true` forms are covered. A test now runs every module-level regex over adversarial 5K strings against a time limit.
  - Round 6: `pass is` also redacts glued names (`dbPass`, `db_pass`), more context words and any non-dictionary token; a credential key next to an escaped quote (`{\"password\":\"v\"}` in a curl body or stored JSON) redacts; known token prefixes, JWTs and 64-hex runs glued after `_` (`credentials_AKIA....json`) redact while ordinary snake_case stays clean.
  - Operations: `--no-import`/`--prepare-only` no longer overwrite `latest-summary.json` (they write `latest-inspection.json`); binaries must be absolute and mise shims are refused; the unused `RHIZE_AUTOLABEL_CHILD` marker is gone; run directories are pruned to `--retain-runs`; `schema.json` is private.
- _2026-09-29_ version bump — 0.40.0 → 0.40.1 (patch); marketplace 2.93.1 → 2.93.2.
- _2026-09-29_ Test-only: `test_context_doctor.py` gives probe workers a realistic 5 s deadline. `test_timeout_is_not_run` keeps an explicit 0.2 s deadline. The old 0.2 s default let interpreter startup under load flip the replayed-identity test about one run in three. `context_doctor.py` is unchanged; 15 consecutive runs pass.
- _2026-09-29_ version bump — 0.39.0 → 0.40.0 (minor); marketplace 2.91.4 → 2.92.0.
- _2026-09-29_ `build_local_skill_map.py` reports cross-origin skill-name collisions: bare names, compared case-insensitively, that are shared by skills from more than one origin (a rhize plugin, a third-party plugin, or a local-approved root). Results go to `skill-map.local.json` `nameCollisions` and a `sourceNotes` line, and are printed. They are report-only; no node is renamed or dropped. This follows the MCP Skills extension (SEP-2640) rule that a skill must never silently shadow a same-named skill from another origin.
- _2026-09-28_ version bump — 0.38.0 → 0.39.0 (minor); marketplace 2.89.0 → 2.90.0.
- Add a versioned taxonomy label importer (`pilot_labels.py`) for the workflow pilot: family, phase, areas, risk stratum and routing choice, with `human_adjudicated` or `ai_model_reviewed` basis, batch import of reviewed AI annotations and a private, revocable label policy (human only by default). It sits outside the collection source digest, so live observations stay importable.
- Research now uses taxonomy labels under the label policy, scores only explicitly judged routing choices, keeps the 200-label floor, adds per-route, per-family and risk-level coverage gates, and reports label bases on every output; model-reviewed results are marked exploratory. Legacy human labels are unchanged and never merged with taxonomy labels.
- _2026-09-28_ version bump — 0.37.0 → 0.38.0 (minor); marketplace 2.88.0 → 2.89.0.
- Add opt-in workflow decision measurement with detached local scoring, missing-capture coverage, human review labels, evidence-bound task outcomes and silent exact-turn Stop observations.
- Add bounded recurring research coordination; insufficient labels hold the cycle, failed attempts remain visible, and holdout/promotion remain separate.
- _2026-09-27_ version bump — 0.36.0 → 0.37.0 (minor); marketplace 2.85.0 → 2.86.0.
- _2026-09-25_ version bump — 0.35.0 → 0.36.0 (minor); marketplace 2.81.2 → 2.85.0 across four decision-layer plugins.
- Add opt-in local Laya shadow scoring for bounded skill and workflow candidates, governed graph query metadata, and source-bound context retention. Keep protected anchors, ACLs, deterministic selectors, and decisions authoritative.

- _2026-09-25_ version bump — 0.35.0 → 0.36.0 (minor); marketplace 2.81.2 → 2.82.0.
- _2026-09-24_ version bump — 0.33.1 → 0.35.0 (minor; 0.34.0 reserved for an unreleased held-out study); marketplace 2.80.0 → 2.81.0.
- Add opt-in local Laya shadow relevance scoring after native Context Pack source verification. Rank at most eight metadata-only candidates, retain every deterministic pack entry, and record checkpoint identity, Arm A inclusion, latency and usage in a private receipt.
- Fix workflow host attribution for nested native CLIs: inherited Codex session IDs alone no longer select Codex, conflicting native host signals remain unknown, and checkpoint text names the opportunity ID explicitly.
- _2026-09-19_ version bump — 0.33.0 → 0.33.1 (patch); marketplace 2.76.2 → 2.76.3.
- _2026-09-19_ Add opt-in workflow opportunity/decision capture, run-bound completion evidence, supported metadata-only procedural recall, and declared/approved local skill roots. Pending, unavailable and skipped opportunities remain separate; native activation is opt-in.
- _2026-09-19_ version bump — 0.32.3 → 0.33.0 (minor); marketplace 2.74.0 → 2.75.0.
- _2026-09-19_ version bump — 0.32.2 → 0.32.3 (patch); marketplace 2.73.2 → 2.73.3.
- Correct passive measurement failure handling: nonblocking warnings, bounded private diagnostics, independently observed answer workers and standalone health status replace silent failure suppression. Preserve real A/B capture, model attribution, authorization and budgets; add failure, privacy, lock, killed-worker and capture-recovery regressions.

- _2026-09-19_ version bump — 0.32.1 → 0.32.2 (patch); marketplace 2.73.1 → 2.73.2.
- _2026-09-19_ version bump — 0.32.0 → 0.32.1 (patch); marketplace 2.73.0 → 2.73.1.
- Memory benchmark evidence: session-scoped Claude model provenance, conservative answer eligibility, auth deferral without budget consumption, versioned curated grading and private blind review packets. The controlled pilot runner records pinned repeated A/B trials and empty-evidence controls; shared reporting includes both hosts and actual native arm arrays. These collection changes do not establish a general benefit claim.
- _2026-09-19_ version bump — 0.31.0 → 0.32.0 (minor); marketplace 2.72.2 → 2.73.0.
- Deterministic context doctor with bounded read-only probes, OK/PROBLEM/NOT_RUN outcomes,
  current-run provenance, calculated coverage/deltas, immutable private evidence and rendering.
- Optional Sentry check-in transport for independent missed-run monitoring, plus deliberate
  auth, launch, timeout, replay, malformed-output and killed-parent regression checks.
- Explicit optional coverage owners/deadlines and procedural-memory admission boundaries.

- _2026-09-11_ version bump — 0.30.0 → 0.31.0 (minor); marketplace 2.70.1 → 2.71.0.
- _2026-09-06_ version bump — 0.29.0 → 0.30.0 (minor); marketplace 2.68.0 → 2.69.0.
- _2026-09-06_ version bump — 0.28.0 → 0.29.0 (minor); marketplace 2.67.0 → 2.68.0.
- _2026-09-05_ version bump — 0.27.1 → 0.28.0 (minor); marketplace 2.66.0 → 2.67.0.
- _2026-09-05_ version bump — 0.27.0 → 0.27.1 (patch); marketplace 2.65.0 → 2.65.1.
- _2026-09-04_ version bump — 0.26.0 → 0.27.0 (minor); marketplace 2.63.0 → 2.64.0.
- _2026-09-04_ version bump — 0.25.3 → 0.26.0 (minor); marketplace 2.62.0 → 2.63.0.
- **Inferred router signals for third-party skills** (WP-I,
  `.claude/plans/skill-governance-optimization.md`). `build_local_skill_map.py`
  now infers up to 3 topic/stack tags per installed third-party skill from its
  name+description against `catalog/tags.json`'s vocabulary, and writes them
  into the resolved indexes' `router.signals[skillId]` as half-weight
  `{kind: "tag-inferred", weight: 0.5}` entries (resolved indexes'
  `schemaVersion` bumped to `1.2.0`; the static artifact and schema are
  untouched); every third-party skill also gets an unconditional `name`
  signal, so index membership never depends on inference hitting.
  `route-core.js`'s `routeFromIndex()` now requires at least one full-weight
  (`weight >= 1`) matched signal, so an inferred-only match never qualifies;
  the half weight itself (max `1 + 3 × 0.5 = 2.5` vs. a declared `1 + 2 = 3`)
  is what keeps an inferred-backed match from outranking a declared one. `skill-router.js`, `agent-brief-router.js`,
  `session-disclosure.js`, and `remediation-suggester.js` render a
  third-party skill's three-segment id as `<plugin>:<skill>` via the shared
  `formatSkillRef()` (the old two-segment regex would have kept the
  marketplace segment attached). Only `skill-router.js` prints signal
  labels, and it suffixes an inferred one with `(inferred)`;
  `agent-brief-router.js`'s change is id parsing in `namedSkillsIn` only
  (its `BRIEF_MIN_SCORE` of 4 sits above the 2.5 inferred ceiling, so an
  inferred-backed candidate never becomes one of its suggestions). New `build_local_skill_map.py --report-inferred`
  flag prints a per-skill inferred-tag table without writing anything, for a
  precision review. See `docs/skill-map/edge-semantics.md`'s "Inferred router
  signals for third-party skills".
- `skill-refine.md`'s `review` section and `learn-harvest.md` now document
  that a `target_skill` under any plugin cache or marketplace checkout
  (`~/.claude/plugins/cache/`, `~/.claude/plugins/marketplaces/`,
  `~/.codex/plugins/`) is refused at review — fork/vendor into a Rhize
  plugin (recording the fork + drift check in `SOURCES.md`) or contribute
  upstream instead — and that routing such a signal through `skill-forge
  refine capture` is deferred until its project-scope override files can be
  materialized into a plugin cache.
- _2026-09-03_ version bump — 0.25.2 → 0.25.3 (patch); marketplace 2.60.0 → 2.61.0.
- _2026-09-03_ version bump — 0.25.1 → 0.25.2 (patch); marketplace 2.59.1 → 2.60.0.
- _2026-09-03_ version bump — 0.25.0 → 0.25.1 (patch); marketplace 2.58.1 → 2.58.2.
- `tests/rhize-context-manager/test_harvest_noise_filter.py` — first test
  coverage for `scripts/harvest_noise_filter.py` (30 cases: tokenizer,
  reference-building, all four classification outcomes at their boundaries,
  `--max-blocks` union behavior, default-threshold regression pin).

### Fixed

- Cache model metadata at Stop, including turns without a memory pair, so later prompts can
  retain attribution when startup records obscure the bounded transcript tail. Record completion
  identity separately without rewriting prompt-time identity or answer availability; reject stale
  turn events before updating the active cache, including after unmeasured prompts. Late model
  discovery cannot create a second pair on prompt replay.
- Keep passive native memory-measurement hooks silent and successful when a versioned entrypoint
  is unavailable or fails. This prevents an infrastructure error from being treated as Codex's
  Stop continuation signal; package, version-root transition, and repeated-failure coverage pins
  the behavior.

### Changed

- `build_local_skill_map.py` and `suggestion_log_report.py` now resolve the
  skill-usage monitor's data directory through a shared `skill_monitor_data_dir()`
  helper (mirroring the standalone rhize-skill-monitor tool's own `paths.py`
  precedence: `RHIZE_SKILL_MONITOR_HOME`, else `RHIZE_SKILL_MONITOR_ROOT`/the
  default checkout's `data/`, else `~/.rhize/skill-monitor/data`) instead of the
  old hardcoded `rhize-ops/skill-monitor/data/` path, now that the monitor ships
  as its own repo. `/learn-harvest`'s runbook steps were updated to match.
- `/skill-refine run`'s `evolve` invocation now passes `--backend claude`
  explicitly — it previously fell back to SkillOpt-Sleep's offline `mock`
  backend silently, which is why the pipeline had never actually consumed a
  queue entry via `evolve` (all 30 prior consumptions were manual fold-ins).
  Verified via a direct, capped `skillopt-sleep dry-run --backend claude`
  (6 sessions, 5 mined tasks, baseline 0.29 → candidate 0.63, 4 genuine
  proposed edits) — the wrapper's `--backend` passthrough was confirmed at
  source (`evolve.ts:152`), not executed end-to-end with a real backend, to
  keep the one real-backend run capped and bounded. Requires `skillopt-sleep`
  on PATH (`pipx install skillopt`).
- `/learn-harvest`'s noise filter reference set (both the command and the
  `daily-learn-harvest` scheduled routine) now includes `docs/session-guardrails.md`
  and the invoking project's auto-memory `MEMORY.md` — MEMORY.md was the
  dominant missing reference (headroom's dry-run output echoes existing
  MEMORY.md sections back as apparent new findings). Measured against the
  reference docs alone (queue excluded), adding MEMORY.md moved 21 of 41
  candidates in a real 2026-09-03 batch from "kept" to correctly `suppressed`;
  with the live queue's own 821 reference chunks included (production
  config), the queue already caught most of that overlap, so the incremental
  production delta on that same batch was 1 of 41 — still a real, cost-free
  fix (a missing reference file warns and skips, never errors), and its value
  scales with how sparse a given project's queue history is.
- `headroom learn` calls in both files now pass `--main-only`, bounding each
  run to top-level sessions (no time-bounded lookback exists otherwise, and
  reanalyzed session counts were growing weekday over weekday). Daily cadence
  itself is kept — the weekly `headroom-learn-sweep` task that would have
  provided redundant coverage is currently disabled.

### Governance review corrections (2026-09-05)

- A leading explicit `Use`/`Invoke`/`Run` request can identify a unique name-only skill in both
  router paths. Ambiguous identities abstain; ordinary prompts retain implicit routing rules.
  These remain suggestions, not evidence of actual invocation or task-quality improvements.
