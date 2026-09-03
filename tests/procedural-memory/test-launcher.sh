#!/bin/sh
# test-launcher.sh — substitute harness for scripts/rhize-skill-launcher.sh's
# own resolution and version-gate logic.
#
# WHY THIS EXISTS INSTEAD OF LIVING PURELY UNDER evals/: `claude plugin eval`
# is gated behind an organization-level early-access flag on this install —
# confirmed on BOTH `claude plugin eval init` and `claude plugin eval <target>
# --case ...` (not just init; both print the identical "currently in early
# access" message and exit non-zero, tested directly). The authored suite
# under evals/ still exists and is the suite of record for when that gate
# opens — see evals/README.md. This script is the substitute: it tests the
# launcher's own load-bearing logic (CLI resolution order, version gate)
# directly via Bash, no Claude Code session or eval harness required, so it
# runs today and actually proves something rather than sitting unverified.
#
# Never runs the REAL rhize-skill CLI or touches the real registry/Postgres —
# every test uses a stub `rhize-skill` + fake `python3` sibling under an
# isolated tmp HOME, with PATH restricted so nothing on this machine's real
# PATH leaks in.
#
# Exits 0 if every assertion passes, non-zero (and prints which one failed)
# otherwise. Run directly: sh tests/procedural-memory/test-launcher.sh

set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
PLUGIN_DIR="$REPO_ROOT/procedural-memory"
LAUNCHER="$PLUGIN_DIR/scripts/rhize-skill-launcher.sh"
SKILL_LAUNCHER="$PLUGIN_DIR/skills/procedural-memory/scripts/procedural-memory.sh"
FUNCTIONIZE_LAUNCHER="$PLUGIN_DIR/skills/functionize/scripts/functionize.sh"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

FAILURES=0

assert_eq() {
    # assert_eq <label> <expected> <actual>
    if [ "$2" != "$3" ]; then
        echo "FAIL: $1 -- expected [$2], got [$3]"
        FAILURES=$((FAILURES + 1))
    else
        echo "ok:   $1"
    fi
}

assert_contains() {
    # assert_contains <label> <haystack-file> <needle>
    if grep -qF "$3" "$2"; then
        echo "ok:   $1"
    else
        echo "FAIL: $1 -- expected to find [$3] in:"
        sed 's/^/         /' "$2"
        FAILURES=$((FAILURES + 1))
    fi
}

assert_absent() {
    # assert_absent <label> <file-that-should-not-exist>
    if [ -e "$2" ]; then
        echo "FAIL: $1 -- $2 should not exist but does"
        FAILURES=$((FAILURES + 1))
    else
        echo "ok:   $1"
    fi
}

mkdir -p "$WORK/empty-home" "$WORK/stub-old/bin" "$WORK/stub-good/bin"

cat > "$WORK/stub-old/bin/rhize-skill" <<'EOF'
#!/bin/sh
echo "invoked: $*" >> "$STUB_LOG"
exit 0
EOF
cat > "$WORK/stub-old/bin/python3" <<'EOF'
#!/bin/sh
echo "0.0.1"
EOF

cat > "$WORK/stub-good/bin/rhize-skill" <<'EOF'
#!/bin/sh
echo "invoked: $*" >> "$STUB_LOG"
exit 0
EOF
cat > "$WORK/stub-good/bin/python3" <<'EOF'
#!/bin/sh
echo "0.2.0"
EOF
chmod +x "$WORK"/stub-*/bin/*

echo "=== Test A: nothing resolvable -> exit 78, refusal names all 3 checked locations ==="
set +e
env -i HOME="$WORK/empty-home" PATH="/usr/bin:/bin" "$LAUNCHER" recall "test task" \
    > "$WORK/testA.out" 2>&1
code=$?
set -e
assert_eq "Test A exit code" "78" "$code"
assert_contains "Test A names \$RHIZE_SKILL_BIN check" "$WORK/testA.out" '$RHIZE_SKILL_BIN'
assert_contains "Test A names PATH check" "$WORK/testA.out" 'rhize-skill on $PATH'
assert_contains "Test A names default-checkout check" "$WORK/testA.out" 'procedural-memory/.venv/bin/rhize-skill'

echo
echo "=== Test B (deliberately broken): stub CLI reports 0.0.1 < MIN_VERSION -> must refuse and go red ==="
rm -f "$WORK/stub-old-log.txt"
set +e
env -i HOME="$WORK/empty-home" PATH="$WORK/stub-old/bin:/usr/bin:/bin" \
    STUB_LOG="$WORK/stub-old-log.txt" "$LAUNCHER" recall "test task" \
    > "$WORK/testB.out" 2>&1
code=$?
set -e
assert_eq "Test B exit code (refusal)" "1" "$code"
assert_contains "Test B names the found version" "$WORK/testB.out" "Found:    rhize-skill 0.0.1"
assert_contains "Test B names the expected version" "$WORK/testB.out" "Expected: >= 0.1.0"
assert_absent "Test B never executed the stub CLI (refused before exec)" "$WORK/stub-old-log.txt"

echo
echo "=== Test C: stub CLI reports 0.2.0 >= MIN_VERSION -> passthrough, real argv reaches it ==="
rm -f "$WORK/stub-good-log.txt"
set +e
env -i HOME="$WORK/empty-home" PATH="$WORK/stub-good/bin:/usr/bin:/bin" \
    STUB_LOG="$WORK/stub-good-log.txt" "$LAUNCHER" recall "sync a GHL contact to Slack" \
    > "$WORK/testC.out" 2>&1
code=$?
set -e
assert_eq "Test C exit code (success passthrough)" "0" "$code"
assert_contains "Test C stub received the real argv" "$WORK/stub-good-log.txt" \
    "invoked: recall sync a GHL contact to Slack"

echo
echo "=== Test C2: self-relative skill launcher works from an unrelated cwd ==="
rm -f "$WORK/stub-skill-log.txt"
set +e
(cd "$WORK/empty-home" && env -i HOME="$WORK/empty-home" \
    PATH="$WORK/stub-good/bin:/usr/bin:/bin" STUB_LOG="$WORK/stub-skill-log.txt" \
    bash "$SKILL_LAUNCHER" verify artifact-name) > "$WORK/testC2.out" 2>&1
code=$?
set -e
assert_eq "Test C2 exit code (success passthrough)" "0" "$code"
assert_contains "Test C2 stub received the real argv" "$WORK/stub-skill-log.txt" \
    "invoked: verify artifact-name"

echo
echo "=== Test C3: Functionize launcher maps only its three compile-only modes ==="
rm -f "$WORK/stub-functionize-log.txt"
set +e
(cd "$WORK/empty-home" && env -i HOME="$WORK/empty-home" \
    PATH="$WORK/stub-good/bin:/usr/bin:/bin" STUB_LOG="$WORK/stub-functionize-log.txt" \
    bash "$FUNCTIONIZE_LAUNCHER" mine git --json) > "$WORK/testC3-mine.out" 2>&1
mine_code=$?
(cd "$WORK/empty-home" && env -i HOME="$WORK/empty-home" \
    PATH="$WORK/stub-good/bin:/usr/bin:/bin" STUB_LOG="$WORK/stub-functionize-log.txt" \
    bash "$FUNCTIONIZE_LAUNCHER" generate candidate.json --proposal-dir proposals) \
    > "$WORK/testC3-generate.out" 2>&1
generate_code=$?
(cd "$WORK/empty-home" && env -i HOME="$WORK/empty-home" \
    PATH="$WORK/stub-good/bin:/usr/bin:/bin" STUB_LOG="$WORK/stub-functionize-log.txt" \
    bash "$FUNCTIONIZE_LAUNCHER" review candidate.json review.json --ledger reviews.jsonl) \
    > "$WORK/testC3-review.out" 2>&1
review_code=$?
set -e
assert_eq "Test C3 mine exit code" "0" "$mine_code"
assert_eq "Test C3 generate exit code" "0" "$generate_code"
assert_eq "Test C3 review exit code" "0" "$review_code"
assert_contains "Test C3 mine maps to functionize" "$WORK/stub-functionize-log.txt" \
    "invoked: functionize git --json"
assert_contains "Test C3 generate maps to functionize-generate" "$WORK/stub-functionize-log.txt" \
    "invoked: functionize-generate candidate.json --proposal-dir proposals"
assert_contains "Test C3 review maps to functionize-review" "$WORK/stub-functionize-log.txt" \
    "invoked: functionize-review candidate.json review.json --ledger reviews.jsonl"

echo
echo "=== Test C4: Functionize launcher refuses registry and execution commands before CLI resolution ==="
for forbidden in promote approve verify run; do
    set +e
    env -i HOME="$WORK/empty-home" PATH="/usr/bin:/bin" \
        bash "$FUNCTIONIZE_LAUNCHER" "$forbidden" artifact-name \
        > "$WORK/testC4-$forbidden.out" 2>&1
    code=$?
    set -e
    assert_eq "Test C4 refuses $forbidden" "64" "$code"
    assert_contains "Test C4 names compile-only boundary for $forbidden" \
        "$WORK/testC4-$forbidden.out" "compile-only modes: mine, generate, review"
done

echo
echo "=== Test D: RHIZE_SKILL_BIN set to a non-executable path -> loud refusal, exit 78 ==="
set +e
env -i HOME="$WORK/empty-home" PATH="/usr/bin:/bin" \
    RHIZE_SKILL_BIN="$WORK/does-not-exist" "$LAUNCHER" run foo \
    > "$WORK/testD.out" 2>&1
code=$?
set -e
assert_eq "Test D exit code" "78" "$code"
assert_contains "Test D names the bad override path" "$WORK/testD.out" "RHIZE_SKILL_BIN is set to"

echo
if [ "$FAILURES" -eq 0 ]; then
    echo "All launcher tests passed."
    exit 0
else
    echo "$FAILURES launcher test(s) FAILED."
    exit 1
fi
