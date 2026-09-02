# What's New — Rhize Plugins

Plain-language highlights of what shipped, for people **using** these plugins.

Looking for the full engineering record — every fix, every version bump, with internal
references? That's [CHANGELOG.md](./CHANGELOG.md). This page is the short version.

---

## September 2026

**Set up only the plugins you want, and see what setup wrote.** `/rhize-ops:rhize-setup` now
starts by asking which of your installed plugins to set up, runs the shared checks once
(dependencies, whether your customizations are under version control, the skill map), then hands
off to each plugin's own setup wizard before wiring the optional guardrails you choose. It ends with
a report of every file it and the plugins created — and
[`rhize-ops/docs/setup-artifacts.md`](./rhize-ops/docs/setup-artifacts.md) is the standing
reference: what each plugin writes on your machine, where, how to look at it, how sensitive it
is, and whether Git tracks it. Each plugin's wizard still runs on its own if you only want that one.

**Start here, roll back anything, and one review command.** There is now a
[START-HERE.md](./START-HERE.md) that explains in plain words what each plugin is for, which ones
to install, how the files you'll meet fit together, and a glossary — and a `docs/` index that
points at every plugin's own docs. Anything the plugins write into your project or home config can
be rolled back with Git: a new preflight tool tells you what is and isn't tracked (the setup wizard
will run it for you in the next release), and skill-forge's `init` now offers to put your skill
folders under version control. The production review gate is a single command,
`/rhize-devflow:review`, with its hard-won routing and pre-merge checklist documented beside it.
Under the hood: the skill-usage monitor works on any machine (no more paths that only existed on
one laptop), the scaffold command asks before installing guardrail rules, test-evidence packets
have a sensible default home, and the procedural-memory hook scrubs anything that looks like a
secret before it records a command.

**Documentation you can actually onboard from.** Every plugin's README and GUIDE was audited
line-by-line against what the code really does, and the marketplace adopted a progressive-disclosure
standard: each document leads with what it is and how to start, then links to depth instead of
burying you in it. Oversized references were split into an overview plus linked detail.

**Obsidian hints now work for everyone's vault.** The advisory hints that fire while you read and
write notes previously only recognized an iCloud-synced vault using Obsidian's default name —
everyone else got silence, with no error to explain why. They now find your vault from an
`OBSIDIAN_VAULT_PATH` setting or from Obsidian's own registered vaults, with the old location
still working.

**CodeGraph is documented as an optional dependency.** Dev Flow uses a code-graph index to answer
"what does this change affect." It was always optional with an automatic fallback, but there was no
guide for setting it up in your own repository. There is now, and the health check reports whether
it's present.

**Rhize Tasks reads as a product, not one person's tool.** Its guide, dashboard, and setup wizard
no longer address a specific individual by name.

## August 2026

**Parallel agent work, with receipts.** Ops gained self-contained routing for running multiple
agents at once, and every run produces evidence of what actually happened rather than a summary you
have to trust.

**Governed promotion of finished branches.** Dev Flow can carry a completed branch through
push, PR, merge, and deployment verification — but only after you authorize it, and always
subordinate to that repository's own release rules.

**Procedural memory.** When a task looks like one that was already solved, the system re-runs the
artifact that solved it instead of having a model reinvent the solution. Nothing in the registry
runs until it passes a content-integrity check, a trust check, and a health check — being in the
registry isn't, by itself, enough to be trusted.

**Context engineering matured.** Deterministic, source-bound context packs; bounded multi-source
memory assembly; and an opt-in experiment framework that measures whether a new retrieval path
actually beats the baseline instead of assuming it does.

**A skill map across the whole marketplace.** Every skill, plugin, and connector, plus the
relationships between them, compiled into a queryable graph — used to surface the right skill for
your stack and to catch two skills quietly doing the same job.

**Measurement you can trust.** Reporting separates measured numbers from estimated and
self-reported ones, and refuses to add them together. A flattering total that mixes evidence
classes is exactly the failure this prevents.

## June–July 2026

**The marketplace took shape.** SEO/AEO/GEO, Obsidian, Dev Flow, Ops, Context Manager, and the
project launcher came together as installable plugins with a consistent documentation convention
and a shared setup wizard.

---

## How versions work

Each plugin carries its own version, listed in the [Plugin Catalog](./README.md#plugin-catalog).
The marketplace has its own version that moves whenever any plugin does. Installing or updating a
plugin does not change the others.

## A note on the engineering changelog

[CHANGELOG.md](./CHANGELOG.md) is written for the people maintaining these plugins. It is detailed
on purpose and references internal tracking IDs. Nothing there is required reading to use a plugin.
