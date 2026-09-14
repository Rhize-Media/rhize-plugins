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
- SkillForge source `0.20.0` adds advisory discovery/body/resource diagnostics and covered
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
`1.8.4`; preparation does not install or adopt the candidate.

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
  Direct test results are recorded separately; no packet was edited to claim execution.
- Arm A live skill outcomes: not run. Arm B live skill outcomes: not run. A generic Codex CLI
  readiness probe was infrastructure evidence only. Automatic approval review blocked the Claude
  probe over possible private host context sent externally; explicit approval was requested.
- Shared description adoption requires matched Claude and Codex evidence. SkillForge remains
  committed and unpublished pending the release-evidence decision; npm's verified latest is `0.19.0`.

Do not infer success from missing events, average disjoint valid cohorts, treat inaccessible
resources as empty, or adopt a shared description solely because it is shorter. Subsequent body
routing experiments and a Codex observation adapter are separate work after this pilot.
