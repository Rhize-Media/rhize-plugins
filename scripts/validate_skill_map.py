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
DEFAULT_INDEXES = REPO_ROOT / "generated" / "skill-map.indexes.json"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_skill_map.py"


def enums_from_schema(schema: dict) -> tuple[set, set, set]:
    """Derive (NODE_KINDS, EDGE_TYPES, EDGE_SOURCES) from the schema itself,
    so the stdlib fallback can never drift from schemas/skill-map.schema.json.
    """
    defs = schema.get("$defs", {})
    node_kinds = set(defs.get("node", {}).get("properties", {}).get("kind", {}).get("enum", []))
    edge_types = set(defs.get("edgeType", {}).get("enum", []))
    edge_sources = set(defs.get("provenanceSource", {}).get("enum", []))
    return node_kinds, edge_types, edge_sources


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


def schema_valid_via_stdlib_fallback(doc, schema):
    node_kinds, edge_types, edge_sources = enums_from_schema(schema)
    errors = []

    expected_version = schema.get("properties", {}).get("schemaVersion", {}).get("const")
    if doc.get("schemaVersion") != expected_version:
        errors.append(f"schemaVersion must be {expected_version!r}")

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
        if node["kind"] not in node_kinds:
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
        if edge.get("type") is not None and edge["type"] not in edge_types:
            errors.append(f"edges[{i}]: invalid type '{edge['type']}'")
        if edge.get("source") is not None and edge["source"] not in edge_sources:
            errors.append(f"edges[{i}]: invalid source '{edge['source']}'")
        if edge.get("type") == "usage-cooccurs" and "usageWeight" not in edge:
            errors.append(f"edges[{i}]: usage-cooccurs edge missing required 'usageWeight'")
        if edge.get("type") == "follows" and "followWeight" not in edge:
            errors.append(f"edges[{i}]: follows edge missing required 'followWeight'")

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


MAX_SUMMARY_LENGTH = 160


def summary_fields_valid(doc):
    """Every node's optional `summary` field (metadata.rhize.summary, carried
    through by scripts/build_skill_map.py for human-facing doc tables — see
    scripts/render_skill_map_docs.py) must be a short, plain sentence: at
    most 160 characters, no backticks. additionalProperties on the node
    schema means jsonschema alone can't enforce this, so it's a standalone
    check here, same shape as referentially_valid() above.
    """
    errors = []
    for i, node in enumerate(doc.get("nodes", [])):
        summary = node.get("summary")
        if summary is None:
            continue
        node_id = node.get("id", f"nodes[{i}]")
        if not isinstance(summary, str):
            errors.append(f"{node_id}: summary must be a string")
            continue
        if len(summary) > MAX_SUMMARY_LENGTH:
            errors.append(
                f"{node_id}: summary is {len(summary)} chars, max {MAX_SUMMARY_LENGTH}"
            )
        if "`" in summary:
            errors.append(f"{node_id}: summary must not contain backticks")
    if errors:
        return False, "; ".join(errors)
    return True, None


def validate_document(doc, label: str) -> bool:
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema_mod = try_import_jsonschema()
    if jsonschema_mod is not None:
        schema_ok, schema_err = schema_valid_via_jsonschema(jsonschema_mod, schema, doc)
    else:
        schema_ok, schema_err = schema_valid_via_stdlib_fallback(doc, schema)

    if not schema_ok:
        print(f"FAIL {label}: schema invalid: {schema_err}")
        return False

    ref_ok, ref_err = referentially_valid(doc)
    if not ref_ok:
        print(f"FAIL {label}: referential integrity failed: {ref_err}")
        return False

    summary_ok, summary_err = summary_fields_valid(doc)
    if not summary_ok:
        print(f"FAIL {label}: summary field invalid: {summary_err}")
        return False

    print(f"PASS {label}: schema_valid=True, referentially_valid=True")
    return True


def check_stale() -> int:
    if not DEFAULT_ARTIFACT.is_file():
        print(f"FAIL --check-stale: committed artifact not found at {DEFAULT_ARTIFACT}")
        return 1
    if not DEFAULT_INDEXES.is_file():
        print(f"FAIL --check-stale: committed indexes not found at {DEFAULT_INDEXES}")
        return 1
    committed = DEFAULT_ARTIFACT.read_bytes()
    committed_indexes = DEFAULT_INDEXES.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "skill-map.static.json"
        tmp_indexes_path = Path(tmp) / "skill-map.indexes.json"
        result = subprocess.run(
            [
                sys.executable, str(BUILD_SCRIPT),
                "--out", str(tmp_path),
                "--indexes-out", str(tmp_indexes_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("FAIL --check-stale: rebuild failed:")
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return 1
        fresh = tmp_path.read_bytes()
        fresh_indexes = tmp_indexes_path.read_bytes()
    if fresh != committed:
        print(
            "FAIL --check-stale: rebuilt artifact differs from committed "
            f"{DEFAULT_ARTIFACT.relative_to(REPO_ROOT)} — run "
            "'python3 scripts/build_skill_map.py' and commit the result."
        )
        return 1
    if fresh_indexes != committed_indexes:
        print(
            "FAIL --check-stale: rebuilt indexes differ from committed "
            f"{DEFAULT_INDEXES.relative_to(REPO_ROOT)} — run "
            "'python3 scripts/build_skill_map.py' and commit the result."
        )
        return 1
    print(
        f"PASS --check-stale: {DEFAULT_ARTIFACT.relative_to(REPO_ROOT)} and "
        f"{DEFAULT_INDEXES.relative_to(REPO_ROOT)} are up to date."
    )
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
