# Credential workflow release and fresh-session handoff

The user authorized pushing and merging this Laya work to main, a full release and installation.
Before acting, recheck current refs, exact-head CI, required review/impact/context receipts and native
evidence. This document records the task; it does not replace host approval or source instructions.

## Source and boundaries

Worktree `/Users/jamesdeola/dev-local/RHIZE/.worktrees/credential-keychain-guard`, branch `codex/credential-keychain-guard`,
[PR55](https://github.com/Rhize-Media/rhize-plugins/pull/55). Read current STATE.md and the PR's actual
head; do not assume an earlier commit is the tested/released head. Preserve unrelated primary-checkout
STATE.md changes. No VBA source/data work belongs to this release.

A concurrent Claude session owns `claude/laya-advise-v2` in
`/Users/jamesdeola/dev-local/RHIZE/.worktrees/laya-advise-v2`. Its current changed paths do not
overlap this branch, but its plan also changes the registry and `workflow-fit` contract. Before
integrating either branch, compare fresh heads and reconcile that shared decision explicitly:
the credential policy must retain its fixed catalog, manual runtime binding and independent GUI
deny; the broader content/general advice policy must not silently replace or inherit them.
Do not reset, stage or commit the other session's files, or change live modes during its work.

The source now scopes the content/general pilot's shadow instruction and implements a separate
bounded credential CLI guidance policy. It defaults to shadow until explicitly activated with the
existing audited registry CLI. The current chat received the older blanket shadow-only developer
instruction and did not change live Laya authority. Reopen a fresh session after installing the
reviewed source so it receives the revised capability-scoped contract.

Dev Flow credential_guard.py must retain SHA256
`3d8238dcf0fb62297b334278d62e9e406c43f91c58b030da8266edb91bd8a3eb` for this verification packet.
It is independent of Laya. Fixed guidance never executes a command, grants permission, reads a
credential or clears the GUI deny. PreToolUse additionalContext alone does not stop a pending call.
Secret-safe CLI use remains an explicit procedural obligation, not a claim of arbitrary-code containment.

## Required native proof

1. Use documented native hook interfaces and inert marker-backed fixtures. Read existing evidence
   before testing. Do not launch Keychain Access or read a real credential.
2. Prove recorder registration and actual PreToolUse callback dispatch independently. Current-source
   native Codex marker-backed allow0/deny2 exists; current-source Claude deny interception remains
   unverified. Earlier Claude callbacks used another guard SHA. Native `/hooks` registration and a
   successful direct-shell marker do not establish interception.
3. The prior model-mediated attempt was stopped by the provider classifier before tool dispatch.
   A fresh session does not clear that refusal: do not rephrase, obfuscate, inject fabricated assistant
   tool calls or change providers to evade it. Use a supported harmless native hook tester if the host
   offers one. If none is available, preserve the hold rather than calling registration a pass.
4. Verify new credential guidance delivery at UserPromptSubmit and a later tool call in both native
   hosts, including active selection, timeout fallback and the unchanged independent hard deny.
   Isolated fixture tests are not installed-host proof. Test the actual installed/trusted hook and
   fresh desktop/CUA path, not only an inline source plugin.

## Release, installation and activation

- Recheck PR head, main and exact-head CI. Apply Dev Flow's read-only review gate and resolve findings.
  Keep the public impact map reconciled and the private exact-ref context gate PASS. No test/hook bypass.
- Complete native prerequisites before declaring the full release verified. Source merge, tag,
  installed files and native enforcement are separate outcomes; if a prerequisite remains unavailable,
  report the exact hold and preserve the reviewed branch without claiming rollout complete.
- Use the repository's managed versions/tag workflow and each host's supported plugin update/install
  interface. Inspect installed CLI help first; never manually overwrite caches or host approval files.
  Read back main/tag/source versions and compare all installed shipped files to the released source.
  Install/verify Dev Flow's hard deny before activating Context Manager guidance. This PR also includes
  Core/Ops catalog updates; update every changed plugin to its released manifest version, not only
  Context Manager. Inspected CLI interfaces support `claude plugin update PLUGIN@MARKETPLACE` and
  `codex plugin marketplace upgrade MARKETPLACE` followed by `codex plugin add PLUGIN@MARKETPLACE`.
  Recheck help/current marketplace identity before use and follow any displayed host approval prompt.
- For reproducible Claude diagnostics use process-local `DISABLE_AUTOUPDATER=1`. A prior native startup
  updater left an incomplete CLI upgrade; the original tested2.1.284 was restored. Do not change the
  user's global updater/npm policy. Inspect current version rather than assuming it remains2.1.284.
- In the fresh session, read `decision_registry.py show` and the supported runtime pin. Activate only
  the reviewed `workflow-fit` policy with a known current checkpoint through the existing CLI:

```sh
python3 rhize-context-manager/scripts/typed_decisions/decision_registry.py set-mode workflow-fit cosign --reason credential_workflow_release --laya-revision CURRENT_VERIFIED_REVISION --manual-override --pin
```

  Replace the revision from fresh readback; do not invent it or use `unknown`. This explicit audited
  operator activation is not a statistical promotion. Do not activate it in a session whose developer
  contract still requires blanket shadow-only operation. Verify effective mode, exact policy/catalog
  hashes, a private enum-only receipt and actual delivered instructions after activation.
- Preserve the new source cohort boundary caused by the checkpoint wording change. Never backfill
  historical labels, pool cohorts or invent acceptance/usage/performance to make readiness appear green.
- Roll back guidance through `set-mode workflow-fit off --reason credential_workflow_rollback`; keep
  the independent credential GUI guard enabled. Report source/CI, installed files, active mode and
  native enforcement separately, with exact refs and remaining limitations.
