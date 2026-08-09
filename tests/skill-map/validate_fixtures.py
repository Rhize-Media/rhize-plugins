#!/usr/bin/env python3
"""Validate the skill-map fixture files against schemas/skill-map.schema.json.

Two layers of checking are applied to every fixture:

1. Schema validation — uses the `jsonschema` package (Draft 2020-12) if it is
   installed; otherwise falls back to a small pure-stdlib structural check
   that covers the properties these fixtures exercise (required top-level
   keys, node `kind` enum, edge `type` enum, edge `source` enum, and the
   skill-node required fields). This fallback is intentionally not a full
   JSON Schema implementation — it exists so this test still runs in
   environments without `jsonschema` installed.
2. Referential integrity — every edge's `from`/`to` must reference a node id
   that exists in the same document. JSON Schema alone can't express "this
   string must match some other array element's id", so this check always
   runs in pure stdlib regardless of which schema layer above ran.

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
SCHEMA_PATH = REPO_ROOT / "schemas" / "skill-map.schema.json"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# fixture filename -> (expect_schema_valid, expect_referentially_valid)
EXPECTATIONS = {
    "valid-map.json": (True, True),
    "dangling-edge.json": (True, False),
    "bad-edge-type.json": (False, None),  # referential check is moot if schema fails
}

NODE_KINDS = {"plugin", "skill", "command", "hook", "tag", "external"}
EDGE_TYPES = {
    "contains",
    "topic-tag",
    "stack-tag",
    "fork-of",
    "supersedes",
    "overlaps-with",
    "depends-on",
    "replaces",
    "usage-cooccurs",
}
EDGE_SOURCES = {"frontmatter", "marketplace", "sources-md", "relations-catalog", "monitor"}


def try_import_jsonschema():
    try:
        import jsonschema  # noqa: F401
        return jsonschema
    except ImportError:
        return None


def schema_valid_via_jsonschema(jsonschema_mod, schema, doc):
    validator_cls = jsonschema_mod.Draft202012Validator
    validator = validator_cls(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        return False, "; ".join(f"{list(e.path)}: {e.message}" for e in errors)
    return True, None


def schema_valid_via_stdlib_fallback(doc):
    """Minimal structural check covering what the fixtures exercise."""
    errors = []

    if doc.get("schemaVersion") != "1.0.0":
        errors.append("schemaVersion must be '1.0.0'")

    nodes = doc.get("nodes")
    if not isinstance(nodes, list):
        errors.append("nodes must be an array")
        nodes = []
    for i, node in enumerate(nodes):
        if "id" not in node or "kind" not in node:
            errors.append(f"nodes[{i}]: missing required id/kind")
            continue
        if node["kind"] not in NODE_KINDS:
            errors.append(f"nodes[{i}]: invalid kind '{node['kind']}'")
        if node["kind"] == "skill":
            for field in ("path", "description", "contentHash"):
                if field not in node:
                    errors.append(f"nodes[{i}]: skill node missing required '{field}'")

    edges = doc.get("edges")
    if not isinstance(edges, list):
        errors.append("edges must be an array")
        edges = []
    for i, edge in enumerate(edges):
        for field in ("from", "to", "type", "source"):
            if field not in edge:
                errors.append(f"edges[{i}]: missing required '{field}'")
        if edge.get("type") is not None and edge["type"] not in EDGE_TYPES:
            errors.append(f"edges[{i}]: invalid type '{edge['type']}'")
        if edge.get("source") is not None and edge["source"] not in EDGE_SOURCES:
            errors.append(f"edges[{i}]: invalid source '{edge['source']}'")
        if edge.get("type") == "usage-cooccurs" and "usageWeight" not in edge:
            errors.append(f"edges[{i}]: usage-cooccurs edge missing required 'usageWeight'")

    if errors:
        return False, "; ".join(errors)
    return True, None


def referentially_valid(doc):
    node_ids = {n["id"] for n in doc.get("nodes", []) if "id" in n}
    errors = []
    for i, edge in enumerate(doc.get("edges", [])):
        for endpoint_field in ("from", "to"):
            endpoint = edge.get(endpoint_field)
            if endpoint is not None and endpoint not in node_ids:
                errors.append(f"edges[{i}].{endpoint_field}: dangling reference '{endpoint}'")
    if errors:
        return False, "; ".join(errors)
    return True, None


def main():
    if not SCHEMA_PATH.exists():
        print(f"FAIL: schema not found at {SCHEMA_PATH}")
        return 1

    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema_mod = try_import_jsonschema()
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
            schema_ok, schema_err = schema_valid_via_jsonschema(jsonschema_mod, schema, doc)
        else:
            schema_ok, schema_err = schema_valid_via_stdlib_fallback(doc)

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

        ref_ok, ref_err = referentially_valid(doc)
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
