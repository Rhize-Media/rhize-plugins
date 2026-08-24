#!/bin/sh
# rhize-skill-launcher.sh — portable resolver + version gate for the procedural-memory
# registry CLI (`rhize-skill`), invoked by this plugin's commands and skill instead of
# any of them hardcoding a path to it.
#
# WHY THIS EXISTS
# ---------------
# rhize-plugins is distributed; a hardcoded
# ~/dev-local/RHIZE/procedural-memory/.venv/bin/rhize-skill only exists on the machine
# that happened to check the registry out there. This shim resolves the binary the
# same shape docs/mcp-secret-launcher.sh already uses for credentials: an explicit
# override first, a sensible convenience default second, and a loud, actionable
# refusal — never a silent no-op, never a confusing downstream error — when neither
# is available.
#
# It also guards against plugin/CLI drift. This plugin was built against a known
# MIN_VERSION of rhize-skill's command surface (flags, exit codes). An older CLI
# resolved from PATH or the convenience default could silently misbehave in ways
# that are hard to diagnose from a single command's output, so the version is
# checked before every invocation and a mismatch fails loudly, naming both versions.
#
# RESOLUTION ORDER
#   1. RHIZE_SKILL_BIN env var — exact path to the `rhize-skill` executable.
#   2. `rhize-skill` on PATH (`command -v`) — the portable case: any machine that
#      installed the CLI normally (pip/pipx install, or its own venv put on PATH).
#   3. The known convenience default for a `procedural-memory` checkout at
#      ~/dev-local/RHIZE/procedural-memory — this developer's machine only. Never
#      assumed to exist; used only if that exact file is present and executable.
#   4. Refuse to run, naming exactly what was checked and how to fix it.
#
# Usage: rhize-skill-launcher.sh <rhize-skill subcommand and args...>
# e.g.:  rhize-skill-launcher.sh recall "sync a GHL contact to Slack"

set -eu

SELF="rhize-skill-launcher.sh"

# Bump when this plugin starts depending on a newer rhize-skill flag/behavior;
# see procedural-memory/docs/decisions/ for the record of what changed and why.
MIN_VERSION="0.1.0"

DEFAULT_BIN="${HOME:-}/dev-local/RHIZE/procedural-memory/.venv/bin/rhize-skill"

# --- 1-3. resolve the binary -------------------------------------------------
BIN=""
if [ -n "${RHIZE_SKILL_BIN:-}" ]; then
    if [ -x "$RHIZE_SKILL_BIN" ]; then
        BIN="$RHIZE_SKILL_BIN"
    else
        echo "$SELF: RHIZE_SKILL_BIN is set to '$RHIZE_SKILL_BIN' but that file is not executable." >&2
        exit 78 # EX_CONFIG
    fi
elif command -v rhize-skill >/dev/null 2>&1; then
    BIN=$(command -v rhize-skill)
elif [ -x "$DEFAULT_BIN" ]; then
    BIN="$DEFAULT_BIN"
fi

# --- 4. refuse loudly if nothing resolved ------------------------------------
if [ -z "$BIN" ]; then
    {
        echo "$SELF: cannot find the rhize-skill CLI (procedural-memory registry)."
        echo
        echo "  Checked, in order:"
        echo "    1. \$RHIZE_SKILL_BIN      -> not set"
        echo "    2. rhize-skill on \$PATH  -> not found"
        echo "    3. $DEFAULT_BIN"
        echo "       -> not present or not executable"
        echo
        echo "  Fix it with ONE of these:"
        echo
        echo "  (a) Already have the CLI built elsewhere? Point straight at it:"
        echo "        export RHIZE_SKILL_BIN=/path/to/rhize-skill"
        echo
        echo "  (b) Build it from a procedural-memory checkout:"
        echo "        cd ~/dev-local/RHIZE/procedural-memory"
        echo "        python3 -m venv .venv && .venv/bin/pip install -e \".[test]\""
        echo "        .venv/bin/rhize-skill doctor   # confirms Postgres/pgvector/Keychain too"
        echo
        echo "  This plugin never guesses at a path that isn't actually there — a"
        echo "  silently-wrong CLI location fails as a confusing downstream error"
        echo "  instead of this clear one."
    } >&2
    exit 78 # EX_CONFIG
fi

# --- version-compatibility gate ----------------------------------------------
# rhize-skill has no --version flag (verified against 0.1.0), so the version is
# read the same way `pip show`/`importlib.metadata` would, using the interpreter
# that owns the same install as the resolved binary (its bin/ sibling, true for
# both a venv and a pipx install — the two ways the CLI's own README documents
# installing it).
BIN_DIR=$(dirname "$BIN")
PY=""
if [ -x "$BIN_DIR/python3" ]; then
    PY="$BIN_DIR/python3"
elif [ -x "$BIN_DIR/python" ]; then
    PY="$BIN_DIR/python"
fi

if [ -n "$PY" ]; then
    ACTUAL_VERSION=$("$PY" -c "import importlib.metadata as m; print(m.version('rhize-skill'))" 2>/dev/null || true)
    if [ -n "$ACTUAL_VERSION" ]; then
        LOWEST=$(printf '%s\n%s\n' "$ACTUAL_VERSION" "$MIN_VERSION" | sort -V | head -n1)
        if [ "$LOWEST" = "$ACTUAL_VERSION" ] && [ "$ACTUAL_VERSION" != "$MIN_VERSION" ]; then
            {
                echo "$SELF: rhize-skill is older than this plugin expects."
                echo
                echo "  Found:    rhize-skill $ACTUAL_VERSION  ($BIN)"
                echo "  Expected: >= $MIN_VERSION"
                echo
                echo "  Update the registry checkout and reinstall:"
                echo "    cd ~/dev-local/RHIZE/procedural-memory && git pull"
                echo "    .venv/bin/pip install -e \".[test]\""
                echo
                echo "  Or point RHIZE_SKILL_BIN at a build that already meets the minimum."
            } >&2
            exit 1
        fi
    else
        echo "$SELF: warning: could not determine rhize-skill's installed version (no importlib.metadata entry for it next to $BIN) — skipping the version-compatibility check." >&2
    fi
else
    echo "$SELF: warning: no sibling python/python3 next to $BIN — skipping the version-compatibility check." >&2
fi

exec "$BIN" "$@"
