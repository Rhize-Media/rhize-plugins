#!/usr/bin/env bash
# Regression test for the config-only exemption in refactor_gate.py.
#
# Exercises hook-write and hook-command against an isolated temp git workspace
# and an isolated RHIZE_REFACTOR_GATE_STATE_DIR, so it never touches real
# session state. Run from anywhere; paths are resolved relative to this file.
#
# Exit 0 = all assertions passed. Exit 1 = at least one assertion failed
# (see stderr for which one and why).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/../refactor_gate.py"

WORKDIR="$(mktemp -d)"
TMPWS="$WORKDIR/ws"
STATEDIR="$WORKDIR/state"
mkdir -p "$TMPWS" "$STATEDIR"

cleanup() {
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

FAILURES=0

assert_exit() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$actual" != "$expected" ]]; then
    echo "FAIL: $label — expected exit $expected, got $actual" >&2
    FAILURES=$((FAILURES + 1))
  else
    echo "PASS: $label (exit $actual)"
  fi
}

# --- Set up an isolated git repo with one committed source file ---
git -C "$TMPWS" init -q
git -C "$TMPWS" config user.email test@test.com
git -C "$TMPWS" config user.name test
mkdir -p "$TMPWS/src" "$TMPWS/.claude/plans"
echo "console.log('hi')" > "$TMPWS/src/app.ts"
git -C "$TMPWS" add -A
git -C "$TMPWS" commit -q -m init

export RHIZE_REFACTOR_GATE_STATE_DIR="$STATEDIR"

# --- Seed a pending receipt via hook-prompt ---
echo "{\"prompt\": \"fix the app code bug\", \"cwd\": \"$TMPWS\"}" \
  | python3 "$GATE" hook-prompt >/dev/null

hook_write() {
  local filepath="$1"
  echo "{\"cwd\": \"$TMPWS\", \"tool_input\": {\"file_path\": \"$filepath\", \"content\": \"x\"}}" \
    | python3 "$GATE" hook-write >/dev/null 2>&1
  echo "$?"
}

hook_command() {
  local cwd="$1" command="$2"
  echo "{\"cwd\": \"$cwd\", \"tool_input\": {\"command\": \"$command\"}}" \
    | python3 "$GATE" hook-command >/dev/null 2>&1
  echo "$?"
}

# --- hook-write matrix ---
assert_exit "hook-write .npmrc (config exempt)" 0 "$(hook_write "$TMPWS/.npmrc")"
assert_exit "hook-write pnpm-workspace.yaml (config exempt)" 0 "$(hook_write "$TMPWS/pnpm-workspace.yaml")"
assert_exit "hook-write src/app.ts (source still blocked)" 2 "$(hook_write "$TMPWS/src/app.ts")"
assert_exit "hook-write .claude/plans/x.md (planning still exempt)" 0 "$(hook_write "$TMPWS/.claude/plans/x.md")"
assert_exit "hook-write .eslintrc.js (code extension wins)" 2 "$(hook_write "$TMPWS/.eslintrc.js")"

# --- hook-command matrix (phase is still "pending": no gated write ever landed) ---
git -C "$TMPWS" checkout -q -- src/app.ts 2>/dev/null || true
rm -f "$TMPWS/.npmrc"

echo "npmrc-change" > "$TMPWS/.npmrc"
assert_exit "hook-command: only config dirty -> allow" 0 \
  "$(hook_command "$TMPWS" "git commit -am x")"

echo "modified" >> "$TMPWS/src/app.ts"
assert_exit "hook-command: config + source dirty -> block" 2 \
  "$(hook_command "$TMPWS" "git commit -am x")"

git -C "$TMPWS" checkout -q -- src/app.ts
rm -f "$TMPWS/.npmrc"
assert_exit "hook-command: clean tree -> allow" 0 \
  "$(hook_command "$TMPWS" "git commit -am x")"

echo "npmrc-change-2" > "$TMPWS/.npmrc"
assert_exit "hook-command: git -C <ws>, config-only, payload cwd elsewhere -> allow" 0 \
  "$(hook_command "/tmp" "git -C $TMPWS commit -am x")"

echo "modified-2" >> "$TMPWS/src/app.ts"
assert_exit "hook-command: git -C <ws>, source dirty, payload cwd elsewhere -> block" 2 \
  "$(hook_command "/tmp" "git -C $TMPWS commit -am x")"

if [[ "$FAILURES" -gt 0 ]]; then
  echo "$FAILURES assertion(s) failed" >&2
  exit 1
fi
echo "All assertions passed."
