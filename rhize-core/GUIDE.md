# rhize-core — User Guide

This guide explains what the rhize-core plugin does and how to get the most out of it. It's the
marketplace control plane — the one command that sets up as many (or as few) of your other Rhize
plugins as you want, in one pass. It ships no skills of its own.

## What This Plugin Does

rhize-core discovers every Rhize plugin you have enabled, hands each one's own expert setup
wizard the wheel for its part, runs a shared dependency and version-control check once instead of
per plugin, establishes free/offline evaluation-coverage baselines, and finishes with an opt-in
guardrail-hook menu. Installing a Rhize plugin never turns on any of its hooks by itself; every
hook this wizard offers gets smoke-tested before it's wired, so a broken hook script can't get
wired silently.

## Setup

There's nothing to set up before using rhize-core — `/rhize-core:setup` **is** the setup wizard.
Run it whenever you install a new Rhize plugin, want to review which guardrail hooks are active
in a project, or want to refresh evaluation baselines.

## Commands Reference

### /setup

**Pick your plugins:** Run it with no flags and you'll see a checklist of every enabled plugin,
pre-checked by default — uncheck anything you don't want touched this run. Already know what you
want? `/rhize-core:setup --plugin obsidian-second-brain --plugin rhize-devflow` skips the
checklist and goes straight to those two; `--all` does the same for everything enabled.

**Example usage:**
> "/rhize-core:setup" — pick your plugins from the checklist (or accept the default of
> everything enabled), work through each selected plugin's own interview (Obsidian's vault
> setup, Rhize Tasks' local install, and so on — whichever ones you picked), confirm baselines
> and the free/offline evaluation seed, review the guardrail-hook menu, and get a final report:
> what's wired, what's tracked in Git, and — for every plugin with one — a one-line "verify with"
> pointer to its own health-check command.

Only want the evaluation subflow, without touching hooks? `/rhize-core:setup --plugin
obsidian-second-brain --evaluations` runs just that for one plugin — this is what
`/vault-setup` itself suggests when you run it standalone. Obsidian is grouped with Context
Manager and Procedural Memory under Knowledge & Context; rhize-core hosts the setup engine as
its own Platform-domain component, not folded into any subject-matter domain.

**What gets written where?** Every plugin's setup wizard (and its day-to-day use) is documented
in one table — see [`rhize-core/docs/setup-artifacts.md`](./docs/setup-artifacts.md).

## Tips & Troubleshooting

**Only have `rhize-ops` installed, not `rhize-core` yet?** `/rhize-ops:rhize-setup` still works —
it runs a byte-identical fallback copy of this same wizard for one release, and its final report
recommends `claude plugin install rhize-core@rhize-plugins` so your next run uses this
actively-developed copy instead. See `docs/contract.md` for exactly what that fallback promises.

**A plugin's wizard didn't run.** Check whether it's actually selected in Phase 2 (it must be
`enabled: true` in your `~/.claude/settings.json`), and whether its manifest even declares a
`wizard` block — not every plugin has its own setup interview.

**Nothing got wired, even though I picked hooks.** Every hook is smoke-tested before wiring; a
failing smoke test shows up as `smoke-test failed` in the final report instead of silently
skipping the item. Fix the underlying script and re-run.

**Bump-version dry-runs by default** — that's `/rhize-ops:bump-version`, a separate command that
stays in `rhize-ops`; it isn't part of this plugin.
