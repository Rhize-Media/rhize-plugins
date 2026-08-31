#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_ROOT="$(cd "${SKILL_DIR}/../.." && pwd)"
MODE="${1:-}"

case "$MODE" in
  mine)
    shift
    exec "${PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh" functionize "$@"
    ;;
  generate)
    shift
    exec "${PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh" functionize-generate "$@"
    ;;
  review)
    shift
    exec "${PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh" functionize-review "$@"
    ;;
  *)
    echo "functionize.sh: expected one of the compile-only modes: mine, generate, review" >&2
    exit 64
    ;;
esac
