import importlib.util
import json
from pathlib import Path

import pytest

from memory_context.core import sha256
from memory_context.model_evaluation import evaluate_answers


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gauntlet = load("run_gauntlet")
# The offline control imports the existing script by name when launched directly.
import sys
sys.modules["run_gauntlet"] = gauntlet
raw_control = load("export_raw_control")
review = load("review_pilot")


def inputs(tmp_path):
    corpus = {"schemaVersion": 1, "name": "fixture", "provenance": "contract fixture", "cases": [{
        "id": "lookup", "question": "What is the policy?", "sources": [{
            "id": "policy", "heading": "Policy", "body": "The review is required."}]}]}
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(corpus))
    grading = {"schemaVersion": 1, "corpusHash": sha256(path.read_bytes()),
               "decisionRule": "Retain all outcomes; human acceptance remains pending.", "cases": [{
                   "id": "lookup", "rubric": {"requiredTerms": ["review"], "requiredSourceIds": ["policy"]},
                   "reviewCriteria": ["The requirement is supported and no approval is invented."]}]}
    grader_path = tmp_path / "grading.json"
    grader_path.write_text(json.dumps(grading))
    return corpus, grading, path, grader_path


def test_separate_tasks_and_grading_bind_exact_bytes_before_execution(tmp_path):
    corpus, grading, path, grader_path = inputs(tmp_path)
    loaded, binding = gauntlet.load_corpus(path, grader_path)
    assert "rubric" in loaded["cases"][0]
    assert binding["decisionRule"] == grading["decisionRule"]
    # No grading material is forwarded by the source-document builder.
    serialized = json.dumps(gauntlet.case_document(loaded["cases"][0]))
    assert "reviewCriteria" not in serialized and grading["decisionRule"] not in serialized
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="bind the exact"):
        gauntlet.load_corpus(path, grader_path)


@pytest.mark.parametrize("field", ["rubric", "answer", "reviewCriteria"])
def test_task_inputs_refuse_grader_leakage(tmp_path, field):
    corpus, grading, path, grader_path = inputs(tmp_path)
    corpus["cases"][0][field] = "grading material"
    path.write_text(json.dumps(corpus))
    grading["corpusHash"] = sha256(path.read_bytes())
    grader_path.write_text(json.dumps(grading))
    with pytest.raises(ValueError, match="must not contain"):
        gauntlet.load_corpus(path, grader_path)


def test_separate_grader_rejects_foreign_sources_and_missing_case(tmp_path):
    _, grading, path, grader_path = inputs(tmp_path)
    grading["cases"][0]["rubric"]["requiredSourceIds"] = ["foreign"]
    grader_path.write_text(json.dumps(grading))
    with pytest.raises(ValueError, match="same case"):
        gauntlet.load_corpus(path, grader_path)
    grading["cases"] = []
    grader_path.write_text(json.dumps(grading))
    with pytest.raises(ValueError, match="match task cases"):
        gauntlet.load_corpus(path, grader_path)


def review_files(tmp_path):
    def executor(*args):
        return {"status": "completed", "actuallyRan": True, "model": "fixture", "answer": "review required", "sourceIds": ["s"], "usage": None}
    comparison = evaluate_answers("codex", "fixture", "What is required?", {"A": "a", "B": "b"}, tmp_path,
                                  rubric={"requiredTerms": ["review"]}, executor=executor, review_dir=tmp_path / "packets")
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"rows": [{"answerComparison": comparison}]}))
    bundle = comparison["reviewBundle"]
    label = next(iter(bundle["armMapping"]))
    template = {"schemaVersion": "memory-pilot-review-v1", "runSha256": sha256(run.read_bytes()),
                "reviewerId": "reviewer-one", "basis": "human", "reviews": [{
                    "packetSha256": bundle["sha256"], "responseId": label, "correctness": True,
                    "materialOmissions": [], "unsupportedClaims": [], "correction": None,
                    "abstentionAppropriate": None, "notes": "Supported."}]}
    first = tmp_path / "first.json"
    first.write_text(json.dumps(template))
    return run, bundle, template, first


def test_review_import_retains_disagreement_unknowns_and_basis(tmp_path):
    run, _, template, first = review_files(tmp_path)
    template["reviewerId"] = "reviewer-two"
    template["basis"] = "model"
    template["reviews"][0].update(correctness=False, materialOmissions=["A qualification was omitted."], correction="Add qualification.")
    second = tmp_path / "second.json"
    second.write_text(json.dumps(template))
    result = review.import_reviews(run, tmp_path / "packets", [first, second])
    assert len(result["records"]) == 2
    assert result["disagreements"][0]["field"] == "correctness"
    assert result["humanAcceptance"] is None
    assert result["reviewerIdentityAuthenticated"] is False
    assert result["records"][0]["abstentionAppropriate"] is None
    assert result["records"][1]["basis"] == "model"


def test_review_import_rejects_duplicate_foreign_or_modified_evidence(tmp_path):
    run, bundle, template, first = review_files(tmp_path)
    with pytest.raises(ValueError, match="duplicate reviewer"):
        review.import_reviews(run, tmp_path / "packets", [first, first])
    template["runSha256"] = "0" * 64
    first.write_text(json.dumps(template))
    with pytest.raises(ValueError, match="another run"):
        review.import_reviews(run, tmp_path / "packets", [first])
    packet_path = tmp_path / "packets" / bundle["file"]
    packet_path.write_text(packet_path.read_text() + "\n")
    with pytest.raises(ValueError, match="packet hash"):
        review.import_reviews(run, tmp_path / "packets", [])


def test_review_packet_is_blind_and_unknown_usage_is_not_zero(tmp_path):
    run, bundle, _, _ = review_files(tmp_path)
    packet = json.loads((tmp_path / "packets" / bundle["file"]).read_text())
    assert "armMapping" not in packet
    assert set(packet["responses"]) == {"response-1", "response-2"}
    arms = json.loads(run.read_text())["rows"][0]["answerComparison"]["arms"]
    assert all(arm["usage"] is None for arm in arms.values())


def test_raw_control_preserves_all_admissible_sources_without_changing_pair(tmp_path):
    _, _, path, grader_path = inputs(tmp_path)
    corpus, _ = gauntlet.load_corpus(path, grader_path)
    document = gauntlet.case_document(corpus["cases"][0])
    document["request"]["totalTokenBudget"] = 1
    foreign = dict(document["adapters"][0]["candidates"][0], sourceId="foreign", tenant="other", content="do not expose")
    document["adapters"][0]["candidates"].append(foreign)
    result = raw_control.prepare_raw_control(document)
    assert result["status"] == "prepared"
    assert result["selectedSourceHashes"] == [sha256("policy")]
    assert "review is required" in result["context"]
    assert "do not expose" not in result["context"]
    assert result["excluded"] == {"scope_denied": 1}
    assert result["modelUsage"] is None and result["refreshCost"] is None
    assert result["actuallyRanModel"] is False


def test_raw_control_refuses_large_input_without_truncating(tmp_path):
    _, _, path, grader_path = inputs(tmp_path)
    corpus, _ = gauntlet.load_corpus(path, grader_path)
    document = gauntlet.case_document(corpus["cases"][0])
    document["adapters"][0]["candidates"][0]["content"] = "source " * 12_000
    result = raw_control.prepare_raw_control(document)
    assert result["status"] == "unavailable"
    assert result["reason"] == "raw_source_input_too_large"
    assert "context" not in result
    assert result["nativeInputBytes"] > 64_000
