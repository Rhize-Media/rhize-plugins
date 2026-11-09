# Compiler batch implementation and native adoption handoff

## Candidate and release state

The isolated candidate implements multi-source, multi-page compilation. It is not published,
installed, scheduled or live-verified in Jim's vault. The baseline was rechecked against GitHub:
main `3b6f073b93388fc929a81e535cffe344ec334dce`, plugin 1.9.0, marketplace 2.117.2. The version
script replaced the unpublished indexing-only 1.9.1/2.117.3 proposal with plugin **1.10.0** and
marketplace **2.118.0**. Engine format version is 1.1.0; this is a separate internal version.
Re-read remote immediately before final integration; these candidate numbers do not reserve a release.

The parent reports that local `AGENTS.override.md` requires private vault-context semantic review
of the exact release ref before push, tag or GitHub UI/API merge. That Mac-side prerequisite is
unavailable to this subthread and cannot be replaced by cloud tests or API publication. The repo
also assigns publishing to the orchestrator. No publication, installation or schedule changes occurred.

## Implemented behavior

- V2 proposals contain 1–100 pages; each claim can cite several registered sources. Source identities,
  revision/line hashes, exact diffs, excerpts and one batch review receipt are retained. V1 proposals
  and 1.0.0 accepted manifests remain readable.
- Pages and sources must share an ACL/egress/retention-label boundary. Per-source expiry and metadata
  drift are checked. Accepted per-page manifests include only the page's actual dependencies.
- All pages are preflighted before a journaled apply. Crash recovery restores the prior batch;
  an accepted transaction survives restart. Terminal journals discard rollback payloads. A purge
  suppresses all owned pages dependent on that source, removes associated review artifacts/snapshots
  and legacy backups, and preserves unrelated pages plus canonical source notes.
- Human edits before preview, after preview, and during interrupted-write recovery are protected.
  Recovery stops with a pending conflict rather than overwriting external bytes. Source-stale
  rebuilds require fresh proposals instead of silently reusing old line numbers.
- `inspect` does not initialize state, chmod, write locks or recover transactions. It reports busy,
  uninitialized or recovery-required explicitly. `status` remains recovery-capable.
- Generated pages start with YAML Properties, then the ownership marker. Provenance/contradiction
  callouts, readable metadata and navigable source links implement useful Obsidian visual conventions.
  Legacy pages migrate only through reviewed rebuilds; no bulk migration runs.

The engine is deterministic. An assistant drafts a proposal from authorized evidence; the engine
checks provenance, not semantic truth. Each bundle needs human review. Multi-file filesystem writes
are not globally atomic to Obsidian readers; locks serialize compiler writers, while the journal
provides recovery. Direct source modifications can make a just-applied projection stale; inspect
health before relying on it. OS permissions are not a sync/backup exclusion policy.

## Evidence

- Compiler/plugin/config suite: 209 passed, 2 skipped, 12 subtests (final pre-release metadata run).
- Offline routing 38/38 and static quality 10/10 pass. Live model benchmark remains pending.
- Strict marketplace/plugin manifest checks, configuration lint, generated skill-map freshness and
  setup-document freshness pass; final metadata checks are recorded in the delivery receipt.
- Tests cover all batch writes, interrupted rollback, acceptance, human conflicts, source/snapshot/
  policy changes, mixed-policy rejection, ownership/case collisions, legacy migration, shared-source
  purge at every journal boundary, retained legacy backups, exact CLI execution and YAML parsing.
- Synthetic demonstration: 3 registered sources → 3 pages in one batch; apply succeeded and all 3 pages
  inspected clean. The portable demo contains synthetic Markdown/proposal/review/evidence only,
  not a transferable live vault configuration or approved production batch id.
- Native Obsidian rendering, installed-host execution, real source selection and lifecycle proof in
  Jim's vault remain outstanding. YAML parsing does not substitute for that native check.

## Native findings supplied by the parent

These are parent audit evidence, not independent checks by this cloud subthread:

- Claude and Codex have second-brain 1.9.0 enabled, matching clean source 3b6f073 and 36 installed files.
- qmd was absent from PATH/standard locations; no collection was found. Manual compilation needs no
  qmd installation, provider credential or model endpoint.
- Codex routines: Vault Inbox Processor Saturdays 14:00; learn harvest weekdays 18:00; Context Doctor
  Thursdays 08:00; skill audit Mondays 18:30; promotion digest Mondays 08:30, Eastern time. Retained
  Claude copies are retired.
- Latest saved summaries: November 7 inbox source changed and validation held; November 6 harvest
  approval hold/no candidates; November 5 Context Doctor failures/blocked monitoring; November 2 skill
  audit missing PyYAML. Configured does not mean successfully executing.
- Native lifecycle verification lost transport. Crontab was denied; n8n remains unverified. Do not
  retry that denied action without materially new relevant authorization evidence.

## Adoption steps for the parent/native worker

1. Integrate onto the current released baseline, reconcile any Context Doctor changes and regenerate
   versions/managed docs as needed. Run the required checks, then obtain the private semantic review
   for the exact release ref. Only the orchestrator publishes after this prerequisite passes.
2. Install/update both hosts through the existing authorized delivery path. Verify version, file
   hashes, enabled state and fresh-session skill discovery separately; do not overwrite local work.
3. Locate the existing project-owned config and inspect it read-only first. Confirm project/tenant/
   scope, source roots, output root, retention, ACL and sync/backup treatment. No new credentials or
   persistent access are needed. Leave qmd/export/scheduling/live-synthesis flags false.
4. Select several already-captured, explicitly approved sources from one project and one policy
   boundary. Draft a project overview, decision record and topic page, with multiple sources cited
   where useful. Register exact revisions; preview using the documented v2 example as a shape only.
5. Show the exact bundle and every cited excerpt/diff. After named-batch approval, apply it, inspect
   every page, then verify native Properties, source navigation and Bases queries in Obsidian.
   Preserve annotations in separate linked notes. Record this as the first real workflow acceptance.
6. Repair existing routines' specific failures through their owners. Avoid duplicate routines. An
   owner can propose adding `inspect` as a read-only observation step, or preparation of a review
   bundle under a clearly writing workflow contract. Scheduling preview creation is still mutation;
   scheduled apply/export/access changes require their action-time authorization. Do not turn gated
   booleans true as an enablement shortcut. Reuse the existing scheduled-routines documentation folder.
7. If ordinary source search is wanted, install qmd only through its separately approved setup and
   use the canonical approved-indexing reference. Never include Compiled or private compiler state.

## Promotion blockers

Private vault-context exact-ref semantic review is pending; native transport/access is unavailable
here. Real-vault adoption and native visual verification therefore remain pending. The prior broad
cloud release gate had an unchanged DevFlow Docker-unavailable failure and an unrelated IPv6 test
failure; use the current delivery's gate log as the authoritative rerun result. No blocker authorizes
bypassing required checks, the private review, or the orchestrator publication lane.

## Final gate reconciliation

The first full gate on the candidate reported the unchanged Docker-unavailable DevFlow failure
(902 passed, 1 failed) and a stale skill-map node because the new reference files were not yet
tracked when it was generated. Regenerating after those files were committed changed only the
knowledge-compiler node's file count, byte count and tree hash. Freshness then passed. The final
full rerun and exact exported-patch tree comparison are recorded in `verification.json` and
`release-gate.log` in the delivery archive. A Docker prerequisite failure is not a green gate.
