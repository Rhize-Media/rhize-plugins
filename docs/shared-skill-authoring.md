# Writing skills for Claude Code and Codex

Maintain one shared workflow and place host-specific behavior in the host adapter or
configuration that owns it. A skill should add useful domain knowledge, operational constraints
or reliable tools while preserving the user's scope and existing authorization.

## Describe the decision to load

Put the capability and its triggering situation first. Use a short description that distinguishes
the skill from its neighbors. List exclusions only when they prevent a likely wrong selection.
Move detailed tool lists, setup steps and output formats into the body or a relevant reference.

For example, describe session recovery as "Resume a development session from its saved context"
rather than triggering on the word "start" in any request. Explicit invocation must still work.
Generic claims such as "always use for any coding task" need a concrete, applicable reason.

Description and body length are review signals, not quality scores. A maximum is not a writing
target. Retain a longer description when its distinctions are necessary; never disable a skill
or lower a safety verdict merely to satisfy a size budget.

## Load the detail the task needs

Keep purpose, essential constraints and mode selection in `SKILL.md`. Link substantial setup,
provider or phase-specific instructions where they become relevant, explaining when to read each.
Do not require every reference to be loaded at invocation. A simple skill can remain one file.

Describe outcomes and decisions when several approaches are valid. Keep exact sequences for
fragile operations: credential handling, deployment, data migration, provenance, approval and
rollback. Reuse existing executable helpers for deterministic work. Do not trim away an invariant
because a newer model is expected to infer it.

## Preserve the shared contract

- Keep names, explicit commands, metadata, invocation policies, permissions and provenance unless
  the requested change actually concerns them. A description edit should leave body bytes intact.
- Preserve relative resource paths and each host's supported frontmatter and substitutions.
  Test complete plugins when skills depend on parent directories or plugin scripts.
- Update owned sources through their release workflow. Do not patch installed caches or repoint
  canonical shared symlinks to optimize one host. Review upstream provenance before modifying a
  shared third-party skill.
- Put model-specific persistence and validation guidance in the appropriate host configuration.
  Do not add a model requirement or disable automatic discovery as a context optimization.
- Distinguish authorization from execution detail. Continue authorized reversible work; retain
  concrete approval boundaries for effects outside that authorization. Define a completion signal
  and a stopping condition, rather than adding indefinite review loops.

## Verify a change at its actual boundary

For description changes, predeclare positive, negative, adjacent-skill and explicit-invocation
cases. Keep body refactors in a separate experiment. Verify resource links, required script
behavior and output constraints when changing the body or packaging.

Compare current content (Arm A) with one candidate (Arm B) inside each host/model cohort, using
matched tasks, tools and settings and recording exact content identities. Claude Skill events and
Codex file reads require different observation logic. A static catalog listing establishes
discovery, not invocation or task success.

Include native commands and neighboring skills in the routing inventory. Claude's `Skill` tool
can load a plugin command such as `/start` without loading the similarly named `SKILL.md`.
Record that route separately and verify its actual source; do not count a command as a target
skill invocation or a missing observation as a correct negative. Test snapshots must replace
the candidate in the test catalog, rather than silently adding a second copy of the same skill.
Keep any test-only catalog override ephemeral; preserve installed skills and shared aliases.
Record model-visible catalog warnings separately: an enabled skill in the host inventory can
still be omitted from the model's list, and its description can be removed before selection.

Treat failed, interrupted and unobserved runs as unavailable evidence. Preserve historical
receipts. Report sample size and coverage; fewer description characters do not establish reduced
latency or better task outcomes. Require Claude compatibility before adopting a shared change.

Use [the evaluation harness](../evals/README.md) and SkillForge's existing audit/refinement paths.
Keep diagnostic advice separate from safety verdicts and installed-skill mutation. After a change,
update the owning plugin's README, GUIDE and changelog and regenerate the skill map through the
repository's release tooling.
