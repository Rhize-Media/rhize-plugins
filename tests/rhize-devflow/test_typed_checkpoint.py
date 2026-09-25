import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "rhize-devflow/scripts/typed_checkpoint.py"
spec = importlib.util.spec_from_file_location("typed_checkpoint_test", SCRIPT)
checkpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoint)


def state(**overrides):
    value = {"signals": ["test_passed"], "required_checks_passed": True,
             "independent_review_passed": True, "approval_satisfied": True}
    value.update(overrides)
    return value


def test_finish_candidate_requires_all_hard_gates():
    answers = {"ready_to_finish": {"noul": 0.99},
               "needs_verification": {"noul": 0.01}, "needs_human": {"noul": 0.01}}
    assert checkpoint.directive("completion", answers, state()) == "finish_candidate"
    assert checkpoint.directive("completion", answers, state(approval_satisfied=False)) == "continue"


def test_stage_specific_shadow_receipt_has_no_raw_state():
    observed = state(signals=["test_failed", "review_pending"])
    def call(base, request):
        assert request["state"]["checkpoint"] == "check"
        assert set(request["questions"]) == set(checkpoint.CHECKS["check"])
        return {"answers": {name: {"type": "noul", "noul": 0.9 if name == "tests_sufficient" else 0.1}
                            for name in request["questions"]},
                "routing": {"model": "typed-decisions"},
                "usage": {"input_tokens": 8, "output_tokens": 3}}, 4.0
    receipt = checkpoint.assess("check", observed, "a" * 64, "typed-decisions",
                                "http://127.0.0.1:8000", call)
    assert receipt["status"] == "shadow" and receipt["gateChanged"] is False
    assert receipt["variant"] == "B_local_laya" and receipt["candidateDirective"] == "continue"
    assert "signals" not in receipt and receipt["stateSha256"] == checkpoint.digest(observed)


@pytest.mark.parametrize("invalid", [
    {"signals": ["test_passed"], "required_checks_passed": True, "independent_review_passed": True},
    state(signals=["unknown"]),
    state(required_checks_passed="true"),
])
def test_unbounded_or_invalid_state_rejected(invalid):
    with pytest.raises(ValueError):
        checkpoint.validate_state(invalid)


def test_checkpoint_result_cannot_grant_permission():
    answers = {"needs_human": {"noul": 0.9},
               "ready_to_finish": {"noul": 0.99}, "needs_verification": {"noul": 0.01}}
    assert checkpoint.directive("completion", answers, state()) == "escalate"


def test_cli_binds_receipt_to_evidence_bytes(monkeypatch, tmp_path, capsys):
    evidence = tmp_path / "current-evidence.json"
    evidence.write_bytes(b'{"passed":true}')
    observed = {}
    def assess(stage, state_value, source_hash, model, base_url):
        observed["hash"] = source_hash
        return {"status": "shadow"}
    monkeypatch.setattr(checkpoint, "assess", assess)
    monkeypatch.setattr(sys, "argv", ["typed_checkpoint.py", "--stage", "check",
                                    "--evidence", str(evidence), "--mode", "shadow"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(state())))
    assert checkpoint.main() == 0
    assert observed["hash"] == hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert json.loads(capsys.readouterr().out)["status"] == "shadow"
