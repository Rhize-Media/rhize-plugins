import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
EVAL = REPO / "evals/skill-forge"


def fake_binary(path: Path, binary_version: str) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        f"VERSION = {binary_version!r}\n"
        "if sys.argv[1:] == ['--version']:\n    print(VERSION); raise SystemExit(0)\n"
        "target = pathlib.Path(sys.argv[2]).name\n"
        "blocked = target.startswith('unsafe-')\n"
        "print(json.dumps({'safety': {'verdict': 'BLOCK' if blocked else 'ALLOW'}}))\n"
        "raise SystemExit(1 if blocked else 0)\n"
    )
    path.chmod(0o755)


def test_version_drift_is_detected_without_installing() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        checkout = temp / "checkout"
        checkout.mkdir()
        (checkout / "package.json").write_text(json.dumps({"version": "0.14.0"}))
        binary = temp / "skill-forge"
        fake_binary(binary, "0.13.0")
        completed = subprocess.run([
            "python3", str(EVAL / "integration_eval.py"), "inspect", "--checkout", str(checkout), "--binary", str(binary)
        ], cwd=REPO, capture_output=True, text=True)
        assert completed.returncode == 1
        assert json.loads(completed.stdout)["version_match"] is False


def test_labeled_safety_corpus_reports_precision_recall_and_latency() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        checkout = temp / "checkout"
        checkout.mkdir()
        (checkout / "package.json").write_text(json.dumps({"version": "0.14.0"}))
        binary = temp / "skill-forge"
        fake_binary(binary, "0.14.0")
        output = temp / "result.json"
        completed = subprocess.run([
            "python3", str(EVAL / "integration_eval.py"), "safety", "--checkout", str(checkout),
            "--binary", str(binary), "--repetitions", "2", "--output", str(output)
        ], cwd=REPO, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(output.read_text())
        assert result["corpus_cases"] == 6 and result["repetitions"] == 2
        assert result["safety"]["precision"] == result["safety"]["recall"] == 1.0
        assert result["performance"]["scan_latency_ms_median"] > 0


def test_evolve_pre_post_reservation_and_noninferiority_validator() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "pair"
        completed = subprocess.run([
            "python3", str(EVAL / "evolve_contract.py"), "reserve", "--pre-digest", "a" * 64,
            "--post-digest", "b" * 64, "--repetition", "1", "--comparison-id", str(uuid.uuid4()), "--output", str(root)
        ], cwd=REPO, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        metrics = {
            "accuracy": 1.0, "routing_precision": 1.0, "routing_recall": 1.0,
            "tokens_input": 10, "tokens_output": 10, "tokens_cache_read": 0, "tokens_cache_write": 0,
            "latency_ms": 100, "tool_calls": 1, "follow_up_reads": 0, "corrections": 0,
            "rework_events": 0, "failures": 0, "refusals": 0
        }
        for run_dir in (path for path in root.iterdir() if path.is_dir()):
            context = json.loads((run_dir / "RUN_CONTEXT.json").read_text())
            (run_dir / "receipt.json").write_text(json.dumps({**context, "metrics": metrics}) + "\n")
        check = subprocess.run(["python3", str(EVAL / "evolve_contract.py"), "validate", str(root)], cwd=REPO, capture_output=True, text=True)
        assert check.returncode == 0, check.stdout + check.stderr
        assert all(json.loads(check.stdout)["non_inferiority"].values())
