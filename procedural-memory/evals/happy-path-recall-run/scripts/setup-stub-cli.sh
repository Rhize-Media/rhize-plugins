#!/bin/sh
# setup-stub-cli.sh — scaffold_script for the happy-path-recall-run case.
#
# Runs BEFORE the agent starts (per claude plugin eval's context.scaffold_script).
# Writes a stub `rhize-skill` CLI + a fake `python3` sibling into the sandbox's
# own $HOME, so the agent's normal /procedural-memory:recall and
# /procedural-memory:run invocations drive the launcher end-to-end WITHOUT the
# real rhize-skill CLI, a real registry checkout, or a real Postgres — see this
# suite's README for why fixture mode is deliberate here, not provisional:
# `run` executes registry artifacts and `promote` commits to the registry,
# neither of which an eval case should ever do against the real thing
# regardless of what the sandbox can reach.
#
# DELIBERATELY NOT $RHIZE_SKILL_BIN: an eval case's `env:` block can only set
# EVAL_-prefixed vars, and asking the agent to `export RHIZE_SKILL_BIN=...`
# itself is fragile — the Bash tool does not persist shell state (env vars,
# cwd aside) across separate tool calls, so an export in one call would not
# reach the next call's launcher invocation. Instead this scaffold places the
# stub at the launcher's own documented convenience-default path
# (resolution order step 3 in scripts/rhize-skill-launcher.sh) inside the
# sandbox's fresh $HOME — the launcher finds it with zero cooperation from
# the agent, and this also happens to exercise that fallback path for real.
#
# The stub logs every invocation to $HOME/.stub-rhize-skill.log so the
# grader (or a human reading the report) can confirm the launcher passed
# through the exact command/args the agent issued.

set -eu

BIN_DIR="$HOME/dev-local/RHIZE/procedural-memory/.venv/bin"
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/rhize-skill" <<'INNER'
#!/bin/sh
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) invoked: $*" >> "$HOME/.stub-rhize-skill.log"
case "$1" in
    recall)
        cat <<'EOF'
1. fixture-artifact@1.0.0  sim=0.91  trust=unreviewed  health=degraded  last_verified=2026-08-20  success_rate=40%  runs=5
   > A fixture artifact standing in for a real registry hit in this eval's fixture mode.
EOF
        ;;
    run)
        echo "REFUSED: trust: fixture-artifact@1.0.0 is unreviewed for this digest" >&2
        exit 1
        ;;
    *)
        echo "stub rhize-skill: unhandled subcommand '$1'" >&2
        exit 1
        ;;
esac
INNER
chmod +x "$BIN_DIR/rhize-skill"

cat > "$BIN_DIR/python3" <<'INNER'
#!/bin/sh
echo "0.9.9"
INNER
chmod +x "$BIN_DIR/python3"

echo "stub CLI ready at $BIN_DIR"
