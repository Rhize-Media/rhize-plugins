"""Typed routing can observe authorized choices without dispatch authority."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "rhize-ops/scripts/typed_routing.py"
spec = importlib.util.spec_from_file_location("typed_routing", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def request():
    return {"schema": module.SCHEMA, "kind": "model", "sourceSha256": "a" * 64,
            "taskSignals": ["implementation", "tests"],
            "options": [{"id": "option_a", "hints": ["capable"], "authorized": True},
                        {"id": "option_b", "hints": ["low-cost"], "authorized": True}],
            "incumbentId": "option_a", "userPinned": True}


def fake_call(_url, payload):
    return {"routing": {"model": payload["model"]},
            "answers": {"c0": {"type": "noul", "noul": 0.1},
                        "c1": {"type": "noul", "noul": 0.9}},
            "usage": {"input_tokens": 8, "output_tokens": 2}}, 5.0


def test_user_pin_and_incumbent_survive_higher_other_score():
    result = module.assess(request(), "typed-decisions", "http://127.0.0.1:8000", fake_call)
    assert result["ranked"][0]["optionId"] == "option_b"
    assert result["incumbentId"] == "option_a" and result["userPinned"] is True
    assert result["dispatchOccurred"] is False


def test_unapproved_or_raw_option_rejected():
    case = request()
    case["options"][1]["authorized"] = False
    with pytest.raises(ValueError, match="authorized"):
        module.validate(case)
    case = request()
    case["options"][1]["hints"] = ["send source to provider"]
    with pytest.raises(ValueError):
        module.validate(case)


def test_unavailable_local_model_records_fallback(tmp_path):
    result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--mode", "shadow",
                             "--base-url", "http://127.0.0.1:1", "--receipt-root", str(tmp_path)],
                            input=json.dumps(request()), text=True, capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["status"] == "unavailable" and output["dispatchOccurred"] is False
    assert Path(output["receipt"]).stat().st_mode & 0o777 == 0o600


def test_invalid_answer_never_enters_ranking():
    case = request()
    def malformed(_url, payload):
        value, latency = fake_call(_url, payload)
        value["answers"]["c1"] = {"type": "noul", "noul": "approve"}
        return value, latency
    with pytest.raises((TypeError, ValueError)):
        module.assess(case, "typed-decisions", "http://127.0.0.1:8000", malformed)
