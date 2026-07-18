---
name: rhize-skill-forge
version: 1.1.0
tier: custom
domain: meta
consumes:
  - skill-refinement
  - skill-creator
maturity: stable
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

## Two modes

Forge works at two scopes:

- **Per-candidate (default)** — one external skill at a time: profile → scan → decide → execute →
  verify → record. That's the workflow below.
- **Set-level (organizer)** — the whole installed set at once: build a capability registry, surface
  internal redundancy, map dependencies. See [Set-level mode](#set-level-mode-organizer) and
  `references/capability-schema.md`. This is the metadata-first on-ramp to the *Skill Customizer &
  Organizer* — no runtime engine.

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
single `SKILL.md`, a `.skill` zip, a **plugin** dir (`.claude-plugin/plugin.json`), or an **MCP
config** dir — reporting the right structure for each. For a GitHub URL, clone/fetch it to a temp
dir first, then point the profiler at it. For an installed marketplace skill, point it at the
skill's directory.

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
on the delta. **Don't schedule this separately** — detection is owned by the `ai-stack-version-drift`
sensor (the only drift cron); `--check-drift` is the on-demand *classifier* it feeds, run via
`/rhize-meta:forge-watch` or off the sensor's report. See `references/drift-boundaries.md`.

---

## Set-level mode (organizer)

Beyond one-candidate-at-a-time, Forge reasons over the **whole installed set** — the metadata
backbone of the Skill Customizer & Organizer. All stdlib, all `--json`.

```bash
# 1. Build the capability registry (tier/domain/consumes/provenance + usage join)
python3 scripts/index_skills.py --skills-root <root> \
  --usage-snapshot rhize-ops/skill-monitor/data/snapshots/<latest>.json --json

# 2. Find internal redundancy (N-way overlap across the set — e.g. duplicate SEO skills)
python3 scripts/overlap_scan.py --set-mode --skills-root <root> --threshold 0.45

# 3. Map custom→resource dependencies from `consumes:` edges
python3 scripts/build_dependency_graph.py --skills-root <root> --json
```

Tag skills with the capability frontmatter (`references/capability-schema.md`) so the registry and
graph are legible; untagged skills surface as rot in the registry output. To build custom skills
*from* resources, see `references/composition-patterns.md` (DEFER+wrap, N-way ABSORB).

---

## Skill discovery & safety (skills.sh + SkillSpector)

Forge ingests external skills — so it owns both **finding** candidates and **proving them safe**
before anything is adopted. Two layered checks; a candidate must clear **both**.

```bash
# Discover candidates for a need (skills.sh — 600k+ skills; needs VERCEL_OIDC_TOKEN)
python3 scripts/skills_sh.py search "<what you need>" --limit 10

# Fast partner audit (Socket / Snyk / Gen Agent Trust Hub / ...) — pass | warn | fail
python3 scripts/skills_sh.py audit <id>

# Deep local scan — MANDATORY before DEFER/ABSORB/FORK. BLOCK on HIGH/CRITICAL.
python3 scripts/skill_safety.py <path-or-git-url> --no-llm
```

**Gate rule (folds into Step 3, the human gate):** never DEFER/ABSORB/FORK a candidate that
SkillSpector rates HIGH or CRITICAL, or that any skills.sh partner marks `fail`. MEDIUM/`warn` →
review findings first. The safety scan is as non-negotiable as provenance.

Setup is checked by `/rhize-meta:skill-doctor` (SkillSpector install + `VERCEL_OIDC_TOKEN`); the
scripts also print exact setup steps when a tool or token is missing. Static scanning needs only
SkillSpector (no key); skills.sh discovery needs the Vercel OIDC token.

---

## CLI pending queue

The `skill-forge` npm CLI (`npx skills@latest add`, wrapped in quarantine + gate) is the
**productized** front door to this same pipeline — it already runs profile → safety scan → overlap
analysis before a human ever sees it, then queues the result for a Claude ingest pass instead of
deciding alone. On invocation, check for pending entries before starting any new profile/scan work:

```bash
cat ~/.skill-forge/queue.json 2>/dev/null
```

If the file exists and has entries with `"status": "pending"`, list them for the user — do **not**
silently drain the queue. For each pending entry:

1. **Reuse the CLI's gate results** — `gate.safetyVerdict`, `gate.safetyFindings`, `gate.license`,
   and (Pro tier) `gate.overlapTop` were already computed by the CLI. Do not re-run
   `profile_skill.py` / `skill_safety.py` / `overlap_scan.py` on the same source; that duplicates
   work the CLI already gated on.
2. **Decide** — apply the five-verb decision matrix using the reused gate data. If
   `gate.suggestedVerb` is set, treat it as a prior the same way the overlap-scan heuristic is
   treated (see `references/overlap-analysis.md`) — not a verdict.
3. **Execute + verify + record** — Steps 4–6 of the [Workflow](#workflow) above, unchanged. The
   entry's `quarantinePath` is the source for FORK/ABSORB extraction; once promoted,
   `installedPath` is what `record_provenance.py --source` should reference going forward.
4. **Close the entry** — set `status` to `"ingested"` once recorded, or `"dismissed"` if the user
   declines. Never delete entries; the queue is the audit trail until provenance recording finishes.

`/rhize-meta:forge-ingest` with no `<source>` argument drains this queue automatically.

### Entry schema

`~/.skill-forge/queue.json` — `{ "version": 1, "entries": [Entry] }`. One `Entry`:

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | short unique slug |
| `source` | string | original slug/url/path the CLI installed from |
| `sourceType` | `"skills.sh"` \| `"git"` \| `"local"` | how the CLI resolved `source` |
| `installedPath` | string \| null | final path after promote; `null` until promoted |
| `quarantinePath` | string | where the CLI staged the candidate for inspection |
| `gate.license` | string \| null | from the CLI's safety scan |
| `gate.safetyVerdict` | `"pass"` \| `"warn"` \| `"block"` | reuse — do not recompute |
| `gate.safetyFindings` | string[] | reuse — do not recompute |
| `gate.overlapTop` | `{skill, score}[]` | Pro tier only; empty array on Free |
| `gate.suggestedVerb` | `"DEFER"` \| `"ABSORB"` \| `"FORK"` \| `"REJECT"` \| `"WATCH"` \| `null` | CLI's heuristic, treat as a prior |
| `status` | `"pending"` \| `"ingested"` \| `"dismissed"` | set by this skill when the entry is closed |
| `createdAt` | string | ISO 8601 |
| `artifactType` | `"skill"` \| `"mcp"` (optional) | what kind of candidate this entry is for; absent means `"skill"` — pre-v0.5 entries stay valid without it |
| `capabilities` | object (optional) | `"mcp"` entries only, skill-forge v0.6+; statically-extracted server capability profile — `{ tools: string[], resources: string[], prompts: string[], transport?: string, declaredConfidence: "high"\|"partial"\|"none" }`. Additive: absent on pre-v0.6 `"mcp"` entries and on `"skill"` entries. See [MCP servers](#mcp-servers-from-skill-forge-v06) below. |
| `origin` | `"evolve"` (optional) | how the entry was produced when it isn't a normal `add`-sourced external install; absent means a normal entry. `"evolve"` (skill-forge v0.7): the skill was self-evolved via `skill-forge evolve` (SkillOpt-Sleep) and already re-gated by the static safety ruleset at adopt time — the decide pass reviews the evolution itself, not an external source |

No file → nothing to drain, proceed as normal. A `queue.json` with zero `pending` entries isn't
worth mentioning to the user.

Starting with skill-forge v0.5, the CLI can also gate MCP servers (`artifactType: "mcp"`) — the
same quarantine → profile → safety → overlap → promote pipeline, but against an mcp config file
(`mcpServers`) instead of a skills root. skill-forge v0.6 adds the deep-forge pass for these
entries — the server-specific five-verb workflow lives in
[MCP servers](#mcp-servers-from-skill-forge-v06) below, and replaces Steps 1–4 above for `"mcp"`
entries. skill-forge v0.7 adds `origin: "evolve"` entries: the skill is already adopted and
re-gated when the entry lands, so treat the CLI verdict as done and focus the five-verb pass on
whether the evolution should stand (compare against the staging `report.md` evidence if present).

---

## MCP servers (from skill-forge v0.6)

skill-forge v0.6 adds a **static capability profile** to `"mcp"` queue entries: the CLI parses the
quarantined server's `package.json`, any shipped `.mcp.json`/manifest, and MCP SDK call patterns
(`server.tool(...)`, `server.registerTool(...)`, `setRequestHandler(ListToolsRequestSchema, ...)`,
`server.resource(...)`, `server.prompt(...)`) into a best-effort `capabilities` object — **never**
by installing, importing, or running the server. This section is where that material becomes a
decision: the same [five-verb matrix](#the-five-verb-decision-matrix) as skills, applied to a
**server** instead of a skill package.

### The five verbs, for a server

| Verb | For an MCP server entry |
|------|--------------------------|
| **DEFER** | Keep the promoted config exactly as-is — it's already wired into the mcp config; close the entry, nothing further to do. |
| **ABSORB** | Tighten the promoted entry's `env`/`args` (narrower scopes, pinned versions, drop unused vars), or fold it into an already-configured server that covers the same tools — don't run two servers exposing the same capability. |
| **FORK** | Re-skin it — wrap the server behind a thin custom skill (`tier: custom`, `consumes:` edge) that injects Rhize context, per the DEFER+wrap variant in `references/decision-matrix.md`. Use when the server itself is fine but needs Rhize-specific framing to be usable. |
| **REJECT** | Remove the server entry from the mcp config via a documented edit — record why, so it isn't silently re-queued next time the same server comes up. |
| **WATCH** | Leave a note in the nearest Rhize skill/ledger and do **not** wire it into the live mcp config. Revisit on drift, same as a skill WATCH. |

### Step 1 — Review declared capabilities statically

Read the entry's `capabilities` field (`tools`, `resources`, `prompts`, optional `transport`,
`declaredConfidence: "high" | "partial" | "none"`) — the CLI's static, execution-free scan of the
quarantined package. **Never `npm install`, `require()`, `import()`, spawn, or otherwise run the
server to see what it does** — that defeats the entire point of quarantining it. If
`declaredConfidence` is `"partial"` or `"none"` (or `capabilities` is absent — pre-v0.6 `"mcp"`
entries never have it), say so explicitly in the recommendation instead of filling the gap by
executing the server; an incomplete static profile is a reason to lean WATCH or ask the user, not a
reason to run code.

### Step 2 — Compare against what's already configured

Check the entry's overlap data (`gate.overlapTop`, Pro tier) and the tools/resources already
exposed by servers already in the live mcp config. High overlap in declared tool names → ABSORB
(merge) or REJECT (redundant); no meaningful overlap → DEFER or FORK depending on whether the
server needs Rhize framing.

### Step 3 — Decide (the same human gate)

Present the recommendation in the same format as [Step 3](#step-3--decide-the-human-gate) above,
adapted for a server: candidate name/version, declared capabilities + `declaredConfidence`,
nearest configured server + overlap, recommended verb, what changes to the config (if any),
license/provenance. Get explicit confirmation before touching the live mcp config — REJECT and
ABSORB both mutate a file every session depends on.

### Step 4 — Act on the promoted config

- **DEFER / WATCH**: no config edit. WATCH also skips wiring the server in at all — do not add it
  to the live mcp config just because it was promoted.
- **ABSORB**: edit `env`/`args` in place, or remove the duplicate entry and note the merge target.
  `promoteMcp.ts` already backs up the config and scrubs `env` values to empty at promote time —
  confirm they're still empty (or placeholder-only) after your edit; never fill in real secret
  values on the user's behalf.
- **FORK**: leave the mcp config entry alone; write the wrapper skill separately.
- **REJECT**: remove the entry from the mcp config, documented in the commit/edit, and record the
  reason.

### Step 5 — Record provenance

Same as a skill: source, verb, target, what was kept/tightened/dropped — plus the capabilities
summary and its `declaredConfidence`, so a future reader knows whether the decision was made on a
partial/unknown profile.

---

## Commands

| Command | Purpose |
|---------|---------|
| `/rhize-meta:forge-ingest <source>` | Full pipeline: profile → scan → decide → execute → verify → record. No `<source>` → drain the CLI pending queue |
| `/rhize-meta:forge-scan <source>` | Overlap report only — no changes, just the recommendation |
| `/rhize-meta:forge-watch` | Drift check across all absorbed sources |
| `/rhize-meta:skill-find <query>` | Discover relevant skills (skills.sh) + partner audit + safety gate |
| `/rhize-meta:skill-doctor` | Check skills.sh + SkillSpector setup |

---

## Scripts

| Script | Type | Command |
|--------|------|---------|
| `profile_skill.py` | 🔧 EXECUTE | `python3 scripts/profile_skill.py <path> --json` (skill, plugin, or MCP) |
| `overlap_scan.py` | 🔧 EXECUTE | `python3 scripts/overlap_scan.py <path> --skills-root <root> --json` · set-level: `--set-mode` |
| `index_skills.py` | 🔧 EXECUTE | `python3 scripts/index_skills.py --skills-root <root> --json` |
| `build_dependency_graph.py` | 🔧 EXECUTE | `python3 scripts/build_dependency_graph.py --skills-root <root> --json` |
| `record_provenance.py` | 🔧 EXECUTE | `python3 scripts/record_provenance.py --source ... --name ...` · drift: `--check-drift` |
| `skills_sh.py` | 🔧 EXECUTE | `python3 scripts/skills_sh.py search/audit/get/curated ...` (skills.sh discovery + audits) |
| `skill_safety.py` | 🔧 EXECUTE | `python3 scripts/skill_safety.py <target> --no-llm` (SkillSpector safety gate) |
| `skill_doctor.py` | 🔧 EXECUTE | `python3 scripts/skill_doctor.py` (skills.sh + SkillSpector setup check) |

All scripts are stdlib-only (no pip installs), accept `--json`, and fail loudly with clear errors
rather than guessing.

---

## References

- `references/decision-matrix.md` — full criteria for each of the five verbs (+ DEFER+wrap / N-way ABSORB variants)
- `references/overlap-analysis.md` — how the similarity score works and when to override it
- `references/provenance.md` — license handling, attribution rules, `SOURCES.md` format
- `references/capability-schema.md` — the tier/domain/consumes/provenance metadata standard (set-level)
- `references/composition-patterns.md` — wrap vs. absorb vs. reference vs. chain (which to actually use)
- `references/drift-boundaries.md` — how drift detection is divided (sensor / classifier / propagator)

---

## Templates

- `templates/ingestion-report.md` — the structured report to fill in per candidate

---

## Related skills

- **skill-creator** — builds skills from scratch; provides the eval loop this skill verifies with
- **skill-refinement** — improves owned skills from usage; provides the patch machinery ABSORB uses
- **dev-flow-foundations** — the verify-first / no-duplication principles this skill enforces
