#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_ROOT="$(cd "${SKILL_DIR}/../.." && pwd)"
exec "${PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh" "$@"
