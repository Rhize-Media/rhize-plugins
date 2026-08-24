# Changelog

All notable changes to the Rhize Plugins marketplace are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- _2026-08-24_ version bump — **procedural-memory** 0.1.0 → 0.2.0 (minor); marketplace 2.37.3 → 2.38.0.
- _2026-08-24_ version bump — **project-launcher** 1.7.2 → 1.7.3 (patch); marketplace 2.37.2 → 2.37.3.
- _2026-08-24_ **procedural-memory 0.1.0 — wraps the `rhize-skill` CLI (Rhize-Media/procedural-memory) so a task that looks already-solved re-executes the artifact that solved it instead of an LLM recomposing it from scratch.** Four thin command wrappers (`/promote`, `/recall`, `/run`, `/verify`) plus a `procedural-memory` skill for natural-language triggers, all routed through a new `scripts/rhize-skill-launcher.sh` — resolves the CLI portably (`RHIZE_SKILL_BIN` env override → `PATH` → a documented machine-local convenience default → a loud, actionable refusal, never a silent no-op or a confusing downstream 401-style error), and checks the resolved CLI isn't older than the plugin expects (via `importlib.metadata` against the binary's own sibling interpreter, since `rhize-skill` has no `--version` flag), naming both versions on a mismatch. Verified live against the real registry (`recall "deploy an n8n workflow safely"` returned ranked real hits with trust/health/success-rate) and against real failure paths (missing-CLI refusal, forced version-mismatch refusal). An earlier handoff proposed a fifth `/prune` command; deliberately not built — see `procedural-memory/docs/decisions/0001-no-prune-command.md` (nothing in the CLI implements pruning; `stale` is a read-only decay report, and deciding what to actually retire is a human call, not a wrapper plugin's). Trigger description deliberately differentiated from claude-mem's `mem-search`/session-retrieval skills ("executing proven code" vs. "recalling past conversation") — confirmed empirically via `skill-forge scan --skill-map` against the resolved map (527 third-party skills including claude-mem's 20): nearest match was `find-skills` at overlap 0.016, ALLOW verdict, claude-mem's skills weren't even the closest match. Hooks scaffolded but left inert (`hooks/hooks.json` with an empty `hooks` object) — wiring deferred to a follow-up task. `claude plugin eval` sandbox reachability (whether it can exec a home-directory binary or reach localhost Postgres) is undocumented in current reference material — recorded as an open question in the plugin's README rather than assumed either way; a future eval suite should default to a fixture/mock mode.
- _2026-08-24_ version bump — **procedural-memory** 0.1.0 (new plugin); marketplace 2.36.5 → 2.37.0.
- _2026-08-24_ **config-lint gate added (`scripts/validate_plugin_configs.py`) — written to catch three separate 2026-08 incidents that had already shipped and been fixed by hand:** an unquoted `${CLAUDE_PLUGIN_ROOT}` word-splitting a hook `command` under a path containing a space (fixed 2026-08-23, `843e3fd`/`6f40626`), a secret-shaped `${VAR}` reference left in a stdio MCP server's `env` block instead of the Keychain launcher (docs/mcp-secret-launcher.md), and a trailing slash on `OBSIDIAN_BASE_URL` doubling every request path (fixed in obsidian-second-brain 1.4.1). The lint is dependency-free stdlib, matches credential-shaped env keys on their last `_`-separated component so `SLACK_TEAM_ID`/`KEY_FILE_PATH` aren't mistaken for secrets, treats HTTP-transport `headers` blocks as correctly using `${VAR}` (out of scope, not a finding), and exits non-zero only on error-severity findings — warnings surface without blocking. Registered in `bump_version.py`'s `REPOSITORY_CONTRACTS` in default (non-`--strict`) mode: a false positive in a release gate blocks every bump including emergencies, and the usual response is to delete the contract, so only genuine errors gate. Fixture-based tests: `tests/config-lint/`. Also fixed the copy-pasteable `security add-generic-password ... -w '<value>' -U` placeholder footgun across `docs/mcp-secret-launcher.md`, both `mcp-secret-launcher.sh` shims, and both plugins' README/GUIDE setup instructions — run verbatim it stored the literal string `<value>` as the Keychain item, passing every existence check while the server 401'd; changed to the prompting form (`-U -w`, `-w` last per `security add-generic-password -h`) so there's nothing to paste wrong and the secret never enters argv or shell history.**
- _2026-08-24_ version bump — **seo-aeo-geo** 1.4.2 → 1.4.3 (patch); marketplace 2.37.1 → 2.37.2.
- _2026-08-24_ version bump — **obsidian-second-brain** 1.4.3 → 1.4.4 (patch); marketplace 2.37.0 → 2.37.1.
- _2026-08-23_ version bump — **seo-aeo-geo** 1.4.1 → 1.4.2 (patch); marketplace 2.36.4 → 2.36.5.
- _2026-08-23_ version bump — **obsidian-second-brain** 1.4.2 → 1.4.3 (patch); marketplace 2.36.3 → 2.36.4.
- _2026-08-23_ version bump — **seo-aeo-geo** 1.4.0 → 1.4.1 (patch); marketplace 2.36.2 → 2.36.3.
- _2026-08-23_ version bump — **project-launcher** 1.7.1 → 1.7.2 (patch); marketplace 2.36.1 → 2.36.2.
- _2026-08-23_ version bump — **obsidian-second-brain** 1.4.1 → 1.4.2 (patch); marketplace 2.36.0 → 2.36.1.
- _2026-08-23_ version bump — **rhize-cowork** 0.1.0 (new plugin); marketplace 2.35.0 → 2.36.0.
- _2026-08-23_ **rhize-cowork 0.1.0 — `project-kickoff`, scaffolding the four Cowork client-context
  files (CLAUDE.md, BUSINESS.md, PERSONALITY.md, INFO.md) from a website, strategy docs, or a guided
  interview.** Recovered from the long-stale `add-rhize-cowork-plugin` branch (87 commits behind main)
  and re-cut onto current main. Two changes were required before it could land: the skill carried no
  `tier`/`domain`/`maturity` frontmatter, unlike the other 27 skills in the marketplace; and its
  description claimed the bare trigger "starts a new project", which collides head-on with
  project-launcher's "ALWAYS invoke this skill for any request to start a new project". The two are
  genuinely distinct capabilities — kickoff produces business-context files, launcher produces a PRD
  and a code scaffold — so the description was narrowed to client/business onboarding and now says
  explicitly that software projects belong to project-launcher, rather than leaving two skills
  competing for one invocation.
- _2026-08-23_ version bump — **obsidian-second-brain** 1.4.0 → 1.4.1 (patch); marketplace 2.34.0 → 2.34.1.
- _2026-08-23_ **obsidian-second-brain 1.4.1 — every Obsidian MCP tool was 404ing because
  `OBSIDIAN_BASE_URL` ended in a trailing slash.** `obsidian_list_tags` returned
  `Not found: /tags/` and `obsidian_search_notes` (text mode) returned
  `Not found: /search/simple/`, while `curl -k -H "Authorization: Bearer $KEY"
  https://127.0.0.1:27124/tags/` returned `200` — so it looked like an auth or upstream problem
  and was neither. `obsidian-mcp-server` builds every request as
  `` `${this.#config.baseUrl}${pathAndQuery}` `` (`dist/services/obsidian/obsidian-service.js`,
  `#request`) and its config schema validates `baseUrl` with `.url()` only — no trailing-slash
  normalization (`dist/config/server-config.js`). The configured
  `"https://127.0.0.1:27124/"` therefore emitted `https://127.0.0.1:27124//tags/`. The Local REST
  API 404s a doubled path, and the server's 404 handler formats the message from the
  *un-doubled* `pathAndQuery`, so the diagnostic actively pointed away from the cause.
  Measured: `//tags/`, `//vault/`, `//commands/`, `//search/simple/` and `//` all return `404`;
  their single-slash forms all return `200`. **Every endpoint was affected, not just the two
  tools that happened to be exercised.** Fix is one character — `OBSIDIAN_BASE_URL` is now
  `https://127.0.0.1:27124`, matching the package's own documented default. Verified end-to-end
  by driving `npx obsidian-mcp-server` over stdio JSON-RPC with each value: the trailing-slash
  run reproduced both error strings exactly, the fixed run returned 200 tags and 573 search hits.
  No upstream patch or local workaround needed — the trailing slash was our misconfiguration —
  though the package would be more robust joining with `new URL(path, base)` or stripping
  `/+$` in the schema.
- _2026-08-20_ version bump — **rhize-devflow** 2.12.1 → 2.13.0 (minor); marketplace 2.34.1 → 2.35.0.
- _2026-08-20_ **rhize-devflow — global refactor-evidence enforcement for Claude and Codex.**
  Material implementation/refactor prompts now create a shared workspace receipt. Source writes
  block until the canonical impact-map workflow has validated a persisted semantic map, queried
  every existing healthy nested-root CodeGraph index (or recorded an explicit `rg` fallback), and
  read/hashed any component registry. Commit, push, merge, and completion block after source edits
  until post-change reconciliation reports `IN_SYNC` or `IN_SYNC_WITH_EXCEPTIONS`. The gate never
  initializes CodeGraph or requires a registry where none exists; false positives use a recorded
  dismissal and `RHIZE_REFACTOR_GATE=off` remains an explicit emergency bypass. A reconciled
  receipt closes as `completed` at the successful Stop boundary, so late same-turn writes still
  invalidate it without letting the old map contaminate a later task. Codex patch text carried
  through `functions.exec` is validated by the command hook, not assumed to arrive as a direct
  write event. Includes 16 lifecycle behavior cases plus updated hook and impact-map contracts.
- _2026-08-19_ version bump — **seo-aeo-geo** 1.3.1 → 1.4.0 (minor); marketplace 2.33.0 → 2.34.0.
- _2026-08-19_ version bump — **obsidian-second-brain** 1.3.2 → 1.4.0 (minor); marketplace 2.32.0 → 2.33.0.
- _2026-08-19_ **obsidian-second-brain 1.4.0 + seo-aeo-geo 1.4.0 — portable credential delivery
  via a committed shim; `${VAR}` removed from both `.mcp.json` files.** Both plugins previously
  passed their API credential as `"env": { "X": "${X}" }`. Claude Code expands `${VAR}` from its
  own process environment at config load — correctly when the variable is present, but passing
  the **literal** string `${X}` through when it is absent, at which point the server authenticates
  with those characters and returns an opaque 401/403. Presence depends on how Claude Code was
  launched (`launchctl setenv` reaches GUI-launched processes; a terminal-launched `claude` gets
  nothing once ambient shell exports are removed), so the same committed config worked in one
  context and failed in another. Verified empirically against Claude Code 2.1.233 with a probe
  MCP server that reported its own environment. Both plugins now ship
  `scripts/mcp-secret-launcher.sh` (POSIX sh — macOS, Linux, Claude Cowork) invoked as
  `"${CLAUDE_PLUGIN_ROOT}/scripts/mcp-secret-launcher.sh"`, so no absolute machine-specific path
  is committed. Resolution order: `mcp-secret-launcher` on PATH or `~/.local/bin` (reads the
  macOS login keychain at `claude-code:<VAR>`, exports into that child process only) → plain
  environment inheritance if the variables are already exported → otherwise exit 78 naming the
  missing variables and both remedies. It never starts a server it knows cannot authenticate.
  No secret is written to any plugin file. New reference: `docs/mcp-secret-launcher.md`, including
  a detector for `${VAR}` regressions across all MCP config locations. **Requires a session
  restart to take effect.**
- _2026-08-17_ version bump — **rhize-tasks** 0.2.0 → 0.3.0 (minor); marketplace 2.31.0 → 2.32.0.
- _2026-08-17_ version bump — **rhize-tasks** 0.1.0 → 0.2.0 (minor); marketplace 2.30.1 → 2.31.0.
- _2026-08-17_ **rhize-tasks 0.3.0 — Reminders TCC redesign, persisted Slack watermark, signing
  auto-detect.** Closes the items 0.2.0 had deferred, per Jim's direction. The Swift EventKit
  helper now runs as its own gui-domain LaunchAgent (`media.rhize.tasks.reminders-helper`)
  serving one JSON request per connection over a 0600 Unix socket at a stable bundle path —
  making the helper its own TCC-responsible process so Reminders prompts/grants work under the
  background agent (reviewer finding #2, fix option 2). Scope stays caller-supplied per request
  (`allowedListId` in each socket request; env for the stdin/dev path). Hardened per a second
  Codex adversarial pass: routine-before-helper stop ordering, helper socket-readiness gating
  before routine bootstrap, `sun_path` length guard, split-brain socket protection (live-probe
  before unlink, inode-checked shutdown cleanup), per-connection read deadlines, write-ambiguity
  classification on socket transport failures with a 1MB response cap, and uninstall item-cleanup
  running through the live helper socket before bootout. Slack syncs now persist a watermark:
  parents always scan the full lookback window, reply pagination is gated on
  `latest_reply` vs watermark (24h grace), and the watermark advances only on untruncated syncs.
  Installer auto-detects a Developer ID Application identity by certificate hash (ad-hoc
  fallback; `RHIZE_TASKS_SIGN_IDENTITY` overrides). Doctor reports the resolved helper
  transport/paths. README known-limitations section removed — remaining operational caveats
  (ad-hoc re-prompt after updates until a signing cert exists; OAuth app must be in Production
  publishing status) are documented as requirements/install notes, not open questions.
  Tests 277 → 328 node + 16 Swift.
- _2026-08-17_ **rhize-tasks 0.2.0 — external-review remediation (Tom Cassidy's 0.1.0 review,
  25 findings + plugin wiring), hardened by a second adversarial pass.** First-run path now works:
  `dashboard` starts the local server itself (pidfile-managed; installer/uninstaller stop it
  cleanly, reinstall no longer conflicts with its own port). Installer: stable Node path
  resolution with capability probing (fails closed on ephemeral fnm/nvm paths), tri-state
  launchctl detection with label-form bootout fallback, bootout-before-swap reinstall ordering,
  rollback gated on verified agent stop (`manual_recovery_required` instead of unsafe mutation),
  process-group kill with SIGTERM forwarding, stderr surfaced from failed `swift build`/`codesign`
  through the CLI JSON boundary, corrupt Keychain token self-heal, stale artifact sweep, scoped
  secret scanner, `--no-warnings` in the LaunchAgent. Connectors: Google `invalid_grant` and
  denied Reminders access now surface as `revoked` (previously indistinguishable from `offline`),
  in-memory Google token cache with shared in-flight refresh + 401 invalidation, `Retry-After`
  honoring backoff, bounded Slack pagination with mrkdwn un-escaping (Jira URLs from real Slack
  now parse) and real channel verification at discovery. API/dashboard: scope-expansion approval
  path wired up end-to-end (preferences-backed, transactional approval), setup-probe orphan
  recovery + concurrency guards, artifact `$`-replacement corruption fixed, discovery-path HTTPS
  enforcement, nonce burn-after-validate, Origin/Host/`x-rhize-tasks-dashboard` header enforcement
  on every cookie-authenticated request, SQLite WAL + 5s busy timeout, doctor now reports
  `agentLoaded`/`plistNodePathExists`/`runtimeVersionMatch`/`lastRoutineRun`. Claude wiring: all
  six commands now invoke their skills via the Skill tool (`allowed-tools` includes `Skill`);
  skills carry a non-macOS (Claude Cowork) platform guard. Tests 181 → 277. Known limitations
  documented in README: Reminders TCC under launchd, ad-hoc signing grant resets, Google
  OAuth Testing-status token expiry, per-run Slack lookback.
- _2026-08-16_ version bump — **rhize-devflow** 2.12.0 → 2.12.1 (patch); marketplace 2.30.0 → 2.30.1.
- _2026-08-16_ version bump — **rhize-context-manager** 0.13.0 → 0.14.0 (minor); **rhize-devflow** 2.11.0 → 2.12.0 (minor); **rhize-ops** 0.9.0 → 0.10.0 (minor); marketplace 2.29.0 → 2.30.0.
- _2026-08-16_ **Rhize Dev Flow becomes the engineering control plane —
  `impact-map → check → review → release`.** Dev Flow now owns the full change lifecycle, not
  just impact mapping: canonical `/rhize-devflow:check` (evidence-driven mid-implementation
  validation — builds a deterministic evidence packet via the new `scripts/devflow.py evidence`
  CLI, selects checks only from repository instructions and known-safe declared package scripts,
  never executes shell text parsed from prose, returns `PASS`/`PASS_WITH_WARNINGS`/`BLOCKED`) and
  `/rhize-devflow:review` (read-only production merge/release gate — resolves the exact base/head
  range from explicit intent, builds a risk map from actual diff evidence across
  deployment/data/security/authorization/billing/migration/cache/external-write categories, routes
  only relevant specialists, requires an independent skeptical reviewer for non-trivial work,
  returns `PASS`/`FAIL_WITH_FIXABLE_GAPS`/`FAIL_REQUIRES_HUMAN`, and is the executable successor to
  the retired `rhize-review` workflow). `/rhize-devflow:mutation-check` and
  `/rhize-devflow:browser-qa` consolidate the former `mutation-analyze`/`mutation-check`/
  `mutation-fix` and `browser-debug`/`browser-help`/`browser-perf`/`browser-test` command sprawl
  into one read-only, scenario-driven command apiece; the six retired commands become one-line
  `> **Deprecated:**` adapters (no duplicated workflow text) for the 2.12.0 compatibility window.
  `scripts/devflow.py doctor` (also reachable as the thin `/rhize-devflow:doctor` slash-command
  adapter) validates plugin health — manifests, canonical commands, referenced assets, duplicate
  bodies, stale tokens, script importability, and capability dependencies — from both a source
  checkout and an installed plugin cache; `schemas/devflow-evidence-v1.schema.json` is the stable output contract
  for `evidence --json`. `setup/manifest.json`'s Sentry/Vercel/GitHub/Chrome DevTools MCP
  dependencies are now capability-scoped and optional at the plugin level (a missing tool degrades
  only the capability it gates, e.g. `browser-qa`, not the whole plugin). A new
  `.codex-plugin/plugin.json` gives Dev Flow a Codex identity that routes through the same
  `skills/dev-flow-foundations` command bodies Claude uses, rather than forking a second workflow.
  Dev Flow's five overlay skills (`chrome-devtools-mcp`, `data-mutation-consistency`,
  `error-lifecycle-management`, `sentry-instrumentation`, `sanity-development`) are narrowed to
  Rhize-specific policy and convention only — stale Zen/Serena/Graphiti requirements and legacy
  `@...` command aliases are removed, `error-lifecycle-management`'s
  `ARCHITECTURE-PROPOSAL.md` is archived outside the plugin, and `chrome-devtools-mcp` shrinks to
  DevTools-protocol mechanics used by `/rhize-devflow:browser-qa` rather than general browser
  guidance. `rhize-context-manager`'s `/impact-map` is now a one-line deprecation adapter to
  `/rhize-devflow:impact-map` (the canonical body moved to Dev Flow), and `/done` truthfully
  delegates code-change review to `/rhize-devflow:review` when Dev Flow is installed and code
  changed this session, disclosing its local fallback checklist otherwise instead of silently
  running it or claiming a bundled verifier that only ever existed in Dev Flow. New
  `evals/rhize-devflow/` trigger/quality/false-positive fixtures and an extended
  `tests/rhize-devflow/` integrity suite (asset-existence, no-unresolved-placeholder,
  no-unjustified-duplicate-command-body, single-canonical-owner, no-stale-dependency-term
  contracts) are wired into the existing unconditional version/CI gate via
  `scripts/bump_version.py`'s `REPOSITORY_CONTRACTS`, so a regression on any of these claims
  fails the same gate a version bump already runs. This is a compatibility release: no public
  command name is removed yet — see both plugins' README migration tables for the full old→new
  command mapping, and the plan at
  `.claude/plans/rhize-devflow-v3-engineering-control-plane.md` for the full task list and the
  30-day/two-release-cycle observation window before Dev Flow 3.0.0 removes the adapters.
- _2026-08-16_ version bump — **rhize-context-manager** 0.12.0 → 0.13.0 (minor); **rhize-devflow** 2.10.3 → 2.11.0 (minor); marketplace 2.28.0 → 2.29.0.
- _2026-08-16_ **CodeGraph-first semantic impact mapping across Rhize Dev Flow and Context
  Manager.** `dev-flow-foundations` now defines a strict authority split: CodeGraph owns current
  structural evidence, while the impact map owns intended behavior, invariants, planned code,
  operational effects, acceptance tests, and explicitly unaffected paths. The single executable
  `/rhize-context-manager:impact-map` command checks each repository root independently, uses an
  existing CodeGraph index before text search, refuses to initialize one implicitly, falls back to
  `rg` when absent or stale, and requires post-implementation graph/diff/map reconciliation with an
  `IN_SYNC`, `IN_SYNC_WITH_EXCEPTIONS`, or blocking `OUT_OF_SYNC` verdict. A cross-plugin contract
  test prevents ownership duplication and workflow drift; the existing version check invokes it
  automatically whenever either owning plugin changes, so CI and configured pre-push gates enforce
  the same contract.
- _2026-08-14_ version bump — **rhize-ops** 0.8.1 → 0.9.0 (minor); **rhize-tasks** 0.0.0 → 0.1.0 (minor); marketplace 2.27.0 → 2.28.0.
- _2026-08-14_ **Rhize Tasks — a local-first unified planning authority for Tom's Rhize and client work.** The new cross-client planning plugin combines approved Jira tasks and structured `#tom-tasks` delegations with Google Calendar and Apple Reminders awareness, then produces a today-first, capacity-aware plan. Assigned Jira work remains first; urgent unassigned work appears only as an approval-required competency-fit opportunity. A seven-stage local wizard preserves Tom's working intervals, breaks, buffers, exclusions, bounded-replanning preference, and prompted-reconciliation preference. The loopback-only service stores state in SQLite and secrets in macOS Keychain, writes only to the exact approved focus calendar and `Rhize Tasks` list, protects manually moved blocks, carries unfinished work forward once per evening evaluation, and turns exact reminder completion into an approval-required Jira reconciliation note. Six shared Claude/Codex skills, six Claude command wrappers, an accessible dashboard, and a read-only Claude artifact provide one consistent control surface. The transactional installer ships a signed Swift EventKit helper and a versioned runtime; uninstall requires explicit and independent local-data/item-retention choices and deletes items only after exact ownership verification. Automated release acceptance uses disposable fakes only—Tom-Mac TCC/OAuth/Jira acceptance is still required before live writes.
- _2026-08-14_ version bump — **rhize-context-manager** 0.11.0 → 0.12.0 (minor); marketplace 2.26.0 → 2.27.0.
- _2026-08-14_ **Harvest noise filter — the queue stops collecting the same lesson twice.**
  New `scripts/harvest_noise_filter.py`, wired as step 7 of `/learn-harvest`. Queue ids are
  `sha1-12(source + pattern)`, so any rewording of a known fact produced a new id and evaded
  id-dedupe; measured on 2026-08-14, 3 of 5 headroom entries restated facts folded into
  CLAUDE.md two days earlier, and the two largest `est_savings` claims (235k, 45k) were the
  two most duplicative — ~30% of a day's yield. The filter scores candidates by greedy
  set-cover against existing queue patterns (any status) and CLAUDE.md blocks, then
  suppresses (≥0.75), flags-but-keeps (≥0.45), or drops as thin (<6 content tokens).
  Thresholds are calibrated against that day's 44 human-labeled dispositions, where real
  signals topped out at 0.70 and fully-covered restatements started at 0.80; `--self-audit`
  reproduces it. Composite entries (`Topic — Fact1. Fact2. Fact3.`) land at 0.46–0.56 and are
  deliberately flagged rather than suppressed — no threshold separates them from genuine
  signals, so the filter declines to guess. Every decision is teed to
  `harvest-logs/<date>-filter.txt`, so a filtered run stays distinguishable from a collector
  that never ran. Stdlib only, deterministic, no network.
- _2026-08-14_ **`/skill-refine review` gains two measured triage facts** — `est_savings` is
  anti-correlated with entry quality (never rank or threshold on it), and `evolve` requires a
  skill *directory*, so bare `~/.claude/skills/learned/*.md` targets can only receive the
  step-3 text fold-in. Triage now also surfaces any `filter_note` set by the harvest filter.
- _2026-08-10_ version bump — **rhize-context-manager** 0.10.1 → 0.11.0 (minor); marketplace 2.25.5 → 2.26.0.
- _2026-08-10_ **Suggestion log — routing suggestions are now measurable.** All four skill-map
  hooks (`skill-router`, `session-disclosure`, `remediation-suggester`, `next-step-suggester`)
  append one JSON line per fired suggestion to `~/.claude/context-manager/suggestion-log.jsonl`
  (`ts`/`session_id`/`hook`/`suggested`/`context_hash` — ids and truncated hashes only, never
  prompt text; fail-silent, sub-millisecond). The router also samples 1-in-20 no-suggestion
  prompts so silence precision has a denominator. New `scripts/suggestion_log_report.py` joins
  the log against skill-monitor usage for per-hook acceptance/ignore rates. Env overrides for
  tests/evals: `RHIZE_SUGGESTION_LOG`, `RHIZE_CONTEXT_MANAGER_DIR` (hooks' map/indexes dir).
- _2026-08-10_ **Skill-graph eval suite** (`evals/skill-map/`, per
  `docs/superpowers/specs/2026-08-10-skill-graph-evals-design.md`): golden-set miner
  (contamination-guarded to pre-router sessions; mined data gitignored — contains user prompt
  text), routing-accuracy eval with the retired grep suggester vendored as baseline (first run:
  router 57.1% top-1 / 76.2% silence precision vs baseline 0.0% / 20.2%), disclosure
  cost/benefit eval (~490 bytes per matching repo vs 5,187-byte banner baseline, silence
  honored), remediation-pattern precision eval with failure-corpus miner, and a weekly-audit
  metrics line (`~/.claude/context-manager/audit-metrics.jsonl`). Curation-gate regression
  fixtures (the four retired ECC forks + graphify must always be flagged) live in
  `@rhize/skill-forge` 0.13.0, which also fixes a real gate bug this work surfaced: `--skill-map`
  read a `type` field no real artifact sets (`kind`) and silently matched nothing.
- _2026-08-10_ **tests/skill-map hardening**: `conftest.py` supplies the previously missing `doc`
  fixture (two artifact-validity tests were silently ERRORing since introduction), and
  `test_stale_gate.py` exercises the weekly audit's step-0 negative branch — seed real drift in
  a scratch clone, assert `--check-stale` FAILs, rebuild, assert PASS, assert the diff confines
  to `generated/*` + the seed, commit. The docstring maps each audit-prose sentence to its
  assertion and names the two honestly untestable residues.
- _2026-08-10_ **Skill-map viewer tooling committed** (`scripts/viewer/`): the interactive
  force-directed skill-graph viewer's template (`viewer-template.html`) and build script
  (`build_viewer.py`) moved into the repo from an ephemeral session scratchpad so the published
  viewer artifact can be regenerated. Builds from the machine-local resolved map when present
  (includes the third-party ecosystem overlay), falling back to the committed static map.
  Default view renders cross-plugin "bridge tags" (tags spanning ≥2 plugins) even with the full
  topic/stack tag layers toggled off. See the Consumers table in `docs/skill-map.md`.
- _2026-08-10_ **`scripts/query_skill_map.py` actually committed.** The two-tier query layer's
  CLI (shipped conceptually in the relationships-v2 change and referenced 5 times by
  `docs/skill-map.md`) had never been tracked — `.gitignore`'s `scripts/*` allowlist silently
  excluded it, the same trap that would have swallowed `scripts/viewer/`. Both are now
  allowlisted; a fresh clone regains the query CLI.

- _2026-08-10_ version bump — **obsidian-second-brain** 1.3.1 → 1.3.2 (patch); marketplace 2.25.4 → 2.25.5.
- _2026-08-10_ version bump — **rhize-devflow** 2.10.2 → 2.10.3 (patch); marketplace 2.25.3 → 2.25.4.
- _2026-08-10_ version bump — **project-launcher** 1.7.0 → 1.7.1 (patch); marketplace 2.25.2 → 2.25.3.
- _2026-08-10_ version bump — **rhize-ops** 0.8.0 → 0.8.1 (patch); marketplace 2.25.1 → 2.25.2.
- _2026-08-10_ version bump — **rhize-context-manager** 0.10.0 → 0.10.1 (patch); marketplace 2.25.0 → 2.25.1.

### Fixed

- _2026-08-10_ **Skill-map connectivity audit: under-declared tags/dependencies corrected.**
  A prior audit verified 12 skills' `SKILL.md` frontmatter against their actual behavior and
  found gaps between what a skill does and what its `metadata.rhize` tags/dependencies claim:
  - **Missing `stacks: [obsidian]`**: `graphify` (ships `graphify export obsidian`),
    `context-stack` (the vault is a named layer of the stack it routes), `delegate-to-teammate`
    and `project-launcher` (both drive the Obsidian MCP). `context-stack`'s bogus `[context]`
    self-reference and `refinement-pipeline`'s bogus `[refinement]` self-reference are removed —
    a skill about a stack isn't itself a member of that stack. The now-unused `context` and
    `refinement` stack tag slugs are removed from `catalog/tags.json`.
  - **Missing `stacks` for platform coverage**: `rhize-visual-plan` gains `nextjs` (ships a
    Next.js viewer app); `data-mutation-consistency` gains `sentry`+`vercel` and
    `sanity-development` gains `sentry` (both instrument Sentry / are Vercel-scoped).
  - **Missing `dependsOn`**: `delegate-to-teammate` now declares all four MCPs it drives
    (`mcp:obsidian-mcp-server`, `mcp:slack`, `mcp:atlassian`, `mcp:fireflies`);
    `skill-dashboard` declares `mcp:chrome-devtools`; `project-launcher` declares
    `mcp:obsidian-mcp-server`; `data-mutation-consistency` declares `mcp:sentry`+`mcp:zen`;
    `error-lifecycle-management` declares `mcp:sentry`+`mcp:vercel`+`mcp:github`;
    `chrome-devtools-mcp` declares `mcp:chrome-devtools`; `qmd-search` declares `mcp:qmd`.
  - **Missing `depends-on` edges** in `catalog/skill-relations.json`: `project-launcher` →
    `external:skill-forge` (runs `npx @rhize/skill-forge find/audit/add`) and
    `command:rhize-context-manager/skill-refine` → `external:skill-forge` (runs
    `npx @rhize/skill-forge evolve`).
  Rebuilt `generated/skill-map.static.json` + `.indexes.json` and re-rendered the managed
  README/`SKILL-CATALOG.md` sections from the corrected map; verified deterministic (identical
  output on a second build) and that all 12 declared MCP servers now resolve as
  `mcp-server` nodes.

- _2026-08-10_ **`/learn-harvest`: stop the collector producing false "source unavailable"
  no-ops.** The 2026-08-10 daily harvest returned 0 entries and marked 2 of 3 sources
  unavailable; both verdicts were wrong, and the corrected run collected 9 entries (queue
  69 → 78). Because "all sources unavailable" and "no new signals" both render as an empty
  table, the failure was invisible while starving the weekly `/skill-refine run` drain.
  Three fixes in `rhize-context-manager/commands/learn-harvest.md`:
  - **Step 2 instructed an unrunnable command.** It said to run `headroom learn --project
    <cwd>` and "add `--all` when invoked with the `all` argument" — but those flags are
    mutually exclusive (exit 2), and `--all` means all ~17 discovered *projects*, not the
    command's three *sources*. The collector followed the spec verbatim, turning a
    seconds-long run into ~13 minutes. Step 2 is now explicit that `all` scopes sources
    only, and that headroom takes neither `--all` nor `--apply`.
  - **Step 2 now requires `timeout: 600000`** on the headroom Bash call — `headroom learn`
    runs an LLM over conversation history and exceeds the tool's 120s *default*, which is
    not a limit. A timeout alone is never grounds to report headroom unavailable.
  - **Step 3 now preloads the deferred claude-mem tools via `ToolSearch`.** Calling one
    directly fails with `InputValidationError`, which reads like an auth error — the
    search server is not auth-gated. Already disproven on 2026-08-09 (claude-mem
    observation #45554); it recurred because nothing in the procedure recorded it.
  - Step 2 also tees headroom stdout to `~/.claude/context-manager/harvest-logs/`;
    `headroom learn` writes nothing to disk itself, so the 2026-08-10 run's output died
    with its shell and the LLM spend was unrecoverable.
  - New **Source-availability rule**: prove a source dead before recording it so
    (`headroom learn --help` exits 0 in <1s), distinguish "the probe failed" from "my call
    failed", and report a 2+-unavailable run loudly rather than as a clean empty table.
  The scheduled routine at `~/Documents/Claude/Scheduled/daily-learn-harvest/SKILL.md`
  (not in this repo) carries the same directives, and now requires them to be copied
  verbatim into its Haiku collector's spawn prompt — every 2026-08-10 failure happened
  inside that subagent, which never reads the routine file.

### Added

- _2026-08-10_ **Skill map: three-way drift — baseline hashes + normalized local hash, so a
  fork's own tagging never reads as drift.** The two-way compare (local-now vs upstream-now) had a
  permanent false positive: Rhize's `metadata.rhize` frontmatter makes every one of the 7 forks'
  raw `contentHash` differ from upstream forever, with zero real divergence. Design:
  `docs/superpowers/specs/2026-08-10-three-way-drift-design.md`.
  - New `scripts/baseline_upstreams.py`: fetches each SOURCES.md entry's http(s) `Source`, hashes
    it, and writes/updates a `- **Upstream baseline:** sha256:<hex> (recorded YYYY-MM-DD)` bullet —
    the deliberate "I reviewed upstream, accept its state" action. Idempotent (unchanged upstream →
    no diff, not even a date bump); `--skill <name>` scopes to one entry; non-URL `Source` entries
    are skipped with a report.
  - `scripts/build_skill_map.py` gains `strip_rhize_metadata_block()` — the ONE normalization
    implementation (textual removal of the `metadata.rhize` frontmatter subtree; removes the whole
    `metadata:` block iff `rhize` is its only key, else just the `rhize:` subtree). The compiler
    copies `SOURCES.md`'s baseline onto the per-skill `external` node as `baselineHash` (never onto
    the display-only `fork-of` edge `driftCheck`), and emits `contentHashNormalized` on every
    `fork-of` skill node. skill-forge compares the hashes it's handed and never re-implements the
    stripping (the duplicated-validator lesson from the retired `strategic-compact` fork).
  - `schemas/skill-map.schema.json`: documented the two new optional node fields
    (`baselineHash` on `external` nodes, `contentHashNormalized` on `skill` nodes), both sha256-hex
    patterned like `contentHash`.
  - Ran `baseline_upstreams.py` for real against all 7 `muratcankoylan/Agent-Skills-for-Context-Engineering`
    forks and committed the recorded hashes; rebuilt+installed the artifact and indexes.
  - New `tests/skill-map/test_baseline_upstreams.py`: normalization unit cases (block present,
    rhize-among-other-keys, no metadata key, no frontmatter), baseline idempotency + selective
    skip + skill-filter tests (fake fetcher, no network dependency), and a compiler test proving
    `baselineHash`/`contentHashNormalized` are emitted only where SOURCES.md actually supplies
    them — never unconditionally.
  - `docs/skill-map.md`: new "Three-way drift" section documenting the baseline field, the
    normalization rule, the four-state verdict matrix (`in-sync`/`local-only`/`upstream-moved`/
    `diverged`, computed by skill-forge's `watch`), and the re-baseline workflow.
  - `~/Documents/Claude/Scheduled/weekly-skill-audit/SKILL.md` (outside this repo): step 0 now
    queues only the actionable verdicts (`upstream-moved`/`diverged`/`unreachable`, plus legacy
    `drifted` for un-baselined edges) into the refinement queue; `in-sync`/`local-only` are counted
    in the report line only, never queued; added the re-baseline instruction.
- _2026-08-10_ **Skill map: remote upstream URLs in `SOURCES.md` — machine-independent drift
  checks.** `rhize-context-manager/skills/SOURCES.md`'s 7 `context-engineering-marketplace` forks
  (context-fundamentals, context-degradation, context-compression, context-optimization,
  memory-systems, filesystem-context, tool-design) had `Source` entries pointing at that
  marketplace's local plugin-cache path — resolvable only on a machine that still has it
  installed, so every fork-of drift check reported `upstream-unreachable` everywhere else.
  Identified the real upstream (`muratcankoylan/Agent-Skills-for-Context-Engineering` on GitHub,
  via the plugin's ingestion commit) and repointed all 7 `Source` fields to verified
  `raw.githubusercontent.com` URLs (each checked with `curl` for HTTP 200 + real SKILL.md
  frontmatter before being recorded). `scripts/build_skill_map.py`'s `SOURCES.md` ingestion now
  detects an `http(s)` `Source` and emits `url` (instead of `path`) on the per-skill `external`
  node — skill-forge's drift checker already reads `node.url ?? node.path`, so no other code
  needed to change. Local-path `Source` entries (the 4 retired `everything-claude-code` forks)
  are unaffected. `npx @rhize/skill-forge watch` now resolves all 7 forks over HTTPS and reports
  genuine `drifted`/`in-sync` verdicts instead of `upstream-unreachable`.
- _2026-08-09_ version bump — **rhize-context-manager** 0.9.1 → 0.10.0 (minor); marketplace 2.24.3 → 2.25.0.
- **Skill map: relationships v2 consumer layer — remediation + next-step suggester hooks, router/
  disclosure hooks read materialized indexes.** Completes the follow-up lane named in the CORE
  entry below (design doc section 7).
  - New `rhize-context-manager/hooks/remediation-suggester.js` (PostToolUse, matcher `Bash`):
    on a failing Bash command, matches `stdout`+`stderr` against the `remediation` index's
    condition patterns and suggests the top-listed remediator for the first matching condition.
    Patterns in `catalog/tags.json` are authored as Python `re` (they use the `(?i)` inline
    case-insensitivity flag, which JS `RegExp` has no equivalent for and throws "Invalid group"
    on) — the hook strips a leading `(?i)` into the JS `i` flag before compiling. An `external:`
    remediator id (a third-party capability with no proper skill-map node, e.g. an `ecc`
    build-resolver *agent*) is phrased as an agent suggestion, not a skill invocation.
  - New `rhize-context-manager/hooks/next-step-suggester.js` (PostToolUse, matcher `Skill`):
    after a skill invocation, looks up the invoked skill in the `succession` index and suggests
    its declared `precedes` successor, falling back to a mined `follows` successor — `precedes`'s
    first runtime consumer.
  - Both auto-wired in `hooks/hooks.json` (like `session-disclosure.js`, not opt-in via
    `setup/manifest.json`). Warm timing for all four hooks in this directory measured <100ms,
    within the <150ms budget.
  - `skill-router.js`/`session-disclosure.js` refactored to read the materialized `router`/
    `disclosure` index sections first (`routeFromIndex()`/`relevantSkillsFromIndex()`), falling
    back to the original map-scanning path (`route()`/`relevantSkills()`) only when no indexes
    file is present/parseable, so an older install degrades gracefully. Behavior is unchanged on
    the existing test suite; one known gap on the index-only path is documented in
    `docs/skill-map.md`'s Tier 1 note (disclosure's extends-folding is computed per stack slug,
    not across the union of all detected stacks — a cross-stack base/extender pair won't fold on
    the index path the way the map-scan fallback would; not exercised by any shipped fixture).
  - `scripts/build_skill_map.py --install`/`scripts/build_local_skill_map.py` already covered the
    indexes files (confirmed, no build-script change needed this round).
  - Tests: `tests/skill-map/test_remediation.js`, `tests/skill-map/test_next_step.js` (new); wired
    fixture-index files for `test_router.js`/`test_disclosure.js` so the index path is what's
    exercised by default, plus one explicit `[fallback]`-labeled map-scan test each.
- **Skill map: relationships v2 core — `follows`/`augments`/`remediates` edges, condition tags,
  `mcp-server` nodes, materialized indexes, query CLI (schema 1.1.0).** Implements the CORE layer
  of `docs/superpowers/specs/2026-08-09-skill-map-relationships-v2-design.md` (router/disclosure
  hook refactor and the two new PostToolUse suggester hooks are a follow-up lane).
  - Schema: new edge types `follows` (directional, requires `followWeight: {sessions,
    windowDays}`), `augments` (skill → topic tag), `remediates` (skill → condition tag); new tag
    kind `condition` (closed at 5: `build-failure`, `type-error`, `test-failure`, `lint-failure`,
    `merge-conflict`, each with failure-detection `patterns` in `catalog/tags.json`); new node
    kind `mcp-server` (id form `mcp:<name>`). `schemaVersion` bumped `1.0.0` → `1.1.0`.
  - Compiler (`scripts/build_skill_map.py`): parses `metadata.rhize.augments`,
    `metadata.rhize.remediates`, and `metadata.rhize.dependsOn` (accepting `mcp:<name>` targets,
    which mint an `mcp-server` node, alongside ordinary skill targets using `extends`'s
    resolution) — each with the same BuildError-on-unknown-slug/unresolved-target discipline as
    `extends`. `catalog/skill-relations.json` continues to carry third-party-owned edges,
    including from `external:` nodes representing third-party capabilities that aren't proper
    skill nodes (e.g. `everything-claude-code` build-resolver *agents*, which have no skill-map
    node kind).
  - Materialized indexes: the build now also emits `generated/skill-map.indexes.json`
    (`router`/`disclosure`/`remediation`/`succession` sections), mirroring
    `skill-router.js`/`session-disclosure.js`'s exact matching semantics so a future hook refactor
    to read this file is a pure data swap. Covered by `validate_skill_map.py --check-stale`.
    `scripts/build_local_skill_map.py` emits a resolved layer
    (`~/.claude/context-manager/skill-map.indexes.resolved.json`) merging mined `follows` edges
    into `succession`.
  - `follows` mining: `rhize-ops/skill-monitor/monitor.py`'s co-occurrence pass now also emits
    ordered, time-adjacent skill pairs (`orderedPairs`, ≥2 distinct sessions) into its snapshot;
    `build_local_skill_map.py` turns them into local-overlay-only `follows` edges (source:
    `monitor`).
  - Query CLI: `catalog/queries.json` (declarative walk specs) + `scripts/query_skill_map.py`
    (one Python walker), seeded with 7 named queries (`what-extends`, `what-augments`,
    `what-remediates`, `what-follows`, `overlap-candidates`, `unroutable-skills`,
    `mcp-dependents`); runnable against the static or resolved map (`--resolved`).
  - Seed data: `seo-aeo-geo/content-seo` augments `content-authoring`; 5 `seo-aeo-geo` skills
    (`aeo-geo-optimization`, `backlink-intelligence`, `keyword-intelligence`, `seo-site-audit`,
    `serp-intelligence`) declare `dependsOn: ["mcp:dataforseo"]` (verified against their SKILL.md
    bodies); `rhize-context-manager/graphiti-memory` declares `dependsOn: ["mcp:graphiti"]`;
    third-party `humanizer` augments `content-authoring` and the `ecc` build-resolver family
    remediates `build-failure`/`type-error`, both via `external:` catalog nodes. Skipped (with
    reason, per the design doc's "verify wording against the skill before tagging"):
    `rhize-devflow/error-lifecycle-management` → `test-failure` — its SKILL.md scope is
    build/deployment/runtime errors; no test-failure vocabulary found in the file.
  - Tests: `tests/skill-map/test_v2_relationships.py` — condition pattern matching against
    fixture failing/passing output, augments/remediates/dependsOn parsing incl. BuildError cases,
    index emission/determinism/staleness, and all 7 query CLI seed queries.

- _2026-08-09_ version bump — **rhize-context-manager** 0.9.0 → 0.9.1 (patch); marketplace 2.24.2 → 2.24.3.
- _2026-08-09_ version bump — **rhize-devflow** 2.10.1 → 2.10.2 (patch); marketplace 2.24.1 → 2.24.2.
- _2026-08-09_ version bump — **seo-aeo-geo** 1.3.0 → 1.3.1 (patch); marketplace 2.24.0 → 2.24.1.
- _2026-08-09_ version bump — **rhize-ops** 0.7.0 → 0.8.0 (minor); marketplace 2.23.2 → 2.24.0.
- **Skill map: third-party plugin/skill inventory in the local overlay (origin-aware resolved
  map).** `scripts/build_local_skill_map.py` now scans every plugin installed on the machine and
  enabled (via the merge of `~/.claude/settings.json`'s `enabledPlugins` map with this repo's
  `.claude/settings.local.json` override) whose marketplace is not this repo's own — e.g. `ecc`,
  `sanity`, `humanizer` — and emits `origin: "third-party"` `plugin`/`skill`/`command` nodes plus
  `contains` edges into `skill-map.local.json` and `skill-map.resolved.json` only. Lets Rhize
  plugins be checked for overlap/complementarity against what's actually installed alongside them,
  not just against each other. Id convention: `plugin:<marketplace>/<name>`,
  `skill:<marketplace>/<plugin>/<skill-dir>`, `command:<marketplace>/<plugin>/<command-stem>` —
  collision-proof against this repo's own bare `plugin:<name>` ids. Descriptions are truncated to
  ~200 chars; a plugin whose cached install path is missing, or a source file that can't be read,
  is skipped and counted (never a build failure) in `local.json`'s `thirdParty.summary`. The
  committed `generated/skill-map.static.json` is untouched — this inventory is local-overlay/
  resolved only, since the installed set is machine-specific. See "Third-party ecosystem
  inventory" in `docs/skill-map.md`.

- **Skill map: `extends` + `precedes` edge types (schema 1.1).** `extends` records deliberate
  layering — a specialized skill deepening a base skill's domain (directional, specialized→base;
  not duplication, not a runtime dependency) — parsed from a new `metadata.rhize.extends`
  frontmatter field and capped at chain depth 2 (a BuildError past that, and on any cycle).
  `precedes` records real ordered-workflow sequencing, hand-declared in
  `catalog/skill-relations.json`. Also adds an optional node `origin: "rhize" | "third-party"`
  property (nodes without it are implicitly `"rhize"`) for a later lane to populate in the local
  overlay only.
  - Tagged: `rhize-context-manager`'s `context-compression`/`context-degradation`/
    `context-optimization` each extend `context-fundamentals`; `rhize-devflow`'s
    `error-lifecycle-management`/`data-mutation-consistency`/`sentry-instrumentation` each extend
    `dev-flow-foundations`; `obsidian-second-brain`'s `obsidian-bases`/`json-canvas` each extend
    `obsidian-markdown`.
  - `catalog/skill-relations.json` gained `precedes` edges for `project-launcher`'s command
    pipeline: `write-prd` → `grill-prd` → `scaffold-gsd`.
  - Consumers: `session-disclosure.js` compacts a matched base and its matched extenders into one
    line (`- plugin:base — matches ... (+N deeper: name, name)`) instead of a line per extender.
    `skill-router.js` breaks a base/extender scoring tie in the extender's favor (the more specific
    skill) whenever the extender's score is at least the base's — max-one-suggestion and the
    2-signal threshold are unchanged.
- _2026-08-09_ version bump — **obsidian-second-brain** 1.3.0 → 1.3.1 (patch); marketplace 2.23.1 → 2.23.2.
- _2026-08-09_ version bump — **rhize-devflow** 2.10.0 → 2.10.1 (patch); marketplace 2.23.0 → 2.23.1.
- _2026-08-09_ version bump — **rhize-context-manager** 0.8.0 → 0.9.0 (minor); marketplace 2.22.0 → 2.23.0.
- **Skill-map phases 3–5 release (all six plugins bumped, 2026-08-09).**
  - *Phase 3a — local overlay (rhize-ops 0.7.0).* `skill-monitor/monitor.py` now aggregates
    session-level skill co-occurrence (counts only — no prompt text, no project paths) into
    `data/skill-cooccurrence.json`; new `scripts/build_local_skill_map.py` joins that snapshot,
    the enabled-plugin set, and the stack config into `~/.claude/context-manager/skill-map.{local,resolved}.json`,
    degrading to the static map when any input is absent.
  - *Phase 3b — stack-aware disclosure (rhize-context-manager 0.8.0; seo-aeo-geo 1.3.0,
    obsidian-second-brain 1.3.0, project-launcher 1.7.0, rhize-devflow 2.10.0).* New auto-wired
    `session-disclosure.js` SessionStart hook fingerprints the repo's stack and surfaces up to 8
    map-relevant skills — silent when no stack is detected. The four per-plugin unconditional
    SessionStart banners were removed (hint hooks preserved); the now-orphaned
    `{seo,obsidian,launcher}-context.md` banner files were deleted in this release. `/start` and
    `context-stack` now name the skill map as their routing substrate.
  - *Phase 4b — governance wiring.* weekly-skill-audit gained step 0 (map rebuild +
    `--check-stale` gate — audit commits the fix then stops on staleness — and skill-forge drift
    checks over `fork-of` edges); `/learn-harvest` gained a `routing-miss` signal (skills used but
    structurally unroutable) feeding the refinement queue with map/tag-targeted fixes.
  - *Phase 5 — generated docs + vault.* `scripts/render_skill_map_docs.py` manages
    `<!-- SKILL-MAP -->` sections in all plugin READMEs, the root Plugin Catalog, and
    `generated/SKILL-CATALOG.md` (idempotent; refuses on missing markers);
    `scripts/publish_skill_map_vault.py` publishes 39 per-skill notes plus `Skill Map.base` and
    `Skill Map.canvas` to the Obsidian vault (path resolved locally, never committed).
- _2026-08-09_ version bump — **rhize-ops** 0.6.0 → 0.7.0 (minor); marketplace 2.21.0 → 2.22.0.
- _2026-08-09_ version bump — **project-launcher** 1.6.0 → 1.7.0 (minor); marketplace 2.20.0 → 2.21.0.
- _2026-08-09_ version bump — **obsidian-second-brain** 1.2.0 → 1.3.0 (minor); marketplace 2.19.0 → 2.20.0.
- _2026-08-09_ version bump — **seo-aeo-geo** 1.2.0 → 1.3.0 (minor); marketplace 2.18.0 → 2.19.0.
- _2026-08-09_ version bump — **rhize-devflow** 2.9.0 → 2.10.0 (minor); marketplace 2.17.0 → 2.18.0.
- _2026-08-09_ version bump — **rhize-context-manager** 0.7.0 → 0.8.0 (minor); marketplace 2.16.0 → 2.17.0.
- _2026-08-09_ version bump — **rhize-context-manager** 0.6.0 → 0.7.0 (minor); marketplace 2.15.0 → 2.16.0.
- **Phase 2 (items 2-3), map-driven skill router (rhize-context-manager).** `hooks/skill-router.js`
  (Node, no deps) replaces the keyword-grep `skill-suggester.sh` on `UserPromptSubmit`: it reads
  the compiled skill-map artifact (`~/.claude/context-manager/skill-map.resolved.json`, falling
  back to `skill-map.static.json`), ranks topic/stack-tag and skill-name word matches against the
  prompt, and surfaces at most one suggestion via `hookSpecificOutput.additionalContext` — never
  more than one, and never on a single weak match (2+ distinct matching signals required to fire
  at all, per the plan's "Router noise" risk). Fails silently (exit 0, no output) if the map is
  missing, unreadable, or corrupt, or if a plugin install can't see this repo's `generated/`
  directory. `scripts/build_skill_map.py` gained an `--install` flag that copies the built
  artifact to `~/.claude/context-manager/skill-map.static.json` for exactly that installed-plugin
  case; the default deterministic output path is unchanged. `skill-suggester.sh` removed
  (`git rm`); `setup/manifest.json`'s opt-in entry repointed from it to `skill-router` (still
  opt-in, `default: false`). Timed ~50ms warm (budget: <150ms). Docs updated:
  `rhize-context-manager/{README,GUIDE}.md`, `skills/context-engineering/SKILL.md`,
  `docs/skill-map.md`, `generated/README.md`. New test: `tests/skill-map/test_router.js`
  (matched/unmatched/corrupt-map/missing-map cases, isolated via a temp `HOME`).
- **Phase 2.1 hook-ownership cleanup (rhize-devflow 2.9.0 / rhize-context-manager 0.6.0).** The plan premise ("6 hooks left behind by the 2.5.0 migration, all move to `rhize-context-manager/hooks/`") only held for 2 of 6 — verified before executing: `context-engineering__duplicate-check.sh`, `pre-commit-guard.sh`, `session-init.sh`, and `skill-suggester.sh` already had live, fully-wired counterparts at `rhize-context-manager/skills/context-engineering/hooks/*.sh` (declared in that plugin's `setup/manifest.json`, documented in its README/GUIDE/SKILL.md) — two byte-identical, two strictly newer there. Relocating the devflow copies would have created a third, unwired duplicate of each, which the marketplace's own Curation Rule exists to prevent. Retired (`git rm`) rather than relocated; rhize-devflow's README/GUIDE/hooks.json now redirect to the context-manager copies instead of documenting a file that no longer lives there. The other two, `skill-refinement__refinement-detector.sh` and `skill-refinement__session-end.sh`, were genuine orphans with no counterpart anywhere — moved+renamed to `rhize-context-manager/hooks/refinement-pipeline__{refinement-detector,session-end}.sh` (matching the `refinement-pipeline` skill that now owns the design), documented as opt-in (not wired) in that plugin's README/GUIDE/hooks.json. Both hooks' suggestion text updated from a bare `npx @rhize/skill-forge refine` to `/rhize-context-manager:learn-harvest` → `/skill-refine review`, matching the gated queue/re-gate trust model the `refinement-pipeline` skill actually documents; `session-end.sh`'s stale in-file comment pointing at `rhize-devflow/setup/manifest.json` was corrected. The manifest gap this originally left open was closed in the same release: `rhize-devflow/setup/manifest.json` dropped the 6 dead entries (10 → 4 items, plus the orphaned `@rhize/skill-forge` dependency block), and `rhize-context-manager/setup/manifest.json` gained opt-in entries for the two arrived hooks (4 → 6 items), so `/rhize-setup` offers exactly the hooks that exist.
- _2026-08-09_ version bump — **rhize-context-manager** 0.5.0 → 0.6.0 (minor); marketplace 2.14.0 → 2.15.0.
- _2026-08-09_ version bump — **rhize-devflow** 2.8.0 → 2.9.0 (minor); marketplace 2.13.0 → 2.14.0.
- _2026-08-04_ version bump — **rhize-ops** 0.5.0 → 0.6.0 (minor); marketplace 2.12.0 → 2.13.0.
- _2026-08-04_ version bump — **rhize-context-manager** 0.4.0 → 0.5.0 (minor); marketplace 2.11.0 → 2.12.0.
- _2026-08-04_ version bump — **rhize-devflow** 2.7.0 → 2.8.0 (minor); marketplace 2.10.0 → 2.11.0.
- _2026-08-04_ version bump — **project-launcher** 1.5.2 → 1.6.0 (minor); marketplace 2.9.0 → 2.10.0.
- _2026-08-04_ version bump — **obsidian-second-brain** 1.1.5 → 1.2.0 (minor); marketplace 2.8.0 → 2.9.0.
- _2026-08-04_ version bump — **seo-aeo-geo** 1.1.3 → 1.2.0 (minor); marketplace 2.7.0 → 2.8.0.
- **Marketplace-wide: dependency-registry + hub + model-routing release.** (1) `setup/manifest.json` (schema 1, unchanged) gains an optional top-level `"dependencies"` array — name/kind (plugin|cli|mcp|data)/purpose/required/degradedBehavior/replacement with an explicit reinventing-the-wheel warning — documented in `rhize-ops/README.md`; `/rhize-ops:rhize-setup` gains a dependency-check step (new step 3) that probes presence and offers install-now / proceed-degraded / adopt-replacement before the opt-in hook menu. Root README gains a Dependency matrix and marks **rhize-ops as the hub plugin** (recommended base install — hosts the fleet wizard and cost/ROI reporting; every other plugin degrades gracefully without it); the other five READMEs gain a short "Fleet setup" note. (2) Hook input parsing hardened repo-wide: every grep/sed JSON-scraping hook converted to `python3 json.loads` (grep/sed extraction truncated at the first escaped quote inside string values — real code payloads silently missed detections, reproduced pre-fix); devflow's `pre-commit-guard`/`skill-suggester` also ported to the `hookSpecificOutput.additionalContext` output contract to match their context-manager twins. (3) Model routing per the quality-vs-cost convention: verifier subagent promoted to the capable tier (opus) as the final commit gate; graphify's extraction fan-out pinned to haiku (largest cost leak found by audit); mechanical commands pinned haiku (seo: rank-track/serp-check/backlink-audit/ai-visibility; obsidian: vault-capture/daily/recall/search; context-hygiene; bump-version) and context-doctor pinned sonnet.
- **rhize-context-manager (0.5.0):** manifest dependencies (skill-forge + headroom required — needed by `/skill-refine` and `/learn-harvest`; harness-audit/claude-mem/OpenWolf/Serena/CodeGraph/Graphiti optional); refinement cadence split — harvest now runs via the standalone daily `daily-learn-harvest` routine (delegating collection to a haiku subagent), the weekly drain keeps the capable model; `/context-doctor` gains a weekly cadence via the new Thursday `weekly-context-doctor` routine (drift-only reporting); docs synced (refinement-pipeline, learn-harvest, context-doctor, graphify haiku dispatch).
- **rhize-ops (0.6.0):** first `setup/manifest.json` (5 optional scorecard data sources incl. the ecc cost-tracker denominator); `/rhize-setup` dependency-check step; skill-monitor README workflow renumbered after the harvest moved out of the weekly audit (drain = step 8, cost reports = step 9).
- **rhize-devflow (2.8.0):** manifest dependencies (Sentry/Vercel/GitHub/Chrome DevTools MCP required; skill-forge optional); 7 guard hooks hardened to real JSON parsing; verifier agent → opus final-gate tier.
- **seo-aeo-geo (1.2.0) / obsidian-second-brain (1.2.0) / project-launcher (1.6.0):** manifest dependencies (DataForSEO MCP required — static-analysis surfaces still work without it; obsidian-mcp-server + Obsidian CLI required, Defuddle/qmd optional; project-launcher's integrated MCP servers + external skills, all optional) plus the Fleet setup README notes and the model pins above.
- _2026-08-04_ version bump — **rhize-ops** 0.4.1 → 0.5.0 (minor); marketplace 2.6.0 → 2.7.0.
- _2026-08-04_ version bump — **rhize-context-manager** 0.3.0 → 0.4.0 (minor); marketplace 2.5.0 → 2.6.0.
- _2026-08-04_ version bump — **rhize-devflow** 2.6.1 → 2.7.0 (minor); marketplace 2.4.3 → 2.5.0.
- _2026-08-04_ version bump — **project-launcher** 1.5.1 → 1.5.2 (patch); marketplace 2.4.2 → 2.4.3.
- _2026-08-04_ version bump — **obsidian-second-brain** 1.1.4 → 1.1.5 (patch); marketplace 2.4.1 → 2.4.2.
- _2026-08-04_ version bump — **seo-aeo-geo** 1.1.2 → 1.1.3 (patch); marketplace 2.4.0 → 2.4.1.
- **Marketplace-wide (2026-08-04): guardrail-tier release.** New shared convention: each plugin may ship `setup/manifest.json` (schema 1) cataloging its opt-in hooks with tier metadata (T3 = advisory context-injection, T4 = blocking); the new `/rhize-ops:rhize-setup` wizard discovers manifests, reads back effective hook state, and wires user-selected items into a project's `.claude/settings.json` after a stdin smoke test. Canonical schema spec lives in `rhize-ops/README.md`.
- **rhize-ops (0.5.0):** `/rhize-setup` fleet guardrail wizard (above); `skill-monitor/savings_scorecard.py` — two-tier (Measured vs. Estimated, never summed together) token/cost savings report across ecc costs.jsonl, rtk, Headroom, claude-mem, OpenWolf, and the headroom-learn digest, with per-source coverage lines; `skill-monitor/skill_roi.py` — joins skill invocations to per-session cost (latest-row-per-session) for a cost-attribution ROI table with prune-candidate flags; `weekly-skill-audit` scheduled task gains step 10 running both scripts (weekly + on-demand cadence; deliberately no per-session wiring).
- **rhize-context-manager (0.4.0):** new `/context-setup` repo-level wizard — scans the repo via `config_generator.py` (fixed: `--scan .` produced an empty project name), probes the active stack, proposes a tailored per-repo layer config, and writes `stack.config.json` on confirmation (config only; hook wiring belongs to `/rhize-setup`); `stack.config.schema.json` v2 adds `repoOverrides`; `/context-doctor` now persists each run to `~/.claude/context-manager/doctor/`, prints a delta vs. the prior run, and chains into `ecc:harness-audit` when available; `setup/manifest.json` catalogs the four context-engineering hooks as opt-in items — two of which were fixed (`pre-commit-guard.sh` emitted stderr the model never sees, now proper `hookSpecificOutput`; `skill-suggester.sh` read a nonexistent `user_prompt` field — permanent no-op — now reads `prompt`); removed the drifted duplicate command copies under `skills/context-engineering/commands/` (registered `commands/` versions were already supersets).
- **rhize-devflow (2.7.0):** `setup/manifest.json` catalogs all 10 opt-in guard hooks for `/rhize-setup`; fixed 4 hooks that could never fire (`skill-suggester` wrong stdin field, `sentry-stale-data` read positional args Claude Code never passes, `prewrite-check` used GNU-only `grep -oP` that BSD grep rejects, `session-end` read env vars Claude Code never sets — now parses the transcript JSONL); fixed `duplicate-check.sh`'s pattern builder (`tr ' ' '.*'` only maps single chars, so kebab-vs-PascalCase duplicates were never caught — verified blocking now).
- **seo-aeo-geo (1.1.3) / obsidian-second-brain (1.1.5) / project-launcher (1.5.2):** hook reliability fix — PreToolUse/PostToolUse hooks were silently dead since inception (read a `$TOOL_INPUT` env var Claude Code never sets, and printed plain stdout the model never sees). Rewritten as stdin-reading scripts under `hooks/scripts/` emitting proper `hookSpecificOutput.additionalContext`, each verified with matching/non-matching payloads. Each plugin also ships an (empty) `setup/manifest.json` adopting the new convention.
- _2026-08-03_ version bump — **rhize-context-manager** 0.2.0 → 0.3.0 (minor); marketplace 2.3.3 → 2.4.0.
- **rhize-context-manager (0.3.0):** gated skill-refinement pipeline — `headroom learn` output redirected from CLAUDE.md into a human-triaged queue (`~/.claude/context-manager/refinement-queue.jsonl`), drained through `@rhize/skill-forge evolve` (SkillOpt-Sleep + safety re-gate). New commands: `/learn-harvest` (collect signals: headroom learn dry-run, claude-mem observations, skill-monitor snapshots; queue-only, never writes context files) and `/skill-refine` (`review` = human triage, `run` = headless-safe gated evolve pass; auto-promote restricted to ALLOW + score-improved + SKILL.md-text-only — proposals touching scripts/hooks/allowed-tools always HOLD). New `refinement-pipeline` skill documents the two-gate trust model. One-time cleanup: the repo CLAUDE.md's five accumulated "Headroom Learned Patterns" sections (2026-06-16 → 2026-07-27) consolidated into one deduped section (308 → 155 lines); future learn output goes to the queue. README/GUIDE synced (also corrects the stale ecc-skill listings from the 0.2.0 curation pass).
- _2026-08-02_ version bump — **rhize-devflow** 2.6.0 → 2.6.1 (patch); marketplace 2.3.2 → 2.3.3.
- _2026-08-02_ version bump — **rhize-ops** 0.4.0 → 0.4.1 (patch); marketplace 2.3.1 → 2.3.2.
- **rhize-ops, rhize-devflow:** `/simplify` pass over the 0.4.0/2.6.0 changes above — `delegate-setup.md`'s legacy-shape migration mapping was restated three times across two files; step 1 now points at SKILL.md's canonical version instead of re-deriving it. SKILL.md's "Resolve the Recipient" step was missing a tie-break for an ambiguous multi-recipient name match (a gap the multi-recipient feature itself introduced) — added a STOP-and-confirm step between the exactly-one-match and no-match cases. rhize-devflow's README `devflow-setup` section trimmed to a pointer at the command's own doc instead of restating it. Patch-bumped both plugins so the installed plugin cache (which is version-pinned) actually picks up these doc fixes.
- _2026-08-02_ version bump — **seo-aeo-geo** 1.1.1 → 1.1.2 (patch); marketplace 2.3.0 → 2.3.1.
- **seo-aeo-geo:** `GUIDE.md`'s command examples now use `example.com` instead of `rhize.media` as the illustrative domain (`/seo-audit rhize.media` → `/seo-audit example.com`, and the same swap across `/keyword-research`, `/serp-check`, `/backlink-audit`, `/content-optimize`, `/competitor-analysis`, `/ai-visibility`, `/technical-audit`, and `/rank-track` examples) — the doc examples shouldn't imply the plugin only works against Rhize's own domain.
- _2026-08-02_ version bump — **rhize-devflow** 2.5.0 → 2.6.0 (minor); marketplace 2.2.0 → 2.3.0.
- **rhize-devflow:** new `/rhize-devflow:devflow-setup` command formalizes the per-machine local-tenant-file convention (`*.local.md` files, e.g. `.claude/error-patterns.local.md`) that already existed informally — creates a zero-real-data template in the target repo's `.claude/`, verifies (and fixes) that the path is gitignored, and documents that these files are machine-local tenant data that never ship. README.md's Commands section now references the convention. Also genericized the one remaining client-identifying reference in the public repo: `CHANGELOG.md`'s "a real 2026-07-28 failure in `clients/glenwood`" line now reads "a real 2026-07-28 failure on a client project" — a repo-wide re-scan for other client identifiers (client/domain names, personal emails) found no further hits in tracked files.
- _2026-08-02_ version bump — **rhize-context-manager** 0.1.0 → 0.2.0 (minor); marketplace 2.1.0 → 2.2.0.
- **rhize-context-manager:** the `context-stack` skill now reads an optional `$HOME/.claude/rhize-context-manager/stack.config.json` (schema: `skills/context-stack/references/stack.config.schema.json`) as the authoritative tool-stack inventory when present — an ordered list of layers (`name`, `layer`: wire/memory/file-intel/index/cli, `scope`: global/per-repo, optional `repos`/`endpoints`, `notes`) — falling back to the skill's built-in default inventory (Headroom, RTK, claude-mem, Graphiti, OpenWolf, Serena, CodeGraph, graphify, Obsidian) when the config is absent. The shipped default inventory in SKILL.md is unchanged. The live config was populated with the actual Rhize stack transcribed from that same inventory.
- _2026-08-02_ version bump — **rhize-ops** 0.3.1 → 0.4.0 (minor); marketplace 2.0.1 → 2.1.0.
- **rhize-ops:** `delegate-to-teammate` now supports **multiple recipients**. The config's single `recipient` object becomes a `recipients` map keyed by short lowercase identifier, with `defaultRecipient` naming which one to use when the delegator doesn't name a person; each recipient carries its own `slack: { channel, channelId }` since the notification channel is recipient-specific, while `jira`/`projectMapping`/`inferenceRules` and the top-level `slack.status`/`slack.workspace` stay workspace-scoped. SKILL.md gained a "Resolve the Recipient" step: named-teammate references are matched case-insensitively against `recipients[*].name`/key, and a named person with no match now stops and points at `/rhize-ops:delegate-setup` instead of silently falling back to the default. `delegate-setup.md` gained an "add another teammate" path and a migration note. Legacy single-`recipient` configs are read as `recipients: { default: <that recipient> }` — no forced file rewrite. The live `~/.claude/rhize-ops/delegate.config.json` was migrated to the new shape (`defaultRecipient: "tom"`, backed up as a sibling `.bak-20260802`); every prior value survives verbatim.
- _2026-08-02_ version bump — **obsidian-second-brain** 1.1.3 → 1.1.4 (patch); marketplace 2.0.0 → 2.0.1.
- **rhize-context-manager (new plugin, 0.1.0):** context engineering & optimization — compression, management, retrieval, and storage. Orchestrates (does not vendor) the Rhize context stack: Headroom wire compression, claude-mem global memory, OpenWolf per-repo file intel, Serena/CodeGraph semantic code navigation, RTK CLI compression, graphify knowledge graphs, and opt-in Graphiti temporal knowledge-graph memory (`graphiti-memory` skill — adoption approved, not a dependency). Ships the Rhize-authored `context-stack` routing/coexistence skill, a `/context-doctor` stack health-check command, the `graphify` skill promoted from user-level, and an 11-skill curated third-party library ingested through `@rhize/skill-forge` (safety-gated, provenance in `skills/SOURCES.md`): context-fundamentals, context-degradation, context-compression, context-optimization, memory-systems, filesystem-context, tool-design (muratcankoylan/Agent-Skills-for-Context-Engineering) and iterative-retrieval, strategic-compact, context-budget, token-budget-advisor (everything-claude-code).
- **rhize-context-manager:** `hooks/context-window-monitor.js` — a Rhize-owned `PreToolUse` hook (matcher `Edit|Write`) that replaces ECC's `pre:edit-write:suggest-compact`. Upstream sizes the context window by sniffing the model id for a literal `[1m]` marker and otherwise assuming 200k; Opus 5 carries a 1M window and no marker, so it reported **97% usage on a session genuinely at 20%** (verified against the client readout 2026-07-28) — wrong for every turn below 200k, and self-correcting only above it, which is why the message alone never gave it away. The replacement resolves strongest-signal-first: env override (`RHIZE_CONTEXT_WINDOW_TOKENS`, plus ECC's own vars so the two can never disagree) → `[1m]` marker → **verified known-model table** → observed usage already past 200k → 200k default. The table is the capability a marker sniff structurally cannot have; it is deliberately sparse, since a wrong entry outranks the evidence beneath it. Ships a 9-case `--self-test` including the exact 197.3k-on-Opus-5 regression, and was verified end-to-end against a live transcript with and without the env override. **ECC's hook must be disabled** (`ECC_DISABLED_HOOKS=pre:edit-write:suggest-compact`) or both fire.
- **rhize-context-manager:** `learning-curation` skill (Rhize-authored, not ingested — no `SOURCES.md` entry). The *editorial* layer above `memory-systems`: given a session learning, decide whether it deserves persistence at all, and where to put it so it actually fires. Three gates — drop tests (if a mechanism could enforce it, build the mechanism instead of the memo), a search-before-drafting pass that resolves duplicates and **contradictions in the same edit**, and a **retrieval-cue placement test**. The cue test is the load-bearing idea: reference material is only consulted when the failure moment emits a searchable signal, but some failures emit none — a silent wrong conclusion does not cue a lookup — so those need always-loaded placement via a tripwire pointing at a reference file, not a reference entry alone. Also covers generalizing accumulated same-shape corrections into the one rule they are instances of (otherwise the store grows a fourth and fifth instance forever), phrasing rules by the *failure behavior* rather than the remedy so a session mid-mistake recognizes itself, mandatory stop conditions on every "do more of X" rule, and this technique's own failure modes (over-extraction, contradiction accretion, eternalizing the temporary, meta-bloat). Derived from a real 2026-07-28 failure on a client project where a session declared a vendor setup step impossible and shipped a handoff document instead of the feature. Cross-references `memory-systems` (storage layer) and `context-optimization`; budgeting and compaction now come from `ecc@everything-claude-code` (see Removed).

### Fixed

- **rhize-ops (skill-monitor):** `monitor.py`'s defensive `(uuid, session_id)` dedup no longer
  flags Claude Desktop's own session-transcript replay as an "investigate"-worthy anomaly.
  Root-caused 2026-08-09: for `entrypoint: claude-desktop` sessions, an assistant turn recorded
  early in a session's main `.jsonl` can reappear later in the *same file* — identical on
  uuid/requestId/parentUuid/timestamp/content, differing only in `cwd` (re-resolved against
  whichever root is active at replay time) and sometimes gaining a `slug` field once the session
  is auto-named — because the desktop app re-serializes session state into the transcript. All 22
  duplicates in a `--days 7` run were confirmed to share this exact shape. Added a third expected
  category (`_is_desktop_main_replay`) alongside the existing main+subagent and
  acompact+acompact cases; a run that hits it now prints an informational
  `· collapsed N duplicate events from Claude Desktop session-transcript replay` line instead of
  `! warning: ... — investigate`. Host-CLI main+main duplicates (no known replay mechanism) still
  trip the loud warning. No change to what gets deduped or to reconciled event counts — only to
  classification and messaging. Documented in `rhize-ops/skill-monitor/README.md`'s new
  "Duplicate-event dedup" subsection.
- **skill-map:** `fork-of` edges no longer share one marketplace-level `external` node with no
  `path`/`url` — every one of `rhize-context-manager`'s 7 non-retired `SOURCES.md` entries
  (context-fundamentals, context-degradation, context-compression, context-optimization,
  memory-systems, filesystem-context, tool-design) reported `upstream-unreachable` from
  `@rhize/skill-forge watch`, because its drift checker resolves the upstream file from
  `node.url ?? node.path`, and a single node representing the whole marketplace can't carry a
  resolvable path for 7 distinct upstream files. `scripts/build_skill_map.py`'s `load_sources_md()`
  now mints one `external:<marketplace-name>/<upstream-skill-path>` node **per fork**, each
  carrying `path` = the ledger's recorded `Source` value with `/SKILL.md` appended and the home
  directory rewritten to `~` for portability. No schema change was needed (`path` was already a
  generic node property, and the `external:<name>` id pattern already allows `/`). Verified against
  a synthetic fixture that the drift checker now genuinely resolves and hashes an upstream file
  (`in-sync` when content matches); on this machine all 7 real edges still report
  `upstream-unreachable` because the `context-engineering-marketplace` plugin has since been
  uninstalled locally — that is now correct, honest reporting of a missing upstream copy, not the
  structural bug this fixes.
- **obsidian-second-brain (1.1.4):** removed the hard `"dependencies": ["qmd@qmd"]` declaration from `plugin.json` — it made the plugin refuse to load ("Dependency qmd@qmd is not installed") on any machine without the `qmd` binary, even though qmd is optional everywhere else in the plugin: the README and every affected command already document graceful fallback to keyword/MCP search when qmd isn't present. The plugin.json schema (`schemas/plugin.schema.json` in `everything-claude-code`) has no optional-dependency field, so there was no declarative alternative — the field is simply removed. README's "qmd Semantic Search" section reworded from "dependency" to "optional" to match.

### Removed

- **rhize-context-manager:** the four skills ingested from `everything-claude-code` are removed — `strategic-compact`, `context-budget`, `iterative-retrieval`, `token-budget-advisor`. With `ecc@everything-claude-code` enabled these were duplicates competing for the same invocations, and inspection showed the copies carried no Rhize value: three differed from upstream **only in frontmatter indentation**, and `strategic-compact` had actively **drifted behind** — ecc 2.0.0 gained a context-size primary signal with window-scaled thresholds (160k on a 200k window, 250k on 1M) plus `COMPACT_CONTEXT_THRESHOLD`/`COMPACT_CONTEXT_INTERVAL`, while the fork still had the old tool-count-only logic. The vendored copy was strictly worse than the thing it vendored, and that stayed invisible until someone diffed it. `SOURCES.md` entries are **kept and annotated** rather than deleted — the ledger records the retirement decision, not just the ingestion. Establishes the marketplace curation rule now in `CLAUDE.md`: **Rhize skills close gaps in proven plugins; they never re-ship them.** Candidate for enforcement in `@rhize/skill-forge`'s ingest gate.
- **rhize-context-manager:** the user-level `~/.claude/skills/graphify/` copy is retired (moved to `~/.claude/skills/.retired-20260728/`) now that the plugin owns `graphify` — the two were byte-identical apart from two stale `.bak` files, so both being present meant two identical skills competing. The `/graphify` pointer in the user's global `CLAUDE.md` was updated in the same change; invocation is by skill name, so behavior is unchanged.

### Changed

- **rhize-devflow (2.5.0):** the `context-engineering` skill and its four session-lifecycle commands (`/start`, `/done`, `/context-hygiene`, `/impact-map`) moved to the new `rhize-context-manager` plugin. Breaking for command invocations: `/rhize-devflow:start` → `/rhize-context-manager:start` (same for the other three). rhize-devflow keeps error lifecycle, data-mutation consistency, Sentry, Chrome DevTools, Sanity house style, and dev-flow foundations.

### Fixed

- **rhize-context-manager:** `context-engineering`'s `context_analyzer.py` no longer sizes the context window from a model-family name. `CONTEXT_LIMITS = {"claude": 200_000}` cannot express Opus 5's 1M window, so any usage percentage derived from it overstated consumption ~5x and would have fired false "approaching limit" warnings for an entire run. Replaced with `resolve_context_limit()`, which reads the strongest available signal first: the `ECC_CONTEXT_WINDOW_TOKENS` / `CLAUDE_CODE_AUTO_COMPACT_WINDOW` env override (the same vars ECC's `suggest-compact` hook honors, so the two can never disagree about one session), then a `[1m]` marker in the model id, then observed usage already past 200k, and only then the family fallback. The family lookup also became a substring match — the old exact-key `.get()` dropped real ids like `claude-opus-5` to the 100k `default`, understating the window. The limit was assigned-but-never-read, so this was a latent defect, not an active one; it is fixed ahead of anyone wiring the percentage up. The live version of this same defect was in ECC's *hook*, not in any skill — the ingested `strategic-compact` skill is prose only — and is addressed by `context-window-monitor.js` above.

### Removed

- **rhize-meta:** the entire plugin is removed from the marketplace — `skill-refinement` (skill + its `refine-skills`, `review-patterns`, `apply-generalization` commands), which is all that remained after the `rhize-skill-forge` removal below. The capability now ships as `skill-forge refine` in the `@rhize/skill-forge` npm package (`npx @rhize/skill-forge refine`), alongside the previously-ported `add`/`scan`/`find`/`ingest`/`watch`/`organize`/`audit`/`evolve` commands. The marketplace no longer includes a skill-governance plugin.
- **rhize-meta:** the `rhize-skill-forge` skill and its five commands (`forge-ingest`, `forge-scan`, `forge-watch`, `skill-find`, `skill-doctor`) — external-skill/MCP vetting, discovery, provenance, and drift-watching. All functionality is now parity-ported to the `@rhize/skill-forge` npm package (`npx @rhize/skill-forge` — commands: `add`, `scan`, `find`, `ingest`, `watch`, `organize`, `audit`, `evolve`). `rhize-meta` keeps only `skill-refinement` and its commands (`refine-skills`, `review-patterns`, `apply-generalization`).

### Changed

- _2026-07-20_ version bump — **rhize-meta** removed (was 2.0.0); marketplace 1.13.0 → 2.0.0 (major — plugin removal is breaking).
- _2026-07-20_ version bump — **rhize-meta** 1.3.1 → 2.0.0 (major — capability removal, see Removed); marketplace 1.12.1 → 1.13.0.
- **rhize-meta:** description/scope narrowed to skill-refinement only; README/GUIDE rewritten, `skill-refinement` SKILL.md's mention of the removed skill replaced with a pointer to the `@rhize/skill-forge` npm CLI's ingest flow. `project-launcher`'s skill-discovery/safety-gate step (SKILL.md) and the `rhize-visual-plan`/`project-launcher` provenance records (`SOURCES.md`, `SKILL.patch.md`) now point at the npm CLI instead of the removed `/rhize-meta:skill-find`/`skill-doctor`/`forge-ingest` commands. `rhize-devflow`'s README lineage notes updated to reflect the further move.

### Added

- _2026-07-16_ version bump — **rhize-ops** 0.3.0 → 0.3.1 (patch); marketplace 1.12.0 → 1.12.1.

### Fixed

- **rhize-meta:** `forge-ingest` queue drain now **re-verifies the safety scan** on each pending entry (`skill_safety.py` or `skill-forge scan --json` against the entry's `quarantinePath`/`installedPath`) instead of trusting `~/.skill-forge/queue.json`'s recorded verdict — the queue file is unsigned and user-writable, so its `safetyVerdict` is advisory only. Profile/overlap results are still reused. Updated in both `commands/forge-ingest.md` and the `rhize-skill-forge` SKILL.md "CLI pending queue" section.
- **rhize-ops:** `delegate-to-teammate` hardened against prompt injection from ingested session/vault/meeting-transcript content — added an explicit Content Trust Boundary so quoted content is never treated as instructions, and the only Slack mention is ever the configured recipient.
- Finished scrubbing personal identity (owner email/domain used as a worked example) and client example names (client/project names used as illustrative flavor text) missed by earlier passes, across `project-launcher`'s visual-plan reference docs and `rhize-meta`'s skill-refinement templates.

### Changed

- **rhize-ops:** `delegate-to-tom` renamed to `delegate-to-teammate` and made fully config-driven — no recipient name, Jira/Slack IDs, or project mapping is hardcoded in the skill anymore. Jira and Slack are each gated by an explicit `ready`/`incomplete`/`disabled` status so the skill skips gracefully instead of guessing when an integration isn't connected. Tool references switched from installation-specific connector-UUID-prefixed MCP tool names to capability-based discovery.
- **rhize-ops:** `skill-dashboard` now resolves its script/data paths via `${CLAUDE_PLUGIN_ROOT}` instead of an absolute local checkout path.
- **project-launcher:** the skill-discovery/safety-gate step now calls `rhize-meta`'s public commands (`/rhize-meta:skill-find`, `/rhize-meta:skill-doctor`) instead of shelling directly into `rhize-meta`'s scripts via a computed sibling-plugin path.
- **rhize-devflow:** `analyze_performance.js` now accepts `--root <path>` (default cwd) and scans conventional Next.js layouts (`app`/`src/app`, etc.) instead of assuming a fixed dual-repo directory structure.

### Fixed

- **rhize-devflow, rhize-meta, obsidian-second-brain:** removed a real client's production domain, repo names, and other real project/client names that had been used as illustrative example content across several skill docs and command examples — replaced with generic placeholders. No functional changes; these were documentation examples only.

### Added

- _2026-07-16_ version bump — **obsidian-second-brain** 1.1.2 → 1.1.3 (patch); **project-launcher** 1.5.0 → 1.5.1 (patch); **rhize-devflow** 2.4.0 → 2.4.1 (patch); **rhize-meta** 1.3.0 → 1.3.1 (patch); **rhize-ops** 0.2.0 → 0.3.0 (minor); marketplace 1.11.0 → 1.12.0.
- **rhize-ops:** `/rhize-ops:delegate-setup` — interview-driven wizard that resolves Jira/Slack identifiers via MCP where connected and writes `~/.claude/rhize-ops/delegate.config.json` (outside the repo). `references/delegate.config.schema.json` is a real Draft 2020-12 JSON Schema for that config.
- _2026-07-12_ version bump — **rhize-meta** 1.2.1 → 1.3.0 (minor); marketplace 1.10.0 → 1.11.0.
- _2026-06-16_ version bump — **rhize-meta** 1.1.0 → 1.1.1 (patch); marketplace 1.8.0 → 1.8.1.
- _2026-06-15_ version bump — **project-launcher** 1.2.1 → 1.3.0 (minor); **rhize-meta** 1.0.0 → 1.1.0 (minor); marketplace 1.7.0 → 1.8.0.
- **Skill discovery + safety (rhize-meta & project-launcher)** — `skills_sh.py` (skills.sh API: search / partner-audit / get / curated, Vercel OIDC auth), `skill_safety.py` (NVIDIA SkillSpector gate — BLOCK on HIGH/CRITICAL), and `skill_doctor.py` (setup check) under `rhize-meta/skills/rhize-skill-forge/scripts/`. Forge folds a mandatory two-layer safety gate (skills.sh partner audit + SkillSpector deep scan) into its decision step; project-launcher suggests + gates skills during scaffolding (reuses the rhize-meta scripts — no duplication). New commands `/rhize-meta:skill-find` and `/rhize-meta:skill-doctor`. Grounded against skills.sh/docs/api + the SkillSpector README; fail-safe when tools/token are absent.
- **Marketplace version-bump tooling** — `scripts/bump_version.py` (stdlib): `--auto` (detect plugins changed since last release + infer level from conventional commits), `--plugin/--level`, `--check`. Coordinates every `plugin.json` + the marketplace per-plugin **and top-level** version + CHANGELOG; never pushes. Adds `.githooks/pre-push` gate, `version-check` + `tag-release` CI, and the `/rhize-ops:bump-version` command. **Supersedes `scripts/bump-plugin.sh`** (per-plugin only — no top-level/CHANGELOG/auto/validate). Implements the ROADMAP item.
- _2026-06-15_ version bump — **rhize-ops** 0.1.1 → 0.2.0 (minor); marketplace 1.6.0 → 1.7.0.
- **New `rhize-meta` plugin** (v1.0.0) — promoted `rhize-skill-forge` and `skill-refinement` out of `rhize-devflow` into a dedicated meta-skills plugin so the coupled skill-governance toolchain lives in one place. **Breaking (namespace):** their commands moved from `/rhize-devflow:{forge-ingest,forge-scan,forge-watch,refine-skills,apply-generalization,review-patterns}` to `/rhize-meta:*`. rhize-devflow 2.2.0 → 2.3.0 (skills relocated); marketplace 1.5.0 → 1.6.0.
- **rhize-skill-forge set-level organizer mode** (rhize-devflow 2.1.0 → 2.2.0) — new stdlib scripts `index_skills.py` (capability registry), `overlap_scan.py --set-mode` (N-way internal-overlap), and `build_dependency_graph.py` (`consumes:` graph); `profile_skill.py` now also profiles plugins and MCP configs; `SOURCES.md` provenance ledger stood up; references `capability-schema.md`, `composition-patterns.md`, `drift-boundaries.md`. Drift detection consolidated to the single `ai-stack-version-drift` sensor (Forge `--check-drift` = on-demand classifier). Phase 3 productization gated, tracked as Jira RT-41.
- **Capability frontmatter on all 29 marketplace skills** — `tier`/`domain`/`maturity` added to every Rhize-authored skill so the organizer classifies them (0 untagged). Patch bumps: rhize-ops 0.1.0 → 0.1.1, seo-aeo-geo 1.1.0 → 1.1.1, obsidian-second-brain 1.1.1 → 1.1.2, project-launcher 1.2.0 → 1.2.1. Marketplace 1.4.0 → 1.5.0.
- **rhize-ops** plugin (v0.1.0) — operations skill set (internal delegation / hand-offs / team-workflow automation), distinct from `rhize-devflow` which is about building software. Houses **`delegate-to-tom`**, migrated out of the standalone `~/.claude/skills/delegate-to-tom/` (which is not version-controlled). The skill's frontmatter `name:` was changed from `rhize:delegate-to-tom` to a plain `delegate-to-tom` slug so its namespace derives from the plugin → canonical `rhize-ops:delegate-to-tom`. This resolves the alias fragmentation where the colon in a standalone skill name was sanitized into three different recorded names (`rhize:delegate-to-tom`, `rhizedelegate-to-tom`, `anthropic-skills:rhizedelegate-to-tom`). Marketplace bumped to 1.4.0.
- **rhize-devflow** plugin (v2.1.0) — consolidated development-workflow skill set migrated from the now-archived `CLAUDE-SKILLS` repo: `context-engineering`, `error-lifecycle-management`, `data-mutation-consistency`, `sentry-instrumentation`, `chrome-devtools-mcp`, `sanity-development`, `dev-flow-foundations`, `skill-refinement`, and the new **`rhize-skill-forge`** meta-skill (investigate & absorb external skills with provenance tracking). All 9 skills given valid YAML frontmatter + keyword-rich descriptions; commands namespaced `/rhize-devflow:*`. Marketplace bumped to 1.3.0.
- **rhize-review** skill — production merge-gate review orchestrator: scopes the diff, routes by stack to `ecc` specialist + security reviewers, aggregates findings at confidence ≥80, and returns a single merge verdict. Tracked here and symlinked into `~/.claude/skills/rhize-review`.
- **obsidian-second-brain** plugin (v0.2.0) — CLI operations, markdown syntax, Bases databases, JSON Canvas, web clipping, second brain methodology, note templates, research pipelines, and knowledge graph workflows
- Obsidian prerequisites section in marketplace README
- **second-brain** skill — Zettelkasten, PARA, MOCs, progressive summarization, atomic notes methodology
- **vault-templates** skill — Note archetypes for meeting notes, book reviews, project briefs, weekly reviews, permanent notes, person notes
- `/vault-research` command — End-to-end research pipeline: clip → summarize → connect to vault
- `/vault-connect` command — Find and build missing links between related vault notes
- `/vault-review` command — Periodic review cycles (daily, weekly, monthly) with theme detection and forgotten note resurfacing
- **vault-alignment** skill — Vault health assessment across 5 dimensions (structure, connectivity, consistency, processing, plugins), drift detection patterns, improvement prioritization, and migration strategies
- `/vault-setup` command — Interactive setup wizard: discovery interview → vault audit → personalized archetype generation → woven plugin recommendations → scaffolding → opt-in migration
- `/vault-align` command — Ongoing vault health monitor with 4 modes: check (health report with focused sub-modes for tags, orphans, links, structure), fix (highest-impact fix), migrate (aggressive batch reorganization), plugins (audit and recommend)
- Community plugin recommendation system — Dataview, Kanban, Templater, Calendar, Tasks with woven inline recommendations during setup
- `_vault-setup-log.md` archetype persistence — bridges setup wizard to ongoing alignment

### Changed

- **nextjs-rhize-stack hookify rules** — `pr-review-on-create` now invokes `/rhize-review` first (prior review skills kept as fallback); `block-direct-push-to-main` regex now also catches the `git -C <path> push` form
- Updated marketplace manifest and README to reflect multi-plugin catalog
- Bumped obsidian-second-brain from v0.2.0 to v0.3.0
- Updated GUIDE.md with Setup & Alignment section and community plugins guide
- Consolidated `/vault-organize` into `/vault-align` — all vault analysis and organization now lives in one command with granular focus options (`check tags`, `check orphans`, `check links`, `check structure`, `check full`)

## [1.0.0] - 2026-03-14

### Added
- Initial marketplace release
- **seo-aeo-geo** plugin (v1.0.0) — SEO, AEO, and GEO auditing powered by DataForSEO API with Next.js + Sanity CMS best practices
- Marketplace manifest for Claude plugin discovery
- Plugin evaluation framework with trigger and quality benchmarks
