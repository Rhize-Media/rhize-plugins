# What's New — Rhize Plugins

Plain-language highlights of what shipped, for people **using** these plugins.

Looking for the full engineering record — every fix, every version bump, with internal
references? That's [CHANGELOG.md](./CHANGELOG.md). This page is the short version.

---

## September 2026

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
artifact that solved it instead of having a model reinvent the solution. Registry entries are gated
on digest, trust, and health checks.

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
