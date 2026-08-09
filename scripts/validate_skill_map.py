#!/usr/bin/env python3
"""validate_skill_map.py — validate a skill-map artifact against the schema.

Usage:
  python3 scripts/validate_skill_map.py <path-to-artifact.json>
  python3 scripts/validate_skill_map.py --check-stale

Two layers of checking, same split as tests/skill-map/validate_fixtures.py:
  1. Schema validation — via the `jsonschema` package (Draft 2020-12) if
     installed, otherwise a pure-stdlib structural fallback covering the
     properties this repo's artifacts actually use.
  2. Referential integrity — every edge's `from`/`to` must reference a node
     id present in the same document (JSON Schema can't express this).

`--check-stale` rebuilds the artifact to a temp path via
scripts/build_skill_map.py and diffs it byte-for-byte against the committed
`generated/skill-map.static.json`, exiting nonzero on any drift. This is the
CI/audit hook the plan calls for ("a CI/audit check fails when the committed
artifact is stale vs sources").

Exit code 0 on success, 1 on any failure.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "skill-map.schema.json"
DEFAULT_ARTIFACT = REPO_ROOT / "generated" / "skill-map.static.json"

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
    errors = []

    if doc.get("schemaVersion") != "1.0.0":
        errors.append("schemaVersion must be '1.0.0'")

    nodes = doc.get("nodes")
    if not isinstance(nodes, list):
        errors.append("nodes must be an array")
        nodes = []
    seen_ids = set()
    for i, node in enumerate(nodes):
        if "id" not in node or "kind" not in node:
            errors.append(f"nodes[{i}]: missing required id/kind")
            continue
        if node["id"] in seen_ids:
            errors.append(f"nodes[{i}]: duplicate node id '{node['id']}'")
        seen_ids.add(node["id"])
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


def validate_document(doc, label: str) -> bool:
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema_mod = try_import_jsonschema()
    if jsonschema_mod is not None:
        schema_ok, schema_err = schema_valid_via_jsonschema(jsonschema_mod, schema, doc)
    else:
        schema_ok, schema_err = schema_valid_via_stdlib_fallback(doc)

    if not schema_ok:
        print(f"FAIL {label}: schema invalid: {schema_err}")
        return False

    ref_ok, ref_err = referentially_valid(doc)
    if not ref_ok:
        print(f"FAIL {label}: referential integrity failed: {ref_err}")
        return False

    print(f"PASS {label}: schema_valid=True, referentially_valid=True")
    return True


def check_stale() -> int:
    if not DEFAULT_ARTIFACT.is_file():
        print(f"FAIL --check-stale: committed artifact not found at {DEFAULT_ARTIFACT}")
        return 1
    committed = DEFAULT_ARTIFACT.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "skill-map.static.json"
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "build_skill_map.py")],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("FAIL --check-stale: rebuild failed:")
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return 1
        # build_skill_map.py always writes to generated/skill-map.static.json;
        # copy that fresh output aside before comparing so we never mutate the
        # committed file mid-check even if paths coincide.
        fresh = DEFAULT_ARTIFACT.read_bytes()
        tmp_path.write_bytes(fresh)
    if fresh != committed:
        print(
            "FAIL --check-stale: rebuilt artifact differs from committed "
            f"{DEFAULT_ARTIFACT.relative_to(REPO_ROOT)} — run "
            "'python3 scripts/build_skill_map.py' and commit the result."
        )
        return 1
    print(f"PASS --check-stale: {DEFAULT_ARTIFACT.relative_to(REPO_ROOT)} is up to date.")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args == ["--check-stale"]:
        return check_stale()
    if len(args) != 1 or args[0].startswith("--"):
        print(__doc__)
        return 1
    artifact_path = Path(args[0])
    if not artifact_path.is_file():
        print(f"FAIL: artifact not found at {artifact_path}")
        return 1
    doc = json.loads(artifact_path.read_text())
    ok = validate_document(doc, str(artifact_path))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
