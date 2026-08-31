# procedural-memory — User Guide

## What problem does this solve?

An agent re-solving a task from scratch every time it comes up is slow and inconsistent — the
same n8n deploy guard, the same vault tagging script, the same PDF-to-markdown conversion, each
recomposed fresh instead of reused. The `procedural-memory` registry keeps proven, working code
for tasks like these, each one carrying a real safety contract (what it needs, what it touches,
how it's been verified). This plugin is how you reach that registry from either Claude Code or
Codex: find the right artifact, run it with the registry's trust/health gates intact, or add a new
one once you've captured working code worth reusing. When a repeated CLI pattern is not yet a
registry artifact, the separate Functionize surface can mine it and compile an inert proposal for
review without registering or running anything.

Claude Code provides seven `/procedural-memory:*` commands and advisory session hooks. Codex uses
the same two natural-language skills through self-relative launchers; it does not claim Claude
Code's slash-command or hook lifecycle.

## When to reach for what

- **"Turn this repeated CLI workflow into a reviewable proposal"**
  → `/procedural-memory:functionize <cli> --auto-compile --proposal-dir <path>`. Mines and
  redacts repeated CLI shapes, then compiles structurally eligible candidates into isolated inert
  bundles. It never registers, trusts, approves, promotes, invokes, or runs them.

- **"Compile this exported Functionize candidate"**
  → `/procedural-memory:functionize-generate <candidate.json> --proposal-dir <path>`. Compiles
  exactly one v2 candidate and reports grader/promotability evidence without crossing a later gate.

- **"Record the completed human review for this candidate"**
  → `/procedural-memory:functionize-review <candidate.json> <review.json> --ledger <path>`.
  Appends a digest-bound decision; conversation prose is not substituted for the review manifest.

- **"Has this been automated before?" / "is there already a tool for X?"**
  → `/procedural-memory:recall "<task description>"`. Returns ranked hits with similarity
  score, trust tier, health, and success rate — not just a name. A hit that's `unreviewed` or
  `degraded` is flagged, not silently offered as safe to run.
  *Example: "Recall a proven artifact for deploying an n8n workflow safely."*

- **"Run the registry version of X"**
  → `/procedural-memory:run <name> [args]`. Registry-only — never a caller-supplied path.
  Refuses if the artifact's content digest, trust tier, or health don't clear the gate; the
  refusal names the exact reason and how to fix it. This plugin will never quietly add a
  bypass flag on your behalf — that decision is yours.
  *Example: "Run vault-tag-merger with --dry-run first."*

- **"I just wrote something reusable — add it to the registry"**
  → `/procedural-memory:promote <path>`. Verifies the artifact's provenance shape (no hardcoded
  paths, no literal secrets), classifies its trust tier statically, commits, and indexes it.
  Does **not** run the smoke test — the artifact lands `unverified`, not `ok`.
  *Example: "Promote registry/skills/apply-client-tags into the registry."*

- **"Is this artifact actually still healthy?" / recovering a self-quarantined artifact**
  → `/procedural-memory:verify <name>`. Re-runs the sandboxed smoke test and every declared
  assertion, and is the only command that ever sets a real `health=ok`/`health=degraded` with
  a fresh `last_verified` date. Add `--offline` to recover an artifact that self-quarantined
  during an offline run, without needing a live Postgres connection.
  *Example: "Verify n8n-safe-deploy — I think it self-quarantined."*

## The session automatically notices when you might have something to promote

In Claude Code, you don't have to remember to run `/procedural-memory:promote` right after writing
something reusable. Two advisory hooks run in the background. Codex does not wire these Claude Code
hooks; invoke the appropriate shared skill explicitly for registry reuse or Functionize work.

- Every time a Bash call in your session matches a known test/build command (`pytest`, `npm
  test`, `cargo test`, `go test`, `vitest`, `tsc`, and a few others) and completes, it's quietly
  noted.
- When the session ends (or a turn finishes with nothing else pending), if anything was noted
  *this session*, you'll see a short summary: which commands passed, which files you wrote or
  edited alongside them, and a reminder that `/procedural-memory:promote <path>` is there if you
  want to capture it.

This is a nudge, not an automation — nothing gets promoted, committed, or indexed on your
behalf. "Passed its test command this session" is not the same claim as "registry-verified";
only `/procedural-memory:verify` (or a fresh `/procedural-memory:promote`) ever makes the latter
claim. If you don't want to capture something, just ignore the nudge — nothing else happens.

## What this plugin is not

It doesn't retrieve past conversations or session history — that's claude-mem's job (its
search/recall skills). It doesn't build a knowledge graph over notes — that's `graphify`
(rhize-context-manager). If the request is "what did we decide last week," you want claude-mem.
If it's "is there working code for this, and can I just run it," you want this plugin.

Unified memory can consume procedural metadata only through the versioned, recall-only
`rhize-procedural-recall-v1` contract. That adapter is not available yet, so the procedural lane
must report `unavailable`; it must not scrape prose, query registry tables directly, or execute an
artifact as a fallback. Recall metadata never bypasses the normal digest, trust, health, or
user-approval gates in either Claude Code or Codex.

It also doesn't implement pruning or deletion. `rhize-skill stale` (a read-only decay report) is
reachable directly through the launcher script if you want it; see
`docs/decisions/0001-no-prune-command.md` for why a `/prune` command was deliberately not built.

It doesn't dedupe promotions itself (that's already inside `rhize-skill promote` via the
skill-forge gate), and it can't make `skill-monitor` score what an artifact's script actually
does (that requires a Skill-tool call, and artifacts run as Bash subprocesses) — see the
README's "Governance & integrations" section if you need the detail behind either of those.

## Tips

- Trust the refusal messages. When `/run` or `/promote` refuses, the CLI names the exact field
  or check that failed and the remediation command — read it rather than asking this plugin to
  work around it.
- `/recall`'s similarity score is not a safety signal by itself. Always look at trust and health
  together with it before treating a hit as "the answer."
- If a command errors with a message starting `rhize-skill-launcher.sh: cannot find the
  rhize-skill CLI`, the registry CLI isn't built/discoverable on this machine yet — follow the
  remediation it prints (build it, or set `RHIZE_SKILL_BIN`). See this plugin's `README.md`
  ("How the CLI is resolved") for the full story.

## Troubleshooting

**"rhize-skill CLI is older than this plugin expects"** — the plugin was built against a newer
`rhize-skill` command surface than what's installed. Update the registry checkout
(`git pull` + reinstall) or point `RHIZE_SKILL_BIN` at a build that already meets the minimum.

**A refusal names "trust: ... was approved for digest X but the current digest is Y"** — the
artifact's code or provenance changed since it was approved. That's the registry working as
designed (an approval is bound to specific bytes, not a name/version forever) — someone with
context needs to re-review and re-approve; this plugin won't do that silently.

**Nothing meaningful comes back from `/recall`** — the registry may genuinely not have anything
close to the task yet. That's a real answer, not a failure; consider whether the task is worth
capturing and promoting once you've solved it by hand.
