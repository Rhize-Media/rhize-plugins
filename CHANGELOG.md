# Changelog

All notable changes to the Rhize Plugins marketplace are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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
