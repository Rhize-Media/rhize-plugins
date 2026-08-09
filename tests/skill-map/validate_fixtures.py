#!/usr/bin/env python3
"""Validate the skill-map fixture files against schemas/skill-map.schema.json.

Delegates the actual schema/referential checks to scripts/validate_skill_map.py
(loaded via tests/skill-map/_util.load_module, the same pattern
tests/skill-map/test_build.py uses) rather than maintaining a second copy of
the same validation logic. This file only owns the fixture expectations and
the pass/fail loop.

Fixtures and expected outcomes:
  - valid-map.json      -> passes both layers
  - dangling-edge.json  -> passes schema validation, fails referential integrity
  - bad-edge-type.json  -> fails schema validation (invalid edge `type` enum value)

Exit code 0 if every fixture matches its expected outcome, 1 otherwise.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "validate_skill_map.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

# fixture filename -> (expect_schema_valid, expect_referentially_valid)
EXPECTATIONS = {
    "valid-map.json": (True, True),
    "dangling-edge.json": (True, False),
    "bad-edge-type.json": (False, None),  # referential check is moot if schema fails
}


def main():
    validate_mod = load_module(VALIDATE_SCRIPT, "validate_skill_map")
    if not validate_mod.SCHEMA_PATH.exists():
        print(f"FAIL: schema not found at {validate_mod.SCHEMA_PATH}")
        return 1

    schema = json.loads(validate_mod.SCHEMA_PATH.read_text())
    jsonschema_mod = validate_mod.try_import_jsonschema()
    if jsonschema_mod is not None:
        print(f"Using jsonschema {jsonschema_mod.__version__} (Draft 2020-12)")
    else:
        print("jsonschema not installed — using pure-stdlib structural fallback")

    overall_ok = True

    for filename, (expect_schema_valid, expect_ref_valid) in EXPECTATIONS.items():
        path = FIXTURES_DIR / filename
        if not path.exists():
            print(f"FAIL {filename}: fixture file missing")
            overall_ok = False
            continue

        doc = json.loads(path.read_text())

        if jsonschema_mod is not None:
            schema_ok, schema_err = validate_mod.schema_valid_via_jsonschema(
                jsonschema_mod, schema, doc
            )
        else:
            schema_ok, schema_err = validate_mod.schema_valid_via_stdlib_fallback(doc, schema)

        if schema_ok != expect_schema_valid:
            print(
                f"FAIL {filename}: expected schema_valid={expect_schema_valid}, "
                f"got {schema_ok} ({schema_err})"
            )
            overall_ok = False
            continue

        if expect_ref_valid is None:
            print(f"PASS {filename}: schema_valid={schema_ok} (as expected; skipped ref check)")
            continue

        ref_ok, ref_err = validate_mod.referentially_valid(doc)
        if ref_ok != expect_ref_valid:
            print(
                f"FAIL {filename}: expected referentially_valid={expect_ref_valid}, "
                f"got {ref_ok} ({ref_err})"
            )
            overall_ok = False
            continue

        print(f"PASS {filename}: schema_valid={schema_ok}, referentially_valid={ref_ok}")

    if overall_ok:
        print("\nAll fixtures matched expected outcomes.")
        return 0
    else:
        print("\nSome fixtures did not match expected outcomes.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
