from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-ops/skills/parallel-agent-optimization/scripts/parallel_metrics.py"
SPEC = importlib.util.spec_from_file_location("parallel_metrics", SCRIPT)
assert SPEC and SPEC.loader
parallel_metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parallel_metrics)


def begin_input(**overrides):
    value = {
        "schema_version": 2,
        "evidence_class": "observational",
        "variant": "rhize",
        "task_class": "mixed_verification",
        "started_at": "2026-08-30T12:00:00-04:00",
        "isolated": False,
        "live_mutation": False,
        "one_writer_enforced": True,
        "comparison_id": None,
    }
    value.update(overrides)
    return value


def final_input(**overrides):
    value = {
        "schema_version": 2,
        "status": "completed",
        "completed_at": "2026-08-30T12:02:00-04:00",
        "decision": "parallel",
        "lanes_planned": 2,
        "agents": [
            {
                "started_at": "2026-08-30T12:00:10-04:00",
                "completed_at": "2026-08-30T12:01:10-04:00",
                "status": "completed",
            }
        ],
        "tool_calls": None,
        "tool_calls_unavailable_reason": "host_not_exposed",
        "tokens": {"input": None, "output": None, "cache_read": None, "cache_write": None},
        "tokens_unavailable_reason": "host_not_exposed",
        "verification": {"required": 3, "completed": 3, "passed": 3},
        "collisions": 0,
        "rework_events": 0,
        "correctness_pass": True,
        "task_graph": {
            "planned": 2,
            "required": 2,
            "required_completed": 2,
            "completed": 2,
            "failed": 0,
            "cancelled": 0,
            "timed_out": 0,
            "blocked_dependency": 0,
            "skipped_optional": 0,
            "cleanup_failed": 0,
            "fan_in_levels": 1,
            "declared_concurrency_cap": 3,
        },
    }
    value.update(overrides)
    return value


def reserve_controlled(store: Path, *, task_class="mixed_verification"):
    comparison = parallel_metrics.new_comparison(store)
    reservations = {}
    for index, variant in enumerate(comparison["order"]):
        reservations[variant] = parallel_metrics.begin_run(
            begin_input(
                evidence_class="controlled",
                variant=variant,
                task_class=task_class,
                started_at=f"2026-08-30T14:{index * 5:02d}:00Z",
                isolated=True,
                comparison_id=comparison["comparison_id"],
            ),
            store,
        )
    return comparison, reservations


def test_begin_then_finalize_writes_private_v2_receipt(tmp_path):
    store = tmp_path / "store"
    reservation = parallel_metrics.begin_run(begin_input(), store)
    receipt = parallel_metrics.finalize_run(reservation["run_id"], final_input(), store)
    assert reservation["status"] == "pending"
    assert reservation["expected_decision"] == "parallel"
    assert receipt["status"] == "completed"
    assert receipt["actual_overlap"] is False
    assert receipt["verification_completeness"] == 1.0
    assert receipt["task_graph"]["required_completed"] == 2
    assert receipt["task_graph"]["completed"] == 2
    path = next((store / "observational").glob("*.jsonl"))
    assert stat.S_IMODE(store.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text())["run_id"] == reservation["run_id"]
    report = parallel_metrics.build_report(store, "observational")
    assert report["evidence"]["observational"]["variants"]["rhize"][
        "task_graph_totals"
    ]["completed"] == 2


def test_expected_decision_is_derived_from_task_class():
    expected = {
        "parallel_read": "parallel",
        "disjoint_write": "parallel",
        "shared_state": "sequential",
        "dependency_chain": "sequential",
        "mixed_verification": "parallel",
        "gated_live": "gated",
    }
    for task_class, decision in expected.items():
        reservation = parallel_metrics.validate_begin(begin_input(task_class=task_class))
        assert reservation["expected_decision"] == decision


def test_canonical_v2_schema_matches_two_arm_lifecycle_contract():
    path = REPO / "rhize-ops/skills/parallel-agent-optimization/references/receipt-v2.schema.json"
    schema = json.loads(path.read_text())
    assert schema["$defs"]["begin"]["properties"]["variant"]["enum"] == ["baseline", "rhize"]
    assert "resource_used" not in schema["$defs"]["begin"]["properties"]
    assert "task_graph" in schema["$defs"]["final"]["required"]
    assert schema["$defs"]["task_graph"]["additionalProperties"] is False
    assert "required_completed" in schema["$defs"]["task_graph"]["required"]


@pytest.mark.parametrize(
    "change,match",
    [
        ({"planned": 3}, "terminal counts"),
        ({"required": 3}, "required"),
        ({"required_completed": 3}, "required_completed"),
        ({"skipped_optional": 1, "completed": 1, "required_completed": 1}, "optional"),
        ({"planned": 3, "required_completed": 1, "skipped_optional": 1}, "optional"),
        ({"declared_concurrency_cap": 0}, "positive"),
    ],
)
def test_v2_rejects_inconsistent_task_graph_aggregates(change, match):
    value = final_input()
    value["task_graph"].update(change)
    with pytest.raises(parallel_metrics.ReceiptError, match=match):
        parallel_metrics.validate_final(value, parallel_metrics.validate_begin(begin_input()))


@pytest.mark.parametrize("forbidden", ("node_ids", "paths", "issue_ids", "decision_prose"))
def test_v2_task_graph_rejects_content_fields(forbidden):
    value = final_input()
    value["task_graph"][forbidden] = ["must-not-land"]
    with pytest.raises(parallel_metrics.ReceiptError, match="unknown"):
        parallel_metrics.validate_final(value, parallel_metrics.validate_begin(begin_input()))


def test_v2_rejects_concurrency_above_declared_cap():
    value = final_input(
        agents=[
            {
                "started_at": "2026-08-30T12:00:10-04:00",
                "completed_at": "2026-08-30T12:01:10-04:00",
                "status": "completed",
            },
            {
                "started_at": "2026-08-30T12:00:20-04:00",
                "completed_at": "2026-08-30T12:01:20-04:00",
                "status": "completed",
            },
        ]
    )
    value["task_graph"]["declared_concurrency_cap"] = 1
    with pytest.raises(parallel_metrics.ReceiptError, match="observed concurrency"):
        parallel_metrics.validate_final(value, parallel_metrics.validate_begin(begin_input()))


def test_v2_rejects_success_when_cleanup_or_required_results_failed():
    cleanup = final_input()
    cleanup["task_graph"]["cleanup_failed"] = 1
    with pytest.raises(parallel_metrics.ReceiptError, match="cleanup failure"):
        parallel_metrics.validate_final(cleanup, parallel_metrics.validate_begin(begin_input()))

    missing = final_input()
    missing["task_graph"].update(required_completed=1, completed=1, failed=1)
    with pytest.raises(parallel_metrics.ReceiptError, match="required node"):
        parallel_metrics.validate_final(missing, parallel_metrics.validate_begin(begin_input()))


def test_v2_rejects_correctness_when_any_required_verification_failed():
    value = final_input(verification={"required": 3, "completed": 3, "passed": 2})

    with pytest.raises(parallel_metrics.ReceiptError, match="fully passed verification"):
        parallel_metrics.validate_final(value, parallel_metrics.validate_begin(begin_input()))


def test_reports_do_not_treat_completed_failed_checks_as_correct():
    retained = parallel_metrics.validate_final(
        final_input(), parallel_metrics.validate_begin(begin_input())
    )
    retained["verification"] = {"required": 3, "completed": 3, "passed": 2}
    baseline = {**retained, "variant": "baseline"}

    assert parallel_metrics.summarize_variant([retained])["correctness_pass_rate"] == 0.0
    readiness = parallel_metrics.build_readiness([[baseline, retained]])
    assert readiness["required_metrics"]["correctness"]["status"] == "fail"
    assert readiness["required_metrics"]["verification"]["status"] == "fail"


def test_v2_rejects_equal_count_swap_that_masks_failed_required_node():
    value = final_input(lanes_planned=3)
    value["task_graph"].update(
        planned=3,
        required=2,
        required_completed=1,
        completed=2,
        failed=1,
    )

    with pytest.raises(parallel_metrics.ReceiptError, match="every required node completed"):
        parallel_metrics.validate_final(value, parallel_metrics.validate_begin(begin_input()))


def test_noncompleted_lifecycle_can_finalize_without_invented_graph_counts():
    value = final_input(
        status="incomplete",
        decision=None,
        lanes_planned=None,
        agents=None,
        verification=None,
        collisions=None,
        rework_events=None,
        correctness_pass=None,
        task_graph=None,
    )
    stored = parallel_metrics.validate_final(value, parallel_metrics.validate_begin(begin_input()))
    assert stored["task_graph"] is None


def test_other_task_class_is_not_accepted_for_controlled_evidence(tmp_path):
    comparison_id = parallel_metrics.new_comparison(tmp_path)["comparison_id"]
    with pytest.raises(parallel_metrics.ReceiptError, match="deterministic task class"):
        parallel_metrics.begin_run(
            begin_input(
                evidence_class="controlled",
                task_class="other",
                variant="baseline",
                isolated=True,
                comparison_id=comparison_id,
            ),
            tmp_path,
        )


def test_new_comparison_has_baseline_and_rhize_only(tmp_path):
    first = parallel_metrics.new_comparison(tmp_path)
    second = parallel_metrics.new_comparison(tmp_path)
    assert first["schema_version"] == 2
    assert first["order"] == ["baseline", "rhize"]
    assert second["order"] == ["rhize", "baseline"]
    assert "ecc" not in first["order"]
    assert "superpowers" not in first["order"]


def test_controlled_begin_requires_reserved_variant_and_safe_boundary(tmp_path):
    comparison = parallel_metrics.new_comparison(tmp_path)
    with pytest.raises(parallel_metrics.ReceiptError, match="isolated=true"):
        parallel_metrics.begin_run(
            begin_input(
                evidence_class="controlled",
                variant="baseline",
                comparison_id=comparison["comparison_id"],
            ),
            tmp_path,
        )
    with pytest.raises(parallel_metrics.ReceiptError, match="variant"):
        parallel_metrics.begin_run(
            begin_input(
                evidence_class="controlled",
                variant="ecc",
                isolated=True,
                comparison_id=comparison["comparison_id"],
            ),
            tmp_path,
        )


def test_finalize_rejects_duplicate_and_completed_incomplete_metrics(tmp_path):
    reservation = parallel_metrics.begin_run(begin_input(), tmp_path)
    parallel_metrics.finalize_run(reservation["run_id"], final_input(), tmp_path)
    with pytest.raises(parallel_metrics.ReceiptError, match="already finalized"):
        parallel_metrics.finalize_run(reservation["run_id"], final_input(), tmp_path)

    other = parallel_metrics.begin_run(begin_input(started_at="2026-08-30T13:00:00Z"), tmp_path)
    with pytest.raises(parallel_metrics.ReceiptError, match="completed status"):
        parallel_metrics.finalize_run(
            other["run_id"],
            final_input(
                completed_at="2026-08-30T13:01:00Z",
                agents=[],
                verification={"required": 3, "completed": 2, "passed": 2},
            ),
            tmp_path,
        )


def test_failed_and_incomplete_are_terminal_and_visible(tmp_path):
    failed = parallel_metrics.begin_run(begin_input(), tmp_path)
    parallel_metrics.finalize_run(
        failed["run_id"], final_input(status="failed", correctness_pass=False), tmp_path
    )
    incomplete = parallel_metrics.begin_run(
        begin_input(started_at="2026-08-30T13:00:00Z"), tmp_path
    )
    parallel_metrics.finalize_run(
        incomplete["run_id"],
        final_input(
            status="incomplete",
            completed_at="2026-08-30T13:01:00Z",
            decision=None,
            lanes_planned=None,
            agents=None,
            correctness_pass=None,
            verification=None,
            collisions=None,
            rework_events=None,
        ),
        tmp_path,
    )
    section = parallel_metrics.build_report(tmp_path, "observational")["evidence"][
        "observational"
    ]
    assert section["terminal_status_counts"] == {"completed": 0, "failed": 1, "incomplete": 1}
    assert section["analyzed_runs"] == 0


def test_pending_audit_flags_only_stale_unfinalized_reservations(tmp_path):
    old = parallel_metrics.begin_run(begin_input(started_at="2026-08-30T10:00:00Z"), tmp_path)
    done = parallel_metrics.begin_run(begin_input(started_at="2026-08-30T10:30:00Z"), tmp_path)
    parallel_metrics.finalize_run(
        done["run_id"], final_input(completed_at="2026-08-30T10:31:00Z", agents=[]), tmp_path
    )
    fresh = parallel_metrics.begin_run(begin_input(started_at="2026-08-30T11:59:30Z"), tmp_path)
    audit = parallel_metrics.pending_audit(
        tmp_path,
        now=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
        stale_after_seconds=60,
    )
    assert audit["pending_count"] == 2
    assert audit["stale_count"] == 1
    assert audit["stale_run_ids"] == [old["run_id"]]
    assert fresh["run_id"] not in audit["stale_run_ids"]


@pytest.mark.parametrize("forbidden", ("prompt", "repository_path", "session_id", "agent_name"))
def test_inputs_reject_free_text_or_identifying_fields(forbidden):
    data = begin_input()
    data[forbidden] = "must-not-land"
    with pytest.raises(parallel_metrics.ReceiptError, match="unknown"):
        parallel_metrics.validate_begin(data)


def test_parallelism_is_derived_from_overlapping_intervals(tmp_path):
    reservation = parallel_metrics.begin_run(begin_input(), tmp_path)
    stored = parallel_metrics.finalize_run(
        reservation["run_id"],
        final_input(
            agents=[
                {
                    "started_at": "2026-08-30T12:00:10-04:00",
                    "completed_at": "2026-08-30T12:01:10-04:00",
                    "status": "completed",
                },
                {
                    "started_at": "2026-08-30T12:00:40-04:00",
                    "completed_at": "2026-08-30T12:01:40-04:00",
                    "status": "completed",
                },
            ]
        ),
        tmp_path,
    )
    assert stored["actual_overlap"] is True
    assert stored["concurrent_agent_ms"] == 30_000
    assert stored["max_concurrency"] == 2


def test_report_reads_legacy_v1_without_pooling_it(tmp_path):
    legacy_dir = tmp_path / "controlled"
    legacy_dir.mkdir(parents=True)
    legacy = {
        "schema_version": 1,
        "evidence_class": "controlled",
        "variant": "ecc",
        "run_id": str(uuid.uuid4()),
    }
    (legacy_dir / "2026-08.jsonl").write_text(json.dumps(legacy) + "\n")
    report = parallel_metrics.build_report(tmp_path, "all")
    assert report["legacy_v1"]["stored_runs"] == 1
    assert report["legacy_v1"]["variants"] == {"ecc": 1}
    assert report["legacy_v1"]["comparable_with_v2"] is False
    assert report["evidence"]["controlled"]["analyzed_runs"] == 0


def test_report_retains_but_excludes_pre_task_graph_v2_receipt(tmp_path):
    directory = tmp_path / "observational"
    directory.mkdir(parents=True)
    row = parallel_metrics.validate_final(final_input(), parallel_metrics.validate_begin(begin_input()))
    row.pop("task_graph")
    (directory / "2026-08.jsonl").write_text(json.dumps(row) + "\n")
    section = parallel_metrics.build_report(tmp_path, "observational")["evidence"][
        "observational"
    ]
    assert section["stored_runs"] == 1
    assert section["pre_task_graph_v2_runs"] == 1
    assert section["analyzed_runs"] == 0


def test_report_retains_but_excludes_pre_required_closure_v2_receipt(tmp_path):
    directory = tmp_path / "observational"
    directory.mkdir(parents=True)
    row = parallel_metrics.validate_final(final_input(), parallel_metrics.validate_begin(begin_input()))
    row["task_graph"].pop("required_completed")
    (directory / "2026-08.jsonl").write_text(json.dumps(row) + "\n")

    section = parallel_metrics.build_report(tmp_path, "observational")["evidence"][
        "observational"
    ]
    assert section["stored_runs"] == 1
    assert section["pre_required_closure_v2_runs"] == 1
    assert section["analyzed_runs"] == 0


def complete_comparison(store: Path, *, task_class="mixed_verification", missing_optional=True):
    comparison, reservations = reserve_controlled(store, task_class=task_class)
    decision = parallel_metrics.TASK_DECISIONS[task_class]
    for index, variant in enumerate(comparison["order"]):
        start_minute = index * 5
        elapsed = {"baseline": 120, "rhize": 90}[variant]
        completed_minute = start_minute + elapsed // 60
        completed_second = elapsed % 60
        result = final_input(
            completed_at=f"2026-08-30T14:{completed_minute:02d}:{completed_second:02d}Z",
            decision=decision,
            agents=[
                {
                    "started_at": f"2026-08-30T14:{start_minute:02d}:05Z",
                    "completed_at": f"2026-08-30T14:{start_minute:02d}:45Z",
                    "status": "completed",
                },
                {
                    "started_at": f"2026-08-30T14:{start_minute:02d}:10Z",
                    "completed_at": f"2026-08-30T14:{start_minute:02d}:50Z",
                    "status": "completed",
                },
            ] if decision == "parallel" else [],
        )
        if not missing_optional:
            result.update(
                tool_calls=8,
                tool_calls_unavailable_reason=None,
                tokens={"input": 10, "output": 10, "cache_read": 0, "cache_write": 0},
                tokens_unavailable_reason=None,
            )
        parallel_metrics.finalize_run(reservations[variant]["run_id"], result, store)


def test_readiness_uses_required_metrics_and_optional_coverage_is_nonblocking(tmp_path):
    for task_class in parallel_metrics.TASK_DECISIONS:
        if task_class == "other":
            continue
        for _ in range(3):
            complete_comparison(tmp_path, task_class=task_class)
    readiness = parallel_metrics.build_report(tmp_path, "controlled")["decision_readiness"]
    assert readiness["decision"] == "ready"
    assert all(metric["status"] == "pass" for metric in readiness["required_metrics"].values())
    assert readiness["optional_metrics"]["tool_calls"]["status"] == "unavailable"
    assert readiness["optional_metrics"]["tokens"]["status"] == "unavailable"


def test_readiness_is_insufficient_with_one_repeat(tmp_path):
    complete_comparison(tmp_path)
    report = parallel_metrics.build_report(tmp_path, "controlled")
    assert report["decision_readiness"]["decision"] == "insufficient_evidence"


def test_cli_begin_finalize_audit_and_report_round_trip(tmp_path):
    store = tmp_path / "store"
    begin_path = tmp_path / "begin.json"
    begin_path.write_text(json.dumps(begin_input()))
    begun = subprocess.run(
        [sys.executable, str(SCRIPT), "--store", str(store), "begin", "--input", str(begin_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    run_id = json.loads(begun.stdout)["run_id"]
    final_path = tmp_path / "final.json"
    final_path.write_text(json.dumps(final_input()))
    subprocess.run(
        [sys.executable, str(SCRIPT), "--store", str(store), "finalize", "--run-id", run_id, "--input", str(final_path)],
        check=True,
    )
    audit = subprocess.run(
        [sys.executable, str(SCRIPT), "--store", str(store), "audit-pending"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(audit.stdout)["pending_count"] == 0
    reported = subprocess.run(
        [sys.executable, str(SCRIPT), "--store", str(store), "report", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(reported.stdout)["evidence"]["observational"]["analyzed_runs"] == 1


def test_skill_contract_is_self_contained_and_provenance_only():
    skill = (REPO / "rhize-ops/skills/parallel-agent-optimization/SKILL.md").read_text()
    modes = (REPO / "rhize-ops/skills/parallel-agent-optimization/references/modes.md").read_text()
    provenance = (REPO / "rhize-ops/skills/parallel-agent-optimization/references/provenance.md").read_text()
    ledger = (REPO / "rhize-ops/skills/SOURCES.md").read_text()
    command = (REPO / "rhize-ops/commands/parallel-optimize.md").read_text()

    assert "consumes:" not in skill
    assert "load `ecc:" not in (skill + modes).lower()
    assert "load `superpowers:" not in (skill + modes).lower()
    assert "--variant" not in skill
    assert "baseline" in modes and "rhize" in modes
    assert "one writer per checkout" in skill
    assert "self-contained" in skill
    assert "ai-stack-version-drift" in provenance
    assert "b44def0f" in provenance and "19689230" in provenance
    assert "**Graph relation:** provenance-only" in ledger
    assert "Pass\n`$ARGUMENTS` unchanged" in command
