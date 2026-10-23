import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/"evals/graph-workflow-builder/evaluate.py"
spec=importlib.util.spec_from_file_location("graph_oracle",PATH)
oracle=importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)

def test_software_oracle_rejects_baseline_and_accepts_repair(tmp_path):
    source=tmp_path/"normalizer.py"
    source.write_bytes((PATH.parent/"tasks/software/normalizer.py").read_bytes())
    with pytest.raises(ValueError):
        oracle.evaluate("software",tmp_path)
    source.write_text("def normalize_email(value):\n    return None if value is None else value.strip().lower() or None\n")
    assert oracle.evaluate("software",tmp_path)["objective_pass"]

def test_reconciliation_oracle_refuses_missing_hold_and_duplicate_event(tmp_path):
    path=tmp_path/"reconciliation.json"
    packet={"dispositions":{"a":"settled","b":"hold","c":"hold","d":"unavailable"},
            "events":[{"key":"settled:a:receipt-a","id":"a","from":"pending","to":"settled"}]}
    path.write_text(json.dumps(packet))
    assert oracle.evaluate("reconciliation",tmp_path)["objective_pass"]
    packet["events"]*=2
    path.write_text(json.dumps(packet))
    with pytest.raises(ValueError):
        oracle.evaluate("reconciliation",tmp_path)

def test_research_oracle_checks_evidence_not_success_flag(tmp_path):
    packet={"claims":[{"question":"alpha workers","answer":2,"sources":["alpha"]},
                      {"question":"beta workers","answer":3,"sources":["beta"]},
                      {"question":"beta dynamic","answer":True,"sources":["beta"]}]}
    path=tmp_path/"report.json"
    path.write_text(json.dumps(packet))
    (tmp_path/"report.md").write_text("A release comparison for maintainers. Alpha supports two workers. Beta adds a third worker and dynamic task discovery.")
    assert oracle.evaluate("research",tmp_path)["subjective_review"]=="pending"
    packet["claims"][1]["sources"]=["alpha"]
    path.write_text(json.dumps(packet))
    with pytest.raises(ValueError):
        oracle.evaluate("research",tmp_path)
    packet["claims"][1]["sources"]=["beta"]
    packet["claims"][2]["answer"]=1
    path.write_text(json.dumps(packet))
    with pytest.raises(ValueError):
        oracle.evaluate("research",tmp_path)
