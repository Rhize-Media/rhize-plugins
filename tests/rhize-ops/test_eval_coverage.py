import json
import subprocess
import tempfile
import uuid
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
EVAL = REPO / "evals/parallel-agent-skills"
RECEIPT_CONTEXT_FIELDS = {
    "run_id", "comparison_id", "variant", "guide_sha256", "task_id", "task_class",
    "repetition", "order_position", "expected_decision",
}


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True, check=False)


def receipt(context: dict, *, agents: list[dict] | None = None, collisions: int = 0, decision: str | None = None) -> dict:
    return {
        **{key: context[key] for key in RECEIPT_CONTEXT_FIELDS},
        "schema_version": "rhize-guide-comparison-v1",
        "status": "completed", "started_at": "2026-08-31T12:00:00Z", "completed_at": "2026-08-31T12:00:01Z",
        "decision": decision or context["expected_decision"],
        "correctness": {"passed": 2, "total": 2, "accuracy": 1.0},
        "routing": {"true_positives": 1, "false_positives": 0, "false_negatives": 0, "precision": 1.0, "recall": 1.0},
        "tokens": {"input": None, "output": None, "cache_read": None, "cache_write": None},
        "tokens_unavailable_reason": "host_not_exposed", "latency_ms": 1000,
        "tool_calls": None, "tool_calls_unavailable_reason": "host_not_exposed",
        "follow_up_reads": 0, "corrections": 0, "rework_events": 0, "failures": 0,
        "refusals": 0, "collisions": collisions, "agents": agents or []
    }


def prepare_group(parent: Path, name: str, *, task: str = "parallel-read", repetition: int = 1) -> Path:
    superpowers = parent / f"{name}-superpowers.md"
    superpowers.write_text("---\nname: dispatching-parallel-agents\n---\n# Guide\n")
    group = parent / name
    prepared = run(
        "python3", str(EVAL / "scripts/prepare_guide_comparison.py"),
        "--task", task, "--repetition", str(repetition), "--comparison-id", str(uuid.uuid4()),
        "--superpowers-guide", str(superpowers),
        "--rhize-guide", str(REPO / "rhize-ops/skills/parallel-agent-optimization/SKILL.md"),
        "--output", str(group),
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    return group


def write_receipts(group: Path, *, with_intervals: bool = False) -> None:
    intervals = {
        "baseline": [
            {"started_at": "2026-08-31T12:00:00Z", "completed_at": "2026-08-31T12:00:00.900Z", "status": "completed"},
        ],
        "superpowers": [
            {"started_at": "2026-08-31T12:00:00Z", "completed_at": "2026-08-31T12:00:00.800Z", "status": "completed"},
            {"started_at": "2026-08-31T12:00:00.200Z", "completed_at": "2026-08-31T12:00:01Z", "status": "completed"},
        ],
        "rhize": [
            {"started_at": "2026-08-31T12:00:00Z", "completed_at": "2026-08-31T12:00:00.900Z", "status": "completed"},
            {"started_at": "2026-08-31T12:00:00.100Z", "completed_at": "2026-08-31T12:00:00.800Z", "status": "completed"},
            {"started_at": "2026-08-31T12:00:00.200Z", "completed_at": "2026-08-31T12:00:00.700Z", "status": "completed"},
        ],
    }
    collision_counts = {"baseline": 0, "superpowers": 2, "rhize": 1}
    for run_dir in (path for path in group.iterdir() if path.is_dir()):
        context = json.loads((run_dir / "RUN_CONTEXT.json").read_text())
        agents = intervals[context["variant"]] if with_intervals else []
        collisions = collision_counts[context["variant"]] if with_intervals else 0
        (run_dir / "receipt.json").write_text(json.dumps(receipt(context, agents=agents, collisions=collisions)) + "\n")


def test_all_ops_skills_have_deterministic_trigger_and_quality_coverage() -> None:
    completed = run("python3", str(EVAL / "scripts/evaluate_ops_skills.py"))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["skills"] == 3
    assert result["routing"]["precision"] == result["routing"]["recall"] == 1.0
    assert result["routing_coverage"]["passed"] == result["routing_coverage"]["total"] == 3
    assert all(item["positive"] == {"passed": 1, "total": 1} for item in result["routing_coverage"]["results"])
    assert all(item["negative"] == {"passed": 2, "total": 2} for item in result["routing_coverage"]["results"])
    assert result["quality_contracts"]["passed"] == result["quality_contracts"]["total"] == 9


def test_ops_runner_rejects_a_skill_with_fewer_than_two_negatives() -> None:
    manifest = json.loads((EVAL / "ops-skill-evals.json").read_text())
    manifest["skills"][0]["negative_cases"] = manifest["skills"][0]["negative_cases"][:1]
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "insufficient-negatives.json"
        path.write_text(json.dumps(manifest))
        completed = run("python3", str(EVAL / "scripts/evaluate_ops_skills.py"), "--manifest", str(path))
    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert "parallel-agent-optimization:coverage-contract" in result["failures"]
    assert result["routing_coverage"]["passed"] == 2


def test_guide_comparison_is_separate_counterbalanced_and_validatable() -> None:
    canonical = json.loads((EVAL / "manifest.json").read_text())
    comparison = json.loads((EVAL / "guide-comparison.manifest.json").read_text())
    assert canonical["variants"] == ["baseline", "rhize"]
    assert comparison["evidence_boundaries"]["feeds_rhize_v2_readiness"] is False
    assert {tuple(pair) for pair in comparison["comparison_pairs"]} == {("baseline", "superpowers"), ("baseline", "rhize")}
    assert set(comparison["fair_routing_metrics"]) == {
        "actual_overlap_runs", "concurrent_agent_milliseconds", "maximum_concurrency",
        "agent_count", "collision_totals",
    }
    for position in range(3):
        assert {comparison["order_by_repetition"][str(rep)][position] for rep in (1, 2, 3)} == {"baseline", "superpowers", "rhize"}

    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        group = prepare_group(temp, "group")
        write_receipts(group, with_intervals=True)
        validated = run("python3", str(EVAL / "scripts/validate_guide_receipts.py"), str(group))
        assert validated.returncode == 0, validated.stdout + validated.stderr
        summary = json.loads(validated.stdout)
        assert summary["runs"] == 3
        assert summary["variants"]["baseline"]["actual_overlap_runs"] == 0
        assert summary["variants"]["baseline"]["maximum_concurrency"] == 1
        assert summary["variants"]["baseline"]["agent_count"] == 1
        assert summary["variants"]["superpowers"]["actual_overlap_runs"] == 1
        assert summary["variants"]["superpowers"]["concurrent_agent_milliseconds"] == 600
        assert summary["variants"]["superpowers"]["maximum_concurrency"] == 2
        assert summary["variants"]["superpowers"]["agent_count"] == 2
        assert summary["variants"]["superpowers"]["collision_totals"] == 2
        assert summary["variants"]["rhize"]["actual_overlap_runs"] == 1
        assert summary["variants"]["rhize"]["concurrent_agent_milliseconds"] == 700
        assert summary["variants"]["rhize"]["maximum_concurrency"] == 3
        assert summary["variants"]["rhize"]["agent_count"] == 3
        assert summary["variants"]["rhize"]["collision_totals"] == 1


def test_tampered_context_and_reservation_boundaries_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        context_group = prepare_group(temp, "context-tamper")
        context_run = next(path for path in context_group.iterdir() if path.is_dir())
        context = json.loads((context_run / "RUN_CONTEXT.json").read_text())
        context["comparison_id"] = str(uuid.uuid4())
        (context_run / "RUN_CONTEXT.json").write_text(json.dumps(context) + "\n")
        write_receipts(context_group)
        checked = run("python3", str(EVAL / "scripts/validate_guide_receipts.py"), str(context_group))
        assert checked.returncode == 1
        assert any("context:comparison_id" in item for item in json.loads(checked.stdout)["errors"])

        reservation_group = prepare_group(temp, "reservation-tamper")
        reservation_path = reservation_group / "GROUP_RESERVATION.json"
        reservation = json.loads(reservation_path.read_text())
        reservation["isolated"] = False
        reservation_path.write_text(json.dumps(reservation) + "\n")
        write_receipts(reservation_group)
        checked = run("python3", str(EVAL / "scripts/validate_guide_receipts.py"), str(reservation_group))
        assert checked.returncode == 1
        errors = json.loads(checked.stdout)["errors"]
        assert any("reservation:isolated" in item for item in errors)
        assert any("context:isolated" in item for item in errors)


def test_duplicate_task_repetition_groups_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first = prepare_group(root, "first")
        second = prepare_group(root, "second")
        write_receipts(first)
        write_receipts(second)
        checked = run("python3", str(EVAL / "scripts/validate_guide_receipts.py"), str(root))
        assert checked.returncode == 1
        assert any("parallel-read:1:duplicate-group" == item for item in json.loads(checked.stdout)["errors"])


def test_completed_receipt_must_match_expected_routing_decision() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        group = prepare_group(Path(temporary), "decision-tamper")
        write_receipts(group)
        run_dir = next(path for path in group.iterdir() if path.is_dir())
        context = json.loads((run_dir / "RUN_CONTEXT.json").read_text())
        wrong = "sequential" if context["expected_decision"] == "parallel" else "parallel"
        (run_dir / "receipt.json").write_text(json.dumps(receipt(context, decision=wrong)) + "\n")
        checked = run("python3", str(EVAL / "scripts/validate_guide_receipts.py"), str(group))
        assert checked.returncode == 1
        assert any("receipt:decision_expected" in item for item in json.loads(checked.stdout)["errors"])
