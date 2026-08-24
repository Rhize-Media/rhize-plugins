#!/bin/sh
# post-bash-candidate-queue.sh — PostToolUse hook (matcher: Bash).
#
# Appends one JSONL line to the procedural-memory candidate queue whenever a
# Bash call matching a known test/build invocation completes. This is the
# cheap half of the two-tier hook design (see session-end-scan.py for the
# heavier half); it fires on EVERY Bash call in EVERY session, so it must
# stay well under 10ms on the common (non-matching) path. See this plugin's
# README "Real measured latency" for the instrumented numbers, including
# what it costs on the rarer matching path and on a pathological huge-output
# input.
#
# WHY THIS NEVER CHECKS AN EXIT CODE (verified empirically 2026-08-24, this
# Claude Code install): the Bash tool_response payload delivered to hooks
# carries only {stdout, stderr, interrupted, isImage, noOutputExpected} — no
# exit-code field exists (confirmed against the shipped sdk-tools.d.ts
# BashOutput interface AND real transcript data). More importantly,
# PostToolUse for Bash was found NOT TO FIRE AT ALL when the tool result is
# an error: a 3-command probe (pass/fail/pass) in an isolated scratch
# session produced exactly two PostToolUse events, for the two passing
# commands — the failing one (exit 7) never reached this hook. So by the
# time this script runs, the command has already succeeded; there is
# nothing to check. This is a deviation from the original brief, which
# assumed reading an exit code — see the plugin README's "What was wrong in
# the brief" note.
#
# QUEUE FILE: deliberately NOT rhize-context-manager's
# ~/.claude/context-manager/refinement-queue.jsonl. That queue is scoped to
# skill-refinement signals (its own SKILL.md: "this plugin's skills +
# ~/.claude/skills/learned/") and triaged by /skill-refine, which is the
# wrong tool for "code that passed a test this session, maybe worth
# promoting to the procedural-memory registry." This hook follows that
# queue's SHAPE (id/ts/source/repo/pattern, status lifecycle,
# one-JSON-object-per-line JSONL) but writes to its own file.
#
# APPEND SAFETY: a single `printf ... >>` is one write(2) syscall for a line
# this short, which POSIX guarantees atomic on a local filesystem opened
# O_APPEND — concurrent sessions interleave whole lines, never corrupt one.
# flock(1) does not exist on macOS/BSD (it's a Linux util-linux tool), so
# this is the portable equivalent — same reasoning
# docs/mcp-secret-launcher.md already applies to prefer a portable mechanism
# over a Linux-only one.
#
# SUBPROCESS BUDGET — this is the section that actually determines latency.
# `/bin/sh` on macOS is bash 3.2.57, and TWO facts about it shape everything
# below:
#
#   1. `${var#*pattern}` / `${var%pattern}` (shortest-match glob strip) on a
#      LARGE string is pathological, not just slow: measured directly, with
#      a payload carrying a ~1MB `tool_response.stdout` (a realistic verbose
#      test/build log), stripping a prefix up to a pattern near the END of
#      that string HUNG for multiple minutes. `case "$x" in *pattern*)` glob
#      MATCHING does not show this — only `#`/`%` extraction does.
#   2. Every external command forked adds real, measurable wall time on
#      macOS (~2-7ms per fork observed here) — dominating the total once
#      you're spawning several. A version of this script that called `cat`
#      for stdin, `grep` four times, and `cut` once measured ~25-35ms/call
#      even on tiny payloads, almost entirely fork overhead, not actual
#      work.
#
# So: read stdin with the `read` builtin (no `cat` fork). Extract
# `command`/`session_id`/`cwd` with plain `${var#...}`/`${var%...}` — safe
# here because these fields are causally guaranteed to precede
# `tool_response` in the payload (Claude Code cannot serialize a tool's
# *response* before the tool has been *called*, so `tool_input` — where
# `command` lives — and the top-level `session_id`/`cwd` are always written
# first). `tool_use_id`, which the same causality places AFTER
# `tool_response` (it's echoed back as post-hoc metadata alongside
# `duration_ms`), is the one field extracted with `grep -o -m1` instead —
# it's the only field a huge `stdout` sits in front of, and `grep` doesn't
# share bash 3.2's pathology. Truncating the (already short, already
# extracted) command uses `${cmd:0:300}`, not `cut`. `date` remains the one
# genuinely unavoidable fork (bash 3.2 predates the `printf '%(fmt)T'` and
# `$EPOCHREALTIME` builtins that would otherwise avoid it) — but it, and the
# one `grep` call, only run on the rare path where a candidate is actually
# being written, never on every Bash call.
#
# This is still not a JSON parser: a `tool_input.command` containing a
# literal, unescaped double-quote (e.g. `pytest -k "test_name"`) defeats
# extraction and this hook silently no-ops for that call — a missed
# candidate, never a crash and never a corrupt queue line. session-end-scan.py
# (Tier 2) has no such constraint and parses the transcript with a real json
# module.

set -eu

QUEUE="${PROCEDURAL_MEMORY_CANDIDATE_QUEUE:-$HOME/.claude/procedural-memory/candidate-queue.jsonl}"

# Slurp stdin without forking `cat` (`read` is a shell builtin). The
# `|| [ -n "$line" ]` keeps the loop running for a final line that has
# content but no trailing newline (the payload isn't guaranteed to end in
# one) — the standard POSIX `read` gotcha.
payload=""
while IFS= read -r line || [ -n "$line" ]; do
    payload="$payload$line"
done

case "$payload" in
    *'"tool_name":"Bash"'*) ;;
    *) exit 0 ;;
esac

# Bail on an interrupted call (rare — Ctrl-C mid-command, or a backgrounded
# task). Not load-bearing for "did it succeed" (see header: a failing call
# never reaches this hook at all), just a defensive skip of a call that
# didn't run to completion.
case "$payload" in
    *'"interrupted":true'*) exit 0 ;;
esac

# command lives in tool_input, which precedes tool_response — safe to
# extract with parameter expansion (see SUBPROCESS BUDGET above).
rest="${payload#*\"command\":\"}"
[ "$rest" != "$payload" ] || exit 0
cmd="${rest%%\"*}"
[ -n "$cmd" ] || exit 0

# Known test/build invocations. `pattern` records which one matched, purely
# for a human reading the queue later — session-end-scan.py doesn't branch
# on it. This case block is also the fast-reject point for the overwhelming
# majority of Bash calls (ls, git, cd, ...): no subprocess has been forked
# yet at all, only shell builtins/glob matching.
pattern=""
case "$cmd" in
    *pytest*) pattern="pytest" ;;
    *"npm test"*|*"npm run test"*) pattern="npm test" ;;
    *"npm run build"*) pattern="npm run build" ;;
    *"yarn test"*) pattern="yarn test" ;;
    *"yarn build"*) pattern="yarn build" ;;
    *"pnpm test"*) pattern="pnpm test" ;;
    *"pnpm build"*) pattern="pnpm build" ;;
    *"cargo test"*) pattern="cargo test" ;;
    *"go test"*) pattern="go test" ;;
    *"go build"*) pattern="go build" ;;
    *vitest*) pattern="vitest" ;;
    *jest*) pattern="jest" ;;
    *tsc*) pattern="tsc" ;;
    *) exit 0 ;;
esac

# --- everything below here only runs for a confirmed candidate ---

session_id="${payload#*\"session_id\":\"}"
session_id="${session_id%%\"*}"

cwd="${payload#*\"cwd\":\"}"
cwd="${cwd%%\"*}"

# tool_use_id sits AFTER tool_response — the one field where a huge stdout
# would make `${payload#*pattern}` pathological (see SUBPROCESS BUDGET).
# `grep -o -m1` does a bounded linear scan instead; stops at first match.
# The `<<<` herestring hands $payload to grep via a shell-managed temp
# file/pipe instead of a `printf | grep` pipeline, so this is exactly one
# fork (grep), not two.
tool_use_id=$(grep -o -m1 '"tool_use_id":"[^"]*"' <<< "$payload") || true
tool_use_id="${tool_use_id#*:\"}"
tool_use_id="${tool_use_id%\"}"
[ -n "$tool_use_id" ] || tool_use_id="unknown-$$"

# Truncate to keep the line comfortably short and the queue file greppable
# — pure substring expansion on the already-short $cmd, not `cut`.
cmd_trunc="${cmd:0:300}"

ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

queue_dir="${QUEUE%/*}"
[ -d "$queue_dir" ] || mkdir -p "$queue_dir"

printf '{"id":"%s","ts":"%s","source":"post-bash-hook","repo":"%s","session_id":"%s","pattern":"%s","command":"%s","status":"pending"}\n' \
    "$tool_use_id" "$ts" "$cwd" "$session_id" "$pattern" "$cmd_trunc" >> "$QUEUE"

exit 0
