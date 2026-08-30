from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-ops/skills/parallel-agent-optimization/scripts/validate_task_graph.py"
SPEC = importlib.util.spec_from_file_location("validate_task_graph", SCRIPT)
assert SPEC and SPEC.loader
task_graph = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(task_graph)


def host(status="verified", value=4):
    return {
        "schema_version": "rhize-host-capability-v1",
        "host": "codex",
        "concurrency": {"status": status, "value": value},
        "cancellation": {"status": "verified", "supported": True},
        "waiting": {"status": "verified", "supported": True},
        "isolated_worktrees": {"status": "verified", "supported": True},
    }


def node(node_id, *, depends=(), writes=(), resources=(), optional=False, approval=False, effect="none"):
    return {
        "id": node_id,
        "deliverable": f"bounded {node_id} result",
        "inputs": [],
        "output_contract": {"kind": "json", "max_items": 2},
        "depends_on": list(depends),
        "reads": [],
        "writes": list(writes),
        "resources": [{"name": name, "capacity": capacity} for name, capacity in resources],
        "requires_approval": approval,
        "external_effect": effect,
        "optional": optional,
        "timeout_seconds": 60,
        "retry": {"max_attempts": 1, "idempotent": False, "renew_approval": False},
        "verification_owner": "coordinator",
    }


def graph(nodes):
    return {
        "schema_version": "rhize-task-graph-v1",
        "expected_checkout_fingerprint": "0" * 64,
        "concurrency_budget": 4,
        "coordinator_slots_reserved": 1,
        "context_item_budget": 4,
        "nodes": nodes,
    }


def state(value):
    return {
        "schema_version": "rhize-task-state-v1",
        "graph_fingerprint": task_graph.fingerprint(value),
        "checkout_fingerprint": value["expected_checkout_fingerprint"],
        "checkout_revalidated": True,
        "approvals_revalidated": False,
        "external_state_revalidated": False,
        "nodes": {
            item["id"]: {
                "previous_status": "pending",
                "status": "pending",
                "output_count": 0,
                "output_contract_satisfied": False,
                "cleanup_ok": True,
            }
            for item in value["nodes"]
        },
    }


def test_valid_graph_produces_deterministic_parallel_then_join_waves():
    value = graph([node("research_a"), node("research_b"), node("join", depends=("research_a", "research_b"))])
    _, host_cap = task_graph.validate_host(host())
    result = task_graph.validate_graph(value, host_cap)
    assert result["waves"] == [["research_a", "research_b"], ["join"]]
    assert result["edge_counts"]["data"] == 2
    assert result["host_worker_cap"] == 3


def test_unknown_host_concurrency_degrades_to_one_worker():
    value = graph([node("a"), node("b")])
    _, host_cap = task_graph.validate_host(host("unknown", None))
    assert task_graph.validate_graph(value, host_cap)["waves"] == [["a"], ["b"]]


def test_graph_cannot_consume_the_reserved_coordinator_slot():
    value = graph([node("work")])
    value.update(concurrency_budget=1, coordinator_slots_reserved=1)
    with pytest.raises(task_graph.GraphError, match="coordinator reservation"):
        task_graph.validate_graph(value, 4)


def test_hidden_write_collision_requires_explicit_order():
    nodes = [node("a", writes=("src",)), node("b", writes=("src/file.py",))]
    with pytest.raises(task_graph.GraphError, match="write_lock"):
        task_graph.validate_graph(graph(nodes), 4)


def test_single_capacity_resource_derives_edge_and_separate_waves():
    nodes = [node("a", resources=(("api", 1),)), node("b", resources=(("api", 1),))]
    result = task_graph.validate_graph(graph(nodes), 4)
    assert result["edge_counts"]["resource_pool"] == 1
    assert result["waves"] == [["a"], ["b"]]


def test_disjoint_shared_checkout_writers_are_still_serialized():
    result = task_graph.validate_graph(graph([node("a", writes=("a",)), node("b", writes=("b",))]), 4)
    assert result["edge_counts"]["write_lock"] == 1
    assert result["waves"] == [["a"], ["b"]]


def test_retry_cannot_infer_authority_for_effectful_node():
    effect = node("publish", approval=True, effect="external_write")
    effect["retry"] = {"max_attempts": 2, "idempotent": True, "renew_approval": False}
    with pytest.raises(task_graph.GraphError, match="renewed authority"):
        task_graph.validate_graph(graph([effect]), 4)


def test_next_wave_waits_for_approval_and_external_state_revalidation():
    value = graph([node("publish", approval=True, effect="external_write")])
    current = state(value)
    assert task_graph.next_wave(value, task_graph.validate_state(current, value), 2)["ready"] == []
    current["approvals_revalidated"] = True
    current["external_state_revalidated"] = True
    assert task_graph.next_wave(value, task_graph.validate_state(current, value), 2)["ready"] == ["publish"]


def test_effectful_completion_requires_revalidated_authority_and_external_state():
    value = graph([node("publish", approval=True, effect="external_write")])
    current = state(value)
    current["nodes"]["publish"].update(
        previous_status="running",
        status="completed",
        output_contract_satisfied=True,
    )
    with pytest.raises(task_graph.GraphError, match="approval must be revalidated"):
        task_graph.validate_state(current, value)
    current["approvals_revalidated"] = True
    with pytest.raises(task_graph.GraphError, match="external state must be revalidated"):
        task_graph.validate_state(current, value)
    current["external_state_revalidated"] = True
    result = task_graph.validate_results(value, task_graph.validate_state(current, value))
    assert result["synthesis_allowed"] is True
    assert result["approval_revalidation_required"] is True
    assert result["external_revalidation_required"] is True
    current["nodes"]["publish"]["previous_status"] = "completed"
    current["approvals_revalidated"] = False
    with pytest.raises(task_graph.GraphError, match="approval must be revalidated"):
        task_graph.validate_state(current, value)


def test_checkout_drift_aborts_wave_before_dispatch():
    value = graph([node("work")])
    current = state(value)
    current["checkout_fingerprint"] = "f" * 64
    with pytest.raises(task_graph.GraphError, match="drifted"):
        task_graph.validate_state(current, value)


@pytest.mark.parametrize("terminal", ("failed", "cancelled", "timed_out"))
def test_failed_or_closed_dependency_deterministically_blocks_downstream(terminal):
    value = graph([node("source"), node("dependent", depends=("source",))])
    current = state(value)
    current["nodes"]["source"].update(previous_status="running", status=terminal)
    validated = task_graph.validate_state(current, value)
    assert task_graph.next_wave(value, validated, 2)["blocked_dependency"] == ["dependent"]


def test_skipped_optional_dependency_blocks_required_consumer_before_scheduling():
    value = graph([
        node("source", optional=True),
        node("dependent", depends=("source",)),
    ])
    current = state(value)
    current["nodes"]["source"].update(status="skipped_optional")

    validated = task_graph.validate_state(current, value)
    assert task_graph.next_wave(value, validated, 2)["blocked_dependency"] == ["dependent"]


def test_skipped_optional_dependency_rejects_already_started_required_consumer():
    value = graph([
        node("source", optional=True),
        node("dependent", depends=("source",)),
    ])
    current = state(value)
    current["nodes"]["source"].update(status="skipped_optional")
    current["nodes"]["dependent"].update(previous_status="ready", status="running")

    with pytest.raises(task_graph.GraphError, match="dependencies must be complete"):
        task_graph.validate_state(current, value)


@pytest.mark.parametrize("dependent_status", ("running", "completed", "failed"))
def test_execution_state_rejects_incomplete_dependency_closure(dependent_status):
    value = graph([
        node("source", optional=True),
        node("dependent", depends=("source",)),
    ])
    current = state(value)
    current["nodes"]["source"].update(previous_status="running", status="failed")
    current["nodes"]["dependent"].update(
        previous_status="running",
        status=dependent_status,
        output_contract_satisfied=dependent_status == "completed",
    )

    with pytest.raises(task_graph.GraphError, match="dependencies must be complete"):
        task_graph.validate_state(current, value)


def test_invalid_state_transition_is_rejected():
    value = graph([node("work")])
    current = state(value)
    current["nodes"]["work"].update(previous_status="completed", status="running")
    with pytest.raises(task_graph.GraphError, match="invalid state transition"):
        task_graph.validate_state(current, value)


def test_missing_required_result_and_cleanup_failure_block_synthesis():
    value = graph([node("required"), node("optional", optional=True)])
    current = state(value)
    current["nodes"]["required"].update(previous_status="running", status="failed", cleanup_ok=False)
    current["nodes"]["optional"].update(status="skipped_optional")
    result = task_graph.validate_results(value, task_graph.validate_state(current, value))
    assert result["synthesis_allowed"] is False
    assert result["missing_required_count"] == 1
    assert result["required_completed"] == 0
    assert result["cleanup_failed"] == 1


def test_unfinished_optional_node_blocks_partial_synthesis_until_explicitly_skipped():
    value = graph([node("required"), node("optional", optional=True)])
    current = state(value)
    current["nodes"]["required"].update(previous_status="running", status="completed", output_contract_satisfied=True)
    result = task_graph.validate_results(value, task_graph.validate_state(current, value))
    assert result["synthesis_allowed"] is False
    assert result["unfinished"] == 1


def test_large_result_bound_requires_layered_fan_in():
    value = graph([node(f"read_{index}") for index in range(5)])
    value["context_item_budget"] = 2
    assert task_graph.validate_graph(value, 4)["fan_in_levels"] >= 2


def test_eval_task_graph_fixtures_cover_resource_partial_and_layered_cases():
    fixtures = REPO / "evals/parallel-agent-skills/fixtures/task-graphs"
    shared = json.loads((fixtures / "shared-resource.json").read_text())
    partial = json.loads((fixtures / "partial-fan-in.json").read_text())
    layered = json.loads((fixtures / "layered-fan-in.json").read_text())
    assert task_graph.validate_graph(shared, 4)["waves"] == [["api_a"], ["api_b"]]
    assert task_graph.validate_graph(partial, 4)["required"] == 1
    assert task_graph.validate_graph(layered, 4)["fan_in_levels"] >= 2


def test_graph_response_contains_no_task_content():
    value = graph([node("safe")])
    result = task_graph.validate_graph(value, 4)
    serialized = str(result)
    assert "bounded safe result" not in serialized
    assert "reads" not in serialized and "writes" not in serialized


def test_claude_and_codex_discover_one_canonical_graph_skill():
    skill = (REPO / "rhize-ops/skills/parallel-agent-optimization/SKILL.md").read_text()
    command = (REPO / "rhize-ops/commands/parallel-optimize.md").read_text()
    codex = json.loads((REPO / "rhize-ops/.codex-plugin/plugin.json").read_text())
    agent = (REPO / "rhize-ops/skills/parallel-agent-optimization/agents/openai.yaml").read_text()
    assert "validate_task_graph.py" in skill
    assert "Pass\n`$ARGUMENTS` unchanged" in command
    assert codex["skills"] == "./skills/"
    assert "$parallel-agent-optimization" in agent
