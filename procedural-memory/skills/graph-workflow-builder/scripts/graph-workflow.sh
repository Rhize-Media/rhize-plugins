#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_ROOT="$(cd "${SKILL_DIR}/../.." && pwd)"
LAUNCHER="${PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh"
if ! help_output=$("$LAUNCHER" graph workflow --help 2>&1); then
    echo "graph-workflow.sh: installed rhize-skill lacks the native workflow contract" >&2
    echo "$help_output" >&2
    exit 78
fi
exec "$LAUNCHER" "$@"
