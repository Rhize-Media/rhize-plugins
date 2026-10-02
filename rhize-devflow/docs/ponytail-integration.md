# Ponytail integration

Ponytail supplies the simplicity ladder and reviews for unnecessary complexity. Keep it as an
upstream plugin. Dev Flow supplies scope, behavior-preservation checks and release authority.
Forge decision: **DEFER**. No upstream rules or hook code are copied into Rhize.

## Install and activate

```bash
claude plugin marketplace add DietrichGebert/ponytail
claude plugin install ponytail@ponytail --scope user
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

Review the installed lifecycle hooks in Codex `/hooks`, trust the inspected commands, and start a
new session. Restart the Codex desktop app after installation. Check that `node` is available in
the non-interactive shell. The hooks use only Node's standard library; no package install, API
key, MCP server or benchmark execution is needed for these two hosts.

Use upstream's **full** default. Its optional shared configuration is
`~/.config/ponytail/config.json` with `"defaultMode": "full"` (preserve other fields). The
`PONYTAIL_DEFAULT_MODE` environment variable takes precedence. Plain mode switches apply to the
current session; `ponytail default full` persists the default. Keep any existing status line.

## How it fits the development workflow

| Stage | Owner and action |
| --- | --- |
| Discovery and planning | Use Context Manager and Dev Flow's impact map to establish actual callers, scope and invariants. |
| Implementation | Use `ponytail:ponytail` in full mode after discovery: reuse existing code, then standard library, native features and installed dependencies before writing custom code. |
| Simplify | Use `ponytail:ponytail-review` as the complexity lens within `rhize-devflow:simplify`; apply only candidates that pass its behavior-preservation gate. |
| Validation | Run `rhize-devflow:check`, relevant tests and all repository-required checks. |
| Release review | Include scoped Ponytail complexity findings as advisory input to `rhize-devflow:review`. A clean complexity review cannot approve a release. |
| Broad audit | Invoke `ponytail:ponytail-audit` only when the user requests a repository-wide audit. It reports candidates; edits require authorization. |
| Deferred shortcuts | Use `ponytail:ponytail-debt` to report existing `ponytail:` markers. Record material limits in the project's state or plan. |
| Help and benchmarks | Use `ponytail:ponytail-help` and `ponytail:ponytail-gain` on request. The gain card reports vendor benchmarks, not measured Rhize savings. |

Claude uses `/ponytail:ponytail`, `/ponytail:ponytail-review`, and the other qualified skill names.
Codex loads the same six skills; select `@ponytail`/`@ponytail-review` or the host's offered skill
selector. Avoid loading a second copied ruleset. The existing Superpowers/ECC planning,
implementation, testing and review workflows remain owners of their procedures.

## Resolve conflicts before applying a suggestion

- Explicit user requirements and repository instructions are constraints. Full mode can choose
  a simpler implementation; it cannot silently remove requested behavior or deliver a partial task.
- Keep security, trust-boundary validation, data-loss handling, accessibility, tenant isolation,
  audit records, concurrency guards, pending UI, retries and idempotency when they protect behavior.
- Ponytail's example email check is not a general replacement for required input validation.
  Review every suggestion against the real consumer and trust boundary.
- Its minimal-test advice cannot reduce mandatory lint, type, build, regression, migration or
  release checks. Re-run relevant checks after applying any simplification.
- Scope review to the established diff. Do not turn a change review into a whole-repository audit.
- Concise output cannot hide required evidence, failures, limitations or requested explanations.
- Hooks inject instructions and track modes. They cannot grant delegation, credential, write,
  commit, push, merge, deployment or messaging authority.
- If Ponytail is absent or off, continue Dev Flow's own simplicity lenses. Do not require an
  optional dependency or turn it back on after a user disables it.

## Verification and upstream changes

Verify installed manifests, all six skills, declared hook commands, Node availability, Codex hook
trust and isolated lifecycle/mode-switch behavior. Installed metadata alone does not prove an
already-running session reloaded its hooks. Treat fresh-session model behavior and actual task
benefit as separate evidence.

Review the exact load surface: manifests, hook scripts and imported local modules, skills and
assets. Retain whole-repository scanner findings separately; benchmark tools and other host
adapters are not runtime dependencies of Claude/Codex. Do not execute them as part of setup.
Use the scanner's explicit verdict and coverage fields; an empty or unknown result is not a pass.

Provenance is in [the companion ledger](ponytail-provenance.md). Use the existing AI-stack drift sensor for
updates. Recheck mode behavior, hooks and these authority boundaries before trusting new hashes.
Do not add another schedule.
