# Next.js + Rhize Stack — Hookify Starter Rules

Reusable hookify rules tuned for Rhize's Next.js + Supabase + Sanity tech stack. Installed into a project's `.claude/` directory during `/scaffold-gsd`, or copied manually into any existing Next.js project.

## Prerequisites

- The `hookify` plugin (or `claude-plugins-official:hookify`) must be installed and enabled in the target project. It's what reads `.claude/hookify.*.local.md` and runs the rules.
- For the PR-review rule: `/rhize-devflow:review` (preferred — prod merge-gate orchestrator), with `pr-review-toolkit:review-pr`, `code-review:code-review`, or `review` as fallback.
- For skill-hint rules: `sanity-plugin:*`, `seo-aeo-geo:*` (already in Rhize plugin set).

## The Rules

| Rule | Event | Action | Purpose |
|------|-------|--------|---------|
| `pr-review-on-create` | bash | warn | **Primary** — triggers the review skill when `gh pr create` runs |
| `block-direct-push-to-main` | bash | **block** | Forces all work through PRs |
| `nextjs-public-secret-leak` | file | **block** | Catches `NEXT_PUBLIC_*_SECRET/_TOKEN/_SERVICE_ROLE` before they ship |
| `supabase-service-role-in-client` | file | **block** | Blocks service-role key references in `'use client'` files |
| `nextjs-stop-checks` | stop | warn | Reminds to run `typecheck`/`lint`/`build` before ending session |
| `sanity-schema-skill-hint` | file | warn | Suggests the Sanity best-practices skill on schema edits |
| `seo-skill-hint` | file | warn | Suggests SEO-AEO-GEO skills on metadata/sitemap/structured-data edits |

## Installation

### Automatic (recommended)

Run `/scaffold-gsd` — the scaffolding step copies these rules into the new project's `.claude/`.

### Manual

From the project root:

```bash
mkdir -p .claude
cp ~/.claude/plugins/marketplaces/rhize-plugins/project-launcher/skills/project-launcher/references/hookify-rules/nextjs-rhize-stack/hookify.*.local.md .claude/
```

Add to `.gitignore` if you want rules to stay local-only:

```
.claude/*.local.md
```

Or commit them so the whole team gets the same guardrails (recommended for the PR-review and secret-leak rules).

## Tuning

- **Too noisy?** Set `enabled: false` in the rule's frontmatter, or change `action: block` → `action: warn`.
- **Too permissive?** Tighten the regex or add a second `conditions:` entry.
- **Need a new rule?** Use `/hookify:hookify "describe the behavior"` and it'll generate one.

Rules are read dynamically — no restart needed after edits.

## Why these seven

These cover the highest-cost dev mistakes on the Rhize stack:

1. **Shipping secrets to the browser** — `NEXT_PUBLIC_` mistakes and Supabase service-role leaks both result in account-takeover-grade incidents
2. **Skipping the PR-review gate** — direct pushes to `main` and unreviewed PRs are the main source of regressions
3. **Stack-specific skill awareness** — Sanity typegen drift, SEO regressions, and broken builds happen when the right skill isn't invoked at the edit point

Future expansions live as separate rule files in this directory.
