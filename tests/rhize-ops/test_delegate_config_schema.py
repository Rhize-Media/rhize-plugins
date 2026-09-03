"""test_delegate_config_schema.py — the optional `confluence` block added to
delegate-to-teammate's config schema (delegate-to-teammate progressive-disclosure task 2).

Structural assertions on the schema's own shape always run and need no third-party package.
The three full-document validation checks need the `jsonschema` package, which the system
python3 on this machine does not ship (see rhize-plugins/CLAUDE.md) — those are skipped via
`pytest.importorskip`, not silently folded into a passing structural check, when it's absent.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO / "rhize-ops" / "skills" / "delegate-to-teammate" / "references"
    / "delegate.config.schema.json"
)


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


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


# ---------- full-document validation (needs jsonschema) ----------

def test_example_validates_against_the_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = load_schema()
    jsonschema.validate(schema["examples"][0], schema)


def test_example_with_ready_confluence_missing_parent_page_id_fails() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = load_schema()
    example = copy.deepcopy(schema["examples"][0])
    del example["confluence"]["parentPageId"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(example, schema)


def test_example_with_confluence_block_removed_still_validates() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = load_schema()
    example = copy.deepcopy(schema["examples"][0])
    del example["confluence"]
    jsonschema.validate(example, schema)
