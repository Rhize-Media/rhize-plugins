#!/usr/bin/env python3
"""Validate scripts/validate_plugin_configs.py's checks against fixture files.

Mirrors tests/skill-map/validate_fixtures.py: loads the script under test via
_util.load_module (avoids a second copy of the detection logic), then asserts
each fixture produces the expected (errors, warnings) count — one positive
(must be caught) and one negative (must NOT be flagged) case per check, plus
the three cases the review specifically called out: SLACK_TEAM_ID and
KEY_FILE_PATH must not match check (b), an HTTP headers block using "${VAR}"
must not be flagged, and a correctly double-quoted "${CLAUDE_PLUGIN_ROOT}/x.py"
must not be flagged by check (a).

Exit code 0 if every fixture matches its expected outcome, 1 otherwise.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_plugin_configs.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str((REPO_ROOT / "tests" / "skill-map").resolve()))
from _util import load_module  # noqa: E402

# fixture filename -> (kind, expected_errors, expected_warnings)
# kind: "hooks" -> lint_hooks_file, "mcp" -> lint_mcp_file
EXPECTATIONS = {
    # check (a): unquoted ${VAR} in hook commands
    "hooks-unquoted-path-error.json": ("hooks", 1, 0),
    "hooks-unquoted-nonpath-warning.json": ("hooks", 0, 1),
    "hooks-quoted-good.json": ("hooks", 0, 0),
    # check (b): secret-shaped env values in a stdio server block
    "mcp-secret-key-error.json": ("mcp", 1, 0),
    "mcp-secret-default-form-error.json": ("mcp", 1, 0),  # ${VAR:-default} form
    "mcp-secret-username-warning.json": ("mcp", 0, 1),
    "mcp-secret-negative.json": ("mcp", 0, 0),  # SLACK_TEAM_ID, KEY_FILE_PATH
    "mcp-http-headers-negative.json": ("mcp", 0, 0),  # HTTP headers ${VAR} is correct, out of scope
    # check (c): trailing slash on a *_URL / *_BASE_URL env value
    "mcp-trailing-slash-warning.json": ("mcp", 0, 1),
    "mcp-no-trailing-slash-negative.json": ("mcp", 0, 0),
}


def main() -> int:
    mod = load_module(SCRIPT_PATH, "validate_plugin_configs")
    overall_ok = True

    for filename, (kind, expect_errors, expect_warnings) in EXPECTATIONS.items():
        path = FIXTURES_DIR / filename
        if not path.exists():
            print(f"FAIL {filename}: fixture file missing")
            overall_ok = False
            continue

        if kind == "hooks":
            findings = mod.lint_hooks_file(path, "test-plugin")
        else:
            findings = mod.lint_mcp_file(path, "test-plugin")

        errors = [f for f in findings if f.severity == "error"]
        warnings = [f for f in findings if f.severity == "warning"]

        if len(errors) != expect_errors or len(warnings) != expect_warnings:
            print(
                f"FAIL {filename}: expected (errors={expect_errors}, warnings={expect_warnings}), "
                f"got (errors={len(errors)}, warnings={len(warnings)}) — "
                f"findings: {[(f.severity, f.pointer, f.message) for f in findings]}"
            )
            overall_ok = False
            continue

        print(f"PASS {filename}: errors={len(errors)}, warnings={len(warnings)}")

    if overall_ok:
        print("\nAll fixtures matched expected outcomes.")
        return 0
    else:
        print("\nSome fixtures did not match expected outcomes.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
