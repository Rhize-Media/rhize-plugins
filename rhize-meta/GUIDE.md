# rhize-meta — User Guide

This guide explains what the rhize-meta plugin does, when to reach for it, and how to get good
results out of it. For install steps and the full skill/command tables, see `README.md` — this
guide is about the "why" and "when," not the "how it's built."

## What This Plugin Does

Your own skills keep drifting from how they're actually used — a trigger that should have fired
didn't, a hook is too aggressive, a pattern needs a new case. Left unmanaged, that means either
nobody ever fixes the false positives everyone's quietly working around, or every fix gets
hand-patched ad hoc with no record of why.

rhize-meta is `skill-refinement`: it keeps what's already **yours** sharp based on how it actually
gets used. It's for anyone who noticed one of their own skills doing the wrong thing and wants that
fix captured, tracked, and — if it recurs — promoted into the default everywhere.

(Investigating and absorbing *external* skills or MCP servers — the other half of skill
governance — now lives in the `@rhize/skill-forge` npm package; see README.md's "Skill vetting
moved" section.)

## Skills Reference

### skill-refinement

**When it activates:** You say a skill "doesn't work," "should have caught," "missed," "false
positive/negative," "why didn't it," or ask to "improve/extend/add to" a skill you already own.
Also fires automatically after long or error-heavy sessions to check whether something's worth
capturing.

**What it knows:** How to gather context on a skill (git status, existing overrides, similar past
refinements, session/error history when available), how to turn "expected vs. actual" into a
specific patch (section patch, extension, config override, or full rewrite), and the
generalization threshold — when the same fix shows up across 2+ projects, it gets promoted from a
one-off project patch into the new user-scope default.

**How to use it effectively:**
- "The duplicate-check hook keeps blocking my test fixtures" — refinement identifies the hook, generates a patch adding a test-directory exclusion, and previews the diff before writing anything.
- "The error-lifecycle skill should also trigger for 'performance issue'" — a trigger extension, applied as an additive patch.
- "Why didn't the skill catch this?" — refinement walks expected vs. actual, proposes a root cause, and recommends the right override type.
- Just describe the mismatch in plain language; refinement asks clarifying questions itself if your description is ambiguous (low-confidence cases trigger a guided mode automatically).

**Key insight:** Refinements start scoped to your current project, not your whole skill set.
That's deliberate — a one-off fix stays a one-off fix until the same pattern recurs elsewhere, at
which point it's promoted to a real default. This means a bad or overly-specific patch never
contaminates every project by default.

## Commands Reference

**`/rhize-meta:refine-skills`** — the main capture workflow. Identifies the target skill and category (trigger, content, hook, tool, pattern, config, or brand new capability), gathers context automatically, walks you through expected-vs-actual, and generates a previewable patch.
- `/rhize-meta:refine-skills` (after describing what went wrong in plain language)

**`/rhize-meta:review-patterns`** — see everything being tracked: patterns still at count 1, patterns ready for generalization (count ≥ 2, meaning they've recurred across projects), and patterns already generalized. Filter by `--status`, `--skill`, or `--project`, or drill into one with `/rhize-meta:review-patterns PATTERN-001`.

**`/rhize-meta:apply-generalization [PATTERN-ID]`** — promote a queued pattern from a project-local patch into the new user-scope default. Shows the affected files and proposed diff before touching anything, backs up existing files first, and supports `--dry-run` and `--rollback` if a generalization turns out to be wrong.
- `/rhize-meta:apply-generalization --list` (see what's eligible)
- `/rhize-meta:apply-generalization PATTERN-001`

## Tips for Getting the Best Results

**Be specific about what's wrong, not just that something's wrong.** "The skill broke" triggers refinement, but "expected: X, got: Y, when I ran Z" gets you out of guided mode and straight to a patch. The more concrete your expected-vs-actual, the higher the confidence score and the less back-and-forth.

**Check the pattern queue periodically.** `/rhize-meta:review-patterns` costs nothing to run and tells you when a project-local fix has quietly become something worth making the default everywhere.

## Troubleshooting

**A refinement patch didn't take effect:** Check override precedence — project-local (`./.claude/skills/[skill]/`) beats project-shared, which beats user-scope. If you patched at the wrong scope, or a project-local override is shadowing the generalized fix, that's why the behavior didn't change.

**A pattern seems stuck at count 1 and never generalizes:** Generalization requires the *same* pattern to recur in a *second, different* project — repeating it in the same project doesn't increment the count. If it should have matched a prior refinement and didn't, check `/rhize-meta:review-patterns --skill <skill-name>` to see if it was logged as a new pattern instead of matched to the existing one.

**An `/rhize-meta:apply-generalization` went wrong:** Every generalization is backed up before it's applied. Run `/rhize-meta:apply-generalization --rollback PATTERN-ID` to restore from backup.
