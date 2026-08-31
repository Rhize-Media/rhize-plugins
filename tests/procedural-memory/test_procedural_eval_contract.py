import json
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_both_skills_have_local_trigger_and_quality_coverage() -> None:
    completed = subprocess.run(["python3", "evals/procedural-memory/run_evals.py"], cwd=REPO, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["skills"] == 2
    assert result["routing"]["precision"] == result["routing"]["recall"] == 1.0
    assert result["quality_contracts"]["passed"] == result["quality_contracts"]["total"] == 6


def test_functionize_agent_cases_are_schema_valid() -> None:
    completed = subprocess.run([
        "python3", "procedural-memory/evals/validate-suite.py", "--eval-dir", "procedural-memory/evals"
    ], cwd=REPO, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "== 8 case(s), 0 error(s), 0 warning(s), 8 clean ==" in completed.stdout
