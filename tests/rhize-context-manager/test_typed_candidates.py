"""Contract checks for the local, non-authoritative candidate scorer."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "rhize-context-manager/scripts/context_experiments/typed_candidates.py"
sys.path.insert(0, str(SCRIPT.parents[1]))
spec = importlib.util.spec_from_file_location("typed_candidates", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def envelope(capability="skill_workflow"):
    return {
        "schema": module.SCHEMA,
        "capability": capability,
        "sourceSha256": "a" * 64,
        "taskSignals": ["python", "tests"],
        "candidates": [
            {"id": "first", "hints": ["python"], "protected": capability == "context_retention"},
            {"id": "second", "hints": ["tests"], "protected": False},
        ],
        "incumbentIds": ["first"],
    }


def fake_call(_url, request):
    return {
        "routing": {"model": request["model"]},
        "answers": {"c0": {"type": "noul", "noul": 0.2}, "c1": {"type": "noul", "noul": 0.8}},
        "usage": {"input_tokens": 20, "output_tokens": 3},
    }, 2.5


def test_rank_is_observational_and_records_arm_a():
    result = module.assess(envelope(), "typed-decisions", "http://127.0.0.1:8000", fake_call)
    assert result["status"] == "shadow"
    assert result["ranking"][0]["candidateId"] == "second"
    assert result["incumbentIds"] == ["first"]
    assert result["incumbentAltered"] is False
    assert result["usage"]["input_tokens"] == 20


def test_protected_retention_cannot_be_missing_from_incumbent():
    case = envelope("context_retention")
    case["incumbentIds"] = ["second"]
    with pytest.raises(ValueError, match="protected context"):
        module.validate(case)


def test_rejects_raw_text_or_foreign_candidate():
    case = envelope("graph_memory")
    case["taskSignals"] = ["private client request"]
    with pytest.raises(ValueError, match="task signals"):
        module.validate(case)
    case = envelope()
    case["incumbentIds"] = ["unknown"]
    with pytest.raises(ValueError, match="incumbent"):
        module.validate(case)


def test_cli_unavailable_writes_private_fallback(tmp_path):
    receipt_root = tmp_path / "receipts"
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--mode", "shadow", "--base-url", "http://127.0.0.1:1",
         "--receipt-root", str(receipt_root)],
        input=json.dumps(envelope()), text=True, capture_output=True, timeout=5,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["status"] == "unavailable"
    assert output["incumbentAltered"] is False
    path = Path(output["receipt"])
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text())["status"] == "unavailable"


def test_receipt_storage_failure_remains_an_incumbent_fallback(tmp_path):
    occupied = tmp_path / "occupied"
    occupied.write_text("not a directory")
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--mode", "shadow", "--base-url", "http://127.0.0.1:1",
         "--receipt-root", str(occupied)],
        input=json.dumps(envelope()), text=True, capture_output=True, timeout=5,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["status"] == "unavailable"
    assert output["reasonCode"] == "receipt_unavailable"
    assert output["receipt"] is None and output["incumbentAltered"] is False


def test_graph_query_scores_only_returned_metadata_and_preserves_results(monkeypatch, tmp_path):
    from argparse import Namespace
    from graph_memory import cli

    captured = {}
    def fake_assess(state, model, endpoint):
        captured.update(state)
        assert model == "typed-decisions"
        assert endpoint == "http://127.0.0.1:8000"
        return {"status": "shadow", "variant": "B_local_laya", "incumbentAltered": False}

    monkeypatch.setattr(cli, "assess_candidates", fake_assess)
    result = {"status": "ok", "operation": "query_context", "results": [
        {"governedId": "private-graph-id", "recordType": "Artifact", "subtype": "Code File",
         "trust": "high", "properties": {"body": "must remain local"}}
    ]}
    before = json.dumps(result, sort_keys=True)
    args = Namespace(typed_signal=["python"], typed_model="typed-decisions",
                     typed_base_url="http://127.0.0.1:8000", typed_receipt_root=tmp_path)
    shadow = cli._score_authorized_graph_results(args, result, {"compilationId": "source"})
    assert json.dumps(result, sort_keys=True) == before
    assert shadow["status"] == "shadow" and shadow["resultsAltered"] is False
    assert captured["incumbentIds"] == [captured["candidates"][0]["id"]]
    assert "must remain local" not in json.dumps(captured)
    assert Path(shadow["receipt"]).stat().st_mode & 0o777 == 0o600


def test_retention_cli_rejects_changed_source_before_model_call(tmp_path):
    evidence = tmp_path / "anchored-summary.json"
    evidence.write_text('{"current":true}')
    case = envelope("context_retention")
    case["sourceSha256"] = "b" * 64
    result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--mode", "shadow",
                             "--evidence", str(evidence), "--base-url", "http://127.0.0.1:1",
                             "--receipt-root", str(tmp_path / "receipts")],
                            input=json.dumps(case), text=True, capture_output=True, timeout=5)
    output = json.loads(result.stdout)
    assert result.returncode == 0
    assert output["status"] == "unavailable" and output["reasonCode"] == "ValueError"
    assert output["incumbentAltered"] is False
