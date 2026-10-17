# Perplexity and decision pre-mortem release evidence

Released: marketplace **2.111.0**, Perplexity Research **0.2.0**, Ops **0.33.0**, Core **1.0.9**.
Implementation checkpoints: `9312a60` and `0896253`. [PR #57](https://github.com/Rhize-Media/rhize-plugins/pull/57)
merged as `6b276baf77acf2afdee3e7807aa1aba73381f06a` on 2026-10-17; tag `v2.111.0` points to that
commit. Published installation verification passed. Timestamps use the execution environment's UTC clock.

## Scope and portability

Perplexity is a self-contained Claude/Codex plugin with eleven MCP tools. It retains the tested
citation mapping, bounded large responses, durable IDs, GET-only recovery, separate report and
summary sources, encrypted session transfer and local cancellation. Canonical runtime and docs
live under `perplexity-research/`; root research docs point there. Both marketplaces, setup
inventory and Core/Ops evaluation mirrors include it: 12 plugins, 68 skills, 80 command files.

Neutral defaults and private JSON replace organization-specific runtime paths and Keychain
names. The selected interpreter, state directory, authorization reference and service name are
configurable; credentials are never JSON settings. Existing installations explicitly retain
old paths/service before switching. Strict owned/private/nonlinked configuration, bounded JSON,
path/type/service checks and detached-worker propagation are regression-tested. Package ownership,
source attribution and optional marketplace setup integration remain identified.

`decision-premortem` replaces `business-premortem` in Ops. It applies the five-step method to
business, project, process and personal decisions without organization-specific assumptions.
Task inputs provide the needed context; no additional configuration or execution authority is
introduced. Historical evaluations remain in `evals/business-premortem` and retain partial labels.

## Independent Fable review

The user explicitly requested Fable review before publication. Native bridge evidence attests
`claude-fable-5-1` for runtime review `70b12bd0-6bd9-476b-acb5-644946d3313a` and packaging review
`9f5237b0-4990-4d13-b9a9-ec76c54676bc`. These were no-tools source reviews, not independent test runs.
Neither found a code-level release blocker; both held readiness on complete checks, and required
native manifest startup plus live GET evidence for the changed User-Agent.

Accepted fixes strengthen the existing-job migration regression, preserve selected interpreter
symlinks in development snapshots, return a controlled startup error when HOME cannot resolve,
and correct setup dependency/viewer and migration guidance. The 143-test Perplexity suite passes.
The launcher consumes `pythonExecutable` before starting MCP, so children correctly inherit that
interpreter. The setup schema supports filesystem artifacts only; Keychain retention is documented
separately. Strict citation/state validation and existing bounded failure semantics were retained;
optional parser relaxations without a reproduced provider failure would weaken these safeguards.

Follow-up review `790d49fb-11ea-4d01-9a18-f6bce6445335` received the fixes and native evidence; its
final disposition found no remaining code or source-readiness defects. It approved PR submission
after the clean local suite, with merge held for exact-head hosted CI and final published-install
verification before removing the old local plugin. Native proof was from post-fix `0896253`.

## Local and candidate verification

- Affected integration suites: **359 passed, 2 existing optional skips** before the final small
  review fixes; focused Perplexity suite after those fixes: **143 passed**.
- Required repository gate rerun against committed `0896253`: **780 Dev Flow tests passed**
  in 375.92 seconds; map/setup freshness and config lint passed, and all three changed plugins
  passed committed version-bump coverage. Seven impact-map contracts also passed in the prior
  gate. Exact-head hosted CI remains required before merge.
- Strict marketplace and all twelve plugin manifest validations passed. Generated map/docs and
  setup artifacts are current; rendering is idempotent. Cold coordinator review completed.
- Earlier full-suite attempts were interrupted: sandbox restrictions affected the first; the next
  exposed four Node shim trust failures after 3,887 passes, six skips and fifteen subtests. The
  complete suite then passed unchanged with PATH selecting the already-installed Node binary:
  **4,429 passed, 7 existing skips, 21 subtests passed in 794.11 seconds** at source `0896253`.
  No tests, trust controls or validation gates were disabled.
- Exact candidate `0896253` was copied into a temporary local marketplace, installed by native
  Codex and exercised through a fresh `codex app-server` MCP client without a model turn. Native
  discovery returned the candidate plugin identity, eleven tools and no discovery error. All
  twenty installed files matched committed source. The original portable manifest was unchanged.
- Native MCP health and models GETs passed with the neutral User-Agent. Existing result and export
  passed: the same recovered Research report, 24,834 full-report characters/243 citations and
  3,274 summary characters/21 citations. All eight saved job files retained identical SHA-256
  hashes. No query was submitted, no credentials refreshed and no job deleted. The temporary
  candidate registration was removed after proof; the original working installation was retained
  until the published replacement passed the same verification below.

## Published release and installed verification

- Exact PR head `316b3d45f1de0146c56c246b1723ade845f75459` passed
  [hosted validation](https://github.com/Rhize-Media/rhize-plugins/actions/runs/39060565801):
  **4,431 passed, 8 skipped, 21 subtests** on Linux/Python 3.12, followed by all manifest,
  config, doctor, generated-document and version gates. The security scan also passed.
  These host-dependent totals are separate from the macOS local totals above.
- Main merge `6b276ba` and automated tag `v2.111.0` were read back from GitHub. The configured
  Git marketplace was refreshed from published main; native Codex installed Perplexity 0.2.0
  and updated the existing Ops installation to 0.33.0. Core 1.0.9 is published; Core was not
  previously installed on this host and was not added merely for this check.
- A fresh native Codex host discovered `perplexity_research` owned by
  `perplexity-research@rhize-plugins`: **11 tools, no discovery error**. Native skill discovery
  found enabled `perplexity-research:perplexity-research` and `rhize-ops:decision-premortem`,
  with no skill errors or active old `business-premortem`. The installed decision skill
  matched source; all 20 installed Perplexity files matched the merged tree byte-for-byte.
- Live MCP health returned ready/Pro with Research model `pplx_alpha`; models, jobs, result,
  export and final jobs calls all succeeded. The same recovered report returned 24,834 full
  characters/243 citations, with 3,274 summary characters/21 citations and 47,854 export
  characters. All 8 saved job hashes remained identical before/after. **No query was submitted,
  no session refreshed and no data migrated or deleted.**
- After this proof, the old `perplexity-local` plugin and marketplace registration were removed.
  The temporary candidate registration was also removed. Private configuration, Keychain session
  and existing job files remain intact. A final readback confirmed the published plugin and Ops
  enabled and the obsolete local plugin absent. This verifies a fresh native host; it does not
  claim hot replacement of tools cached by an already-running chat.

## Limits

This is an experimental subscription-web integration, not provider-supported API access.
Remaining quota, remote cancellation/refunds, factual accuracy and browser parity are unverified.
Undocumented endpoints can change. Decision pre-mortem has partial synthetic evaluation evidence,
not calibrated prediction or demonstrated real-world benefit. A fresh native host proves package
loading; an already-running chat may need reload to replace cached tools.
