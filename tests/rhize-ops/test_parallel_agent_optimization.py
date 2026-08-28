from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO
    / "rhize-ops"
    / "skills"
    / "parallel-agent-optimization"
    / "scripts"
    / "parallel_metrics.py"
)
SPEC = importlib.util.spec_from_file_location("parallel_metrics", SCRIPT)
assert SPEC and SPEC.loader
parallel_metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parallel_metrics)


def receipt(**overrides):
    value = {
        "schema_version": 1,
        "evidence_class": "observational",
        "variant": "rhize",
        "resource_used": "ecc",
        "task_class": "mixed_verification",
        "started_at": "2026-08-27T14:00:00-04:00",
        "completed_at": "2026-08-27T14:02:00-04:00",
        "decision": "parallel",
        "expected_decision": None,
        "lanes_planned": 2,
        "agents": [
            {
                "started_at": "2026-08-27T14:00:10-04:00",
                "completed_at": "2026-08-27T14:01:10-04:00",
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
        "isolated": False,
        "live_mutation": False,
        "one_writer_enforced": True,
        "comparison_id": None,
    }
    value.update(overrides)
    return value


def controlled(variant="baseline", resource="none", comparison_id=None, **overrides):
    values = {
        "evidence_class": "controlled",
        "variant": variant,
        "resource_used": resource,
        "expected_decision": "parallel",
        "isolated": True,
        "live_mutation": False,
        "comparison_id": comparison_id or str(uuid.uuid4()),
    }
    values.update(overrides)
    return receipt(**values)


def test_append_writes_private_observational_receipt(tmp_path):
    stored = parallel_metrics.validate_receipt(receipt())
    path = parallel_metrics.append_receipt(stored, tmp_path / "store")

    assert path.parent.name == "observational"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    row = json.loads(path.read_text())
    assert row["variant"] == "rhize"
    assert row["actual_overlap"] is False
    assert row["verification_completeness"] == 1.0
    assert row["routing_appropriate"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("isolated", False),
        ("live_mutation", True),
        ("one_writer_enforced", False),
        ("expected_decision", None),
        ("comparison_id", None),
        ("correctness_pass", None),
        ("verification", {"required": 0, "completed": 0, "passed": 0}),
    ),
)
def test_controlled_receipt_requires_safe_replay_boundary(field, value):
    data = controlled()
    data[field] = value
    with pytest.raises(parallel_metrics.ReceiptError):
        parallel_metrics.validate_receipt(data)


@pytest.mark.parametrize("variant", ("ecc", "superpowers"))
def test_controlled_candidate_arm_cannot_claim_an_unavailable_resource(variant):
    with pytest.raises(parallel_metrics.ReceiptError, match="requires resource"):
        parallel_metrics.validate_receipt(controlled(variant=variant, resource="none"))


@pytest.mark.parametrize("forbidden", ("prompt", "repository_path", "session_id", "agent_name"))
def test_receipt_rejects_free_text_or_identifying_fields(forbidden):
    data = receipt()
    data[forbidden] = "must-not-land"
    with pytest.raises(parallel_metrics.ReceiptError, match="unknown"):
        parallel_metrics.validate_receipt(data)


def test_parallelism_is_derived_from_overlapping_intervals():
    data = receipt(
        agents=[
            {
                "started_at": "2026-08-27T14:00:10-04:00",
                "completed_at": "2026-08-27T14:01:10-04:00",
                "status": "completed",
            },
            {
                "started_at": "2026-08-27T14:00:40-04:00",
                "completed_at": "2026-08-27T14:01:40-04:00",
                "status": "completed",
            },
        ]
    )
    stored = parallel_metrics.validate_receipt(data)
    assert stored["actual_overlap"] is True
    assert stored["concurrent_agent_ms"] == 30_000
    assert stored["max_concurrency"] == 2


def test_parallelism_handles_triple_overlap_and_adjacent_intervals():
    agents = []
    for started_at, completed_at in (
        ("2026-08-27T14:00:10-04:00", "2026-08-27T14:00:50-04:00"),
        ("2026-08-27T14:00:20-04:00", "2026-08-27T14:00:40-04:00"),
        ("2026-08-27T14:00:30-04:00", "2026-08-27T14:00:50-04:00"),
        ("2026-08-27T14:00:50-04:00", "2026-08-27T14:01:10-04:00"),
    ):
        agents.append({"started_at": started_at, "completed_at": completed_at, "status": "completed"})
    stored = parallel_metrics.validate_receipt(receipt(agents=agents))
    assert stored["actual_overlap"] is True
    assert stored["concurrent_agent_ms"] == 30_000
    assert stored["max_concurrency"] == 3


def test_assignment_balances_observational_variants(tmp_path):
    store = tmp_path / "store"
    first = parallel_metrics.choose_observational_variant(store)
    assert first["variant"] == "baseline"

    for variant, resource in (("baseline", "none"), ("ecc", "ecc")):
        row = parallel_metrics.validate_receipt(receipt(variant=variant, resource_used=resource))
        parallel_metrics.append_receipt(row, store)

    assigned = parallel_metrics.choose_observational_variant(store)
    assert assigned["variant"] == "superpowers"
    assert assigned["counts"] == {"baseline": 1, "ecc": 1, "superpowers": 0, "rhize": 0}


def test_new_comparison_has_four_separate_arms_and_no_combined_arm(tmp_path):
    store = tmp_path / "store"
    comparison = parallel_metrics.new_comparison(store)
    next_comparison = parallel_metrics.new_comparison(store)
    assert set(comparison["order"]) == {"baseline", "ecc", "superpowers", "rhize"}
    assert len(comparison["order"]) == 4
    assert "ecc+superpowers" not in comparison["order"]
    assert uuid.UUID(comparison["comparison_id"]).version == 4
    assert next_comparison["order"] == ["ecc", "superpowers", "rhize", "baseline"]
    reservations = store / "comparison-reservations.jsonl"
    assert stat.S_IMODE(reservations.stat().st_mode) == 0o600
    assert len(reservations.read_text().splitlines()) == 2


def test_report_keeps_observational_and_controlled_evidence_separate(tmp_path):
    store = tmp_path / "store"
    observational = parallel_metrics.validate_receipt(receipt())
    controlled_row = parallel_metrics.validate_receipt(controlled())
    parallel_metrics.append_receipt(observational, store)
    parallel_metrics.append_receipt(controlled_row, store)

    report = parallel_metrics.build_report(store, "all")
    assert report["evidence"]["observational"]["runs"] == 1
    assert report["evidence"]["controlled"]["stored_runs"] == 1
    assert report["evidence"]["controlled"]["runs"] == 0
    assert report["evidence"]["controlled"]["excluded_receipt_count"] == 1
    assert "runs" not in report
    markdown = parallel_metrics.render_markdown(report)
    assert "## Observational" in markdown
    assert "## Controlled" in markdown
    assert "overall" not in markdown.lower()


def test_complete_comparison_requires_each_distinct_arm(tmp_path):
    store = tmp_path / "store"
    comparison_id = parallel_metrics.new_comparison(store)["comparison_id"]
    for _ in range(4):
        row = parallel_metrics.validate_receipt(
            controlled(variant="baseline", resource="none", comparison_id=comparison_id)
        )
        parallel_metrics.append_receipt(row, store)

    section = parallel_metrics.build_report(store, "controlled")["evidence"]["controlled"]
    assert section["comparison_count"] == 1
    assert section["complete_comparison_count"] == 0
    assert section["duplicate_comparison_count"] == 1
    assert section["runs"] == 0
    assert section["excluded_receipt_count"] == 4


def test_controlled_metrics_include_only_complete_matched_comparisons(tmp_path):
    store = tmp_path / "store"
    reservation = parallel_metrics.new_comparison(store)
    resources = {"baseline": "none", "ecc": "ecc", "superpowers": "superpowers", "rhize": "none"}
    for position, variant in enumerate(reservation["order"]):
        start_minute = position * 2
        row = parallel_metrics.validate_receipt(
            controlled(
                variant=variant,
                resource=resources[variant],
                comparison_id=reservation["comparison_id"],
                started_at=f"2026-08-27T14:{start_minute:02d}:00-04:00",
                completed_at=f"2026-08-27T14:{start_minute + 1:02d}:00-04:00",
                agents=[],
            )
        )
        parallel_metrics.append_receipt(row, store)

    section = parallel_metrics.build_report(store, "controlled")["evidence"]["controlled"]
    assert section["stored_runs"] == 4
    assert section["runs"] == 4
    assert section["complete_comparison_count"] == 1
    assert section["excluded_receipt_count"] == 0
    assert all(section["variants"][variant]["runs"] == 1 for variant in parallel_metrics.VARIANTS)


def test_controlled_metrics_exclude_wrong_order_or_overlapping_arms(tmp_path):
    store = tmp_path / "store"
    resources = {"baseline": "none", "ecc": "ecc", "superpowers": "superpowers", "rhize": "none"}

    wrong_order = parallel_metrics.new_comparison(store)
    for position, variant in enumerate(reversed(wrong_order["order"])):
        start_minute = position * 2
        row = parallel_metrics.validate_receipt(
            controlled(
                variant=variant,
                resource=resources[variant],
                comparison_id=wrong_order["comparison_id"],
                started_at=f"2026-08-27T14:{start_minute:02d}:00-04:00",
                completed_at=f"2026-08-27T14:{start_minute + 1:02d}:00-04:00",
                agents=[],
            )
        )
        parallel_metrics.append_receipt(row, store)

    overlapping = parallel_metrics.new_comparison(store)
    for variant in overlapping["order"]:
        row = parallel_metrics.validate_receipt(
            controlled(
                variant=variant,
                resource=resources[variant],
                comparison_id=overlapping["comparison_id"],
            )
        )
        parallel_metrics.append_receipt(row, store)

    section = parallel_metrics.build_report(store, "controlled")["evidence"]["controlled"]
    assert section["comparison_count"] == 2
    assert section["complete_comparison_count"] == 0
    assert section["invalid_comparison_count"] == 2
    assert section["runs"] == 0
    assert section["excluded_receipt_count"] == 8


def test_controlled_metrics_exclude_unreserved_or_mismatched_groups(tmp_path):
    store = tmp_path / "store"
    reserved_id = parallel_metrics.new_comparison(store)["comparison_id"]
    unreserved_id = str(uuid.uuid4())
    resources = {
        "baseline": "none",
        "ecc": "ecc",
        "superpowers": "superpowers",
        "rhize": "none",
    }
    for comparison_id in (reserved_id, unreserved_id):
        for variant in parallel_metrics.VARIANTS:
            overrides = {}
            if comparison_id == reserved_id and variant == "rhize":
                overrides = {
                    "task_class": "gated_live",
                    "expected_decision": "gated",
                    "verification": {"required": 9, "completed": 9, "passed": 9},
                    "decision": "gated",
                }
            row = parallel_metrics.validate_receipt(
                controlled(
                    variant=variant,
                    resource=resources[variant],
                    comparison_id=comparison_id,
                    **overrides,
                )
            )
            parallel_metrics.append_receipt(row, store)

    section = parallel_metrics.build_report(store, "controlled")["evidence"]["controlled"]
    assert section["comparison_count"] == 2
    assert section["complete_comparison_count"] == 0
    assert section["invalid_comparison_count"] == 1
    assert section["unreserved_comparison_count"] == 1
    assert section["runs"] == 0
    assert section["excluded_receipt_count"] == 8


def test_skill_and_command_preserve_safety_and_provenance_contracts():
    skill = (REPO / "rhize-ops/skills/parallel-agent-optimization/SKILL.md").read_text()
    command = (REPO / "rhize-ops/commands/parallel-optimize.md").read_text()
    provenance = (
        REPO / "rhize-ops/skills/parallel-agent-optimization/references/provenance.md"
    ).read_text()
    ledger = (REPO / "rhize-ops/skills/SOURCES.md").read_text()
    skill_map = json.loads((REPO / "generated/skill-map.static.json").read_text())

    assert "Never duplicate a live task" in skill
    assert "one writer per checkout" in skill
    assert "Never load `ecc:parallel-execution-optimizer` and `superpowers:dispatching-parallel-agents`" in skill
    assert "observational and controlled evidence separate" in skill
    assert "no upstream code or prose copied" in provenance
    assert "ai-stack-version-drift" in provenance
    assert "**Graph relation:** consumes" in ledger
    assert "**Additional source:**" in ledger
    assert "Pass\n`$ARGUMENTS` unchanged" in command
    edges = [edge for edge in skill_map["edges"] if edge["from"] == "skill:rhize-ops/parallel-agent-optimization"]
    assert not any(edge["type"] == "fork-of" for edge in edges)
    assert {
        edge["to"] for edge in edges if edge["type"] == "depends-on"
    } == {
        "external:ecc-parallel-execution-optimizer",
        "external:superpowers-dispatching-parallel-agents",
    }


def test_cli_append_then_report_round_trip(tmp_path):
    input_path = tmp_path / "receipt.json"
    input_path.write_text(json.dumps(receipt()), encoding="utf-8")
    store = tmp_path / "store"

    appended = subprocess.run(
        [sys.executable, str(SCRIPT), "--store", str(store), "append", "--input", str(input_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(appended.stdout)["evidence_class"] == "observational"

    reported = subprocess.run(
        [sys.executable, str(SCRIPT), "--store", str(store), "report", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(reported.stdout)
    assert report["evidence"]["observational"]["runs"] == 1
    assert report["evidence"]["controlled"]["runs"] == 0


def test_partial_writes_are_completed_under_lock(tmp_path, monkeypatch):
    real_write = parallel_metrics.os.write

    def partial_write(descriptor, payload):
        return real_write(descriptor, payload[: max(1, len(payload) // 3)])

    monkeypatch.setattr(parallel_metrics.os, "write", partial_write)
    stored = parallel_metrics.validate_receipt(receipt())
    path = parallel_metrics.append_receipt(stored, tmp_path / "store")
    assert json.loads(path.read_text())["run_id"] == stored["run_id"]


def test_concurrent_cli_appends_remain_valid_json_lines(tmp_path):
    store = tmp_path / "store"
    processes = []
    for index in range(8):
        input_path = tmp_path / f"receipt-{index}.json"
        input_path.write_text(json.dumps(receipt()), encoding="utf-8")
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--store",
                    str(store),
                    "append",
                    "--input",
                    str(input_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )
    for process in processes:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        assert json.loads(stdout)["evidence_class"] == "observational"

    paths = list((store / "observational").glob("*.jsonl"))
    assert len(paths) == 1
    rows = [json.loads(line) for line in paths[0].read_text().splitlines()]
    assert len(rows) == 8
    assert len({row["run_id"] for row in rows}) == 8
