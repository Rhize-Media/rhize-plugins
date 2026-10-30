"""Safety/diagnostic contracts use synthetic answers, never a model service."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("measurement_research", ROOT / "evals/typed-decision/research.py")
research = importlib.util.module_from_spec(spec)
spec.loader.exec_module(research)


def case(label="verify", *, kind="choice", critical=True):
    question = {"type": kind, "instructions": "Is verification required?"}
    if kind == "choice":
        question["criteria"] = {"verify": "Verify", "continue": "Continue"}
    return {"case_id": "one", "group_id": "group", "decision_type": "verification",
            "stratum": "critical_safety" if critical else "routine", "label_source": "fixture",
            "adjudicated": True, "state": "Synthetic request", "questions": {"q": question},
            "labels": {"q": label}}


def provider(kind="choice", probability=0.6):
    answer = ({"type": kind, "choice": "verify", "answer_confidence": probability,
               "probabilities": {"verify": probability, "continue": 1 - probability}}
              if kind == "choice" else {"type": kind, "noul": probability})
    return lambda _: ({"answers": {"q": answer}, "usage": {"input_tokens": 1, "output_tokens": 0}}, 1.0)


@pytest.mark.parametrize("kind,label", [("choice", "verify"), ("noul", True)])
def test_critical_abstentions_are_missed_decisions_not_reported_unsafe_actions(kind, label):
    result = research.evaluate([case(label, kind=kind)],
                               {"id": "threshold", "model": "fixture", "abstain_below": .9}, provider(kind))
    assert result["critical_misses"] == 1
    assert result["critical_abstentions"] == 1
    assert result["critical_wrong_answers"] == 0
    assert result["unsafe_actions"] is None
    assert result["metrics_schema"] == "rhize-typed-research-metrics-v2"


def test_critical_noul_false_positive_is_visible_separately_from_false_negative():
    result = research.evaluate([case(False, kind="noul")], {"id": "base", "model": "fixture"}, provider("noul", .99))
    assert result["critical_misses"] == result["critical_wrong_answers"] == 1
    assert result["critical_false_negatives"] == 0
    other = research.evaluate([case(True, kind="noul")], {"id": "base", "model": "fixture"}, provider("noul", .01))
    assert other["critical_false_negatives"] == 1


def test_noncritical_abstention_does_not_inflate_critical_misses():
    result = research.evaluate([case(critical=False)],
                               {"id": "threshold", "model": "fixture", "abstain_below": .9}, provider())
    assert result["critical_misses"] == 0 and result["abstention_rate"] == 1


def test_diagnostics_disclose_class_support_and_do_not_claim_calibration():
    rows = [case(), {**case("continue"), "case_id": "two"}]
    result = research.evaluate(rows, {"id": "base", "model": "fixture"}, provider())
    diag = result["diagnostics"][0]
    assert diag["n"] == 2 and diag["independent_groups"] == 1
    assert diag["candidate_count"] == 2 and diag["balanced_accuracy"] == .5
    assert diag["label_bases"] == {"unspecified": 2} and diag["calibrated"] is False
    assert diag["ece"] == pytest.approx(.1)
    assert diag["risk_coverage"][-1]["error_rate"] is None


def test_tuning_baseline_is_independent_of_validation_labels():
    baseline = research.tuning_majority([case(), {**case(), "case_id": "two"}])
    result = research.evaluate([case("continue")], {"id": "base", "model": "fixture"}, provider(), baseline=baseline)
    assert result["majority_baseline"]["accuracy"] == 0
    assert result["majority_baseline"]["tuning_sha256"] == baseline["tuning_sha256"]


def test_current_holdout_requires_a_keep_with_current_metric_semantics():
    legacy = [{"dataset_sha256": "d", "candidate_sha256": "c", "seed_sha256": "s", "status": "keep"}]
    with pytest.raises(ValueError, match="recorded development keep"):
        research.check_holdout_authority(legacy, "d", "s", "c", research.METRICS_SCHEMA)
    legacy[0]["metrics_schema"] = research.METRICS_SCHEMA
    research.check_holdout_authority(legacy, "d", "s", "c", research.METRICS_SCHEMA)
    legacy.append({"dataset_sha256": "d", "status": "holdout"})
    with pytest.raises(ValueError, match="already used"):
        research.check_holdout_authority(legacy, "d", "s", "c", research.METRICS_SCHEMA)


def test_search_does_not_mix_legacy_rank_or_block_current_metric_attempt(tmp_path, monkeypatch):
    rows = [{**case(critical=False), 'case_id': str(i), 'group_id': f'g{i}'} for i in range(24)]
    split = tmp_path / 'split'
    manifest = research.prepare_corpus(rows, 'fixture', split)
    candidate = {'id': 'baseline', 'model': 'fixture'}
    candidates = tmp_path / 'candidates.json'
    candidates.write_text(json.dumps([candidate]))
    ledger = tmp_path / 'ledger.jsonl'
    old = {'dataset_sha256': manifest['corpus_sha256'], 'seed_sha256': manifest['seed_sha256'],
           'candidate_sha256': research.digest(candidate), 'status': 'keep',
           'validation': {'critical_misses': 0, 'accuracy': 1, 'abstention_rate': 0}}
    ledger.write_text(json.dumps(old) + '\n')
    monkeypatch.setattr(sys, 'argv', ['research', '--phase', 'search', '--manifest', str(split / 'manifest.json'),
                                    '--train', str(split / 'train.jsonl'), '--validation', str(split / 'validation.jsonl'),
                                    '--candidates', str(candidates), '--ledger', str(ledger)])
    def local_call(_url, request, *, admission_wait_ms):
        assert admission_wait_ms == 2000
        return provider()(request)
    monkeypatch.setattr(research, 'local_call', local_call)
    assert research.main() == 0
    entries = research.read_ledger(ledger)
    assert entries[0] == old and entries[1]['status'] == 'keep'
    assert entries[1]['metrics_schema'] == research.METRICS_SCHEMA
    assert entries[1]['validation']['majority_baseline']['accuracy'] == 1


@pytest.mark.parametrize('usage', [True, -1, '0', None])
def test_invalid_provider_usage_is_missing_not_zero_or_negative_credit(usage):
    def call(request):
        reply, latency = provider()(request)
        reply['usage']['input_tokens'] = usage
        return reply, latency
    result = research.evaluate([case()], {'id': 'base', 'model': 'fixture'}, call)
    assert result['usage']['input_tokens'] is None
