# Context-tool dogfood decision — 2026-08-27

## Decision

| Capability | Decision | Evidence boundary |
|---|---|---|
| Managed mgrep | Reject current pilot | Stopped before signup/upload because the published free-tier data-use terms conflict; no account, credential, store, or remote data exists to purge. |
| Local grepai retrieval | Reject current provider/configuration | Real six-case run: recall@5 0.166667 and five critical misses versus ripgrep recall@5 1.0 and zero misses; watcher isolation also adds material operational risk. |
| Pinned upstream Context Compiler | Retain as an eval/reference provider | Real nine-case Python behavior corpus passed its guardrail gate, but the provider is Python-only and the real Rhize runner pack was too broad and unsafe to inject. |
| Rhize native context pack v1 | Bundle as advanced opt-in | Real provider, local-only; five native cases passed with zero critical misses and 39.02% median reduction across four accepted cases. An actual repository target and one-shot query-discovery run were accepted. Correctness/follow-up-read telemetry still requires human review. |
| Combined retrieval + compiled context | Skip | Neither managed nor local semantic retrieval passed its independent prerequisite gate; a 2x2 run would not support an adoption claim. |

## Reconciled evidence

- Compiled context has 14 paired offline cases: nine pinned-upstream cases plus five native cases.
- Retrieval has six paired real-provider cases. Arm A and Arm B variants are named in every report;
  skipped or failed provider rows are not counted as successful executions.
- `native-context-phase-4-v1` passed 5/5: TypeScript, JavaScript, Python, mixed-language, and
  dynamic-import fallback. Four accepted cases had median estimated reduction 39.02%; the dynamic
  case rejected use with an explicit warning.
- The actual `rhize-plugins` provider-target smoke selected 4/318 files and used 8,759 estimated
  tokens versus 680,703 for the supported-source baseline (98.713% reduction), with no warning.
- The actual runner-target smoke selected 24/318 files and reduced the estimate by 94.341%, but
  rejected use because a dynamic dependency edge was present. This is a safety success, not a
  performance win.
- The one-shot selector built a six-file native pack before the next implementation slice with
  Arm B live and Arm A shadow: 10,907 versus 682,821 estimated tokens. After documentation edits,
  `verify-pack` returned `snapshotCurrent=false` with no changed entry, proving that even an
  unrelated snapshot change prevents reuse; recompilation produced a new accepted pack. The
  receipt warns that task outcome and follow-up reads still need human review, preventing this run
  from being misreported as proof of correctness.

## Bundle boundary

Ship only the local native pack, inspection command, stale-pack verifier, fixed corpus, and
disabled-by-default one-shot selector integration in `rhize-context-manager`. Do not install or
authenticate mgrep, start a grepai watcher, enable the hooks globally, or add a consumer to
`rhize-devflow`. The pinned upstream adapter and rejected retrieval adapters remain evidence
infrastructure, not default routing layers.

Revisit the native path after five reviewed live receipts or 14 days, whichever comes first. A
default-enable or `rhize-devflow` consumption point still requires the original 20-task adoption
gate, including human correctness review and follow-up-read accounting. Revisit managed retrieval
only after materially different provider terms/capability or a safer, higher-recall local option.
