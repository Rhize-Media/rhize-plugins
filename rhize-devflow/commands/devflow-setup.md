---
description: Interview-driven setup wizard for the per-repo local-tenant-file convention used by error-lifecycle-management
---

# /rhize-devflow:devflow-setup

Interview-driven setup wizard that establishes the **per-machine local-tenant-file
convention** used by `error-lifecycle-management` (and any other rhize-devflow skill that
needs to keep real client/tenant specifics out of a public or shared repo). Run this once
per repo that needs client-specific error patterns, or any time you're starting fresh on a
new client project.

## What "local-tenant-file" means

Some knowledge is genuinely useful to keep close at hand — exact commands, real repo names,
real domains, client-specific gotchas — but must never ship in a plugin repo that's public
or shared across clients. The convention: any file ending in `*.local.md` is machine-local
tenant data. It:

- lives in the target repo's (or this plugin's working dir's) `.claude/` directory,
- is always gitignored — never committed, never shipped, never visible to a fork,
- supplements (not replaces) the public, genericized reference file that ships in the repo.

`rhize-devflow/.claude/error-patterns.local.md` is the reference example this wizard's
template is modeled on — read it for the section shape if you want to see a filled-in
instance, but never copy real content out of it into a new repo's template.

## Steps

### 1. Determine the target location

Ask (or infer from context) which directory this setup is for:
- The **current repo's root** (most common — the client project you're working in), or
- This plugin's own working directory, if the user is documenting a rhize-devflow-internal
  pattern rather than a client project's.

Target directory is `<location>/.claude/`.

### 2. Create the `.claude/` directory

- Create `<location>/.claude/` if it doesn't already exist.
- If it already exists (most repos have one for hooks/settings), just confirm it's there —
  don't touch anything else inside it.

### 3. Write the `error-patterns.local.md` template

Write `<location>/.claude/error-patterns.local.md` using this template — **zero real client
data goes in this file**; it is a skeleton for the user (or a future session) to fill in
with that repo's actual specifics:

```markdown
# Local Supplement: [Project/Client Name] Specific Errors

This file is a gitignored, machine-local copy of client-specific error patterns for this
project. It supplements the public, genericized reference in
`skills/error-lifecycle-management/reference/error-patterns.md` with real repo-specific
details — exact commands, internal repo names, real domains — that must not ship in the
public plugin repo or be visible to other clients.

**This file is machine-local tenant data — it is gitignored and never committed.**

## [Project/Client Name] Specific Errors

### [Error Category — e.g. "Payment Provider Errors", "CMS-Specific Errors"]

#### [Error Name]
**Pattern:** [The exact error message or symptom]
**Root Causes:**
1. [Cause]
**Solution:**
```[language]
[Exact fix — real commands, real paths, real config]
```

### [Next Category]

#### [Error Name]
**Pattern:**
**Causes:**
**Solution:**
```

Do not pre-fill any category or error entry beyond this skeleton — the delegator fills in
real content as errors are actually encountered on this project.

If `<location>/.claude/error-patterns.local.md` already exists, do NOT overwrite it — tell
the user it's already set up and ask whether they want to review it instead.

### 4. Verify (and fix) the gitignore

Check whether `<location>/.claude/` (or more narrowly, `*.local.md`) is covered by an
existing `.gitignore` in the target repo:

- If the repo's root `.gitignore` already ignores `.claude/` wholesale (common pattern —
  check for a bare `.claude/` line), nothing more is needed.
- If `.claude/` is tracked or only partially ignored (e.g. an allowlist-style `.gitignore`
  that re-includes some paths under `.claude/`), add a dedicated `*.local.md` ignore rule
  instead of assuming the whole directory is safe — this avoids accidentally un-ignoring
  something the repo's existing `.claude/` convention intentionally tracks.
- If there's no `.gitignore` at all in the target repo, create one with at minimum:
  ```
  # Machine-local tenant data — never committed, never shipped
  *.local.md
  ```
- Confirm the fix worked: `git check-ignore -v <location>/.claude/error-patterns.local.md`
  should print a match. If it doesn't, the ignore rule didn't take — investigate rather than
  assuming success.

### 5. Reference the convention in README.md

If the target repo has a `README.md` with a relevant "local setup" or "conventions" section,
add a short pointer to the `*.local.md` convention there (one or two sentences: what it is,
where it lives, why it's gitignored). If no such section exists and the repo is this
rhize-devflow plugin itself, the convention is already documented in the plugin's own
`README.md` — don't duplicate it elsewhere.

### 6. Confirm

Tell the user:
- The `.claude/error-patterns.local.md` template was created at `<location>/.claude/`
- It's confirmed gitignored (or what was added to make it so)
- They (or a future session) should fill in real error patterns as they're encountered —
  this file is never auto-populated
- Re-run this command in any other repo that needs the same local-tenant-file setup

### 7. Hand back to the orchestrator, or suggest it

Parse `$ARGUMENTS`. If it contains `--from-rhize-setup`, stop here — `/rhize-core:setup`
invoked this wizard as part of its own run and continues on to its evaluation-baseline and
hook-wiring phases itself; re-invoking it here would loop back into the same run. Otherwise
(this wizard was run standalone), suggest `/rhize-core:setup --plugin rhize-devflow` to
establish the evaluation baseline — identify the exact incumbent review/test/debug workflow as
Arm A, then run the free/offline seed. Correctness and rework are primary gates; token or latency
reductions never compensate for a regression. Keep tenant-file contents, repository paths, error
messages, and Sentry identifiers out of receipts. Any other argument in `$ARGUMENTS` is ignored
with a note — this wizard stays standalone-runnable and remains the expert for its own setup.

## Related

- `error-lifecycle-management` skill — reads the public `error-patterns.md` reference;
  a filled-in `.claude/error-patterns.local.md` supplements it with real per-project detail.
