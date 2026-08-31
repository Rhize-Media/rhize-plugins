import json
import subprocess
import tempfile
import uuid
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
EVAL = REPO / "evals/rhize-tasks"


def test_six_skill_routing_quality_and_benefit_contract() -> None:
    completed = subprocess.run(["python3", str(EVAL / "run_evals.py")], cwd=REPO, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["skills"] == 6
    assert result["routing"]["precision"] == result["routing"]["recall"] == 1.0
    assert result["quality_contracts"]["passed"] == result["quality_contracts"]["total"] == 18
    benchmark = json.loads((EVAL / "benefit-benchmark.json").read_text())
    assert len(benchmark["skills"]) == 6 and benchmark["repetitions"] == 3
    assert benchmark["arms"]["baseline"].startswith("Arm A:")
    assert benchmark["arms"]["rhize"].startswith("Arm B:")


def test_benefit_pair_records_actual_arm_and_validates() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "pair"
        create = subprocess.run([
            "python3", str(EVAL / "benchmark_contract.py"), "reserve",
            "--skill", "plan-my-day", "--repetition", "1", "--comparison-id", str(uuid.uuid4()), "--output", str(root)
        ], cwd=REPO, capture_output=True, text=True)
        assert create.returncode == 0, create.stdout + create.stderr
        for run_dir in (path for path in root.iterdir() if path.is_dir()):
            context = json.loads((run_dir / "RUN_CONTEXT.json").read_text())
            value = {
                "schema_version": "rhize-tasks-benefit-v1", **context, "status": "completed",
                "started_at": "2026-08-31T12:00:00Z", "completed_at": "2026-08-31T12:00:01Z",
                "correctness": {"passed": 1, "total": 1, "accuracy": 1.0},
                "routing": {"true_positives": 1, "false_positives": 0, "false_negatives": 0, "precision": 1.0, "recall": 1.0},
                "tokens": {"input": None, "output": None, "cache_read": None, "cache_write": None},
                "tokens_unavailable_reason": "host_not_exposed", "latency_ms": 1,
                "tool_calls": None, "tool_calls_unavailable_reason": "host_not_exposed",
                "follow_up_reads": 0, "corrections": 0, "rework_events": 0, "failures": 0, "refusals": 0
            }
            (run_dir / "receipt.json").write_text(json.dumps(value) + "\n")
        check = subprocess.run(["python3", str(EVAL / "benchmark_contract.py"), "validate", str(root)], cwd=REPO, capture_output=True, text=True)
        assert check.returncode == 0, check.stdout + check.stderr
        assert json.loads(check.stdout)["receipts"] == 2
