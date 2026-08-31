#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_ROOT="$(cd "${SKILL_DIR}/../.." && pwd)"
MODE="${1:-}"
SUBCOMMAND=""

case "$MODE" in
  mine)
    shift
    SUBCOMMAND="functionize"
    ;;
  generate)
    shift
    SUBCOMMAND="functionize-generate"
    ;;
  review)
    shift
    SUBCOMMAND="functionize-review"
    ;;
  *)
    echo "functionize.sh: expected one of the compile-only modes: mine, generate, review" >&2
    exit 64
    ;;
esac

# Functionize was added without a rhize-skill package-version bump, so semver alone cannot
# distinguish a stale 0.1.0 install. Prove the exact side-effect-free command surface before
# dispatching user arguments; an older same-version CLI must fail closed rather than fall through
# to an opaque "unknown command" error.
if ! HELP_OUTPUT=$("${PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh" "$SUBCOMMAND" --help 2>&1); then
  {
    printf '%s\n' \
      "functionize.sh: resolved rhize-skill does not expose required compile-only subcommand '$SUBCOMMAND'."
    printf '%s\n' "$HELP_OUTPUT"
  } >&2
  exit 78
fi

exec "${PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh" "$SUBCOMMAND" "$@"
