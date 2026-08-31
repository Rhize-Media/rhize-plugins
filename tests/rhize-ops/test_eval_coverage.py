import json
import subprocess
import tempfile
import uuid
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
EVAL = REPO / "evals/parallel-agent-skills"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True, check=False)


def receipt(context: dict) -> dict:
    return {
        **context, "schema_version": "rhize-guide-comparison-v1",
        "status": "completed", "started_at": "2026-08-31T12:00:00Z", "completed_at": "2026-08-31T12:00:01Z",
        "decision": context["expected_decision"],
        "correctness": {"passed": 2, "total": 2, "accuracy": 1.0},
        "routing": {"true_positives": 1, "false_positives": 0, "false_negatives": 0, "precision": 1.0, "recall": 1.0},
        "tokens": {"input": None, "output": None, "cache_read": None, "cache_write": None},
        "tokens_unavailable_reason": "host_not_exposed", "latency_ms": 1000,
        "tool_calls": None, "tool_calls_unavailable_reason": "host_not_exposed",
        "follow_up_reads": 0, "corrections": 0, "rework_events": 0, "failures": 0,
        "refusals": 0, "collisions": 0, "agents": []
    }


def test_all_ops_skills_have_deterministic_trigger_and_quality_coverage() -> None:
    completed = run("python3", str(EVAL / "scripts/evaluate_ops_skills.py"))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["skills"] == 3
    assert result["routing"]["precision"] == result["routing"]["recall"] == 1.0
    assert result["quality_contracts"]["passed"] == result["quality_contracts"]["total"] == 9


def test_guide_comparison_is_separate_counterbalanced_and_validatable() -> None:
    canonical = json.loads((EVAL / "manifest.json").read_text())
    comparison = json.loads((EVAL / "guide-comparison.manifest.json").read_text())
    assert canonical["variants"] == ["baseline", "rhize"]
    assert comparison["evidence_boundaries"]["feeds_rhize_v2_readiness"] is False
    assert {tuple(pair) for pair in comparison["comparison_pairs"]} == {("baseline", "superpowers"), ("baseline", "rhize")}
    for position in range(3):
        assert {comparison["order_by_repetition"][str(rep)][position] for rep in (1, 2, 3)} == {"baseline", "superpowers", "rhize"}

    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        superpowers = temp / "superpowers.md"
        superpowers.write_text("---\nname: dispatching-parallel-agents\n---\n# Guide\n")
        group = temp / "group"
        prepared = run(
            "python3", str(EVAL / "scripts/prepare_guide_comparison.py"),
            "--task", "parallel-read", "--repetition", "1", "--comparison-id", str(uuid.uuid4()),
            "--superpowers-guide", str(superpowers),
            "--rhize-guide", str(REPO / "rhize-ops/skills/parallel-agent-optimization/SKILL.md"),
            "--output", str(group),
        )
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        for run_dir in (path for path in group.iterdir() if path.is_dir()):
            context = json.loads((run_dir / "RUN_CONTEXT.json").read_text())
            (run_dir / "receipt.json").write_text(json.dumps(receipt(context)) + "\n")
        validated = run("python3", str(EVAL / "scripts/validate_guide_receipts.py"), str(group))
        assert validated.returncode == 0, validated.stdout + validated.stderr
        assert json.loads(validated.stdout)["runs"] == 3
