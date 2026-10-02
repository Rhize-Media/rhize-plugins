#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_ROOT="$(cd "${SKILL_DIR}/../.." && pwd)"
LAUNCHER="${PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh"

if [[ "${1:-}" == "recipe-stage" ]]; then
    shift
    command_name="functionize-recipe-stage"
    if ! help_output=$("$LAUNCHER" "$command_name" --help 2>&1); then
        echo "procedural-memory.sh: installed rhize-skill does not support $command_name" >&2
        echo "$help_output" >&2
        exit 78
    fi
    exec "$LAUNCHER" "$command_name" "$@"
fi

exec "$LAUNCHER" "$@"
