#!/bin/sh
# Compile-only Functionize skill boundary. Registry and execution commands are intentionally absent.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
LAUNCHER="$PLUGIN_ROOT/scripts/rhize-skill-launcher.sh"

usage() {
    echo "usage: functionize.sh <mine|generate|review> [arguments...]" >&2
    echo "compile-only modes: mine, generate, review" >&2
}

mode=${1:-}
case "$mode" in
    mine)
        command_name="functionize"
        ;;
    generate)
        command_name="functionize-generate"
        ;;
    review)
        command_name="functionize-review"
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        usage
        exit 64
        ;;
esac
shift

if ! help_output=$("$LAUNCHER" "$command_name" --help 2>&1); then
    echo "functionize.sh: installed rhize-skill does not support $command_name" >&2
    echo "$help_output" >&2
    exit 78
fi

exec "$LAUNCHER" "$command_name" "$@"
