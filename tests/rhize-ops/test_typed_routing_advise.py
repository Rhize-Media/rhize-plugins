"""Advise mode for typed routing: earned-mode matrix, pin, holdback, unavailable, unauthorized ids, outcome."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "rhize-ops/scripts"


def _load(name):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


routing = _load("typed_routing")
advice = _load("typed_advice")


def envelope(task_id="task-a", pinned=False, **extra):
    return {"schema": routing.SCHEMA, "kind": "model", "sourceSha256": "a" * 64,
            "taskSignals": ["implementation", "tests"], "taskId": task_id,
            "options": [{"id": "option_a", "hints": ["capable"], "authorized": True,
                         "description": "Strong model for multi-file changes"},
                        {"id": "option_b", "hints": ["low-cost"], "authorized": True}],
            "incumbentId": "option_a", "userPinned": pinned, **extra}


def state(store, mode="advise", **overrides):
    entry = {"mode": mode, "policySha256": advice.policy_sha256("model-routing", routing.QUESTION, routing.POLICY),
             "instrumentSha256": advice.INSTRUMENT_SHA256, **overrides}
    (store / "registry-state.json").write_text(json.dumps({"decisions": {"model-routing": entry}}))


def laya(choice="option_b", status="ok"):
    def call(request, files, question, candidates, **kwargs):
        ids = [c["id"] for c in candidates]
        return {"status": status, "choice": choice if status == "ok" else None,
                "probabilities": {i: (0.8 if i == choice else 0.2) for i in ids} if status == "ok" else None,
                "latencyMs": 1.0}
    return call


def task_id(held):
    for n in range(500):
        candidate = f"task-{n}"
        if advice.holdback("model-routing", candidate) is held:
            return candidate
    raise AssertionError("no key found")


def run(tmp_path, value=None, call=None, **kwargs):
    return routing.advise_routing(value or envelope(**kwargs), "http://127.0.0.1:1", store=tmp_path, call=call)


def test_earned_advise_shows_recommendation(tmp_path):
    state(tmp_path)
    out = run(tmp_path, call=laya(), task_id=task_id(False))
    assert out["mode"] == "advise" and out["recommendation"]["id"] == "option_b"
    assert "Laya advises the model `option_b`" in out["advice"] and out["variant"] == "B_laya_advice"
    assert out["incumbentId"] == "option_a" and out["dispatchOccurred"] is False


@pytest.mark.parametrize("mode", ["shadow", "off"])
def test_non_advise_modes_show_nothing(tmp_path, mode):
    state(tmp_path, mode=mode)
    out = run(tmp_path, call=laya(), task_id=task_id(False))
    assert out["recommendation"] is None and out["advice"] == "" and out["mode"] == mode


def test_missing_corrupt_or_stale_binding_reads_shadow(tmp_path):
    assert run(tmp_path, call=laya(), task_id=task_id(False))["mode"] == "shadow"
    (tmp_path / "registry-state.json").write_text("{not json")
    assert run(tmp_path, call=laya(), task_id=task_id(False))["mode"] == "shadow"
    state(tmp_path, policySha256="f" * 64)
    out = run(tmp_path, call=laya(), task_id=task_id(False))
    assert out["mode"] == "shadow" and out["recommendation"] is None


def test_holdback_records_but_never_advises(tmp_path):
    state(tmp_path)
    out = run(tmp_path, call=laya(), task_id=task_id(True))
    assert out["holdback"] is True and out["recommendation"] is None and out["advice"] == ""
    record = advice.load("model-routing", out["decisionId"], store=tmp_path)
    assert record["arm"] == "holdback" and record["laya"]["choice"] == "option_b"


def test_user_pin_skips_laya_and_records_nothing(tmp_path):
    state(tmp_path)
    def boom(*a, **k):
        raise AssertionError("Laya must not be called for a pinned task")
    out = run(tmp_path, call=boom, pinned=True)
    assert out["mode"] == "pinned" and out["recommendation"] is None and out["status"] == "pinned"
    assert not (tmp_path / "model-routing").exists()


def test_unavailable_laya_yields_incumbent(tmp_path):
    state(tmp_path)
    out = run(tmp_path, call=laya(status="unavailable"), task_id=task_id(False))
    assert out["recommendation"] is None and out["variant"] == "A_incumbent"


def test_unauthorized_or_unknown_option_ids_rejected(tmp_path):
    state(tmp_path)
    bad = envelope()
    bad["options"][1]["authorized"] = False
    with pytest.raises(ValueError):
        run(tmp_path, bad, call=laya())
    # Laya naming an id outside the authorized set never becomes a recommendation.
    out = run(tmp_path, call=laya(choice="option_zzz"), task_id=task_id(False))
    assert out["recommendation"] is None
    with pytest.raises(ValueError):
        run(tmp_path, envelope(extra_key=1), call=laya())


def test_single_option_cannot_be_advised(tmp_path):
    state(tmp_path)
    single = envelope()
    single["options"] = single["options"][:1]
    with pytest.raises(ValueError):
        run(tmp_path, single, call=laya())


def test_key_falls_back_to_envelope_digest(tmp_path):
    state(tmp_path)
    value = envelope()
    del value["taskId"]
    first = run(tmp_path, value, call=laya())
    assert first["decisionId"] == run(tmp_path, value, call=laya())["decisionId"]


def test_outcome_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("RHIZE_TYPED_DECISIONS_ROOT", str(tmp_path))
    state(tmp_path)
    out = run(tmp_path, call=laya(), task_id=task_id(False))
    def outcome(chosen):
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / "typed_routing.py"), "outcome",
                               "--decision-id", out["decisionId"], "--chosen", chosen],
                              capture_output=True, text=True, timeout=10,
                              env={**__import__("os").environ, "RHIZE_TYPED_DECISIONS_ROOT": str(tmp_path)})
    assert outcome("option_zzz").returncode == 1  # not a candidate
    done = outcome("option_a")
    assert done.returncode == 0 and json.loads(done.stdout) == {"recorded": True}
    assert outcome("option_b").returncode == 1  # first write wins
    stored = advice.load("model-routing", out["decisionId"], kind="outcome", store=tmp_path)
    assert stored["chosen"] == "option_a" and stored["followed"] is False


def test_cli_advise_unreachable_laya_is_incumbent(tmp_path):
    state(tmp_path)
    result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "typed_routing.py"), "--mode", "advise",
                             "--base-url", "http://127.0.0.1:1"], input=json.dumps(envelope()), text=True,
                            capture_output=True, timeout=15,
                            env={**__import__("os").environ, "RHIZE_TYPED_DECISIONS_ROOT": str(tmp_path)})
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["recommendation"] is None and out["dispatchOccurred"] is False
    bad = subprocess.run([sys.executable, "-B", str(SCRIPTS / "typed_routing.py"), "--mode", "advise"],
                         input="{}", text=True, capture_output=True, timeout=10)
    assert json.loads(bad.stdout)["status"] == "unavailable"
