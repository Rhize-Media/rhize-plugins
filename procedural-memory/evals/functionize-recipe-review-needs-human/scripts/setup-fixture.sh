#!/bin/sh
# Shared synthetic fixture scaffold, resolved from this case's own path.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec sh "$SCRIPT_DIR/../../functionize-cross-call/scripts/setup-fixture.sh" functionize-recipe-review-needs-human
