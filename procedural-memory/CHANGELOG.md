# Changelog — procedural-memory

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-19_ Add the canonical RHIZE Content Engine entrypoint with explicit local/CMS draft scope, canonical benchmark capture and current offline registry metadata. Full publishing remains unsupported; graph trust and host activation are separate.
- _2026-09-19_ version bump — 0.5.8 → 0.6.0 (minor); marketplace 2.75.0 → 2.76.0.
- _2026-09-15_ version bump — 0.5.7 → 0.5.8 (patch); marketplace 2.72.1 → 2.72.2.
- _2026-09-15_ `hooks/session-start-env.sh` (SessionStart): exports `PROCEDURAL_MEMORY_PLUGIN_ROOT`
  through `$CLAUDE_ENV_FILE` so Bash tool calls can reach `scripts/rhize-skill-launcher.sh` by an
  absolute path. Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` into command/hook text at load time
  but never exports it to the shell (measured in `claude plugin eval` and in a normal session), so
  shell commands that named the launcher through the variable expanded to `/scripts/...` and failed
  with 127. Advisory-only, exit 0 always, POSIX sh, tested under sh and dash. SKILL.md names the
  exported variable as the Bash-side path; the slash commands are unchanged. The sandbox probe now
  also checks the exported root and the Postgres Unix socket, and `evals/README.md` names the
  network wall precisely: the eval sandbox's egress is the `WebFetch(domain:…)` grants only, so
  localhost Postgres (TCP or socket) is unreachable from any case by harness design — fixture mode
  is not a workaround but the only option.
- _2026-09-15_ version bump — 0.5.6 → 0.5.7 (patch); marketplace 2.71.0 → 2.71.1.

### Changed

- _2026-09-15_ Eval suite hardened after its first real `claude plugin eval` run (the org gate
  lifted; 8 cases, 46 sessions, routing 6/6 positive fires and 12/12 negative silences).
  `happy-path-recall-run`: the `recall-reports-provenance` regex window widened 20→60 chars so
  the stub's own refusal line (`REFUSED: trust: <artifact> is unreviewed …`) counts as reporting
  the trust tier (it was graded a miss); new scored `uses-launcher` grader (`arm: both`) so the
  case measures the plugin's procedural contribution — the scaffold installs the stub CLI for
  both arms and the no-plugin baseline can drive it through plain Bash; `max_turns` 8→14.
  `probe-sandbox-reachability` rewritten as a `case.yaml` with a scaffold that records the
  plugin root into the sandbox HOME (`${CLAUDE_PLUGIN_ROOT}` is not exported to the Bash tool)
  and probes 127.0.0.1:5432 with `nc -z` (the tool shell is zsh; bash's `/dev/tcp` tested
  nothing). Turn caps raised where every run hit them: `trigger-recall`, `functionize-trigger`,
  `functionize-negative-registry-promotion` 6→12; `negative-memory-search` 6→8. `evals/README.md`
  and the README's "Eval coverage" section now describe the open gate, the Docker credential-store
  prerequisite, the pinned run command, and the measured probe result.


### Added

- _2026-09-04_ version bump — 0.5.5 → 0.5.6 (patch); marketplace 2.61.3 → 2.61.4.
- _2026-09-04_ version bump — 0.5.4 → 0.5.5 (patch); marketplace 2.61.2 → 2.61.3.

### Fixed

- _2026-09-03_ `hooks/post-bash-candidate-queue.sh` is POSIX sh again: a bash-only `<<<` herestring
  and a `${var:0:n}` substring expansion broke the hook under dash (Ubuntu's `/bin/sh`), found by the
  first runs of the promoted CI gate. Every shipped `#!/bin/sh` script now passes `dash -n`, and the
  hook's tests run it under every POSIX shell present on the machine (sh and dash).

### Added

- _2026-09-03_ version bump — 0.5.3 → 0.5.4 (patch); marketplace 2.61.0 → 2.61.1.
- _2026-09-03_ version bump — 0.5.2 → 0.5.3 (patch); marketplace 2.58.1 → 2.58.2.
