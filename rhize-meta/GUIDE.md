# rhize-meta — User Guide

This guide explains what the rhize-meta plugin does, when to reach for each half of it, and how to get good results out of it. For install steps, the full skill/command tables, and the skill-discovery-and-safety architecture, see `README.md` — this guide is about the "why" and "when," not the "how it's built."

## What This Plugin Does

Rhize's skill set is a living thing — you keep finding good skills other people built, and your own skills keep drifting from how they're actually used. Left unmanaged, that means either a bloated skill set full of half-vetted external skills, or a stagnant one where nobody ever fixes the false positives everyone's been quietly working around.

rhize-meta is skill governance: it decides what comes **in** from the outside world, and keeps what's already **yours** sharp based on how it actually gets used. It's for anyone maintaining the Rhize skill set — deciding whether to adopt something new, or fixing something that keeps misbehaving.

## The Two Halves

**Bringing in new skills → `rhize-skill-forge`.** You found something outside the Rhize set — a marketplace skill, an Anthropic example, a GitHub repo, an MCP server — and you're wondering whether it's worth adopting. Forge investigates it, checks it for overlap with what you already have, decides one of five outcomes (adopt as-is, absorb the good parts, fork and reskin, reject, or just watch it), and — critically — proves it's safe and actually better before anything sticks.

**Keeping your own skills sharp → `skill-refinement`.** A skill you already own did the wrong thing — missed a trigger, blocked something it shouldn't have, needs a new pattern. Refinement captures what you expected vs. what happened, generates a targeted patch, and tracks the pattern so that if the same fix shows up in two or more projects, it gets promoted from a one-off patch into the new default.

Quick way to tell them apart: if the skill in question **doesn't exist in Rhize yet**, that's forge. If it's **already yours and behaving badly**, that's refinement. Forge actually calls on refinement's patch machinery internally when it does an ABSORB — so refinement is the mechanic, forge is the one deciding what needs fixing.

## Skills Reference

### rhize-skill-forge

**When it activates:** You say "should we adopt," "ingest," "absorb," "evaluate," "steal the good parts of," "vendor," or "import" in reference to an external skill, plugin, or MCP server. Also activates for "did upstream change?" drift checks on things you've already absorbed.

**What it knows:** The five-verb decision matrix (DEFER / ABSORB / FORK / REJECT / WATCH) and the criteria for each; how to profile a candidate's structure, license, and dependencies; how to score overlap against your existing skill set; the two-layer safety gate (skills.sh partner audits + SkillSpector deep scan) that every candidate must clear before adoption; and how to record provenance so you can always answer "where did this come from, and are we allowed to use it?" It also reasons over the whole installed set at once — building a capability registry and finding N-way redundancy across skills you already have.

**How to use it effectively:**
- "Should we adopt the `engineering:debug` skill, or does it duplicate our error-lifecycle skill?" — forge profiles it, scores the overlap, and recommends a verb.
- "There's a great Sanity skill on GitHub, steal the good parts" — forge extracts the worthwhile patterns and hands them to skill-refinement as a patch, rather than copying the whole thing.
- "Ingest the Anthropic `internal-comms` example skill" — full pipeline: profile, scan, decide, execute, verify, record.
- "Re-check the skills we've absorbed — did any upstream sources change?" — drift watch.
- "Find me a skill for X" — forge can discover candidates via skills.sh before you even have one in hand.

**Key insight:** Forge never adopts on trust. Every DEFER/ABSORB/FORK has to clear a safety scan (blocked on HIGH/CRITICAL findings) and get a license check, and every absorbed or forked result has to be proven better than the baseline skill it's replacing — not just assumed to be. If that verification step gets skipped, you haven't adopted a skill, you've just added bloat with extra confidence.

### skill-refinement

**When it activates:** You say a skill "doesn't work," "should have caught," "missed," "false positive/negative," "why didn't it," or ask to "improve/extend/add to" a skill you already own. Also fires automatically after long or error-heavy sessions to check whether something's worth capturing.

**What it knows:** How to gather context on a skill (git status, existing overrides, similar past refinements, session/error history when available), how to turn "expected vs. actual" into a specific patch (section patch, extension, config override, or full rewrite), and the generalization threshold — when the same fix shows up across 2+ projects, it gets promoted from a one-off project patch into the new user-scope default.

**How to use it effectively:**
- "The duplicate-check hook keeps blocking my test fixtures" — refinement identifies the hook, generates a patch adding a test-directory exclusion, and previews the diff before writing anything.
- "The error-lifecycle skill should also trigger for 'performance issue'" — a trigger extension, applied as an additive patch.
- "Why didn't the skill catch this?" — refinement walks expected vs. actual, proposes a root cause, and recommends the right override type.
- Just describe the mismatch in plain language; refinement asks clarifying questions itself if your description is ambiguous (low-confidence cases trigger a guided mode automatically).

**Key insight:** Refinements start scoped to your current project, not your whole skill set. That's deliberate — a one-off fix stays a one-off fix until the same pattern recurs elsewhere, at which point it's promoted to a real default. This means a bad or overly-specific patch never contaminates every project by default.

## Commands Reference

### rhize-skill-forge commands

**`/rhize-meta:forge-ingest [source]`** — the full pipeline: profile → scan → decide → execute → verify → record. `<source>` can be a directory, `SKILL.md`, `.skill` bundle, marketplace skill name, or GitHub URL. Run it with no argument and it drains the `skill-forge` CLI's pending queue instead (candidates the CLI already quarantined and gated, waiting on a decision).
- `/rhize-meta:forge-ingest ~/Downloads/some-skill/`
- `/rhize-meta:forge-ingest https://github.com/someuser/some-skill`
- `/rhize-meta:forge-ingest` (drains the pending queue)

**`/rhize-meta:forge-scan <source>`** — read-only triage. Profile + overlap + recommended verb, no changes made. Use this to work through a backlog of candidates before committing to a full ingestion.
- `/rhize-meta:forge-scan skills.sh/some-candidate`

**`/rhize-meta:forge-watch`** — drift check across everything already absorbed, deferred, or watched. Surfaces sources whose upstream moved since you adopted them. Good candidate for a weekly scheduled task.

**`/rhize-meta:skill-find <query>`** — discover candidates for a need via skills.sh, then vet them: partner audit (Socket/Snyk/etc.) plus a deep SkillSpector scan before anything is handed off to forge for the actual adopt/reject decision.
- `/rhize-meta:skill-find "PDF form filling"`

**`/rhize-meta:skill-doctor`** — checks that the discovery and safety tooling itself is set up (SkillSpector installed, skills.sh's Vercel OIDC token present). Run this first if forge or skill-find reports a setup gap.

### skill-refinement commands

**`/rhize-meta:refine-skills`** — the main capture workflow. Identifies the target skill and category (trigger, content, hook, tool, pattern, config, or brand new capability), gathers context automatically, walks you through expected-vs-actual, and generates a previewable patch.
- `/rhize-meta:refine-skills` (after describing what went wrong in plain language)

**`/rhize-meta:review-patterns`** — see everything being tracked: patterns still at count 1, patterns ready for generalization (count ≥ 2, meaning they've recurred across projects), and patterns already generalized. Filter by `--status`, `--skill`, or `--project`, or drill into one with `/rhize-meta:review-patterns PATTERN-001`.

**`/rhize-meta:apply-generalization [PATTERN-ID]`** — promote a queued pattern from a project-local patch into the new user-scope default. Shows the affected files and proposed diff before touching anything, backs up existing files first, and supports `--dry-run` and `--rollback` if a generalization turns out to be wrong.
- `/rhize-meta:apply-generalization --list` (see what's eligible)
- `/rhize-meta:apply-generalization PATTERN-001`

## How Forge and Refinement Compose

These two halves are meant to be used together across a skill's lifecycle, not in isolation:

1. **Bring a skill in.** `/rhize-meta:forge-ingest` on an external candidate. Say it scores ABSORB against your existing SEO skill — forge extracts the worthwhile patterns rather than copying the whole thing.
2. **Forge hands off to refinement.** The ABSORB step doesn't hand-merge the patterns; it calls skill-refinement's patch machinery to apply them as a tracked, generalizable patch against the target skill. This is also why forge insists on verifying with the skill-creator eval loop afterward — an absorbed patch is only worth keeping if it beats the pre-absorption baseline.
3. **Use it for a while.** The absorbed (or entirely home-grown) skill runs in real projects. Eventually something about it doesn't quite fit — a trigger that should've fired didn't, a hook is too aggressive, whatever.
4. **Refine it from feedback.** `/rhize-meta:refine-skills` captures the gap and patches it, scoped to the project where you noticed it.
5. **Let recurring fixes graduate.** If the same patch pattern shows up in a second project, `/rhize-meta:review-patterns` flags it as ready, and `/rhize-meta:apply-generalization` promotes it to the new default for everyone — closing the loop from "one project's workaround" to "how the skill actually works now."

## Tips for Getting the Best Results

**Be specific about what's wrong, not just that something's wrong.** "The skill broke" triggers refinement, but "expected: X, got: Y, when I ran Z" gets you out of guided mode and straight to a patch. The more concrete your expected-vs-actual, the higher the confidence score and the less back-and-forth.

**Let forge do the deciding — don't skip straight to copying.** If you're tempted to just copy an external skill's directory in wholesale, run `/rhize-meta:forge-scan` first. Most external skills aren't worth adopting whole; the value is usually a handful of patterns, and forge's overlap scan will tell you which existing Rhize skill they belong in instead.

**Treat "worth a closer look: no" as a real answer.** A forge-scan verdict of REJECT or WATCH isn't a consolation prize — it's the point of running the scan before doing the work of a full ingestion.

**Don't manually merge an ABSORB.** Always let forge hand the extraction to skill-refinement's patch machinery rather than editing the target skill by hand — that's what keeps the change tracked, generalizable, and reversible.

**Run `/rhize-meta:skill-doctor` before your first forge session.** Safety scanning (SkillSpector) needs no external account, but skills.sh discovery needs a Vercel OIDC token — better to find that out before you're mid-ingestion.

**Check the pattern queue periodically.** `/rhize-meta:review-patterns` costs nothing to run and tells you when a project-local fix has quietly become something worth making the default everywhere.

## Troubleshooting

**Forge won't proceed past Step 3 ("Decide"):** It's blocking on license or safety. A restrictive/unknown license, or a SkillSpector HIGH/CRITICAL finding, is a hard stop by design — resolve the underlying issue (get explicit licensing clarity, or address the flagged risk) rather than trying to force the adoption through.

**`skill-find` or `forge-ingest` reports missing setup:** Run `/rhize-meta:skill-doctor`. Static safety scanning only needs SkillSpector installed locally; skills.sh discovery additionally needs `VERCEL_OIDC_TOKEN` (enable OIDC Federation on a Vercel project, then `vercel link && vercel env pull`).

**Nothing happens when you run `/rhize-meta:forge-ingest` with no source:** That's expected if `~/.skill-forge/queue.json` doesn't exist or has no `pending` entries — there's nothing to drain. It's not a failure.

**A refinement patch didn't take effect:** Check override precedence — project-local (`./.claude/skills/[skill]/`) beats project-shared, which beats user-scope. If you patched at the wrong scope, or a project-local override is shadowing the generalized fix, that's why the behavior didn't change.

**A pattern seems stuck at count 1 and never generalizes:** Generalization requires the *same* pattern to recur in a *second, different* project — repeating it in the same project doesn't increment the count. If it should have matched a prior refinement and didn't, check `/rhize-meta:review-patterns --skill <skill-name>` to see if it was logged as a new pattern instead of matched to the existing one.

**An `/rhize-meta:apply-generalization` went wrong:** Every generalization is backed up before it's applied. Run `/rhize-meta:apply-generalization --rollback PATTERN-ID` to restore from backup.

**Forge's overlap score feels wrong (too high or too low):** The overlap scan is a heuristic prior based on name/description/keyword similarity, not a verdict — always read the actual candidate and target skill before trusting it, especially near the decision boundary between ABSORB and FORK.
