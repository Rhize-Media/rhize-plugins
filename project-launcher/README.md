# Project Launcher Plugin

End-to-end project launcher for Rhize Media. Takes a project idea from napkin sketch through research, PRD generation, critical gap analysis, project scaffolding, and GSD v2 handoff for autonomous development.

## Setup

Install via the marketplace (see the root [README's Quick Start](../README.md#quick-start)) —
there's no account to create and no credential this plugin itself requires before first use.

The 13 MCP servers and 12 external skills listed below (Integrated MCP Servers, Integrated
Skills) each add capability to one or more phases, but every one of them is optional: without a
given server or skill connected, that phase's step is skipped or falls back to generic prompting
instead of failing. Connect the ones relevant to your work — DataForSEO and `seo-aeo-geo:*` for
content projects, Sentry/PostHog for apps you'll instrument, and so on — and run `/launch-project`
or `/write-prd` with whatever subset you have.

**GSD handoff dependency:** Phase 5 installs a project-local typed decision client and GSD
skill for planner, executor, and verifier. Phase 6 requires a successful synthetic request
to a Jev-compatible `/v1/systemone` provider. Use `TYPESAFE_API_KEY` for hosted Jev,
or set `TYPESAFE_BASE_URL` to a running loopback Laya server. Optional `LAYA_API_KEY`
authenticates to a local server that requires it. Keys stay in the environment. An
unavailable provider blocks the handoff ready claim. This integration pins GSD 1.42.3,
which exposes `/gsd-autonomous` in Claude Code.

The client records checkpoint, requested and routed model, question IDs, latency,
provider token usage, outcome, and a state hash in
`.planning/decision-layer/receipts.jsonl`; it never stores request state.
The installer adds that receipt file to the new project's `.gitignore`.
Installed `SubagentStart` and `SubagentStop` hooks require each GSD planner, executor,
and verifier to make its own call or record an unavailable attempt. Their
Foreman-style multi-check call returns an observational `candidate_directive`;
it cannot change a worker or bypass tests or approval gates. The default `shadow` mode records calls
without recommendations. Set `RHIZE_DECISION_MODE=advisory` only after validating
the selected checkpoint on task-relevant cases. For local Laya, set
`TYPESAFE_DEFAULT_MODEL=typed-decisions` to pin that candidate for a pilot;
without an override, Laya chooses its own checkpoint. Record the actual returned
model and routed checkpoint in receipts. The launch probe rejects a different
local checkpoint and requires Laya's `instructions` field. Research and holdout
evaluation instructions live in [evals/typed-decision](../evals/typed-decision/README.md).

From a scaffolded project, run `python3 .claude/rhize-decision/typed_decision.py status`
and `gsd-sdk query agent-skills gsd-planner` (also executor and verifier). A `ready`
status proves configuration and a recent provider probe; inspect per-agent receipts
during the project to verify runtime use. Run `status` with the same provider and
model environment as the probe; a changed or missing local model pin blocks readiness.

## Commands

| Command | Description |
|---------|-------------|
| `/launch-project` | Full 6-phase pipeline: research → PRD → gap analysis → scaffold → GSD handoff |
| `/write-prd` | Phases 1-4: research → interview → PRD → gap analysis |
| `/scaffold-gsd` | Phases 5-6: create project directory + GSD v2 handoff from existing PRD |
| `/grill-prd` | Phase 4 standalone: critical gap analysis of an existing PRD |
| `/visual-plan` | Turn a plan or PRD into a reviewable `.mdx` visual plan (diagrams, wireframes, file maps, data/API contracts) via the `rhize-visual-plan` skill |

## Skills

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `project-launcher` | Takes a project idea through research, requirements, a PRD, and a scaffolded project folder. | automation, obsidian, project-planning, workflow-patterns |
| `rhize-visual-plan` | Turns an implementation plan into a reviewable visual document with diagrams and file maps. | nextjs, obsidian, project-planning, visualization |
<!-- SKILL-MAP:END -->

## Reference Docs

| File | Purpose |
|------|---------|
| `references/interview-question-bank.md` | 65 categorized questions across 11 domains |
| `references/prd-template.md` | 14-section PRD structure template |
| `references/claude-md-template.md` | CLAUDE.md generation template with post-phase verification |
| `references/gsd-handoff-guide.md` | Complete guide to .planning/ docs and GSD v2 setup |
| `references/plan-discipline.md` | Cross-cutting review-surface methodology (plan-as-approval-gate, lead-with-reuse, adversarial self-review) for Phases 3-4; shared with `rhize-visual-plan` |

## Integrated MCP Servers

| MCP Server | Phase(s) | Purpose |
|------------|----------|---------|
| Obsidian | 1 | Vault search for prior art |
| Firecrawl | 1 | External documentation scraping |
| Context7 | 1, 3 | Framework/library documentation |
| DataForSEO | 1, 2, 3 | SEO keyword data (content projects) |
| Slack | 2, 4, 6 | Team context, approval flows |
| Google Drive | 1, 2 | Existing documents |
| Atlassian | 1 | Jira project history |
| Sentry | 3, 5 | Error tracking setup |
| PostHog | 3, 5 | Analytics integration |
| Sequential Thinking | 3, 4 | Complex reasoning |
| Serena | 1, 5 | Codebase exploration |
| n8n-builder | 3, 5 | n8n node search, workflow validation |
| n8n-executor | 5, 6 | Execute/test n8n workflows on n8n Cloud |

## Integrated Skills (external dependencies †)

| Skill | Phase | Purpose |
|-------|-------|---------|
| `obsidian-second-brain:vault-search` † | 1 | Vault search for prior art |
| `obsidian-second-brain:vault-research` † | 1 | Deep topic research |
| `grill-me` † | 4 | Critical gap analysis |
| `write-a-prd` † | 3 | PRD generation |
| `seo-aeo-geo:*` † | 1, 3 | SEO skills for content projects |
| `brand-voice:*` † | 3 | Brand voice for content projects |
| `n8n-automation` † | 3, 5 | n8n workflow building |
| `engineering:system-design` † | 3 | System architecture |
| `engineering:architecture` † | 3, 4 | ADR creation |
| `tdd` † | 5, 6 | Test-driven development |
| `prd-to-issues` † | 4→5 | PRD → GitHub issues (vertical slices) |
| `simplify` † | 6, post-phase | Code review and simplification |

## Commands & Execution Flags

| Command/Flag | Phase(s) | Purpose |
|-------------|----------|---------|
| `/batch` | 5, 6 | Batch parallel operations |
| `/sc:reflect` | Post-phase | Validate task implementation |
| `/simplify` | Post-phase | Review and simplify code |

## Hooks

| Hook | Matcher | Behavior |
|------|---------|----------|
| **PreToolUse** | `Write\|Edit` on launcher artifacts | When writing PRDs, requirements, research docs, context files, discovery notes, or roadmaps — and an Obsidian vault exists at `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault` — nudges Claude to also save the artifact to the vault using second-brain methodology: `[[wikilinks]]` to related projects, `#tags` in frontmatter, parent MOC links, and placement under the appropriate `Projects/` folder. If no vault exists, the hook stays silent. |

> **SessionStart banner removed (2026-08-09):** the unconditional command-menu banner moved
> to [`rhize-context-manager`'s `session-disclosure.js`](../rhize-context-manager/README.md#hooks)
> — Phase 3 of the skill-map plan (`docs/skill-map.md`) — a single stack-aware disclosure
> surface replaces per-plugin command menus.

Hooks fail silently on error (3-5s timeout) and never block operations. The vault detection is path-based — no external tools required.

**Artifact detection patterns** (path or content): `prd`, `requirements`, `research`, `context`, `gap-analysis`, `interview`, `discovery`, `roadmap`, `project.md`, `requirements.md`, plus content headings like `## PRD`, `## Requirements`, `# Product Requirements`.

The PreToolUse hook is implemented in `hooks/scripts/launcher-vault-hint.py`. It reads the
tool-call payload from stdin (as Claude Code delivers it — `{"tool_name": ..., "tool_input":
{...}}`) and emits advisory context via the standard `hookSpecificOutput` contract; it's
auto-wired through `hooks/hooks.json`, so no setup step is required to use it.

## Setup Manifest

`setup/manifest.json` lists opt-in capabilities this plugin could offer beyond what's
auto-wired in `hooks/hooks.json` — read by the `/rhize-core:setup` wizard (in the `rhize-core`
plugin) so a project can pick which ones to wire into its `.claude/settings.json`. It's
currently empty: this plugin's one hook is already scoped to launcher artifacts, advisory-only,
and auto-wired, so there's nothing here that needs to be opt-in rather than on-by-default. It
does declare a `dependencies` array (the integrated MCP servers and external skills above)
that the wizard's dependency check reads.

**Fleet setup:** `/rhize-core:setup` is what actually wires opt-in items and checks
`dependencies` for you — it requires the `rhize-core` plugin. Without it, wire an item
manually per the snippet in [rhize-core/README.md § Setup manifest
schema](../rhize-core/README.md#setup-manifest-schema).

## Post-Phase Verification Pattern

After each GSD phase, the autonomous Claude runs:
```
/sc:reflect on whether all tasks were implemented and then /simplify your code changes where needed for an optimal solution
```
