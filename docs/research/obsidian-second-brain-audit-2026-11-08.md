# Obsidian Second Brain: capability audit and adoption plan

**Historical baseline audit.** The later [compiler batch implementation](obsidian-compiler-batch-review-2026-11-08.md)
addresses several findings below and supersedes the initial indexing-only version proposal.

Audited 2026-11-08 against published main `3b6f073b93388fc929a81e535cffe344ec334dce`.
This report concerns published source and isolated fixtures. It does not establish a user's
installed plugin version, host discovery, vault configuration, running jobs or retrieval quality.

## Version evidence

- Claude and Codex manifests both publish **1.9.0**. The plugin's latest source commit at the
  audited main is `c228477` (2026-10-10). Marketplace tag is **v2.117.2**; marketplace and
  individual plugin versions are different version streams.
- [Published CI](https://github.com/Rhize-Media/rhize-plugins/actions/runs/42290054272) succeeded
  for the audited main. No GitHub Release objects were returned; version evidence comes from
  manifests, commits and the Git tag, not a release download.
- This review prepares **1.9.1**, marketplace **2.117.3**, using the repository bump script.
  It is not a claim that either version has been published or installed.

## What actually works, and what remains gated

| Capability | Evidence and boundary | Best initial use |
| --- | --- | --- |
| Capture, daily notes, review | Agent command instructions using MCP/CLI; some daily-note paths create absent notes. No resident service is bundled. | Interactive capture and a report-only review over existing notes. |
| Search/recall/connections | Optional qmd; MCP/CLI fallback. Link suggestions need review. Old instructions used obsolete CLI/package forms and unsafe whole-vault roots. | One approved project scope; cite live notes and benchmark a small question set. |
| Knowledge compiler | Deterministic Python engine. One source and one page per proposal; line-range/revision hashes, strict manifest, exact diff, lock, compare-and-swap, expiry, recovery. | One non-sensitive source in an isolated pilot, preview first. |
| Apply | Engine verifies preview identity and current source/target/policy state. Explicit human approval is enforced by the host workflow; the CLI accepts a preview ID, not a signed human-consent proof. | Review the exact preview ID/diff before invoking apply. |
| Staleness/rebuild/purge | Source change/removal and manifest/target tampering are detected. Rebuild produces a new preview. Purge deletes compiler projections/snapshots and records raw-source retention. | Interactive maintenance with transaction-specific authority. |
| qmd export of compiled pages | `qmd_enabled: true` is rejected. No ACL/freshness/retention/purge-aware physical-index adapter exists. | Keep disabled. Ordinary approved source-note indexing is separate. |
| Scheduled compilation, live synthesis, context packs, Graphify, Neo4j export | All five corresponding true flags are rejected by `load_settings`. No scheduler implementation is supplied. | Keep disabled; these need implementation and acceptance tests. |
| Vault hooks | Advisory context only; timeout/failure does not block writes. Host support differs. | Useful reminders, never proof of policy enforcement. |
| Format support | Markdown, Bases and JSON Canvas instruction skills already exist. | Small dashboard and portable visual workflow without a new native plugin. |

## Findings and improvements

**P1 — Reconcile indexing before wider adoption.** README's approved-subfolder rule was contradicted
by `vault-setup` and `qmd-search`. Every operational path now delegates to one canonical reference.
Examples use current `@tobilu/qmd`, a named index, explicit collection filters, and update before
embed. Inspect every collection and update hook before refresh; do not treat `status` exit zero as
scope, coverage or vector readiness. Existing broad indexes need a separately reviewed cleanup:
narrowing a path does not prove old stored text/embeddings were erased. A query filter is not an ACL.

**P1 — Separate observation from recovery.** `status_report` calls `recover_incomplete`, which can
restore an interrupted apply or complete an interrupted purge. Even config loading creates/chmods
private state. A supposedly read-only scheduled health check must not invoke this route. Add a
pure observer with no mkdir/chmod/lock/recovery, a stable JSON result, and explicit `recover` action.
Test complete filesystem byte/metadata invariance, interrupted journals, expired/stale sources and
the absence of accidental privacy retention. This patch documents the behavior; it does not change it.

**P1 — Verify compiled-page Properties before adding Bases views.** `render_page` emits an ownership
HTML comment before the YAML fence. [Obsidian Properties](https://help.obsidian.md/properties)
requires the fence at the very beginning. Source inspection therefore indicates the generated
metadata will not be recognized as native frontmatter. Native-app confirmation is outstanding.
Fix with versioned rendering/ownership recognition that accepts legacy pages, preserves human-edit
protection, and migrates through reviewed rebuilds rather than a bulk rewrite. Test in Obsidian
and a Bases/property query; current tests explicitly expect the leading comment.

**P1 — Make evidence quality visible.** Hashes prove which bytes were cited, not whether they support
a claim. Contradiction candidates are supplied by the proposal; the engine does not discover semantic
contradictions. Add separate source excerpt/claim comparison, unsupported-claim flags, and a human
review outcome. Do not convert a valid hash or a green state badge into a factual-confidence score.

**P2 — Add a capability doctor.** Report installed path/version/hash per host, enabled state, fresh
session discovery, actual MCP tools and URL, qmd package/runtime/index roots, pending embeddings,
compiler config gates, and last verified check. Distinguish installed, discovered and exercised.
No credential values should appear in its report.

**P2 — Validate privacy outside the index.** The current compiler state is constrained beneath the
vault, with restrictive filesystem permissions. Those permissions do not establish exclusion from
sync/backup. Confirm retention, sync and backup behavior before using confidential sources; an
unsynced pilot vault avoids assuming hidden files stay local. A later external private state root
needs explicit path/recovery/migration design.

**P2 — Measure retrieval and native execution.** The benchmark spec has `status: pending`, no arm
ran, and empty results. Offline routing contracts are substring checks, not observed model invocation.
Use the same approved notes/questions/model in baseline and plugin arms. Measure source correctness,
unsupported answers, out-of-scope exposure, latency, cost, follow-up reads and user corrections.
Include no-answer, contradictory, renamed/deleted and cross-client negative cases. Keep this local
and bounded until any model/provider egress is explicitly authorized.

## Daily workflow and scheduling plan

Start with client/project recall and weekly review; adapt to the user's existing properties and
folders rather than replacing their vault with another person's template.

1. **Start of day:** read existing daily/project notes and identify three priorities, pending
   decisions and linked evidence. Do not create a note simply because it is absent.
2. **During work:** interactive capture into the existing inbox; retrieve within the current
   client/project scope; read live sources before answering. Suggest 1–3 links with reasons.
3. **End of day:** summarize only existing notes; surface unresolved tasks and one decision to
   confirm. Save only when requested. Avoid duplicating email alerts or the task system of record.
4. **Weekly:** a short review of open decisions, unprocessed captures, stale projects and two old
   notes worth revisiting. Human reflection stays part of the process.
5. **Compiler pilot:** one non-sensitive source → registered snapshot → proposed claims → preview
   → named human approval → apply → source-edit/staleness demonstration. All advanced export and
   scheduling flags remain false.

Potential future schedules are end-of-day reporting, weekly review and monthly dependency/version
review. Specify the exact scope, destination, timezone, overlap lock, deduplication key, missed-run
behavior, offline-host behavior and retention before activation. Never reuse daily/open commands or
compiler status in a report-only job. An offline Mac must yield an unavailable result, not a stale
success. Prefer an existing orchestrator over adding another independent scheduler. Investigate
ChatGPT tasks, Claude/Codex tasks, launchd, cron and n8n separately; source files do not prove a job
is installed, enabled or healthy. No schedules are created by this patch.

## What to borrow from the seven linked repositories

The original [X post](https://x.com/rvaniaaaa/status/2119056971298980112) is a collection of building
blocks, not an alternative AI system. Its list was recovered from a public mirror; the technical
assessment below uses each project's own source/docs.

| Repository | Useful adaptation | Boundary |
| --- | --- | --- |
| [kepano-obsidian](https://github.com/kepano/kepano-obsidian) | Composable project/meeting templates; consistent list properties; linked category pages and Bases views; progressive reviews and random revisit. | Preserve existing folders, names and privacy scopes. Do not copy the whole vault configuration. |
| [jsoncanvas](https://github.com/obsidianmd/jsoncanvas) | Source → proposal → reviewed decision maps, labeled links and compact groups. Store as portable `.canvas`. | A canvas is a view, not authoritative compiler status or approval. Avoid copying private source text into shareable boards. |
| [obsidian-releases](https://github.com/obsidianmd/obsidian-releases) | Resolve canonical plugin/theme identities and compatibility; use as the inventory source for a dependency doctor. | It is a registry/release repository, not the Obsidian app's source or evidence that every plugin is appropriate. |
| [obsidian-sample-plugin](https://github.com/obsidianmd/obsidian-sample-plugin) | If needed later, a native command, settings pane and review modal around the existing engine. | First use existing skills/Bases/Canvas. Do not duplicate hashing/policy/recovery logic in TypeScript or install a timer automatically. |
| [40-questions](https://github.com/kepano/40-questions) | Optional annual/decade reflection; choose a few prompts in the user's review template. | Not a reason to add 40 daily prompts or delegate personal reflection. |
| [obsidian-minimal](https://github.com/kepano/obsidian-minimal) | Readable line widths, restrained UI, clear tables; cards for image-rich research. | Preserve current theme until chosen; text-heavy project work usually benefits more from tables. |
| [flexoki](https://github.com/kepano/flexoki) | A consistent light/dark palette with calm neutrals and a few semantic accents. | Pair every color with a text state/icon; verify contrast and keyboard behavior. Color never signifies verified evidence by itself. |

Suggested home view: **Today / Projects / Review queue**, with columns Project, Next action,
Owner, Decision due and Last reviewed. Research cards may show source, captured date, status and
one-sentence relevance. Use text labels **Draft**, **Needs review**, **Reviewed**, **Stale** and
**Conflicting** with optional color. Keep business task status separate from compiler state.
Link from a decision to its live sources; avoid raw provenance hashes in everyday navigation.
Compiler freshness needs a real observer, not a cached frontmatter badge.

## Reconnection acceptance checklist

- Resolve actual Claude/Codex plugin install paths, enabled state, versions and source hashes;
  compare with published manifest and restart a host session before verifying discovery.
- Read vault registry and setup log; inspect relevant settings without printing secrets.
- Verify installed Obsidian/CLI, Local REST API and pinned MCP server tools. Any Keychain access
  uses CLI only and must not reveal the value. No credentials are created by this investigation.
- Enumerate local/host/n8n jobs, exact commands/scopes, last results, timezones and duplicates.
- Inspect actual qmd configs/index roots and update hooks before any scan; identify old broad indexes.
- Confirm compiler config/state/sync behavior, preview support and native Properties rendering.
- Run a small synthetic indexing boundary/refresh test; then obtain exact approval for real scope.
- Review proposed display changes in a copy/test vault. Enable only the chosen workflow.

Validation receipts and any environment-specific failures accompany the review bundle. Live qmd
models, Obsidian rendering, installed host invocation and private-vault workflow acceptance remain
separate from source/fixture verification.
