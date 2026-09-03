"""test_delegate_config_schema.py — the optional `confluence` block added to
delegate-to-teammate's config schema (delegate-to-teammate progressive-disclosure task 2).

Structural assertions on the schema's own shape always run and need no third-party package.
The three full-document validation checks (Ruling 14) run unconditionally against a small
stdlib-only JSON Schema subset validator defined below, covering exactly the keywords this
schema uses: type (including ["string","null"] unions), required, properties,
additionalProperties (false or a schema for map-like objects), enum, pattern, minLength,
minItems, uniqueItems, propertyNames.pattern, $ref to #/$defs/..., and allOf/if/then with
properties/const. The system python3 on this machine ships no `jsonschema` package (see
rhize-plugins/CLAUDE.md), so `jsonschema` is used only as an optional second, independent
check when importable — never required for these tests to run or pass.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

try:
    import jsonschema
except ImportError:
    jsonschema = None

REPO = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO / "rhize-ops" / "skills" / "delegate-to-teammate" / "references"
    / "delegate.config.schema.json"
)


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class SchemaValidationError(AssertionError):
    """Raised by validate_subset() below on any violation of the stdlib-subset schema."""


def _resolve_ref(ref: str, root: dict) -> dict:
    assert ref.startswith("#/$defs/"), f"unsupported $ref target: {ref}"
    return root["$defs"][ref[len("#/$defs/"):]]


def _type_matches(instance: Any, type_spec: Any) -> bool:
    types = type_spec if isinstance(type_spec, list) else [type_spec]
    checks = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "null": lambda v: v is None,
        "boolean": lambda v: isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    }
    return any(checks[t](instance) for t in types)


def _schema_matches(instance: Any, schema: dict, root: dict) -> bool:
    try:
        validate_subset(instance, schema, root)
        return True
    except SchemaValidationError:
        return False


def validate_subset(instance: Any, schema: dict, root: dict | None = None) -> None:
    """Stdlib-only validator for the keyword subset this schema uses (see module docstring).
    Raises SchemaValidationError on the first violation; returns None on success. Unknown
    keywords (title, description, $schema, $id, format, minProperties, ...) are ignored —
    this schema doesn't rely on them to distinguish a passing document from a failing one."""
    root = schema if root is None else root

    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], root)

    if "type" in schema and not _type_matches(instance, schema["type"]):
        raise SchemaValidationError(f"expected type {schema['type']!r}, got {instance!r}")

    if "const" in schema and instance != schema["const"]:
        raise SchemaValidationError(f"{instance!r} != const {schema['const']!r}")

    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaValidationError(f"{instance!r} not in enum {schema['enum']!r}")

    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            raise SchemaValidationError(f"{instance!r} does not match pattern {schema['pattern']!r}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise SchemaValidationError(f"{instance!r} shorter than minLength {schema['minLength']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise SchemaValidationError(f"array shorter than minItems {schema['minItems']}")
        if schema.get("uniqueItems") and len(instance) != len(
            {json.dumps(item, sort_keys=True) for item in instance}
        ):
            raise SchemaValidationError("array items are not unique")
        if "items" in schema:
            for item in instance:
                validate_subset(item, schema["items"], root)

    if isinstance(instance, dict):
        missing = [key for key in schema.get("required", []) if key not in instance]
        if missing:
            raise SchemaValidationError(f"missing required properties: {missing}")

        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                validate_subset(value, properties[key], root)

        property_names_pattern = schema.get("propertyNames", {}).get("pattern")
        if property_names_pattern:
            for key in instance:
                if not re.match(property_names_pattern, key):
                    raise SchemaValidationError(
                        f"property name {key!r} does not match {property_names_pattern!r}"
                    )

        additional = schema.get("additionalProperties")
        if additional is False:
            extra = [key for key in instance if key not in properties]
            if extra:
                raise SchemaValidationError(f"additional properties not allowed: {extra}")
        elif isinstance(additional, dict):
            for key, value in instance.items():
                if key not in properties:
                    validate_subset(value, additional, root)

    for entry in schema.get("allOf", []):
        if "if" in entry:
            if _schema_matches(instance, entry["if"], root):
                validate_subset(instance, entry["then"], root)
        else:
            validate_subset(instance, entry, root)


def assert_valid(instance: Any, schema: dict) -> None:
    validate_subset(instance, schema)
    if jsonschema is not None:
        jsonschema.validate(instance, schema)


def assert_invalid(instance: Any, schema: dict) -> None:
    with pytest.raises(SchemaValidationError):
        validate_subset(instance, schema)
    if jsonschema is not None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance, schema)


# ---------- structural (always run) ----------

def test_schema_parses_and_confluence_property_shape_is_exact() -> None:
    schema = load_schema()
    assert schema["title"] == "delegate-to-teammate configuration"
    confluence = schema["properties"]["confluence"]
    assert set(confluence["properties"]) == {
        "status", "spaceKey", "spaceId", "parentPageId", "parentPageTitle",
    }
    assert confluence["additionalProperties"] is False


def test_confluence_is_not_in_the_top_level_required_list() -> None:
    schema = load_schema()
    assert "confluence" not in schema["required"]


def test_an_allof_entry_gates_confluence_ready_on_space_and_parent_page() -> None:
    schema = load_schema()
    matches = [
        entry for entry in schema["allOf"]
        if entry.get("if", {}).get("properties", {}).get("confluence", {})
        .get("properties", {}).get("status", {}).get("const") == "ready"
    ]
    assert len(matches) == 1, "expected exactly one allOf entry gated on confluence.status == ready"
    then_confluence = matches[0]["then"]["properties"]["confluence"]
    assert set(then_confluence["required"]) >= {"spaceId", "parentPageId"}
    assert then_confluence["properties"]["spaceId"] == {"type": "string"}
    assert then_confluence["properties"]["parentPageId"] == {"type": "string"}


def test_example_confluence_block_is_ready_with_both_ids() -> None:
    schema = load_schema()
    confluence = schema["examples"][0]["confluence"]
    assert confluence["status"] == "ready"
    assert confluence["spaceId"]
    assert confluence["parentPageId"]


# ---------- full-document validation (Ruling 14: always run, via validate_subset above;
# jsonschema is an optional second check, applied automatically by assert_valid/assert_invalid
# when the package happens to be importable) ----------

def test_example_validates_against_the_schema() -> None:
    schema = load_schema()
    assert_valid(schema["examples"][0], schema)


def test_example_with_ready_confluence_missing_parent_page_id_fails() -> None:
    schema = load_schema()
    example = copy.deepcopy(schema["examples"][0])
    del example["confluence"]["parentPageId"]
    assert_invalid(example, schema)


def test_example_with_confluence_block_removed_still_validates() -> None:
    schema = load_schema()
    example = copy.deepcopy(schema["examples"][0])
    del example["confluence"]
    assert_valid(example, schema)
