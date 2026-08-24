---
description: Verify, classify trust, write provenance, commit, and index a staged artifact into the procedural-memory registry
argument-hint: <path-under-registry>
allowed-tools: Bash
---

Promote a staged artifact into the procedural-memory registry: $ARGUMENTS

Run:

    ${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh promote $ARGUMENTS

Promotion runs the root-location scan, literal-secret scan, and static trust classification,
then commits and indexes unconditionally (write-through). **It does not execute the artifact's
smoke test** — a freshly promoted artifact lands `health=unverified`, not `health=ok`. Never
describe a promoted artifact as verified or safe to run on that basis alone; tell the user to
follow up with `/procedural-memory:verify <name>` if they want a real health signal before
relying on it.

If promotion refuses (a hardcoded root, a literal secret, a missing `execution` block), show
the CLI's message verbatim rather than summarizing — the exact field it names is what the user
needs to fix.
