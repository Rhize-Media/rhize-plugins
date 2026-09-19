---
name: rhize-content-engine
description: >-
  Select and follow the established RHIZE Content Engine for writing, combining, regenerating,
  or revising resource articles and website/blog drafts. Use for "our content engine protocol",
  "Rhize Media resource article", or "record the content benchmark" before composing.
  Binds the requested local-draft or CMS-draft scope to the procedural registry; full public
  publishing is unsupported. This RHIZE workflow is distinct from ECC's content-engine.
metadata:
  rhize:
    topics: [workflow-patterns, content-authoring]
    stacks: []
---

# RHIZE Content Engine

This is the canonical host-visible entrypoint for Claude and Codex. It selects the
RHIZE graph/prose workflow and its measurement contract. It does not replace ECC's
cross-platform repurposing skill, infer publishing permission, or silently choose it
when the RHIZE runtime is unavailable.

## Before the first substantial write

1. Read the user's audience, topic, article/series context and intended destination.
   Default to a **local draft**. Keep source-backed qualifications and missing data visible.
2. Use the self-relative launcher for current registry metadata:
   `bash scripts/procedural-memory.sh recall "content engine article" --json`.
   This is offline lexical discovery, not an embedding similarity or execution approval.
3. Select the authorized variant. Inspect exact version/digest/trust/health; normal graph
   preflight remains mandatory. Missing capability is `unavailable`, never a silent fallback.
4. If a Context Manager opportunity ID was supplied, record the choice using its
   `scripts/workflow_selection.py decide --id ID --decision reuse --workflow rhize-content-engine
   --variant local-draft --reason existing_workflow --run-id RUN_ID --source-sha256 ARTIFACT_DIGEST`. Use `adapt`, `no_match`, `unavailable`
   or `candidate` honestly when appropriate. Do not mark a suggestion as execution.

| Requested scope | Registry binding | Completion boundary |
|---|---|---|
| Local draft (default) | `content-engine-local` | Validated Markdown plus benchmark capture; no CMS or social writes |
| Explicit CMS draft | `content-engine` | Existing graph's Sanity/image/GHL draft effects require their own authorization |
| Full publishing | Unsupported | Do not substitute the draft graph or publish implicitly |

## Editorial protocol

Freeze source material with dated source references, audience, requested length, exact measured
keyword evidence (null when unavailable), required links, style requirements and series context.
Proceed through outline, SEO/AEO planning, composition, Humanizer, source/claim and link validation,
then the selected output boundary. The source-aware review is a check, not proof of factual truth.
An unavailable live internal-link catalog must stay unavailable; do not invent CMS document IDs.

Use the graph's own schemas and gates. Model calls use only the authorized host/provider lane.
A local draft may use supplied URL evidence without CMS credentials. Never claim a full graph run
when following the manual prose protocol; label `manual-content-engine-article-only` and record
which stages actually ran. Preserve original text and the Humanizer diff. Do not fabricate timing,
tokens, costs or previous baseline values.

## Capture is a completion step

Use the canonical registry writer through this launcher for **future** manual rows:
`bash scripts/procedural-memory.sh run bench-append --offline -- NOTE_PATH MARKDOWN_ROW`.
The graph uses the pinned `bench-append` node. Successful append must have both the row and durable
capture receipt. On a nonzero result, inspect whether the row already landed; never blindly retry
or duplicate a historical row to obtain a receipt. The legacy vault append script is superseded.

Record actual stage clocks, host/model, variant, source identities, validation results, unavailable
metrics and failures. Graph receipts and setup checks remain separate from matched Arm A/B benefit.
After an attempted workflow, use Context Manager's `record` for execution, validation and capture
with real evidence files and matching `--run-id RUN_ID --source-sha256 ARTIFACT_DIGEST`, then `finish --status completed|failed|partial|unavailable|skipped`.
Record the actual artifact digest from metadata/preflight and the graph/manual run ID at selection.
A changed source requires a new opportunity. These records do not prove selection preceded the first write.
`completed` requires the latest status of all three evidence stages to pass. Failed/partial/unavailable
completion requires `--reason` and an actual `--evidence` file; terminal records are sealed. A failed or partial run still gets an outcome receipt;
it is not converted into a successful article benchmark. Never fill missing stages with zeros.

## Trust and runtime

All registry calls use the self-relative launcher. Normal promotion, digest, health and approval
checks remain unchanged. An unreviewed changed graph needs explicit digest-bound approval;
implementation authority is not that approval. Never add `--approve-unreviewed` for the user.
Do not edit registry provenance, health, approval or digest records by hand.
