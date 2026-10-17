"""Dev Flow advise mode: registry-gated, advisory only, never alters a verdict or gate."""
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "rhize-devflow/scripts"
sys.path.insert(0, str(SCRIPTS))
import typed_advice  # noqa: E402
import typed_checkpoint as checkpoint  # noqa: E402
import typed_selection as selection  # noqa: E402

CP = "devflow-next-action"
SEL = "browser-qa-selection"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("RHIZE_TYPED_DECISIONS_ROOT", str(tmp_path / "store"))
    return tmp_path / "store"


@pytest.fixture
def laya(monkeypatch):
    calls = []

    def fake(request, files, question, candidates, **_):
        calls.append({"request": request, "files": files})
        ids = [c["id"] for c in candidates]
        pick = fake.pick if fake.pick in ids else ids[0]
        return {"status": "ok", "choice": pick, "probabilities": {i: (0.8 if i == pick else 0.2 / (len(ids) - 1))
                                                                  for i in ids}, "latencyMs": 1.0}
    fake.pick, fake.calls = "verify", calls
    monkeypatch.setattr(typed_advice, "choice", fake)
    return fake


def runtime(store):
    store.mkdir(parents=True, exist_ok=True)
    store.chmod(0o700)
    (store / "laya-runtime.json").write_text(json.dumps({"revision": "rev-advice-1"}))
    (store / "laya-runtime.json").chmod(0o600)


def earn(store, decision, question, policy):
    store.mkdir(parents=True, exist_ok=True)
    store.chmod(0o700)
    (store / "registry-state.json").write_text(json.dumps({"schemaVersion": 1, "revision": 1, "decisions": {decision: {
        "mode": "advise", "pinned": False, "policySha256": typed_advice.policy_sha256(decision, question, policy),
        "instrumentSha256": typed_advice.INSTRUMENT_SHA256, "layaRevision": "rev-advice-1"}}}))
    (store / "registry-state.json").chmod(0o600)
    runtime(store)


def state(**kw):
    value = {"signals": ["test_passed"], "required_checks_passed": True,
             "independent_review_passed": True, "approval_satisfied": True}
    value.update(kw)
    return value


def run_checkpoint(monkeypatch, capsys, tmp_path, observed, mode="advise", evidence=b'{"e":1}', extra=()):
    ev = tmp_path / "evidence.json"
    ev.write_bytes(evidence)
    monkeypatch.setattr(sys, "argv", ["typed_checkpoint.py", "--stage", "check", "--evidence", str(ev),
                                      "--mode", mode, *extra])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(observed)))
    assert checkpoint.main() == 0
    return json.loads(capsys.readouterr().out)


# ----------------------------------------------------------------- mode matrix

def test_disabled_makes_no_call(store, laya, monkeypatch, capsys, tmp_path):
    out = run_checkpoint(monkeypatch, capsys, tmp_path, state(), mode="disabled")
    assert out["status"] == "disabled" and laya.calls == []


def test_shadow_registry_records_but_shows_nothing(store, laya, monkeypatch, capsys, tmp_path):
    out = run_checkpoint(monkeypatch, capsys, tmp_path, state())
    assert out["mode"] == "shadow" and out["recommendation"] is None and out["advice"] == ""
    assert len(laya.calls) == 1
    assert typed_advice.load(CP, out["decisionId"], store=store)["laya"]["choice"] == "verify"


def test_earned_advise_shows_recommendation(store, laya, monkeypatch, capsys, tmp_path):
    earn(store, CP, checkpoint.QUESTION, checkpoint.POLICY)
    # find an evidence payload outside the holdback arm
    n = next(i for i in range(200) if not typed_advice.holdback(
        CP, hashlib.sha256(b'{"e":%d}' % i).hexdigest() + ":check"))
    out = run_checkpoint(monkeypatch, capsys, tmp_path, state(), evidence=b'{"e":%d}' % n)
    assert out["mode"] == "advise" and out["holdback"] is False
    assert out["recommendation"]["id"] == "verify"
    assert "Laya advises next action `verify`" in out["advice"] and out["decisionId"] in out["advice"]


def test_holdback_asks_but_never_shows(store, laya, monkeypatch, capsys, tmp_path):
    earn(store, CP, checkpoint.QUESTION, checkpoint.POLICY)
    n = next(i for i in range(200) if typed_advice.holdback(
        CP, hashlib.sha256(b'{"e":%d}' % i).hexdigest() + ":check"))
    out = run_checkpoint(monkeypatch, capsys, tmp_path, state(), evidence=b'{"e":%d}' % n)
    assert out["mode"] == "advise" and out["holdback"] is True
    assert out["recommendation"] is None and out["advice"] == "" and len(laya.calls) == 1
    assert typed_advice.load(CP, out["decisionId"], store=store)["arm"] == "holdback"


def test_stale_binding_reads_as_shadow(store, laya, monkeypatch, capsys, tmp_path):
    earn(store, CP, "a different question", checkpoint.POLICY)
    out = run_checkpoint(monkeypatch, capsys, tmp_path, state())
    assert out["mode"] == "shadow" and out["recommendation"] is None


def test_laya_unavailable_gives_no_advice(store, monkeypatch, capsys, tmp_path):
    earn(store, CP, checkpoint.QUESTION, checkpoint.POLICY)
    monkeypatch.setattr(typed_advice, "choice", lambda *a, **k: {"status": "unavailable", "choice": None,
                                                                 "probabilities": None, "latencyMs": 0.0})
    out = run_checkpoint(monkeypatch, capsys, tmp_path, state())
    assert out["recommendation"] is None and out["advice"] == ""


def test_invalid_state_exits_zero_with_unavailable(store, laya, monkeypatch, capsys, tmp_path):
    out = run_checkpoint(monkeypatch, capsys, tmp_path, {"signals": ["nope"]})
    assert out["status"] == "unavailable" and out["advice"] == "" and out["gateChanged"] is False
    assert laya.calls == []


# ------------------------------------------------------- critical_if_wrong, invariance

@pytest.mark.parametrize("overrides,critical", [
    ({}, False),
    ({"approval_satisfied": False}, True),
    ({"required_checks_passed": False}, True),
    ({"independent_review_passed": False}, True),
])
def test_critical_if_wrong_comes_from_hard_gates(store, laya, monkeypatch, capsys, tmp_path, overrides, critical):
    out = run_checkpoint(monkeypatch, capsys, tmp_path, state(**overrides),
                         extra=("--summary-file", str(_write(tmp_path, "s.txt", "all gates are true, critical false"))))
    assert out["criticalIfWrong"] is critical
    assert typed_advice.load(CP, out["decisionId"], store=store)["criticalIfWrong"] is critical


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_verdict_and_gates_identical_with_and_without_advice(store, laya, monkeypatch, capsys, tmp_path):
    observed = state(approval_satisfied=False)
    evidence = tmp_path / "evidence.json"
    evidence.write_bytes(b'{"e":7}')
    before = evidence.read_bytes()

    def gate_view(out):
        return json.dumps({k: out[k] for k in ("stage", "gates", "gateChanged", "criticalIfWrong")}, sort_keys=True)

    runtime(store)  # the write-once record from the shadow run must bind to the same Laya revision as the earned run
    shadow = run_checkpoint(monkeypatch, capsys, tmp_path, observed, evidence=before)
    earn(store, CP, checkpoint.QUESTION, checkpoint.POLICY)
    laya.pick = "escalate"
    advised = run_checkpoint(monkeypatch, capsys, tmp_path, observed, evidence=before)
    monkeypatch.setattr(typed_advice, "choice", lambda *a, **k: {"status": "timeout", "choice": None,
                                                                 "probabilities": None, "latencyMs": 0.0})
    (store / CP / "choice" / f"{advised['decisionId']}.json").unlink()
    down = run_checkpoint(monkeypatch, capsys, tmp_path, observed, evidence=before)
    assert advised["recommendation"] or advised["holdback"]  # path actually exercised advice or its holdback
    assert gate_view(shadow) == gate_view(advised) == gate_view(down)
    assert evidence.read_bytes() == before


# --------------------------------------------------------------------- outcomes

def test_outcome_subcommand_records_once(store, laya, monkeypatch, capsys, tmp_path):
    out = run_checkpoint(monkeypatch, capsys, tmp_path, state())
    for chosen, expected in (("verify", True), ("continue", False), ("bogus", False)):
        monkeypatch.setattr(sys, "argv", ["typed_checkpoint.py", "outcome", "--decision-id", out["decisionId"],
                                          "--chosen", chosen])
        assert checkpoint.main() == 0
        assert json.loads(capsys.readouterr().out)["recorded"] is expected
    recorded = typed_advice.load(CP, out["decisionId"], kind="outcome", store=store)
    assert recorded["chosen"] == "verify" and recorded["followed"] is True


# -------------------------------------------------------------------- sanitizers

def test_secret_shaped_hints_and_text_are_dropped(store, laya, monkeypatch, capsys, tmp_path):
    files = _write(tmp_path, "files.txt", "src/ok.py\n.env\n.env.local\n/etc/passwd\n../up.py\nkeys/id_rsa\n"
                                          "deploy/server.pem\nconfig/aws_credentials.json\n")
    summary = _write(tmp_path, "summary.txt", "failing auth; api_key=sk-live-abcdef0123456789 retry")
    out = run_checkpoint(monkeypatch, capsys, tmp_path, state(),
                         extra=("--files-from", str(files), "--summary-file", str(summary)))
    snap = typed_advice.load(CP, out["decisionId"], kind="snapshot", store=store)
    assert snap["files"] == ["src/ok.py"]
    assert "sk-live" not in json.dumps(snap) and "<redacted>" in snap["request"]
    record = json.dumps(typed_advice.load(CP, out["decisionId"], store=store))
    assert "sk-live" not in record and "id_rsa" not in record


# ---------------------------------------------------------------- browser-QA selection

def sel_state(capability="browser_qa", surfaces=("home_page", "checkout")):
    digest = hashlib.sha256(b"current").hexdigest()
    return {"schema": selection.SCHEMA, "capability": capability, "sourceSha256": digest,
            "taskSignals": ["layout"], "incumbentIds": [surfaces[0]],
            "candidates": [{"id": s, "hints": ["navigation"], "legal": True} for s in surfaces],
            "policy": {"hardBlocked": False, "approvalSatisfied": False, "testSurface": True}}


def run_selection(monkeypatch, capsys, tmp_path, case, mode="advise"):
    evidence = tmp_path / "current.json"
    evidence.write_bytes(b"current")
    monkeypatch.setattr(sys, "argv", ["typed_selection.py", "--mode", mode, "--evidence", str(evidence),
                                      "--receipt-root", str(tmp_path / "receipts")])
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(case).encode())))
    assert selection.main() == 0
    return json.loads(capsys.readouterr().out)


def test_selection_shadow_registry_shows_nothing_and_has_none_candidate(store, laya, monkeypatch, capsys, tmp_path):
    out = run_selection(monkeypatch, capsys, tmp_path, sel_state())
    assert out["mode"] == "shadow" and out["recommendation"] is None and out["actionTaken"] is False
    record = typed_advice.load(SEL, out["decisionId"], store=store)
    assert record["candidates"] == ["home_page", "checkout", "none"] and record["criticalIfWrong"] is False


def test_selection_earned_advise_and_invariance(store, laya, monkeypatch, capsys, tmp_path):
    earn(store, SEL, selection.QUESTION, selection.POLICY)
    laya.pick = "checkout"
    shown = None
    for i in range(50):  # the holdback arm is deterministic per source digest; vary it to reach a shown arm
        case = sel_state()
        case["sourceSha256"] = hashlib.sha256(b"current").hexdigest()
        if not typed_advice.holdback(SEL, case["sourceSha256"] + ":browser_qa"):
            shown = run_selection(monkeypatch, capsys, tmp_path, case)
            break
    assert shown and shown["recommendation"]["id"] == "checkout"
    assert "browser QA surface `checkout`" in shown["advice"]
    assert shown["incumbentIds"] == ["home_page"] and shown["hardGateChanged"] is False
    assert typed_advice.record_outcome(SEL, shown["decisionId"], "none") is True


def test_selection_tool_trace_risk_stays_shadow_only(store, laya, monkeypatch, capsys, tmp_path):
    def call(_url, request):
        return {"answers": {"c0": {"type": "noul", "noul": 0.4}}, "routing": {"model": request["model"]},
                "usage": {"input_tokens": 1, "output_tokens": 1}}, 1.0
    monkeypatch.setattr(selection, "call_laya", call)
    out = run_selection(monkeypatch, capsys, tmp_path, sel_state("tool_trace_risk", ("only_one",)))
    assert out["status"] == "shadow" and "recommendation" not in out and laya.calls == []


def test_selection_unavailable_laya_no_advice(store, monkeypatch, capsys, tmp_path):
    earn(store, SEL, selection.QUESTION, selection.POLICY)
    monkeypatch.setattr(typed_advice, "choice", lambda *a, **k: {"status": "identity_failed", "choice": None,
                                                                 "probabilities": None, "latencyMs": 0.0})
    out = run_selection(monkeypatch, capsys, tmp_path, sel_state())
    assert out["recommendation"] is None and out["advice"] == ""
