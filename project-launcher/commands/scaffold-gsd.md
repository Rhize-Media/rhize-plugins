---
description: "Scaffold a project directory and prepare for GSD v2 autonomous handoff"
---

# Scaffold for GSD v2

Create a project directory with CLAUDE.md, .planning/ docs, and GSD v2 framework — ready for autonomous development.

## Instructions

This command runs Phases 5-6 of the project-launcher pipeline. It assumes a PRD already exists.

### Required Input

The user must provide either:
- A path to an existing PRD: `$ARGUMENTS`
- A project directory that already contains a PRD in `prd/` or `.claude/plans/`

If no PRD is found, tell the user to run `/launch-project` for the full pipeline, or `/write-prd` to create a PRD first.

### Process

1. **Read the PRD** — Extract all requirements, architecture, tech stack, integrations
2. **Create project directory** (if it doesn't exist) — Ask user for location
3. **Generate CLAUDE.md** — Using `references/claude-md-template.md`, populate with PRD details
4. **Generate .planning/ docs**:
   - `PROJECT.md` — Vision, stakeholders, constraints from PRD
   - `REQUIREMENTS.md` — All FRs and NFRs from PRD
   - `ROADMAP.md` — Break PRD into phases and plans (see `references/gsd-handoff-guide.md`)
   - `STATE.md` — Initialize at Phase 01
   - `config.json` — Default GSD config
5. **Install GSD** — `npx --yes get-shit-done-cc@1.42.3 --claude --local`; verify `.claude/get-shit-done/VERSION` is `1.42.3` and `.claude/commands/gsd/autonomous.md` exists
5a. **Install the typed decision layer** — After GSD installation, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/typed_decision.py" install --project "<project-dir>"`. The installer adds project-local client and skill files and merges `.planning/config.json` `agent_skills` for `gsd-planner`, `gsd-executor`, and `gsd-verifier`.
5b. **Probe and check** — Configure `TYPESAFE_API_KEY` for hosted Jev, or `TYPESAFE_BASE_URL=http://127.0.0.1:8000` for a running Laya-compatible server. For a local Laya pilot, set `TYPESAFE_DEFAULT_MODEL=typed-decisions` to pin that checkpoint and leave the client in its default `shadow` mode. Run `python3 "<project-dir>/.claude/rhize-decision/typed_decision.py" probe --project "<project-dir>"`, then `status --project "<project-dir>"`. Both must succeed. Inspect `gsd-sdk query agent-skills gsd-planner`, `gsd-executor`, and `gsd-verifier` from the project root to confirm GSD loads the skill. A missing provider or failed probe means the scaffold is **blocked**, not ready for handoff.
6. **Initialize git** — `git init`; preserve the installer's `/.planning/decision-layer/receipts.jsonl` entry when adding the project's other `.gitignore` rules
7. **Create deliverable directories** — Based on project type (workflows/, src/, scripts/, templates/)
8. **Offer hookify guardrails** — If the project uses the Rhize Next.js stack (Next.js + Supabase + Sanity), offer the starter rule set from `references/hookify-rules/nextjs-rhize-stack/` as an opt-in choice. Installing never auto-wires guardrails silently (same contract `rhize-ops/commands/rhize-setup.md` follows for the fleet-level setup wizard). List the seven available rules:

   | Rule | Purpose |
   |------|---------|
   | `pr-review-on-create` | Triggers the review skill when `gh pr create` runs |
   | `block-direct-push-to-main` | Forces all work through PRs |
   | `nextjs-public-secret-leak` | Catches `NEXT_PUBLIC_*_SECRET/_TOKEN/_SERVICE_ROLE` before they ship |
   | `supabase-service-role-in-client` | Blocks service-role key references in `'use client'` files |
   | `nextjs-stop-checks` | Reminds to run `typecheck`/`lint`/`build` before ending session |
   | `sanity-schema-skill-hint` | Suggests the Sanity best-practices skill on schema edits |
   | `seo-skill-hint` | Suggests SEO-AEO-GEO skills on metadata/sitemap/structured-data edits |

   Present the choice with `AskUserQuestion` (`multiSelect: true`), one question offering all seven rules as options. Append `" (recommended)"` to the option label for `pr-review-on-create`, `block-direct-push-to-main`, `nextjs-public-secret-leak`, and `supabase-service-role-in-client` — per the rules README's "Why these seven," these four (the PR-review gate plus the two secret/service-role blocks and the direct-push block) cover the highest-cost mistakes; the remaining three are lower-stakes hints. Copy only the rules the user selects:
   ```bash
   mkdir -p .claude
   cp "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/marketplaces/rhize-plugins/project-launcher}/skills/project-launcher/references/hookify-rules/nextjs-rhize-stack/hookify.<rule-id>.local.md" .claude/
   ```
   (one `cp` per selected rule). Print a copied/skipped table:

   | Rule | Status |
   |------|--------|
   | `<rule-id>` | `copied` / `skipped (user declined)` |

   See `references/hookify-rules/nextjs-rhize-stack/README.md` for the full rule table (event, action, prerequisites). Record the selected/skipped rules in the scaffold summary (step 11).
9. **Copy PRD** — Into `prd/` directory
10. **Run handoff checklist** — Verify all files, the installed GSD skill query, and the typed-decision receipt are consistent
11. **Brief user** — How to start `/gsd-autonomous`; include the decision layer status and hookify copied/skipped table from step 8
