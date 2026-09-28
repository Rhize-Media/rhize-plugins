from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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


def node(node_id, *, depends=(), writes=(), resources=(), optional=False, approval=False, effect="none", purpose=None):
    value = {
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
    if purpose is not None:
        value["purpose"] = purpose
    return value


def objective(goal="Ship the goal-ancestry absorption", done_signal="v2 schema and validator ship together"):
    return {"goal": goal, "done_signal": done_signal}


def graph(nodes, *, version="rhize-task-graph-v1", objective_value=None):
    value = {
        "schema_version": version,
        "expected_checkout_fingerprint": "0" * 64,
        "concurrency_budget": 4,
        "coordinator_slots_reserved": 1,
        "context_item_budget": 4,
        "nodes": nodes,
    }
    if objective_value is not None:
        value["objective"] = objective_value
    return value


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


# --- Goal ancestry (task-graph v2) ---


def test_v1_graph_still_validates_with_advisory_objective_missing_warning():
    value = graph([node("work")])
    result = task_graph.validate_graph(value, 4)
    assert result["schema_version"] == "rhize-task-graph-v1"
    assert result["warnings"] == ["objective_missing_v1"]
    assert result["waves"] == [["work"]]


def test_v2_graph_with_objective_and_purpose_validates_without_warning():
    value = graph(
        [node("work", purpose="Delivers the objective's required evidence")],
        version="rhize-task-graph-v2",
        objective_value=objective(),
    )
    result = task_graph.validate_graph(value, 4)
    assert result["schema_version"] == "rhize-task-graph-v2"
    assert result["warnings"] == []
    assert result["waves"] == [["work"]]


def test_v2_graph_missing_objective_is_rejected():
    value = graph([node("work", purpose="Delivers the objective's required evidence")], version="rhize-task-graph-v2")
    with pytest.raises(task_graph.GraphError, match="graph"):
        task_graph.validate_graph(value, 4)


def test_v2_node_missing_purpose_is_rejected():
    value = graph([node("work")], version="rhize-task-graph-v2", objective_value=objective())
    with pytest.raises(task_graph.GraphError, match="nodes\\[0\\]"):
        task_graph.validate_graph(value, 4)


@pytest.mark.parametrize("field", ("goal", "done_signal"))
def test_v2_rejects_whitespace_only_objective_fields(field):
    bad_objective = objective()
    bad_objective[field] = "   "
    value = graph(
        [node("work", purpose="Delivers the objective's required evidence")],
        version="rhize-task-graph-v2",
        objective_value=bad_objective,
    )
    with pytest.raises(task_graph.GraphError, match=f"objective.{field}"):
        task_graph.validate_graph(value, 4)


def test_v2_rejects_whitespace_only_purpose():
    value = graph([node("work", purpose="   ")], version="rhize-task-graph-v2", objective_value=objective())
    with pytest.raises(task_graph.GraphError, match="work.purpose"):
        task_graph.validate_graph(value, 4)


def test_v2_rejects_purpose_equal_to_deliverable_after_normalize_and_casefold():
    value = graph(
        [node("work", purpose="  Bounded WORK Result  ")],
        version="rhize-task-graph-v2",
        objective_value=objective(),
    )
    with pytest.raises(task_graph.GraphError, match="purpose must differ"):
        task_graph.validate_graph(value, 4)


def test_v2_rejects_purpose_equal_to_deliverable_with_internal_whitespace():
    value = graph(
        [node("work", purpose="Bounded   work\tresult")],
        version="rhize-task-graph-v2",
        objective_value=objective(),
    )
    with pytest.raises(task_graph.GraphError, match="purpose must differ"):
        task_graph.validate_graph(value, 4)


def test_next_wave_and_validate_results_work_on_a_v2_graph():
    value = graph(
        [node("work", purpose="Delivers the objective's required evidence")],
        version="rhize-task-graph-v2",
        objective_value=objective(),
    )
    current = state(value)
    validated = task_graph.validate_state(current, value)
    assert task_graph.next_wave(value, validated, 2)["ready"] == ["work"]

    current["nodes"]["work"].update(
        previous_status="running", status="completed", output_contract_satisfied=True, output_count=1
    )
    result = task_graph.validate_results(value, task_graph.validate_state(current, value))
    assert result["synthesis_allowed"] is True


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_v2_validator_cli_never_echoes_objective_or_purpose_text(tmp_path):
    marker_goal = "SECRET-GOAL-MARKER-12345"
    marker_done = "SECRET-DONE-MARKER-67890"
    marker_purpose = "SECRET-PURPOSE-MARKER-ABCDE"
    value = graph(
        [node("work", purpose=marker_purpose)],
        version="rhize-task-graph-v2",
        objective_value={"goal": marker_goal, "done_signal": marker_done},
    )
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(value))
    host_path = tmp_path / "host.json"
    host_path.write_text(json.dumps(host()))
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state(value)))

    validated = _run_cli("validate", "--graph", str(graph_path), "--capabilities", str(host_path))
    assert validated.returncode == 0, validated.stdout + validated.stderr

    next_wave_result = _run_cli(
        "next-wave", "--graph", str(graph_path), "--capabilities", str(host_path), "--state", str(state_path)
    )
    assert next_wave_result.returncode == 0, next_wave_result.stdout + next_wave_result.stderr

    results = _run_cli("validate-results", "--graph", str(graph_path), "--state", str(state_path))
    assert results.returncode == 0, results.stdout + results.stderr

    for marker in (marker_goal, marker_done, marker_purpose):
        assert marker not in validated.stdout and marker not in validated.stderr
        assert marker not in next_wave_result.stdout and marker not in next_wave_result.stderr
        assert marker not in results.stdout and marker not in results.stderr


# --- Isolated-worktree writers (task-graph v2 `isolation`) ---------------------------------

ROOT_A = "a" * 64
ROOT_B = "b" * 64
ROOT_C = "c" * 64


def isolated(node_value, root, kind="worktree"):
    node_value["isolation"] = {"kind": kind, "root_fingerprint": root}
    return node_value


def v2_node(node_id, **kwargs):
    return node(node_id, purpose=f"Lane {node_id} advances the shared objective", **kwargs)


SHARED_ROOT = "d" * 64


def v2_graph(nodes, *, shared_root=SHARED_ROOT, **overrides):
    value = graph(nodes, version="rhize-task-graph-v2", objective_value=objective())
    if shared_root is not None:
        value["shared_root_fingerprint"] = shared_root
    value.update(overrides)
    return value


def test_isolated_writers_with_distinct_roots_share_a_wave_without_write_locks():
    value = v2_graph(
        [
            isolated(v2_node("repo_a", writes=("src",)), ROOT_A),
            isolated(v2_node("repo_b", writes=("src",)), ROOT_B),
            isolated(v2_node("repo_c", writes=("src",)), ROOT_C),
        ]
    )
    result = task_graph.validate_graph(value, 4, isolation_supported=True)
    assert result["edge_counts"]["write_lock"] == 0
    assert result["waves"] == [["repo_a", "repo_b", "repo_c"]]
    assert result["isolated_write_roots"] == 3


def test_isolated_waves_still_respect_the_worker_cap():
    value = v2_graph(
        [isolated(v2_node(f"repo_{index}", writes=("src",)), str(index) * 64) for index in range(1, 5)]
    )
    result = task_graph.validate_graph(value, 4, isolation_supported=True)
    assert result["host_worker_cap"] == 3
    assert [len(wave) for wave in result["waves"]] == [3, 1]


def test_writers_sharing_an_isolated_root_still_serialize():
    value = v2_graph(
        [isolated(v2_node("a", writes=("a",)), ROOT_A), isolated(v2_node("b", writes=("b",)), ROOT_A)]
    )
    result = task_graph.validate_graph(value, 4, isolation_supported=True)
    assert result["edge_counts"]["write_lock"] == 1
    assert result["waves"] == [["a"], ["b"]]
    assert result["isolated_write_roots"] == 1


def test_shared_checkout_writer_and_isolated_writer_do_not_lock_each_other():
    value = v2_graph([v2_node("local", writes=("src",)), isolated(v2_node("remote", writes=("src",)), ROOT_A)])
    result = task_graph.validate_graph(value, 4, isolation_supported=True)
    assert result["edge_counts"]["write_lock"] == 0
    assert result["waves"] == [["local", "remote"]]


def test_overlapping_territories_under_the_same_root_still_require_order():
    value = v2_graph(
        [isolated(v2_node("a", writes=("src",)), ROOT_A), isolated(v2_node("b", writes=("src/x.py",)), ROOT_A)]
    )
    with pytest.raises(task_graph.GraphError, match="write_lock"):
        task_graph.validate_graph(value, 4, isolation_supported=True)


def test_isolation_requires_verified_host_support_and_fails_closed_by_default():
    value = v2_graph([isolated(v2_node("a", writes=("src",)), ROOT_A)])
    with pytest.raises(task_graph.GraphError, match="isolated_worktrees"):
        task_graph.validate_graph(value, 4)
    with pytest.raises(task_graph.GraphError, match="isolated_worktrees"):
        task_graph.validate_graph(value, 4, isolation_supported=False)


def test_isolation_root_cannot_be_the_shared_checkout():
    value = v2_graph([isolated(v2_node("a", writes=("src",)), "0" * 64)])
    with pytest.raises(task_graph.GraphError, match="shared checkout"):
        task_graph.validate_graph(value, 4, isolation_supported=True)


@pytest.mark.parametrize(
    "isolation",
    (
        {"kind": "worktree", "root_fingerprint": "not-a-hash"},
        {"kind": "container", "root_fingerprint": "a" * 64},
        {"kind": "worktree"},
        {"kind": "worktree", "root_fingerprint": "a" * 64, "path": "/tmp/x"},
    ),
)
def test_malformed_isolation_is_rejected(isolation):
    item = v2_node("a", writes=("src",))
    item["isolation"] = isolation
    with pytest.raises(task_graph.GraphError):
        task_graph.validate_graph(v2_graph([item]), 4, isolation_supported=True)


def test_copy_isolation_kind_is_accepted():
    value = v2_graph(
        [isolated(v2_node("a", writes=("src",)), ROOT_A, kind="copy"), isolated(v2_node("b", writes=("src",)), ROOT_B)]
    )
    assert task_graph.validate_graph(value, 4, isolation_supported=True)["waves"] == [["a", "b"]]


def test_v1_graph_rejects_isolation():
    item = node("a", writes=("src",))
    item["isolation"] = {"kind": "worktree", "root_fingerprint": ROOT_A}
    with pytest.raises(task_graph.GraphError):
        task_graph.validate_graph(graph([item]), 4, isolation_supported=True)


def test_v2_graph_without_isolation_is_unchanged():
    value = v2_graph([v2_node("a", writes=("a",)), v2_node("b", writes=("b",))])
    result = task_graph.validate_graph(value, 4)
    assert result["edge_counts"]["write_lock"] == 1
    assert result["waves"] == [["a"], ["b"]]
    assert result["isolated_write_roots"] == 0


def test_next_wave_dispatches_isolated_writers_together():
    value = v2_graph(
        [isolated(v2_node("repo_a", writes=("src",)), ROOT_A), isolated(v2_node("repo_b", writes=("src",)), ROOT_B)]
    )
    validated = task_graph.validate_state(state(value), value)
    assert task_graph.next_wave(value, validated, 3)["ready"] == ["repo_a", "repo_b"]


def test_cli_validate_uses_host_isolation_support_and_never_echoes_fingerprints(tmp_path):
    value = v2_graph(
        [isolated(v2_node("repo_a", writes=("src",)), ROOT_A), isolated(v2_node("repo_b", writes=("src",)), ROOT_B)]
    )
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(value))
    supported = tmp_path / "host.json"
    supported.write_text(json.dumps(host()))
    unsupported_host = host()
    unsupported_host["isolated_worktrees"] = {"status": "unknown", "supported": None}
    unsupported = tmp_path / "host-unknown.json"
    unsupported.write_text(json.dumps(unsupported_host))

    ok = _run_cli("validate", "--graph", str(graph_path), "--capabilities", str(supported))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert json.loads(ok.stdout)["waves"] == [["repo_a", "repo_b"]]
    assert ROOT_A not in ok.stdout and ROOT_B not in ok.stdout

    refused = _run_cli("validate", "--graph", str(graph_path), "--capabilities", str(unsupported))
    assert refused.returncode == 2
    assert "isolated_worktrees" in refused.stderr

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state(value)))
    results = _run_cli("validate-results", "--graph", str(graph_path), "--state", str(state_path))
    assert results.returncode == 0, results.stdout + results.stderr


def _identity(path):
    import hashlib
    import os

    info = os.stat(path)
    return hashlib.sha256(f"{info.st_dev}:{info.st_ino}".encode()).hexdigest()


def test_root_fingerprint_hashes_the_git_toplevel_filesystem_identity(tmp_path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    subprocess.run(["git", "-c", "core.excludesFile=/dev/null", "init", "-q", str(repo)], check=True)
    top = _run_cli("root-fingerprint", "--path", str(repo))
    nested = _run_cli("root-fingerprint", "--path", str(repo / "sub"))
    assert top.returncode == 0, top.stderr
    assert json.loads(top.stdout) == {"root_fingerprint": _identity(repo)}
    assert json.loads(nested.stdout) == {"root_fingerprint": _identity(repo)}

    plain = tmp_path / "copy"
    plain.mkdir()
    assert json.loads(_run_cli("root-fingerprint", "--path", str(plain)).stdout)["root_fingerprint"] == _identity(plain)


def test_root_fingerprint_collapses_symlink_and_case_aliases(tmp_path):
    real = tmp_path / "RealCopy"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    expected = json.loads(_run_cli("root-fingerprint", "--path", str(real)).stdout)["root_fingerprint"]
    assert json.loads(_run_cli("root-fingerprint", "--path", str(link)).stdout)["root_fingerprint"] == expected
    alias = tmp_path / "realcopy"
    if alias.exists():  # case-insensitive filesystem (default macOS APFS)
        assert json.loads(_run_cli("root-fingerprint", "--path", str(alias)).stdout)["root_fingerprint"] == expected


def test_isolation_requires_a_shared_root_fingerprint():
    value = v2_graph([isolated(v2_node("a", writes=("src",)), ROOT_A)], shared_root=None)
    with pytest.raises(task_graph.GraphError, match="shared_root_fingerprint"):
        task_graph.validate_graph(value, 4, isolation_supported=True)


def test_isolation_root_cannot_be_the_shared_directory():
    value = v2_graph([isolated(v2_node("a", writes=("src",)), SHARED_ROOT)])
    with pytest.raises(task_graph.GraphError, match="shared checkout"):
        task_graph.validate_graph(value, 4, isolation_supported=True)


def test_malformed_shared_root_fingerprint_is_rejected_and_v1_rejects_it():
    with pytest.raises(task_graph.GraphError):
        task_graph.validate_graph(v2_graph([v2_node("a")], shared_root="nope"), 4)
    legacy = graph([node("a")])
    legacy["shared_root_fingerprint"] = SHARED_ROOT
    with pytest.raises(task_graph.GraphError):
        task_graph.validate_graph(legacy, 4)
