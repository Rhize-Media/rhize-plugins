# Project State

## Verified facts

- 2026-10-10: Laya's daily AI labeler retained a `context_unavailable` warning because a native Codex session transcript had grown to 348 MiB, above its 256 MiB regular-file admission limit. The shared reader candidate raises only that finite ceiling to 512 MiB, retaining streaming and all exact source-binding checks. A boundary regression reproduces the old rejection at 348 MiB and preserves refusal above 512 MiB. Missing enum context and image-caption hash mismatches remain visible; never repair historical capture or normalize mismatched requests to clear a label gate. Source verification and activation of the reviewed private pin remain separate from model labeling or host reload.

- 2026-10-04: The Dev Flow 2.25.7 write gate reproduced a false source classification for new Obsidian `Projects/.../*.md` notes. The candidate detects ordinary Markdown beneath an actual `.obsidian/` directory and shares that decision across write, reconciliation and release checks. Embedded Git/plugin roots, hidden runtime paths, SKILL.md, executable files, MDX and mixed patches retain source checks. Source validation and installed-host activation are separate; this change does not edit the installed cache.

- 2026-10-02: Context coverage 0.43.0 / marketplace 2.100.0 is merged into main/dev (d3f6a703), hosted CI 2,522 passed, five existing skips, 18 subtests. Both native hosts create private pre-decision snapshots and enum context. The Codex activation probe exposed a 15.5-second delay between its hook and transcript publication; exact session/request match was excluded by the pre-capture timestamp condition. The 0.43.1 patch allows publication within the existing 60-second observation tolerance while keeping exact bindings and pre-decision seal checks. Collection source remains e8c40f12; historical 18 accepted AI labels (13 explicit) remain in their frozen source, with actual source-bound export counts reported separately. Patch labeler checks: 135 passed, one existing skip; scoped Context Manager/config suite: 951 passed, three Node-shim HOME failures and three existing skips. The three failures passed unchanged with the configured actual Node binary alongside the labeler module (139 targeted checks passed). Independent cold and native Fable reviews found no blocker. Both private native snapshot bindings validate against real transcripts under the patch. Publication remains pending.

- 2026-10-02: Functionize PR46 CI run37049439805 passed 2,465 tests but failed the existing fake-Codex termination test on an empty PID file. The fixture emitted a forbidden tool event before persisting its PID, allowing correct immediate process termination to interrupt the write. Persist and close the PID before event emission; keep real labeler code, the kill assertion and its timing bound unchanged. The labeler module passes 113 tests with one existing skip; 20 repeated immediate-tool-kill checks pass. Independent and Fable fix reviews have no blocker. Hosted CI rerun is pending.
- 2026-10-02: Native vault access is restored. Independent comparison confirms Context Manager 0.42.1 and Dev Flow 2.25.7 source matches current main; both Functionize wrappers and all 59 scoped eval/test files match reviewed candidate d0d805a. Twelve offline fixture checks and twelve schemas pass. Fable integration review has no blocking finding. Procedural Memory 0.9.0 / marketplace 2.99.0 remains the target; exact-ref vault/release checks, publication and fresh host activation are pending.

- 2026-09-30: Procedural Memory 0.9.0 / marketplace 2.99.0 candidate completes Functionize recipe-review/status dispatch and an explicitly requested documentation-only recipe-stage alias. The Functionize launcher still refuses staging/promotion/execution verbs; the registry launcher preserves existing raw CLI passthrough. Companion runtime `094aaac` enforces latest approval, exact digest, acknowledgements and stage conflicts; wrappers cannot authenticate human identity or intent. No real recipe decisions, registry writes or runtime source changes occurred. Focused source checks: 123 passed, plus two unchanged sandbox-limited tests passed with required access; runtime guard suite: 64 passed in isolated fixtures. Twelve offline eval scaffold/regex checks and 12 native-case schemas pass; new native model evaluations remain unrun.
- 2026-10-02: Ponytail release CI exposed the same regex timing failure already present on published main da11fe0 (run 36757379532); CREDENTIAL_TAIL and NAME_END diagnostic search/finditer repeated whitespace and overlong-name backtracking. Two suffix-start guards retain runtime anchored match spans, whitespace tolerance and existing timing thresholds. All 351 redaction contracts, including the added before/after span regression, pass; no live pilot labeling/import is activated.

- 2026-10-02: Ponytail 4.10.1 (`6c97ffa48710714672214915ad092e3fc6e85516`, MIT) is an optional standalone companion for Claude and Codex. Dev Flow defers its implementation simplicity ladder and scoped complexity lens to upstream; required checks, behavior and release authority remain with Rhize. Both installed load surfaces matched all 36 inspected files; 11 upstream Node hook/command/package tests passed. User chose full default mode. The static load-surface scan returned LOW/CAUTION with one MEDIUM warning for benchmark command text in an SVG; executable hook files were manually inspected. Full-repository scan is CRITICAL and retained separately (development/benchmark files and other host adapters); optional semantic analyzers were unavailable, binary logos were outside static scope, and four components had partial parser coverage (two SVGs, ponytail-runtime.js and ponytail-statusline.sh); the runtime source was manually inspected. No benchmark or other-host adapter is executed in setup. Lesson: the installed Forge safety wrapper expects old top-level risk fields and falsely emits an empty ALLOW against SkillSpector 2.11.2; use raw risk_assessment and analysis_completeness until that separate defect is fixed. Local simplified-english ingestion was reconciled with existing MIT provenance and verified shared host links; no upstream skill content was changed. Native Codex discovery reports all six Ponytail skills enabled and all three hooks trusted; Simplified English is enabled. Required release checks passed: 493 Dev Flow tests, seven impact-map contracts, all 23 static quality eval cases, manifest validation, config lint and generated map/setup freshness. Cold self-review and mapped reconciliation completed. Fresh desktop/session activation and measured Rhize task benefit remain separate from installation evidence.

- 2026-09-29: rhize-ops 0.29.0 / marketplace 2.97.0 (`1672004`, tag `v2.97.0`). delegate-to-teammate Step 2 now also takes Slack clip/huddle context, from a transcript or huddle-notes canvas, via `references/meeting-context-sources.md`. The connected Slack connector's file-read returns clip audio as base64 with no transcript, so audio-only clips are skipped and never guessed. SKILL.md is capped at 28,000 bytes (`test_skill_stays_under_byte_budget`, now 27,537): put new procedure in references. Pushes are gated by the private vault-context pre-push review; update `Plugins/<plugin>.md` + the hub and run `vault-context review` per changed component. Not yet exercised against a real Slack clip transcript.
- 2026-09-29: The collision report (rhize-context-manager 0.41.0) also reads claude.ai-synced account skills (`~/.claude/skills/synced`), for detection only; resolved outputs are unchanged. This host has 5 cross-origin name collisions: `context-compression`, `context-optimization`, `api-design`, `deep-research` and `rhize-content-engine`. They are same-name, different-content skills that hosts keep apart by prefix. Decision: no rename or `extends`.
- 2026-09-29: The daily AI labeling step (`rhize-context-manager/scripts/pilot_autolabel.py`, 0.42.0) exists as code, tests and docs only; it has not run against real models or the live pilot store. It labels eligible v2 decisions that lack an explicit-choice label: hash-matched, redacted transcript context (session UUID digest to `sessionHash`, user-text digest to `promptHash`, at most four prior turns) goes to two independent no-tools annotators (Claude `claude-sonnet-5-5`, Codex `gpt-5.6-sol`), a Claude `claude-fable-5-1` reviewer settles agreed cases, and `pilot_labels.import_batch(..., supersede=True)` imports the result. Supersession replaces a family-derived AI label with an explicitly judged one (or any AI label with a human one), archives the old record under `pilot/v2/taxonomy-labels-superseded/`, and never replaces a human label or a directly judged AI label. Packets carry only the redacted request and prior turns (tests assert a key whitelist and the absence of Arm A/B, consultation, score, label and request-question data). Subscription CLIs only: login checked before any call, allowlisted child environment, no API-key fallback. Both modules sit outside the collection source digest, which is unchanged (26111b6a...). 490 tests pass and 2 skip across tests/rhize-context-manager, tests/project-launcher/test_pilot_cycle_v2.py, tests/typed-decision and tests/config-lint. Not verified: a live run (Codex `gpt-5.6-sol` availability, Claude `--json-schema` reliability on a full batch, and how many transcripts hash-match are unknowns for the first `--no-import` run); scheduling, the private wrapper and the Codex automation prompt remain operator work. Lesson: `tests/rhize-devflow/test_skylos_evidence.py` had two timing failures (`process_cleanup_unavailable`) inside a full `bump_version.py --check` run that pass in isolation (43 passed).

- 2026-09-29, labeler review fixes (still code, tests and docs only; no live run, import or install): the two independent reviews of the first build were addressed in a second commit on `claude/laya-autolabel`. Redaction now covers the whole message before truncation with the missing token families, a key-name-anywhere line rule and a generic long-key fallback (all length-bounded, tested on a 26 KB dotted run); prior context is user-typed turns only; Codex runs in a private per-call `CODEX_HOME` holding only `auth.json` (refreshed login written back atomically, never logged; measured 33,747 vs 415 characters of user context with `codex debug prompt-input`, the `$HOME/.agents/skills` catalog of about 15K characters remains); the Codex feature lockdown was re-verified against `codex features list` (0.158.0), where `unified_exec` still prints as enabled under an override so only the canary can prove it; the ledger mirrors per-record import dispositions, `import-run <runDir>` settles a saved run, the reviewer needs `native_model_usage` identity and a model distinct from both annotators, supersession archives commit only after the replacement, and inspection runs no longer overwrite `latest-summary.json`. Round 4 (2026-09-29, canary): the live canary showed Claude working and every Codex call killed as a tool attempt because Codex reports its own warnings (the code-mode notice our lockdown triggers, reconnects, transport fallbacks) as `error` items and events; those are now recorded, not fatal. Also `pwd=`, fail-closed string-aware containers, YAML block indicators, npm variants and path-safe entropy redaction, and stricter login pins. Round 3 (2026-09-29): credential names match when concatenated (`PGPASSWORD`, `_authToken`), redaction bounds fail closed, a Codex refresh may never remove or empty login fields (loud warning on a skip), Codex output must be JSON, `import-run` checks the run manifest, and a deterministic import skip is capped at two retries. Round 2 (2026-09-29, after the two re-reviews): redaction normalizes before matching (zero-width, NFKC, homoglyphs, escapes) and covers many more shapes; prior context is bounded by the session's first pilot artifact and omitted when unprovable; the Codex login is locked, symlink-safe and key-checked and a tool attempt is killed at its first stdout line; import-pending ledger rows no longer use attempts. Round 5 (2026-09-30): the path check behind the base64 rule was an exponentially backtracking regex (`sanitize` of `docs/archive/error-lifecycle-management-ARCHITECTURE-PROPOSAL` took 0.48 s, `fullmatch('a'*24+'A')` 1.3 s and doubling per character, and it runs during packet build while the run lock is held); it is now a linear scanner (same path sanitizes in 0.1 ms, a 200K line in 0.16 s), a test runs every module-level regex over adversarial 5K strings, and random base64 with `/` still redacts (residual about 1 in 20,000 blobs parses as words). A completed Codex turn with no message is `codex_answer_missing` (counted toward the failed-call cap); stored call output is sanitized and capped. Still open: the single live canary through both CLIs (Jim approved; add a tool-inducing case and an input-token check), then release, repin, `--prepare-only`, `--no-import`, import and launchd.

- 2026-09-29, MCP follow-ups (marketplace 2.95.0, rebased on procedural-memory 0.8.0 / 2.93.0):
  - **Codex and bundled MCP servers:** Codex (CLI 0.158.0) loads a plugin's `.mcp.json` but never expands `${CLAUDE_PLUGIN_ROOT}` or any `${...}` variable. It passes only `HOME`/`PATH`/`USER` to MCP children, and a `config.toml` server of the same name shadows the plugin's. Plugins that bundle servers therefore carry an inline `mcpServers` entry in `.codex-plugin/plugin.json` (`./scripts/…`, `cwd: "."`). `tests/config-lint/test_codex_mcp_parity.py` enforces parity, and also that a Codex-catalog plugin with `.mcp.json` ships a Codex manifest. obsidian-second-brain 1.7.7 and seo-aeo-geo 1.6.0 (a new Codex manifest) are fixed.
  - **Visual-plan viewer:** it runs through `viewer/bin/launch.mjs` (project-launcher 1.12.0), which uses a content-addressed `npm ci` cache under `~/.cache/rhize-plan-viewer/` with a committed lockfile and never writes into the skill.
  - **Refactor gate:** Dev Flow 2.25.5 exempts prose under `.claude/analyses/`.
  - **context-doctor test:** it uses realistic worker deadlines.
  - **Lessons:**
    - `git add <dir>` before `build_skill_map.py` stages those files into whichever commit comes next. Commit per plugin with explicit pathspecs, and check each commit with `git show --stat`.
    - Rebase onto a fresh `origin/main` before running `bump_version.py`: a concurrent release took marketplace 2.93.0 first, and bumping on the stale base produced a colliding version chain.

- 2026-09-29, MCP Tier 1 hardening, following the MCP Skills extension (SEP-2640) and the 2026-07-28 stateless revision:
  - **Skill map:** static skill nodes carry `treeHash`, `fileCount` and `totalBytes` over git-tracked files. `--check-stale` now fails on any tracked skill-file edit (`references/`, `scripts/`, `templates/`) until the map is rebuilt. `validate_skill_map.py` fails skills above 512 files or 16 MiB.
  - **obsidian-mcp-server:** 3.0.0 (2026-04-29) renamed its tools, and the unpinned `npx` had left the vault commands naming tools that did not exist. It is now pinned at 3.6.0 with the 3.x names; `tests/obsidian-second-brain/test_mcp_tool_names.py` checks them against a recorded `tools/list`, which must be re-recorded on any pin bump. dataforseo-mcp-server is pinned at 3.1.1. `tests/config-lint/test_mcp_npx_pins.py` rejects unpinned `npx` servers.
  - **rhize-bridge:** stays a legacy MCP server. It answers 2025-11-25 for an unknown `initialize` version and `-32601` to `server/discover`, a non-modern error so dual-era clients fall back. Hosts get this only after a bridge reinstall.
  - **Name collisions:** `build_local_skill_map.py` reports cross-origin skill-name collisions. On this host it cannot see skills synced from claude.ai.
  - **Visual-plan:** the viewer is installed from a checkout only. Installed copies are 37 files; the 433 MB `node_modules` exists only in a dev checkout.
  - **Lessons:**
    - On a branch whose last commit bumped a version, `bump_version.py --check` with its default base proves nothing: the base is the last `marketplace.json` commit, which is HEAD. Run `--check --since origin/main`. CI passes `BASE_REF`, so CI is unaffected.
    - Local `validate_skill_map.py` uses the stdlib fallback when `jsonschema` is missing, so schema `pattern`/`minimum` constraints are enforced only where jsonschema is installed (CI).
    - A skill directory with a SKILL.md but no git-tracked files is now a `BuildError` ("`git add` the skill"). It used to silently produce `fileCount` 0.
    - Never pipe a gating test run through `tail` inside an `&&` chain without `set -o pipefail`. A failing run committed that way on this branch and had to be amended.

- 2026-09-28: The Dev Flow refactor-evidence gate (2.25.3) resolves the release target from the command itself — a single leading `cd <dir>`, `git -C`, `--work-tree=` or `--git-dir=` — and repo-roots it, so a commit or push into another repository is judged against that repository's receipt instead of the session cwd's. Ambiguous shapes (a later `cd`, subshells, `pushd`, shell variables or substitutions in the path) and non-Git targets keep the cwd behavior, so the gate is never loosened.
- 2026-09-28: Versioned taxonomy labels (`rhize-context-manager/scripts/pilot_labels.py`) import family/phase/areas/risk/choice labels with `human_adjudicated` or `ai_model_reviewed` basis into `pilot/v2/taxonomy-labels`, outside the collection source digest (unchanged by this change). A private, revocable label policy (default human only) decides which bases research uses. The cycle keeps the 200 floor, scores only explicitly judged routing choices, adds per-route (>=15), family (>=4 at >=15) and risk (>=20 elevated/critical) gates, and marks results that include model-reviewed labels exploratory. Family-derived choices count for coverage only.
- Final v2 source verification (2026-09-28): 1,838 repository tests and 18 subtests passed, with five existing skips. All 12 native manifest validations, configuration lint, Dev Flow doctor, skill-map/setup freshness, render idempotence and the 468-test release contract passed. Three isolated implementation lanes and independent Claude Fable 5.1 plan/final reviews identified and corrected failure-classification, binding, subprocess and research-identity issues. Source approval does not establish native activation or task benefit. Private operator tests separately cover snapshot recovery and timeout cleanup.

- 2026-09-28: Workflow pilot v2 separates eligible new/changed tasks from operational events, missing context and held captures. B receives an immutable enum-only request before Arm A consultation; consultation and catalog no-match are recorded separately. Continuations inherit validated context without rescoring. The check wrapper records actual Arm A process evidence while preserving unknown task acceptance and agent usage. Private operator reports v1 and v2 separately; original cohorts and failed experiments are retained.
- V2 development research shares the live routing decoder, requires at least 200 human-adjudicated cases and explicit diversity coverage, and keeps connected session/task/input identities in immutable splits. Missing legacy holdout membership holds research without opening locked cases. Human adjudication, native activation and causal task benefit remain separate from source readiness.

- 2026-09-27: Context-document gate repair reproduces the rejected `.planning/STATE.md` patch and expands the shared prose classifier to `.planning/`, `docs/`, and standard nested context Markdown filenames. Source code, MDX, and mixed source/context edits remain gated. Baseline regression: 17 failures / 13 passes; repaired focused suite: 66 passes. The initial sandboxed Devflow run had 466 passes and the previously observed `process_cleanup_unavailable` subprocess-cleanup failure; the unchanged test passes outside the sandbox. Full suite outside the sandbox: 1,671 passed, 5 existing skips, 18 subtests passed. All eleven plugin manifests, marketplace, configuration lint, generated skill-map/setup freshness, idempotent documentation rendering, and Devflow doctor passed. Cold self-review checked shared write/reconciliation/release consumers and preserved hook approval configuration. Reconciliation uses an explicit rg fallback in the isolated worktree, which has no CodeGraph index. Release: Devflow 2.25.2 / marketplace 2.86.1; the host must load the updated plugin before native-hook behavior changes.

- 2026-09-27: Workflow decision measurement pilot adds opt-in background inference bound to the existing opportunity, visible missing-capture denominators, a deterministic review queue, source-bound human labels/task outcomes and a bounded research coordinator. Stop is observational only; it cannot establish acceptance. Empty allowlisted task signals abstain instead of sending an uninformative request. The coordinator preserves failed attempts and never runs holdout or promotes a candidate. Real human labels and causal task-benefit evidence remain outstanding.


- 2026-09-25: A Codex marketplace upgrade of the released decision-layer source failed because the tracked Codex catalog declared `rhize-media` and listed only Outreach while the existing configured marketplace is `rhize-plugins`. The catalog repair aligns its name and all 11 published plugin paths with the Claude marketplace; the parity test guards this host activation path.

- 2026-09-25: The local Laya decision-layer source now includes bounded shadow candidates for
  skill/workflow fit, governed graph relevance, protected context retention, Dev Flow tool-risk
  and browser QA, authorized model/worker fit, and the existing project-local GSD checkpoints.
  The focused changed-path suite passed 77 Python cases and 11 router cases; a full plugin run
  passed 1,605 cases with 5 skipped and one unrelated process-cleanup timing failure that passed
  alone. Candidate scores leave incumbent decisions and hard gates in force. The private task
  trial ledger reserves duplicate controls under the 1,000,000-token ceiling, validates a
  frozen outcome rubric, and reports only complete matched pairs as evaluable; it cannot enforce
  a host runtime limit. There are no adjudicated real labels, paired accepted-task outcomes, or
  newly scaffolded project receipts yet, so benefit and active promotion remain unproven.

- 2026-09-24: Updating Project Launcher to 1.10.0 during an already-running Codex task left that task's edit hook pointing to removed cache version 1.9.1; `apply_patch` failed before any source edit. The prepared Dev Flow gate and shell edit path worked in the isolated worktree. Start a fresh task after plugin updates to reload hook paths; do not treat installed version metadata as proof that a running task reloaded its hooks.

- 2026-09-24: A disposable 26-file Git fixture produced a source-bound native Context Pack with two entries; the opt-in local Laya shadow scored both and recorded the routed `typed-decisions` checkpoint without altering pack inclusion. A synthetic Dev Flow `check` call recorded four bounded Noul scores and a `verify` candidate bound to the current evidence file hash. This is functional integration only; Laya checkpoint confidence and Rhize task benefit remain unmeasured.

- 2026-09-24: Laya 0.3.20's Jev-compatible server ignores unknown Jev model IDs and
  routes to a base checkpoint. Project Launcher 1.9.1 omits a forced model on local
  calls unless `TYPESAFE_DEFAULT_MODEL` is set; hosted Jev retains `jev-latest`.
  New clients default to shadow because Laya's published generic benchmarks do not
  validate Rhize software-development decisions. A synthetic probe establishes
  connectivity/schema only; evaluate a pinned checkpoint before advisory use.

- 2026-09-24: Devflow 2.23.0 adds a per-invocation `required` prompt-hook policy for an explicit
  implementation task kind while leaving the installed hook on `auto`. The off study condition is
  physical plugin omission, not a runtime gate disable. A frozen 48-prompt product-contract corpus
  checks both Claude and Codex payload shapes, source-bound lifecycle events, prompt hashing, and
  completion parity without provider calls.
- 2026-09-24: the 2.23.1 progressive-disclosure candidate reduces the always-loaded impact-map
  command from 1,606 to 494 words. Deterministic checks retain CodeGraph preflight/fallback, every
  required semantic-map section, prepare/reconcile/dismiss commands, and all reconciliation
  verdicts; detailed examples and troubleshooting remain in an on-demand reference.

- Workflow host attribution now rejects inherited-session-only identity and retains conflicting native signals as unknown. Cross-host canaries must isolate host/session environment markers; historical mislabeled receipts are preserved.

- 2026-09-19: workflow discovery repair adds the canonical RHIZE Content Engine skill,
  declared/approved-root inventory and inert procedural metadata. The opt-in checkpoint creates
  pending opportunities; the task agent records scope, run and source identity before composition.
  Recommendation, decision, execution, validation and capture are distinct. Completion ordering
  remains operator-reported; benchmark evidence lives outside this repository.

- 2026-09-19: paired-measurement commands in `rhize-context-manager/hooks/hooks.json` resolve
  through `${CLAUDE_PLUGIN_ROOT}`. Codex documents this compatibility variable and a versioned
  marketplace cache; source does not embed a specific cache version.
- The checked-out 0.32.0 package and local Codex cache copies at 0.31.0 and 0.32.0 contain the tool
  and Stop entrypoints. Current cache contents do not prove what was present when the failure
  occurred.
- Codex's current user config enables `rhize-context-manager`; it has no `installed_plugins.json`
  registry here. The exact plugin root loaded by the historical task is not recoverable from current
  state.
- A Python missing-file error exits nonzero with stderr. Codex treats a Stop hook's exit code 2 plus
  stderr as a continuation request. Release 0.32.1 suppressed these failures. The corrective release retains exit zero while
  emitting a bounded warning and persisting private diagnostic state.

## General rules

- Benchmark control arms for a safety/workflow plugin should omit the plugin entirely. Do not add
  an `off` branch to a safety gate merely to model the control; it still exposes treatment assets
  and creates a bypass surface.

- Keep private benchmark findings, raw research results and article evidence in the operator's
  consolidated vault. Repository evaluation code, fixtures and versioned validation contracts
  remain with their implementation; machine-local output routes must preserve this boundary.
- Relocating evidence requires source/destination hash verification and a reversible archive.
  Preserve historical receipts unchanged and record their path mapping separately.
- Passive paired-measurement hooks must not block, continue, or alter user work when capture is
  unavailable. Preserve A/B, privacy, scope, authorization, and hook-trust gates.
- Do not mutate the global Codex config or installed cache to repair a version-root issue without
  evidence and a reversible verification plan.

## Open failures

- 2026-10-10: The Dev Flow test-evidence release gate cannot support Python regression evidence in this repository: `test_evidence.py run` exits 2 with `package.json does not exist`; its current runner also has no trusted execution adapter. Actual pytest results and read-only exact transcript recovery remain separate evidence. The transcript-limit patch stays a local candidate; do not manufacture a package manifest, hand-edit a supported packet, or change the pinned runtime to bypass the gate.

- The historical 0.31.0 file absence is not reproducible from current cache state. A source packaging
  omission and wrong compatibility variable are not supported by current evidence; a transiently
  incomplete or removed task-pinned cache root remains possible, but Codex's historical update
  lifecycle evidence is unavailable.
- Native review was completed for the previously presented workflow-selection hook. The local
  opt-in configuration is now present, and a synthetic smoke of the installed Context Manager
  0.36.0 hook emitted the expected checkpoint. Trust status for any later hook digest still needs
  verification in a fresh host session.

## Lessons learned

- Vault prose cannot be recognized from software-repository folder prefixes alone. Use a filesystem vault marker with project/runtime boundaries, and exercise the same classification in write, reconciliation and release paths.

- Native eval scaffolds must require explicit fixture mode and refuse pre-existing or symlinked write targets before any write. Grade staging separately from checks, and bound regex lookaheads to the current command so valid chained operations are not penalized.
- Use this repository's Python environment for plugin tests; the companion runtime virtualenv lacks PyYAML and makes unrelated skill-map parsing checks fail. Distinguish a wrapper's documented authorization policy from runtime technical enforcement, and preserve raw passthrough when it was already part of the contract.
- A new skill must update both the generated inventory and central evaluation catalogs/coverage.
  The core and ops compatibility copies remain byte-identical. Release CI caught this omission.
- Preserve the pinned incumbent memory core byte-for-byte. Procedural metadata preview extends it
  only through an opt-in assembler; changing a source hash is not permission to repin Arm A.

- Keyword classification failed negated destinations and quoted instructions in two frozen
  diagnostic sets. Use the current task agent's full conversation context for workflow choice;
  capture pending/skipped/unavailable outcomes rather than adding unbounded routing rules.
- The Dev Flow prompt gate repeatedly interrupted work when a complete impact map existed but its
  separate `prepare` call was missed. The repair auto-prepares only one recent complete map bound
  to the exact prompt receipt ID and discovery query; ambiguity, stale metadata or invalid sections
  remain blocked.
- A selection receipt is not proof of workflow execution. Keep run/source bindings, latest stage
  status and separate decided/selected counters; preserve failed experiments and missing data.

- An infrastructure failure on Codex Stop differs from a normal silent hook skip: stderr plus exit 2
  is interpreted as a request to continue the agent. Non-blocking telemetry hooks must protect the
  process boundary as well as catch errors inside the script.
- Marketplace version bumps must be followed by `scripts/render_skill_map_docs.py`; the full-suite
  idempotence check catches stale generated README version tables even when skill inventories do
  not change.

## Last session

- 2026-10-10: Diagnosed the daily labeler warning as a 348 MiB regular transcript excluded by the 256 MiB ceiling. The minimal 512 MiB candidate preserves all binding checks, passes 139 reader tests (one existing skip), and verifies the original immutable request in 1.608 seconds without labeling/importing it. Independent review found no code blocker but requires supported test-evidence; the current runner is unavailable for this repository. Missing enum captures and image/referent mismatches remain deferred. No model labeler, holdout, promotion, historical runtime change or native-cache reload occurred. Publication and current-runtime pin remain held.

- 2026-10-06: Codex native multipart prompt text concatenates captions without separators; the AI-label transcript reader inserted newlines and rejected exact immutable snapshot hashes. Context Manager 0.43.2 / marketplace 2.100.3 preserves native concatenation for Codex and Claude newline separation. Synthetic native regressions fail before the repair and pass after (137 passed, one existing skip); the wider source-binding/configuration suite passes 992 with two existing skips. The 534-test release contract, seven impact-map contracts and generated map/setup/config checks pass against published Dev Flow 2.25.8. Independent native Claude Fable 5.1 review found no blocker; cold coordinator review verified the only transcript consumer discards assistant turns, no alternate Codex reader exists here, and private actual snapshots supply host parity evidence beyond the synthetic fixture. Native capture/hook source, collection digest, host trust and Arm A authority are unchanged; the reader and importer stay outside the collection digest. Labels are AI-reviewed silver data, not human acceptance or task-benefit evidence. Publication and final operator repin are pending.

- 2026-10-04 Obsidian-note gate fix: reproduced the source-gate rejection for both native writes and Codex Add File patches. All 138 focused gate tests and the full 533-test Dev Flow release suite pass; config tests pass 91 with two existing skips. Manifest validation, doctor, map/setup freshness and config lint pass. Cold self-review found no blocking scope or boundary issue; no independent agent ran because this side conversation forbids delegation. The 2.25.8 candidate leaves the active 2.25.7 installation untouched to avoid disrupting the main thread. Passive workflow measurement could not write its protected receipt; that does not alter test results.

- 2026-09-30 Functionize lifecycle candidate: wrappers, public documentation, discovery metadata, synthetic native cases and generated source inventory are prepared on `codex/functionize-plugin-completion`. Independent review found no blocking implementation findings. Full source validation: 2,453 passed, five existing skips and 18 subtests; seven unchanged Node checks passed after bypassing the version-manager shim with the installed binary (no host trust changes). The 492-test release contract passes before commit; commit-bound verification follows the candidate commit. Fable findings on scaffold target safety and grader false positives are addressed; final targeted verification follows. Publication and installed-host activation are not complete. Arm A remains authoritative; Laya Arm B remains shadow-only.
- 2026-09-24 Devflow Harbor v2 source candidates: T1 and T2 were built as separate commits in an
  isolated worktree. Provider-free routing/lifecycle and full Devflow validation passed. No Harbor,
  Docker, provider, installed-cache, automation, vault, or benchmark-output mutation occurred.

- 2026-09-19 workflow repair: Context Manager 0.33.0 and Procedural Memory plugin 0.6.0 source
  prepared. Independent read-only review found no remaining blockers after counter/router review.
  Runtime metadata/staging and local graph are a separate runtime change. Broad hook activation,
  native trust and graph approval remain separate; no frozen Harbor treatment was changed.

- 2026-09-19: verified no other reachable branch or shared checkout contained a fix, added a
  fail-silent process boundary to all four native paired-measurement events, and added isolated
  version-root and repeated-Stop regression coverage. The 120 Context Manager tests and 362 Dev
  Flow release tests pass. Version 0.32.1 is prepared but not installed in Codex; active tasks must
  reload and the changed hook definition must be reviewed/trusted by the host.

## Benchmark capture follow-through — 2026-09-19

- Model metadata may first become visible near the transcript tail at Stop. Capture now persists
  that bounded, matching-session observation even without a pending pair. Later prompts may use
  the session cache; existing receipt model/answer-status fields remain unchanged.
- A clean native smoke must use an explicit stdin boundary. A Python heredoc inherited by a
  Claude subprocess contaminated the smoke prompt; this was not host-added action guidance.
  Controlled answer drivers already use explicit stdin PIPE and were unaffected.
- The expanded exploratory memory screen completed 180 calls across both hosts, with frozen
  source snapshots preserved before this patch. Synthetic transport completion and term checks
  are separate from semantic review and do not establish general benefit.
- Cold source review checked stale-turn handling, no-pair persistence, scope, bounded transcript
  reads and immutable prompt-time evidence. Focused regressions cover each boundary. Version
  0.32.2 follows the separately merged 0.32.1 hook-containment release; installation and observed
  native activation are verified separately from source checks.

- Independent model review found delayed-Stop and replay-counting edge cases in the initial patch.
  Explicit turn bindings now survive unmeasured prompts, while late-resolved model identity is
  excluded from pair identity. Regressions pin both cases and mixed prompt/Stop turn-id presence.
  Hosts that omit explicit turn identifiers cannot supply a reliable stale-event comparison.

## Passive measurement corrective release — 2026-09-19

- Verified the four passive hooks still suppressed missing entrypoint and runner failures on base
  5788492, after the separate 0.32.2 attribution fix. No historical cache cause was established.
- Claude Code Fable (native observed claude-fable-5-1) reviewed the full private plan before source
  implementation. Incorporated flock/fd inheritance, detached stdio, dead-worker lock probes,
  superseded-install eviction, quiet oversized-payload handling and atomic warning deduplication.
- New stdlib runtime separates foreground and worker diagnostics from actual A/B completeness.
  Missing/corrupt diagnostic storage remains unavailable, never healthy; runtime recovery cannot
  reconstruct lost measurements. No existing capture/attribution engine or budget was rewritten.
- Baseline: 214 focused tests passed. Corrected full suite: 1,461 passed, 5 skipped and 18
  subtests passed; Dev Flow release suite: 362 passed. Marketplace/all ten plugin manifests,
  configuration lint, map freshness, setup-artifact freshness and doc idempotence passed.
  Packaged failure/recovery exercises do not establish native-host activation.
- Full-suite concurrency testing reproduced macOS ENOENT during simultaneous O_CREAT|O_NOFOLLOW
  lock creation. Exclusive creation followed by no-create reopening preserves no-follow safety;
  25 repeated concurrent first-create/dedup cycles passed. Process-inspection and Git-hardlink
  tests require execution outside the restricted sandbox; both pass with required access.
- General rule: passive measurements may let user work continue, but failure must remain observable.
  A worker that retains a host pipe can block the host despite start_new_session; disconnect all
  stdio and validate the inherited lock. A/B receipt completeness is separate from runtime health.

- Fable implementation review found no security/data-integrity blocker; its minor warning-cadence
  correction, active-worker eviction protection, long-running status advisory and detached fixture
  cleanup were incorporated. Runner success returns0 and resolved installation identity match
  were verified directly. No new worker watchdog can orphan separate native process groups.

## Skylos advisory integration — 2026-09-19

- Devflow can consume an explicitly provided, source/base/policy-bound Skylos 4.38.0 report.
  Scanner execution is optional and isolated on macOS with a dedicated runtime; no automatic
  installation, hooks, uploads, source execution or cleanup is added. Context Pack remains WATCH.
- The approved inert sentinel verified selected-source reads, unrelated-content denial, denied
  source writes/networking, scratch writes and unchanged source. Serial scanning avoids IPC
  permissions; direct Command Line Tools Git avoids Apple's launcher shim in the sandbox.
- All 13 real fixture pairs ran. Seven Arm B cases had findings, four were incomplete and two had
  no findings. Strict rule/location matching detected 5/9 targets; two expectation mismatches and
  two missing-test-impact targets remain explicit in evals/skylos/RESULTS.md. No task-benefit claim.
- The 407-test Devflow suite passed. Independent implementation review passed after fixing malformed
  input handling, failed/missing coverage, non-Python behavior gaps and read-only Git boundaries.
- General rule: schema/digest acceptance is consistency and freshness, never an execution
  attestation. Static findings cannot prove regression coverage or approve release. Required
  checks must complete; non-applicable language checks must be explicit.
- Runtime support is initially macOS/Apple Command Line Tools. Other hosts fail closed.
  The existing test-evidence runner still reports execution_unavailable.
- Final merged-tree validation: 1,507 tests passed, 5 skipped and 18 subtests passed. All ten plugin
  manifests, marketplace, configuration lint, skill-map/setup freshness and doctor passed. Tests
  using temporary HOME must use the real Node binary rather than the mise shim.

## Local Laya and typed-decision research — 2026-09-24

- Laya 0.3.20 imports and serves on loopback on Apple MPS outside the restricted tool sandbox. A real
  `typed-decisions` request routes to `convaiinnovations/laya/typed-decisions`; the generic response
  `model` is `laya-rl-agent` and does not identify the checkpoint. The shipped checkpoint emitted an
  invalid-temperature warning on first load, so confidence is not yet calibrated for Rhize tasks.
- Laya requires a nonempty `instructions` field on every typed question. The old synthetic Project
  Launcher probe returned HTTP 422 without it. The corrected project-local copy passed a live
  synthetic probe and the GSD verifier multi-check contract, both in shadow mode.
- Karpathy autoresearch's original training code needs NVIDIA CUDA. The local Rhize research runner
  applies its fixed-evaluator and keep/discard method to Laya checkpoint, question and threshold
  candidates. Its `prepare` phase physically separates train, validation and holdout files; candidate
  search does not receive a holdout path. A four-case synthetic run verified search and one-time
  holdout mechanics only; no real benchmark labels or software-task benefit exist yet.
- Foreman-style GSD checks produce a deterministic observational directive and numeric assessment
  receipts. They do not steer, stop, retry, finish or approve a worker. Graph relevance, Dev Flow
  lifecycle supervision, calibration, and matched task-benefit trials remain open workstreams.

## Rhize Outreach plugin — 2026-09-21 (RT-180)

- Added the internal `rhize-outreach` plugin as the control/distribution layer for the separate runtime. Claude and Codex manifests expose setup, doctor, campaign, business review/manual entry, package review, email review and delivery reconciliation skills.
- The seven-stage loopback wizard installs pinned runtime commit `5104082e2e17ac8663a20f165e6247485927e4cc`, keeps non-secret settings in Application Support and writes entered credentials only to macOS Keychain. Gmail/GHL default to draft-only; Vercel defaults disabled.
- Setup verifies runtime/template compatibility and can run the redacted runtime doctor plus exact workflow-skill resolver without discovery, provider writes, publishing or sending. Generated Tom handoff files contain variable names and local-entry instructions, never secret values.
- Focused evidence: Plugin Creator validation passes; offline evaluation 12/12, plugin tests 4/4 and setup-manifest tests 36/36 pass. The complete repository suite passes 1,538 tests with 5 skipped and 18 subtests. Generated skill-map/catalog/docs include the new plugin and outreach/prospecting/PostgreSQL/Supabase tags.
- No production Supabase deployment, data cutover, provider call, public deployment, email draft creation or send occurred. Shared-repository migration and live connector execution remain later reviewed slices.


## Jev/Laya Project Launcher decision path — 2026-09-24

- Verified against a disposable local install of `get-shit-done-cc@1.42.3`: Claude Code
  exposes `/gsd-autonomous`, and `gsd-sdk query agent-skills` loads the project-local
  typed-decision skill for `gsd-planner`, `gsd-executor`, and `gsd-verifier`. The older
  `/gsd:autonomous` handoff text was stale for this host.
- Project Launcher installs a Jev-compatible standard-library client, merges GSD
  `agent_skills`, and adds agent-scoped start/stop hooks. The stop hook checks an agent's
  own receipt; a synthetic probe and status check gate the ready claim. Provider
  unavailability is explicit, and no hosted call with real project content has run.
- Focused tests use a local fake `/v1/systemone` server. These prove wire validation,
  config preservation, malformed-response fallback, privacy-safe receipts, and per-agent
  receipt matching, but do not establish Jev/Laya accuracy or task efficiency gains.
- The full nine-workstream implementation and Arm A/B benchmark ladder remain in the
  vault plan. Duplicate coding-agent control runs have a hard 1,000,000-token ceiling;
  no such run has been spent yet.


## Rhize Outreach graph installer — 2026-09-24

- The selected-business graph runtime is pinned to `c8778dda0bba65380bee5d8a7bf99e214a8b22fa`. It runs locally through Codex CLI and stops for human package and email review. It does not send email or publish pages.
- Marketplace Outreach setup is a token-protected loopback wizard for local prerequisites, storage location and explicit pinned install. Config is path-only. Legacy credential-collecting setup code was removed.
- The current plugin has no GHL/Gmail, shared Supabase, Resend or Vercel adapter. Background website generation cannot execute the UI/UX Pro Max CLI or browser-rendered visual QA; the run receipt must keep those limitations explicit.
- After upstream marketplace 2.81.0 shipped, rebased the Outreach candidate onto that release so Dev Flow 2.24.0 and Context Manager 0.35.0 remain intact. Candidate versions: marketplace 2.81.2, Outreach 0.2.0, core 1.0.6, ops 0.25.2.
- Post-rebase checks: setup wizard 5/5, focused plugin/core setup tests 19/19, outreach eval 5/5, Dev Flow tests 427 passed, plugin config and skill-map checks passed, and setup-artifact freshness passed. The coordinated version check reports no pending release-contract errors.
- Plugin commit `661172e9b3d4734f5edc260c293878fe9029f7ac` is published on marketplace `main` and tag `v2.81.2`; the feature branch is also pushed. Runtime commit `c8778dda0bba65380bee5d8a7bf99e214a8b22fa` remains a pinned separate source branch. A fresh-machine install and external delivery have not been run.

## CI hardening — September 27, 2026

- Local CI changes consolidate PR version validation into the static release-contract job,
  restrict push validation to main, and keep executable instruction/reference Markdown in
  scope while skipping narrative docs. Pure validation cancels superseded runs; marketplace
  tag publication retains serialization without cancellation. No runtime, hook, manifest or
  plugin version changed.
- Actions resolve to verified commit SHAs; Python test packages and Claude 2.1.278 are pinned
  and cached. The npm validator wrapper requires its explicit install.cjs binary-copy step;
  `npm ci --ignore-scripts` alone leaves its executable unavailable. Static manifest validation
  needs no model login or provider call. Existing Dependabot cooldown is retained.
- Actionlint, all twelve static manifest checks, configuration lint, doctor, skill/setup
  freshness and render idempotence passed locally. Three focused CI contract tests passed.
  Full repository suite passed: 1,639 tests, five pre-existing skips and 18 subtests (334.96s).
  Version contract passed its 435-test suite (166.40s). The initial sandbox-denied process
  cleanup retry passed unchanged with required permissions. Hosted green and docs-only no-run
  evidence remain the publishing coordinator's acceptance gates.

2026-09-27 CI review correction: stateful tag/OIDC publishers explicitly use queue:max with cancellation off. This preserves up to100 pending runs; default concurrency retains only one pending run. Pure CI cancellation stays enabled. No release/tag was triggered to test publication.


## Workflow context coverage — October 2, 2026

- Fresh v2 request snapshots are redacted before persistence and immutable before consultation.
  Explicit earlier same-session user-request links enrich label context without changing ancestry.
- Background observer classification requires positive launcher flags and exact native source
  bindings. A native user role, quoted prompt or working directory alone is insufficient.
- Private request provenance never becomes enum-only Laya scoring input. Snapshot faults defer
  labeling and record bounded diagnostics while the incumbent task continues.
- Collection source changes remain strict cohort boundaries. Label reports partition recorded
  coverage by source; reviewed historical runtimes preserve prior research without pooling.
- Capture readiness and synthetic fixtures do not establish context yield, routing accuracy or
  task benefit. Final release/activation evidence is retained in the private implementation plan.
- Final Context Manager/config integration: 951 passed, three existing skips. Release contract:
  494 passed. Full repository checks initially hit 14 sandbox-only cache/socket/process/Git
  access denials; all 14 passed unchanged with required access. Manifest/config/map/setup and
  impact-map reconciliation passed. Independent cold review passed; Fable conditions verified.
