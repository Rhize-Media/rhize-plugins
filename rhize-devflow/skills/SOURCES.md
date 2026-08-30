# Skill Forge — Provenance Ledger

One entry per external-skill ingestion decision owned by Rhize Dev Flow.

## completed-branch-promotion — 2026-08-30
- **Source:** https://github.com/obra/superpowers/tree/main/skills/finishing-a-development-branch
- **Upstream ref:** Superpowers 6.3.0
- **License:** MIT
- **Verb:** DEFER
- **Graph relation:** consumes
- **Target:** rhize-devflow:completed-branch-promotion
- **Took:** nothing copied; the wrapper consumes maintained environment detection, detached-worktree handling, rejected-push safeguards, and cleanup mechanics
- **Verified:** skill validator; deterministic trigger/quality evals; promotion contract tests; skill-map freshness; full repository tests
- **Drift check:** `use existing ai-stack-version-drift sensor; rerun completed-branch-promotion trigger, quality, contract, and full Dev Flow tests on movement`
- **Notes:** DEFER+wrap approved 2026-08-30. Rhize owns only explicit authorization precedence, repository-policy resolution, simplify/check/review gating, protected task-to-dev-to-main (or dev-less task-to-main) PR choreography, migration/deployment ordering, Vercel author-safe release heads, and exact remote/deployment verification. The maintained Superpowers skill remains the single owner of generic branch-finishing and worktree-cleanup mechanics.

## simplify — 2026-08-24
- **Source:** https://docs.anthropic.com/en/docs/claude-code/cli-usage
- **Upstream ref:** Claude Code 2.1.241 built-in `/simplify` command; command body is not exposed as a stable filesystem or URL resource
- **License:** Anthropic product command; no separately stated content license
- **Verb:** FORK
- **Target:** rhize-devflow/skills/simplify/SKILL.md + commands/simplify.md
- **Took:** the reuse, quality, and efficiency review lenses
- **Verified:** skill/plugin authoring validators; deterministic trigger and quality evals; full repository tests
- **Drift check:** compare `claude --version` with `2.1.241`; on any version change, run built-in `/simplify` in a fresh fixture repo containing a duplicated policy helper, prop-mirrored React state, and a repeated calculation, then compare the upstream lenses, edit behavior, and authority boundaries with this entry before changing the fork
- **Upstream baseline:** three independent lenses (reuse, quality, efficiency), apply resulting improvements, review recently changed code
- **Notes:** load-bearing Rhize/Codex additions are exact diff resolution, dirty-worktree protection, verified no-op outcomes, React/Next.js conventions, behavior/authorization/concurrency/migration gates, regression evidence, and separation of edit from release authority. The plugin keeps one canonical skill body plus a thin qualified slash-command adapter to prevent host drift. The Source URL anchors the official Claude Code CLI product surface; the versioned fixture check is the content drift detector because Anthropic does not publish the built-in prompt body there.
