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
# otherwise. Run directly: sh tests/test-launcher.sh

set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
LAUNCHER="$SCRIPT_DIR/../scripts/rhize-skill-launcher.sh"
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
