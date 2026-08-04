---
name: refinement-pipeline
description: >-
  Operate and reason about the gated skill-refinement pipeline: headroom learn +
  claude-mem + skill-monitor signals flow into a human-triaged queue, then
  skill-forge evolve (SkillOpt-Sleep + safety re-gate) refines target skills with
  auto-promote for gate-passing SKILL.md edits. Use when the user says "harvest
  learnings", "refine skills", "drain the refinement queue", asks where headroom
  learn output should go, or when a scheduled refinement pass needs its rules.
---

# Refinement Pipeline — Signals → Queue → Gated Evolve

```
SIGNALS                        QUEUE (human gate)            REFINEMENT (machine gate)
headroom learn (dry-run) ──┐                              ┌→ skill-forge evolve per skill
claude-mem observations ───┼→ refinement-queue.jsonl ─────┤  (SkillOpt-Sleep + re-gate)
skill-monitor snapshots ───┘  pending → triaged|rejected  └→ ALLOW + score↑ + SKILL.md-only
                              (/skill-refine review)          → AUTO-PROMOTE, else HOLD
```

- Queue: `~/.claude/context-manager/refinement-queue.jsonl` (schema in
  `/learn-harvest`). Run reports: `~/.claude/context-manager/runs/`.
- Commands: `/learn-harvest` (collect), `/skill-refine review` (triage),
  `/skill-refine run` (drain — headless-safe).
- Scope (iteration 1): this plugin's skills + `~/.claude/skills/learned/`.
- Schedule (changed 2026-08): harvest and drain now run on separate cadences. Harvest
  (`/learn-harvest`) runs DAILY as its own standalone scheduled task,
  `~/Documents/Claude/Scheduled/daily-learn-harvest/SKILL.md`, on a cheap model
  (mechanical collection — no judgment). Drain (`/skill-refine run`) stays WEEKLY, inside
  the existing `weekly-skill-audit` routine
  (`~/Documents/Claude/Scheduled/weekly-skill-audit/SKILL.md`, step 8) on a capable model
  — the drain/promote decision plus the audit's own judgment calls justify keeping it on
  the smarter tier. Triage (`/skill-refine review`) stays manual between runs, on
  whatever cadence Jim chooses. The daily harvest means the weekly drain now works from a
  full week of accumulated queue entries instead of a single once-a-week collection pass.

## Trust model (why two gates)

The human gate is at **triage**: the operator curates what the optimizer ever
sees, so noisy or wrong signals die in the queue, not in a skill. The machine
gate is at **promote**: skill-forge re-scans every SkillOpt proposal with its
safety ruleset — SkillOpt's own validation only checks score improvement, so
the re-gate is what makes auto-promote defensible. Auto-promote is further
restricted to SKILL.md/reference-markdown edits; anything touching `scripts/`,
`hooks/`, or `allowed-tools` HOLDs for human review, always.

## Rules that keep the loop honest

1. **headroom learn never writes context files in this pipeline.** It runs
   dry-run (the default); `--apply` is reserved for deliberate, reviewed use.
   Learned patterns belong in skills (durable, routed) — not appended forever
   to CLAUDE.md, where they historically accumulated as duplicated
   "Headroom Learned Patterns" sections.
2. **Never evolve untriaged.** The queue is the only path into a refinement run.
3. **Never `--force` past a HOLD.**
4. **Every run leaves a report** (`runs/<date>.md`) — per skill: signals
   consumed, verdict, promoted/held. The report is the audit trail that makes
   auto-promote reviewable after the fact.
5. **Drift check**: third-party skills refined here remain subject to
   `skill-forge watch` (SOURCES.md ledger) — evolution does not detach them
   from upstream tracking.

## Relationship to neighbors

- `learning-curation` decides IF a learning deserves persistence and WHERE
  (config vs skill vs hook vs nowhere) — use it during triage when the right
  target isn't obvious.
- The Compounding Contract's "write verified failure modes into skills" is the
  manual fast-path this pipeline automates for the recurring case.
- Productization: proven logic graduates into `@rhize/skill-forge` as
  `evolve --signals <file>` (formal queue schema); these commands then thin to
  wrappers.
