# Instruction optimization implementation — 2026-09-14

This first implementation applies the [OpenAI article's](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
description, selective-reading and completion guidance while preserving shared Claude Code
workflows. The date was checked against the environment clock. Three isolated implementation
lanes and an independent reviewer were used; runtime savings have not been established.

## Implemented

- The Claude evaluation adapter excludes launch failures, nonzero exits, timeouts, malformed
  streams and unsuccessful terminal events from scoring. Unknown usage is null, never zero.
  F1 uses confusion counts; quality deltas require matched valid cases. Legacy reports remain
  readable. Source, fixture and variant metadata are separate from host CLI arguments.
- [Shared authoring guidance](../shared-skill-authoring.md) preserves operational constraints,
  explicit invocation, metadata, source ownership and host compatibility. It makes description
  length advisory and separates description experiments from body refactors.
- Published SkillForge `0.20.0` adds advisory discovery/body/resource diagnostics and covered
  comparison deltas. No safety severity, gate decision, installation or runtime dependency changes.
  Unreadable or bounded resource inventories stay unavailable while safety auditing continues.
- The maintained Codex-only policy was independently reviewed, committed and merged at
  `8ef8e7d` in `claude-config`. It scopes discovery and repeated checks to the task and continues
  authorized local work. Claude's policy, shared skill aliases and installed plugin caches were
  not changed.

## Description pilot remains experimental

Branch `codex/astra-description-pilot` contains three description candidates and a digest-pinned
19-case first-selection fixture. It covers positive, negative, adjacent-skill and explicit use,
including implicit session closure, existing-PRD gap review and risky single-file sign-off.
All three skill bodies and non-description frontmatter remain byte-identical to the baseline
`8c9003e7ca6bc2d6143d2f091a6d7ad9c40d81fd`. Downstream workflow calls, including project-launcher's
Phase 3 visual plan, remain permitted.

The descriptions total 801 Unicode code points against 3,035 in Arm A. This static reduction
does not establish host context savings, selection improvement, latency or task quality.
Candidate package metadata is prepared for context-manager `0.31.1` and project-launcher
`1.8.4`; neither candidate version was adopted or installed. The published plugins keep their
existing descriptions, complete bodies, commands, hooks, permissions and shared aliases.

## Verification and remaining boundaries

- Evaluation regression suite: 21 passed. Integrated router/parity check: 41 passed, 3 expected
  skips. Required repository contracts: 363 passed, plus freshness/config checks.
- Description integrity/router/parity checks: 22 passed, 3 expected skips. Independent static
  review verified baseline Git blobs, complete body hashes and preserved routing distinctions.
- SkillForge: typecheck/build passed; 1,417 tests passed, 207 existing conditional skips.
  Package dry-run: 18 files, 538,267 packed bytes. Source release commit: `8678dd7`.
- Independent review reproduced and verified fixes for misleading evaluation denominators and
  unreadable resource traversal. The native test-evidence runner `1.1.0` has no execution adapter:
  its packet is valid but reports `execution_unavailable`, so the formal packet gate is unsupported.
  The user explicitly approved publication using the independently verified direct tests; no
  packet was edited to claim execution. [OIDC release run 34875503841](https://github.com/Rhize-Media/skill-forge/actions/runs/34875503841)
  published tag `v0.20.0` from `8678dd7`. Public npm latest/version and gitHead matched, and a
  clean temporary install returned CLI version `0.20.0`. Publication documentation is at `c38ab29`.
- The user explicitly approved the subscription-host probes. Claude first-selection screening
  completed 114 observations: 19 fixed cases × 3 repetitions × both arms, using Claude Code
  `2.1.266`, resolved model `claude-sonnet-5`, requested effort `low` (resolved effort unavailable).
  Exact bodies were verified for selected skills; source snapshots, prompts and observer were
  frozen. [Sanitized observations and protocol](astra-description-screening.json) retain all rows.
- Only 10 of 57 pairs met the frozen scoring/identity requirements. Of 84 unscored observations,
  73 selected other native capabilities; supplemental inspection verified 67 plugin-command
  bodies, while six built-in `run` loads lacked owned-source evidence. Eleven responses lacked
  the exact `NONE` marker. These are observation limitations, not failed Claude workflows.
- Each arm returned explicit `NONE` for two positive sign-off requests, in different repetitions.
  Both arms passed the target expectations in the ten valid matched pairs, but that narrow
  coverage cannot establish improvement or adoption. Keep the candidate at `bead5c2` on `codex/astra-description-pilot`; do
  not rewrite expectations or count command loads as the requested SKILL.md to obtain a pass.
- Codex `0.153.4` completed 18 explicit-load probes: three named skills × three repetitions ×
  both arms, requested model `gpt-6-astra` and effort `low`. Per-run resolved identity is unavailable;
  the native app-server preflight is separate. Supplemental checks verified all 18 exact target
  file reads and successful turns. However, every run reported removing all skill descriptions
  and omitting either 490 or 502 additional skills from the model-visible list. The frozen
  observer rejected this newly observed warning; all 18 original invalid outcomes remain intact.
  File-load evidence cannot establish description-selection quality or full catalog availability.
- The Codex test processes replaced only the three duplicate installed baseline candidates with
  arm snapshots through ephemeral configuration. Every other skill remained configured; no
  persistent host configuration or shared installation changed. A full Codex selection cohort
  was not run after the Claude adoption screen failed. The earlier approval-review rejection in
  the child context was resolved by running the same approved probes from the parent task.

Do not infer success from missing events, average disjoint valid cohorts, treat inaccessible
resources as empty, or adopt a shared description solely because it is shorter. Before another
adoption attempt, predeclare a command-aware routing fixture and use native source observations
for both hosts. Full workflow completion, ordinary unwrapped routing and
savings remain unmeasured. Subsequent body routing experiments stay separate.
