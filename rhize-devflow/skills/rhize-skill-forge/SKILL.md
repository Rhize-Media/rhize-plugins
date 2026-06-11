---
name: rhize-skill-forge
version: 1.0.0
description: >-
  Investigate an EXTERNAL skill and decide how to absorb it into the Rhize skill set. Use when the
  user wants to "ingest", "absorb", "evaluate", "import", "vendor", "steal the good parts of", or
  "should we adopt" a skill — whether it's a marketplace skill, an Anthropic example skill, a
  GitHub repo, a `.skill` bundle, or a directory path. Profiles the candidate, scans overlap
  against the existing Rhize skills, applies a defer/absorb/fork/reject/watch decision matrix,
  extracts only the patterns worth keeping (via the skill-refinement patch machinery), verifies
  the result with the skill-creator eval loop, and records provenance + license so nothing is
  adopted blindly. Distinct from skill-refinement (which improves skills you already own from your
  own usage); this one decides what to pull IN from the outside world. Also triggers on "drift
  check" / "did upstream change" for skills already absorbed.
---

# Rhize Skill Forge

> Investigate an external skill → decide → absorb the worthwhile parts → verify → record provenance.

This skill is the **import side** of the Rhize meta-toolchain. `skill-creator` builds skills from
scratch; `skill-refinement` improves your own skills from usage feedback; **`rhize-skill-forge`
decides what to pull in from someone else's skill and how to make it ours** without bloat,
licensing risk, or duplicating something you already have.

The core idea: most external skills are *not* worth adopting whole. The value is usually a few
patterns, a reference doc, or one good script. Forge exists to extract that signal and reject the
rest — and to prove the absorbed version is actually better before you keep it.

---

## When to reach for this

- "Should we adopt `<some marketplace skill>`?"
- "Ingest the Anthropic `internal-comms` example skill."
- "There's a great Sanity skill on GitHub — steal the good parts."
- "We installed `engineering:debug` — does it make our error-lifecycle skill redundant?"
- "Re-check the skills we absorbed — did any upstream sources change?" (drift watch)

If the request is to *create* a skill from nothing → use `skill-creator`.
If the request is to *fix our own* skill from how it behaved → use `skill-refinement`.

---

## The five-verb decision matrix

Every candidate resolves to exactly one verb. This is the heart of the skill — read
`references/decision-matrix.md` for the full criteria and edge cases.

| Verb | Meaning | Typical signal |
|------|---------|----------------|
| **DEFER** | Adopt as-is; just install/keep it, point Rhize skills at it | High quality, low overlap, well-maintained, permissive license |
| **ABSORB** | Pull specific patterns into an existing Rhize skill via a patch | High overlap with one Rhize skill; candidate has a few better parts |
| **FORK** | Copy + re-skin with Rhize conventions as a new Rhize skill | Good bones, but house style / stack assumptions differ enough |
| **REJECT** | Take nothing | Low quality, redundant, restrictive license, or net-negative |
| **WATCH** | Don't adopt now, but link as reference and track upstream | Promising but immature, or you want it only as a citation |

**Why a forced single verb:** ambiguity is where bloat creeps in. If a candidate looks like both
ABSORB and FORK, that's a signal the overlap analysis isn't finished — go back to step 2.

---

## Workflow

### Step 1 — Profile the candidate

Run the profiler to get a structured read of what you're dealing with. It handles a directory, a
single `SKILL.md`, or a `.skill` zip. For a GitHub URL, clone/fetch it to a temp dir first, then
point the profiler at it. For an installed marketplace skill, point it at the skill's directory.

```bash
python3 scripts/profile_skill.py <path-to-skill-or-.skill> --json
```

You get: name, description, version, **license** (file or frontmatter), body size, structure
(headers), bundled resources (scripts/references/commands/hooks/assets/templates counts), declared
MCP/tool dependencies, and external package imports. Read it before forming any opinion — you
cannot judge overlap or licensing from the description alone.

### Step 2 — Scan overlap against the Rhize set

```bash
python3 scripts/overlap_scan.py <candidate-path> --skills-root <rhize-skills-root> --json
```

This ranks the candidate against every existing Rhize skill by name + description + keyword
overlap and returns a similarity score per skill plus a **suggested verb** heuristic. Treat the
heuristic as a prior, not a verdict — `references/overlap-analysis.md` explains how to read it and
when to override. The nearest Rhize skill is the ABSORB target if you go that route.

### Step 3 — Decide (the human gate)

Present a tight recommendation to the user before doing anything irreversible:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔨 Forge: <candidate-name>  (v<version>, <license>)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nearest Rhize skill : <name>  (overlap <score>)
Recommended verb    : ABSORB
What's worth taking  : <bullet list of specific patterns/files>
What to leave behind : <bullet list>
License/provenance   : <permissive | needs attribution | blocked>
Proposed target      : <rhize-skill> via SKILL.patch.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Get explicit confirmation. **Never absorb on a restrictive/unknown license** — escalate to the
user with the exact license text (see `references/provenance.md`).

### Step 4 — Execute the verb

- **DEFER:** add/keep the install; update the relevant Rhize skill `description` to say "for X,
  defer to `<plugin:skill>`". No copying.
- **ABSORB:** extract the chosen patterns and hand them to `skill-refinement` as a patch against
  the target skill (`SKILL.patch.md` / `SKILL.extend.md` / a new reference file). Do **not**
  hand-merge — reuse the existing patch machinery so the change is tracked and generalizable.
- **FORK:** copy into a new `rhize-<name>/` skill dir, then rewrite the frontmatter/description to
  the Rhize standard (valid `---` frontmatter, pushy keyword-rich description), strip stack
  assumptions that don't match, and add a `SOURCES.md` provenance entry.
- **REJECT:** record the decision and reason in the ledger so it isn't re-evaluated later.
- **WATCH:** add a reference link in the nearest Rhize skill + a ledger entry with an upstream
  check command.

### Step 5 — Verify (do not skip)

Absorbed or forked output must be **proven better than baseline**, not assumed. Invoke the
`skill-creator` eval loop on the changed/new skill: a couple of realistic prompts, with-skill vs
baseline, reviewed in the eval viewer. If the absorbed version doesn't beat baseline, you took the
wrong patterns — return to Step 2. This is the single most important step; an unverified absorption
is just bloat with extra confidence.

### Step 6 — Record provenance

```bash
python3 scripts/record_provenance.py \
  --source "<url-or-path>" --name "<candidate>" --version "<v>" --license "<license>" \
  --verb ABSORB --target "<rhize-skill>" --took "<what was taken>" \
  --skills-root <rhize-skills-root>
```

This appends to `SOURCES.md` (the audit ledger) and emits a vault note stub so the decision lives
in the Obsidian second brain, not just git. Provenance is non-negotiable — you are adopting other
people's work and must be able to answer "where did this come from and are we allowed to use it?"

---

## Drift watch

External sources change. For anything you DEFER, ABSORB, or WATCH, the ledger stores an upstream
identifier. Periodically:

```bash
python3 scripts/record_provenance.py --check-drift --skills-root <rhize-skills-root>
```

This lists absorbed sources whose upstream version/commit has moved, so you can re-run the forge
on the delta. Good candidates for a scheduled task (weekly).

---

## Commands

| Command | Purpose |
|---------|---------|
| `/rhize-devflow:forge-ingest <source>` | Full pipeline: profile → scan → decide → execute → verify → record |
| `/rhize-devflow:forge-scan <source>` | Overlap report only — no changes, just the recommendation |
| `/rhize-devflow:forge-watch` | Drift check across all absorbed sources |

---

## Scripts

| Script | Type | Command |
|--------|------|---------|
| `profile_skill.py` | 🔧 EXECUTE | `python3 scripts/profile_skill.py <path> --json` |
| `overlap_scan.py` | 🔧 EXECUTE | `python3 scripts/overlap_scan.py <path> --skills-root <root> --json` |
| `record_provenance.py` | 🔧 EXECUTE | `python3 scripts/record_provenance.py --source ... --name ...` |

All scripts are stdlib-only (no pip installs), accept `--json`, and fail loudly with clear errors
rather than guessing.

---

## References

- `references/decision-matrix.md` — full criteria for each of the five verbs + edge cases
- `references/overlap-analysis.md` — how the similarity score works and when to override it
- `references/provenance.md` — license handling, attribution rules, `SOURCES.md` format

---

## Templates

- `templates/ingestion-report.md` — the structured report to fill in per candidate

---

## Related skills

- **skill-creator** — builds skills from scratch; provides the eval loop this skill verifies with
- **skill-refinement** — improves owned skills from usage; provides the patch machinery ABSORB uses
- **dev-flow-foundations** — the verify-first / no-duplication principles this skill enforces
