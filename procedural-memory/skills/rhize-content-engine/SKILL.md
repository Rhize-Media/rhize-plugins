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
   Read [the reader-focused workflow](references/reader-focused-workflow.md) and freeze the
   reader question, practical outcome and evidence limits before outlining.
   Default to a **local draft**. Keep source-backed qualifications and missing data visible.
2. Resolve `scripts/procedural-memory.sh` relative to this skill directory, not the project cwd.
   Use that launcher for current registry metadata:
   `bash scripts/procedural-memory.sh recall "content engine article" --json`.
   This is offline lexical discovery, not an embedding similarity or execution approval.
3. Select the authorized variant. Inspect exact version/digest/trust/health; normal graph
   preflight remains mandatory. Missing capability is `unavailable`, never a silent fallback.
4. If a Context Manager opportunity ID was supplied, record the choice using its
   `scripts/workflow_selection.py decide --id ID --decision reuse --workflow rhize-content-engine
   --variant VARIANT --reason existing_workflow --run-id RUN_ID --source-sha256 ARTIFACT_DIGEST`. Use `adapt`, `no_match`, `unavailable`
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

## Reader focus is a delivery gate

Apply the linked workflow to **every variant**, including manual articles, graph-generated
outputs, revisions and requested derivative content. The title must describe a recognizable
task or question; do not lead with an internal project name unless that name is itself the
reader's intended search, backed by measured keyword/SERP evidence or an explicit user instruction
recorded in the brief. Give a direct answer in the opening, then concrete steps, examples,
tradeoffs and a useful next action. Align the SEO title, description and proposed slug with
that intent; changing an existing public URL still needs its normal redirect/release review.

Write benefits in terms of the reader's work. Distinguish observed results from plausible uses;
never replace a removed caveat with an unsupported saving, ranking or outcome promise. Put
material limitations beside the claim or step they qualify, expressed as useful guidance.

For revisions, rewrite the affected passage or whole post into cohesive final copy. Keep
before/after history, missing-evidence investigations and correction commentary in the private editorial record.
Do not carry phrases such as "the revised publication omits" into an article or social post.
Do not conceal a material error or suppress a necessary public correction: flag that need for
the editor and keep it separate from routine copy cleanup.

When derivatives are requested, pass the same reader intent, supported claims and current
article URL into the platform adaptation. If no published URL exists, mark the link pending
and keep link-dependent derivatives on hold; never fabricate a URL from a proposed slug. Each post must stand alone around one reader problem,
useful takeaway and appropriate next step. Respect platform format and voice; do not copy the
internal release announcement or editorial audit. Social-only tasks still belong to ECC's
content-engine; this rule governs derivatives handed off from the article workflow.

Before output handoff, save `editorial-review.md` beside the private run evidence and use it
as validation-stage evidence. Record pass or revise/hold with an excerpt or reason for: title/query
fit, direct opening answer, practical usefulness, claim support, material qualifications, clean
reader-facing copy, metadata alignment and each requested derivative. Record whether a material
public correction is needed (needed/not needed, with reason). Revise and recheck failures;
Unresolved review holds require partial/failed completion, never completed. This is editorial judgment, not a keyword-match guarantee.

Carry the reader brief through supported graph inputs/source material without changing graph
schemas or frozen artifacts. Inspect the exact selected schema first. A graph's internal checks
do not replace this coordinator review. If it writes CMS/GHL drafts before review, those drafts
remain on hold until checked; never present them as ready. If correction needs an unauthorized
CMS write, finish partial with the review evidence; do not deliver the graph output as a finished article. An incompatible graph is unavailable
for this contract; disclose a manual adaptation when authorized, preserving all trust and effect gates.

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
