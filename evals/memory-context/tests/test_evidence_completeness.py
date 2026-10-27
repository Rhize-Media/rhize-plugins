import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from memory_context.core import MemoryContextAssembler
from memory_context.evidence_completeness import diagnose


NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[3]


def document():
    return {"schemaVersion": 1, "request": {"tenant": "rhize", "project": "test", "query": "policy"},
            "adapters": [{"name": "files", "memoryType": "semantic", "status": "available", "candidates": [{
                "sourceSystem": "canonical-file", "sourceId": "policy", "sourceRevision": "v1",
                "tenant": "rhize", "project": "test", "content": "The policy is evidence.", "relevance": 1}]}]}


def requirements(source="policy", revision="v1", adapter="files"):
    return {"schemaVersion": 1, "requirements": [{"id": "required-policy", "adapter": adapter,
                                                 "sourceId": source, "sourceRevision": revision}]}


def report(doc, required=None):
    manifest, _ = MemoryContextAssembler().assemble(doc, NOW)
    return diagnose(doc, manifest, required or requirements())


def test_declared_exact_source_is_advisory_and_missing_revision_does_not_pass():
    complete = report(document())
    assert complete["coverage"] == "complete"
    assert complete["advisory"] is True
    assert complete["semanticCompleteness"] is None
    assert report(document(), requirements(revision="v2"))["requirements"][0]["status"] == "missing"
    assert "required-policy" not in json.dumps(complete)
    empty = report(document(), {"schemaVersion": 1, "requirements": []})
    assert empty["coverage"] == "unknown"


@pytest.mark.parametrize("status,expected", [("empty", "empty"), ("unavailable", "unavailable"),
                                             ("unauthorized", "unavailable"), ("partial", "unknown")])
def test_empty_unavailable_and_partial_are_distinct(status, expected):
    doc = document()
    doc["adapters"][0].update(status=status, candidates=[])
    assert report(doc)["requirements"][0]["status"] == expected
    assert report(document(), requirements(adapter="absent"))["requirements"][0]["reason"] == "adapter_not_supplied"


def test_budget_exclusion_is_explicit_and_scope_denial_does_not_disclose_record():
    doc = document()
    doc["request"]["totalTokenBudget"] = 1
    result = report(doc)["requirements"][0]
    assert (result["status"], result["reason"]) == ("excluded", "selection_budget")
    denied = document()
    denied["adapters"][0]["candidates"][0].update(tenant="other", content="private secret material")
    result = report(denied)
    assert result["requirements"][0]["status"] == "missing"
    assert "private secret" not in json.dumps(result)


def test_report_rejects_foreign_manifest_and_malformed_requirements():
    doc = document()
    manifest, _ = MemoryContextAssembler().assemble(doc, NOW)
    changed = copy.deepcopy(doc)
    changed["adapters"][0]["candidates"][0]["content"] = "changed"
    with pytest.raises(ValueError, match="exact source"):
        diagnose(changed, manifest, requirements())
    for value in ({}, {"schemaVersion": 1, "requirements": [{}]},
                  {"schemaVersion": 1, "requirements": requirements()["requirements"] * 2}):
        with pytest.raises(ValueError):
            diagnose(doc, manifest, value)


def test_cli_exposes_diagnostics_without_changing_pack(tmp_path):
    source, checklist = tmp_path / "request.json", tmp_path / "requirements.json"
    source.write_text(json.dumps(document()))
    checklist.write_text(json.dumps(requirements()))
    command = [sys.executable, str(ROOT / "rhize-context-manager/scripts/memory_context/runner.py"),
               "preview", "--input", str(source), "--data-dir", str(tmp_path / "store"), "--now", NOW.isoformat()]
    plain = json.loads(subprocess.check_output(command))
    checked = json.loads(subprocess.check_output(command + ["--requirements", str(checklist)]))
    assert plain["packId"] == checked["packId"]
    assert "evidenceCompleteness" not in plain
    assert checked["evidenceCompleteness"]["coverage"] == "complete"
