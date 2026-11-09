# Compiler batch impact map — 2026-11-08

## Intended delta
Accept a v2 proposal containing multiple pages, each with citations to multiple registered sources. Preserve v1 proposals/manifests and per-page provenance. Produce a content-addressed batch review receipt referencing immutable per-page previews; apply all preflighted pages in one recoverable transaction. Start frontmatter at byte zero for native Properties/Bases. Block human edits before preview as well as after preview and during crash recovery.

## Invariants
- No source discovery outside configured roots; no source registration without explicit policy.
- Each page combines only identical ACL, egress and retention labels; bundles also require one policy boundary.
- Every citation is tied to a retained canonical revision and line hash; semantic entailment requires human review.
- No target rename, ownership takeover, duplicate page/path, stale sources, expired review, or forged receipt.
- Recovery preserves external edits. Multi-file writes are logically journaled, not globally atomic to Obsidian readers.
- Per-page accepted manifests contain only their own dependencies. Purging a shared source suppresses all dependent pages and relevant review artifacts, preserving other pages and human edits.
- No scheduler/export/credential/access activation. Local installation and routines require independent native verification.

## Planned paths
`obsidian-second-brain/scripts/compiled_knowledge.py`, new batch implementation module if useful, compiler skill/reference schemas, README/GUIDE, focused tests; generated docs only when needed. Version/marketplace/CHANGELOG finalization waits for Context Doctor released baseline and orchestrator coordination.

## Acceptance
Legacy lifecycle tests; multi-source/multi-page happy path, no-op, rebuild, per-source stale/retention/policy changes; malformed citations/duplicate IDs/paths; second-page failure must write no targets; source/target changes before apply; failures at each journaled write and restart; interrupted recovery; external edits preserved; purge shared dependency including completed transaction backups; native frontmatter and source navigation; CLI end-to-end synthetic vault. Existing disabled adapter gates remain fail closed.

## Local evidence supplied by parent (not independently verified here)
Installed Claude/Codex1.9.0 matches3b6f073,36files. qmd not found. Five Codex routines configured; saved summaries include holds/failures, so configuration is not execution success. Crontab denied; n8n unverified. Do not retry those native actions here; no native-worker tool is exposed to this subthread.

## Reconciled implementation scope
The same engine now includes batch receipt/apply/recovery helpers and a side-effect-free `inspect`
path, rather than a second module. Legacy single-page recovery also gains compare-before-restore
and terminal backup disposal. Read-only inspection was added because existing health routines must
not accidentally invoke `status` recovery. Source policy/snapshot drift is visible in health reports.
README/GUIDE/skill/command and example/reference docs are updated, with new batch tests. No manifest
version changes are made in this continuation; final version and CHANGELOG generation wait for the
first release lane. The earlier provisional audit version commit must be reconciled, not blindly
cherry-picked onto the new marketplace baseline.

## Final candidate version reconciliation
After the parent confirmed the competing 2.117.3 candidate was unpublished/unreserved, remote main
was rechecked at 3b6f073 (plugin 1.9.0/marketplace 2.117.2). Provisional version files/changelogs were
restored from that baseline and the repository script produced plugin 1.10.0 / marketplace 2.118.0.
Touched release metadata: marketplace manifest, both Obsidian host manifests, both changelogs;
managed root/docs READMEs and skill-map regenerated. No other plugin version was changed. Final
publication still requires refreshed remote state and the parent's private exact-ref review.

## Deployment continuation — 2026-11-09

The user explicitly authorized full deployment and real-vault enablement. The current session
still exposes only cloud Linux, with no native Mac worker or mounted vault. Remote main remains
3b6f073. Installation and exact-ref private vault review require that actual connection.

Release-gate correction planned before edits: the provider-free remote-context/image-volume unit
test stubs DockerSandbox.client but leaks a host dependency through shutil.which. Stub only that
lookup within the test, prevent any accidental process invocation, and add a separate negative test
for the real missing-binary branch. Production Docker policy, runtime code, test assertions, release
requirements and plugin versions remain unchanged. Acceptance: focused sandbox contracts and the
complete repository bump_version --check gate must pass without installing Docker or executing it.
Touched paths: tests/rhize-devflow/test_test_sandbox.py and this impact record; new release receipt
will replace the earlier claim that a Docker installation is needed for this provider-free gate.
