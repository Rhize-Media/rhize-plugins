# 0002 — The post-Bash hook never reads an exit code (there isn't one)

**Status:** decided, 2026-08-24 (hooks wiring)

## Context

The task handing off the hooks wiring specified: "post-Bash: pure shell
pattern-match. Recognize a test/build command that **exited 0**... append a
line to a queue file." That phrasing assumes the PostToolUse hook payload
for Bash carries (or can derive) an exit code.

## What was actually found

Empirically verified against this Claude Code install (2026-08-24), three
independent ways:

1. The shipped `sdk-tools.d.ts` (`@anthropic-ai/claude-code`)'s `BashOutput`
   interface: `{stdout, stderr, rawOutputPath?, interrupted, isImage?,
   backgroundTaskId?}` — no exit-code field.
2. Real transcript data from live sessions in this repo: every Bash
   `toolUseResult` observed has exactly the keys `{stdout, stderr,
   interrupted, isImage, noOutputExpected}`.
3. A live probe: an isolated scratch session (`claude -p ... --allowedTools
   Bash`) was made to run three Bash calls in order — pass, fail (`exit 7`),
   pass — with a temporary PostToolUse/Bash hook dumping its raw stdin
   payload to a file. **Only the two passing commands produced a
   PostToolUse event.** The failing command never reached the hook at all.

So there are two independent facts, not one: no exit-code field exists in
the payload, *and* PostToolUse for Bash does not fire when the tool result
is an error. The second fact makes the first moot for this hook's purpose —
by the time `post-bash-candidate-queue.sh` runs, the command has already
succeeded. There is nothing to check.

(Separately, the transcript's `tool_result` blocks — a different structure
from the hook payload, read by `session-end-scan.py` from the transcript
file, not delivered to this hook — do carry `is_error`, and it does track
non-zero exit. That's real and used, in Tier 2, for the same probe's
fail case: `is_error: true` there. It just isn't visible to the
PostToolUse hook itself.)

## Decision

`post-bash-candidate-queue.sh` does not read, derive, or check an exit code.
It pattern-matches `tool_input.command` against known test/build
invocations and, if matched, appends a candidate — full stop. The two
empirical facts above are why this is correct rather than a shortcut:
nothing reaching this hook can be a failure.

## Consequences

- The header comment of `post-bash-candidate-queue.sh` documents this in
  detail — read it before changing the hook's success-detection logic.
- `session-end-scan.py` (Tier 2) still defensively checks `is_error` when
  cross-referencing the transcript, in case a future Claude Code version
  changes when PostToolUse fires. If that ever happens, entries whose
  transcript `is_error` is `true` are marked `rejected`, not `surfaced` —
  the defense is already in place, just currently unreachable.
- If a future Claude Code version starts firing PostToolUse on Bash
  failures too, this decision needs revisiting — the guard above will catch
  it functionally (rejected entries just won't stay quiet on newer
  installs), but the STATUS 1 reasoning above will be stale and should be
  re-verified/rewritten rather than assumed.

## Related

- A second, independent finding from the same investigation:
  `${payload#*pattern}` (bash 3.2's shortest-prefix glob-strip, `/bin/sh` on
  macOS) hangs for minutes on a payload whose `tool_response.stdout` is
  large (~1MB) and whose target field sits after it — `case ... in
  *pattern*)` glob matching does not share this pathology. This shaped the
  hook's field-extraction approach (parameter expansion for fields
  guaranteed to precede `tool_response`, `grep -o -m1` for the one field —
  `tool_use_id` — that doesn't). See the script's own "SUBPROCESS BUDGET"
  comment for the full reasoning; this is documented there rather than
  duplicated here because it's an implementation detail, not a scope
  decision.
