#!/usr/bin/env python3
"""Validate and advance an ephemeral Rhize task graph without executing work."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


GRAPH_VERSION = "rhize-task-graph-v1"
HOST_VERSION = "rhize-host-capability-v1"
STATE_VERSION = "rhize-task-state-v1"
STATUSES = {
    "pending", "ready", "running", "completed", "failed", "cancelled", "timed_out",
    "blocked_dependency", "skipped_optional",
}
STATUS_TRANSITIONS = {
    "pending": {"pending", "ready", "blocked_dependency", "cancelled", "skipped_optional"},
    "ready": {"ready", "running", "cancelled", "skipped_optional"},
    "running": {"running", "completed", "failed", "cancelled", "timed_out"},
    "completed": {"completed"},
    "failed": {"failed"},
    "cancelled": {"cancelled"},
    "timed_out": {"timed_out"},
    "blocked_dependency": {"blocked_dependency"},
    "skipped_optional": {"skipped_optional"},
}
EXTERNAL_EFFECTS = {"none", "external_read", "external_write", "paid_call", "production"}
NODE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class GraphError(ValueError):
    """The graph, capability profile, or state violates the contract."""


def exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GraphError(f"{label} must be an object")
    if set(value) != keys:
        raise GraphError(f"{label} keys invalid")
    return value


def positive(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GraphError(f"{label} must be a positive integer")
    return value


def fingerprint(graph: dict[str, Any]) -> str:
    payload = json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def is_ancestor(nodes: dict[str, dict[str, Any]], ancestor: str, descendant: str) -> bool:
    pending = list(nodes[descendant]["depends_on"])
    seen: set[str] = set()
    while pending:
        node_id = pending.pop()
        if node_id == ancestor:
            return True
        if node_id not in seen:
            seen.add(node_id)
            pending.extend(nodes[node_id]["depends_on"])
    return False


def territories_overlap(left: str, right: str) -> bool:
    left = left.rstrip("/")
    right = right.rstrip("/")
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def bounded_wave(ready: list[str], nodes: dict[str, dict[str, Any]], cap: int) -> list[str]:
    wave: list[str] = []
    usage: Counter[str] = Counter()
    for node_id in ready:
        node = nodes[node_id]
        resources = [(item["name"], item["capacity"]) for item in node["resources"]]
        if node["requires_approval"]:
            resources.append(("__approval__", 1))
        if node["external_effect"] != "none":
            resources.append(("__external_effect__", 1))
        if node["writes"]:
            resources.append(("__checkout_writer__", 1))
        if len(wave) >= cap or any(usage[name] >= capacity for name, capacity in resources):
            continue
        wave.append(node_id)
        usage.update(name for name, _ in resources)
    return wave


def validate_host(raw: Any) -> tuple[dict[str, Any], int]:
    host = exact(raw, {"schema_version", "host", "concurrency", "cancellation", "waiting", "isolated_worktrees"}, "host")
    if (
        host["schema_version"] != HOST_VERSION
        or not isinstance(host["host"], str)
        or host["host"] not in {"claude-code", "codex", "unknown"}
    ):
        raise GraphError("invalid host capability identity")
    concurrency = exact(host["concurrency"], {"status", "value"}, "host.concurrency")
    if not isinstance(concurrency["status"], str) or concurrency["status"] not in {"verified", "unknown", "unsupported"}:
        raise GraphError("invalid host concurrency status")
    if concurrency["status"] == "verified":
        cap = positive(concurrency["value"], "host.concurrency.value")
    elif concurrency["value"] is not None:
        raise GraphError("unknown/unsupported concurrency must use value=null")
    else:
        cap = 1
    for field in ("cancellation", "waiting", "isolated_worktrees"):
        capability = exact(host[field], {"status", "supported"}, f"host.{field}")
        if not isinstance(capability["status"], str) or capability["status"] not in {"verified", "unknown", "unsupported"}:
            raise GraphError(f"invalid host {field} status")
        if capability["status"] == "verified" and not isinstance(capability["supported"], bool):
            raise GraphError(f"verified host {field} requires a boolean")
        if capability["status"] != "verified" and capability["supported"] is not None:
            raise GraphError(f"unknown/unsupported host {field} must use supported=null")
    return host, cap


def validate_graph(raw: Any, host_cap: int) -> dict[str, Any]:
    graph = exact(raw, {"schema_version", "expected_checkout_fingerprint", "concurrency_budget", "coordinator_slots_reserved", "context_item_budget", "nodes"}, "graph")
    if graph["schema_version"] != GRAPH_VERSION:
        raise GraphError(f"schema_version must be {GRAPH_VERSION}")
    if not isinstance(graph["expected_checkout_fingerprint"], str) or len(graph["expected_checkout_fingerprint"]) != 64 or any(
        character not in "0123456789abcdef" for character in graph["expected_checkout_fingerprint"]
    ):
        raise GraphError("expected_checkout_fingerprint must be sha256")
    budget = positive(graph["concurrency_budget"], "concurrency_budget")
    reserved = positive(graph["coordinator_slots_reserved"], "coordinator_slots_reserved")
    item_budget = positive(graph["context_item_budget"], "context_item_budget")
    if not isinstance(graph["nodes"], list) or not graph["nodes"]:
        raise GraphError("nodes must be a non-empty array")
    if reserved >= budget:
        raise GraphError("coordinator reservation leaves no worker slot")
    node_keys = {"id", "deliverable", "inputs", "output_contract", "depends_on", "reads", "writes", "resources", "requires_approval", "external_effect", "optional", "timeout_seconds", "retry", "verification_owner"}
    nodes: dict[str, dict[str, Any]] = {}
    resource_capacities: dict[str, int] = {}
    for index, value in enumerate(graph["nodes"]):
        node = exact(value, node_keys, f"nodes[{index}]")
        node_id = node["id"]
        if not isinstance(node_id, str) or not NODE_ID.fullmatch(node_id) or node_id in nodes:
            raise GraphError("node ids must be non-empty and unique")
        if not isinstance(node["deliverable"], str) or not node["deliverable"].strip() or len(node["deliverable"]) > 500:
            raise GraphError(f"{node_id} needs a bounded deliverable")
        for field in ("inputs", "depends_on", "reads", "writes", "resources"):
            if not isinstance(node[field], list):
                raise GraphError(f"{node_id}.{field} must be an array")
        for field in ("inputs", "depends_on", "reads", "writes"):
            if any(not isinstance(item, str) or not item for item in node[field]):
                raise GraphError(f"{node_id}.{field} values must be non-empty strings")
            if len(set(node[field])) != len(node[field]):
                raise GraphError(f"{node_id}.{field} values must be unique")
        output = exact(node["output_contract"], {"kind", "max_items"}, f"{node_id}.output_contract")
        if not isinstance(output["kind"], str) or output["kind"] not in {"json", "text", "files", "decision"}:
            raise GraphError(f"invalid output kind for {node_id}")
        positive(output["max_items"], f"{node_id}.output_contract.max_items")
        if node["verification_owner"] != "coordinator":
            raise GraphError(f"{node_id} verification must be coordinator-owned")
        if not isinstance(node["requires_approval"], bool) or not isinstance(node["optional"], bool):
            raise GraphError(f"{node_id} approval/optional fields must be booleans")
        if not isinstance(node["external_effect"], str) or node["external_effect"] not in EXTERNAL_EFFECTS:
            raise GraphError(f"invalid external effect for {node_id}")
        positive(node["timeout_seconds"], f"{node_id}.timeout_seconds")
        retry = exact(node["retry"], {"max_attempts", "idempotent", "renew_approval"}, f"{node_id}.retry")
        attempts = positive(retry["max_attempts"], f"{node_id}.retry.max_attempts")
        if attempts > 3 or any(not isinstance(retry[key], bool) for key in ("idempotent", "renew_approval")):
            raise GraphError(f"invalid retry policy for {node_id}")
        effectful = node["requires_approval"] or node["external_effect"] != "none" or bool(node["writes"])
        if attempts > 1 and (not retry["idempotent"] or (effectful and not retry["renew_approval"])):
            raise GraphError(f"{node_id} retries require idempotency and renewed authority")
        resource_names: set[str] = set()
        for resource in node["resources"]:
            resource = exact(resource, {"name", "capacity"}, f"{node_id}.resource")
            if not isinstance(resource["name"], str) or not resource["name"] or resource["name"] in resource_names:
                raise GraphError(f"{node_id} resource names must be non-empty and unique")
            resource_names.add(resource["name"])
            capacity = positive(resource["capacity"], f"{node_id}.resource.capacity")
            if resource["name"] in resource_capacities and resource_capacities[resource["name"]] != capacity:
                raise GraphError(f"resource {resource['name']} has conflicting capacities")
            resource_capacities[resource["name"]] = capacity
        nodes[node_id] = node
    for node_id, node in nodes.items():
        for dependency in node["depends_on"]:
            if dependency not in nodes or dependency == node_id:
                raise GraphError(f"{node_id} has an unresolved dependency")
    # A traversal from every node also detects indirect cycles.
    for node_id in nodes:
        if is_ancestor(nodes, node_id, node_id):
            raise GraphError("graph contains a cycle")

    edge_counts: Counter[str] = Counter()
    for node_id, node in nodes.items():
        for dependency in node["depends_on"]:
            edge_counts["data"] += 1
    node_list = list(nodes.values())
    for index, left in enumerate(node_list):
        for right in node_list[index + 1:]:
            ordered = is_ancestor(nodes, left["id"], right["id"]) or is_ancestor(nodes, right["id"], left["id"])
            shared_checkout_writers = bool(left["writes"] and right["writes"])
            write_collision = any(territories_overlap(a, b) for a in left["writes"] for b in right["writes"])
            shared_resources = {
                item["name"] for item in left["resources"]
            } & {item["name"] for item in right["resources"]}
            if write_collision and not ordered:
                raise GraphError(f"unordered write_lock collision between {left['id']} and {right['id']}")
            if shared_checkout_writers:
                edge_counts["write_lock"] += 1
            if shared_resources:
                edge_counts["resource_pool"] += len(shared_resources)
    edge_counts["approval"] = sum(node["requires_approval"] for node in node_list)
    edge_counts["external_effect"] = sum(node["external_effect"] != "none" for node in node_list)

    worker_cap = max(1, min(budget - reserved, max(1, host_cap - reserved)))
    levels: list[list[str]] = []
    remaining = set(nodes)
    completed: set[str] = set()
    while remaining:
        ready = sorted(node_id for node_id in remaining if set(nodes[node_id]["depends_on"]) <= completed)
        if not ready:
            raise GraphError("graph contains a cycle")
        unscheduled = ready
        while unscheduled:
            wave = bounded_wave(unscheduled, nodes, worker_cap)
            if not wave:
                raise GraphError("resource capacities cannot produce a schedulable wave")
            levels.append(wave)
            unscheduled = [node_id for node_id in unscheduled if node_id not in wave]
        completed.update(ready)
        remaining.difference_update(ready)
    total_items = sum(node["output_contract"]["max_items"] for node in node_list)
    if total_items > 1 and item_budget == 1:
        raise GraphError("context_item_budget=1 cannot reduce a multi-item fan-in")
    fan_in_levels = 1 if total_items <= item_budget else math.ceil(math.log(total_items, item_budget))
    return {
        "schema_version": GRAPH_VERSION,
        "graph_fingerprint": fingerprint(graph),
        "host_worker_cap": worker_cap,
        "edge_counts": {name: edge_counts[name] for name in ("data", "write_lock", "resource_pool", "approval", "external_effect")},
        "waves": levels,
        "fan_in_levels": fan_in_levels,
        "planned": len(nodes),
        "required": sum(not node["optional"] for node in node_list),
    }


def validate_state(raw: Any, graph: dict[str, Any]) -> dict[str, Any]:
    state = exact(raw, {"schema_version", "graph_fingerprint", "checkout_fingerprint", "checkout_revalidated", "approvals_revalidated", "external_state_revalidated", "nodes"}, "state")
    if state["schema_version"] != STATE_VERSION or state["graph_fingerprint"] != fingerprint(graph):
        raise GraphError("state is stale or bound to a different graph")
    if state["checkout_fingerprint"] != graph["expected_checkout_fingerprint"]:
        raise GraphError("checkout fingerprint drifted from the validated graph")
    for field in ("checkout_revalidated", "approvals_revalidated", "external_state_revalidated"):
        if not isinstance(state[field], bool):
            raise GraphError(f"state.{field} must be a boolean")
    graph_nodes = {node["id"]: node for node in graph["nodes"]}
    if not isinstance(state["nodes"], dict) or set(state["nodes"]) != set(graph_nodes):
        raise GraphError("state must contain every graph node exactly once")
    node_keys = {"previous_status", "status", "output_count", "output_contract_satisfied", "cleanup_ok"}
    execution_statuses = {"running", "completed", "failed", "cancelled", "timed_out"}
    for node_id, value in state["nodes"].items():
        node_state = exact(value, node_keys, f"state.nodes.{node_id}")
        if (
            not isinstance(node_state["previous_status"], str)
            or not isinstance(node_state["status"], str)
            or node_state["previous_status"] not in STATUSES
            or node_state["status"] not in STATUSES
        ):
            raise GraphError(f"invalid status for {node_id}")
        if node_state["status"] not in STATUS_TRANSITIONS[node_state["previous_status"]]:
            raise GraphError(f"invalid state transition for {node_id}")
        if isinstance(node_state["output_count"], bool) or not isinstance(node_state["output_count"], int) or node_state["output_count"] < 0:
            raise GraphError(f"invalid output count for {node_id}")
        if not isinstance(node_state["output_contract_satisfied"], bool) or not isinstance(node_state["cleanup_ok"], bool):
            raise GraphError(f"invalid output/cleanup flags for {node_id}")
        if node_state["output_count"] > graph_nodes[node_id]["output_contract"]["max_items"]:
            raise GraphError(f"output count exceeds contract for {node_id}")
        if node_state["status"] == "completed" and not node_state["output_contract_satisfied"]:
            raise GraphError(f"completed node {node_id} must satisfy its output contract")
        if node_state["status"] != "completed" and node_state["output_contract_satisfied"]:
            raise GraphError(f"non-completed node {node_id} cannot satisfy its output contract")
        if (
            node_state["status"] == "skipped_optional"
            or node_state["previous_status"] == "skipped_optional"
        ) and not graph_nodes[node_id]["optional"]:
            raise GraphError(f"required node {node_id} cannot be skipped")
        execution_started = (
            node_state["previous_status"] in execution_statuses
            or node_state["status"] in execution_statuses
        )
        if (
            execution_started
            and graph_nodes[node_id]["requires_approval"]
            and not state["approvals_revalidated"]
        ):
            raise GraphError(f"approval must be revalidated before executing {node_id}")
        if (
            execution_started
            and graph_nodes[node_id]["external_effect"] != "none"
            and not state["external_state_revalidated"]
        ):
            raise GraphError(f"external state must be revalidated before executing {node_id}")
    for node_id, node in graph_nodes.items():
        node_state = state["nodes"][node_id]
        execution_started = (
            node_state["previous_status"] in execution_statuses
            or node_state["status"] in execution_statuses
        )
        if execution_started and any(
            state["nodes"][dependency]["status"] not in {"completed", "skipped_optional"}
            for dependency in node["depends_on"]
        ):
            raise GraphError(f"dependencies must be complete before executing {node_id}")
    return state


def next_wave(graph: dict[str, Any], state: dict[str, Any], cap: int) -> dict[str, Any]:
    nodes = {node["id"]: node for node in graph["nodes"]}
    statuses = {node_id: value["status"] for node_id, value in state["nodes"].items()}
    if not state["checkout_revalidated"]:
        raise GraphError("checkout must be revalidated before dispatch")
    ready: list[str] = []
    blocked: list[str] = []
    for node_id in sorted(nodes):
        if statuses[node_id] not in {"pending", "ready"}:
            continue
        dependency_statuses = [statuses[item] for item in nodes[node_id]["depends_on"]]
        if any(status in {"failed", "cancelled", "timed_out", "blocked_dependency"} for status in dependency_statuses):
            blocked.append(node_id)
            continue
        if all(status in {"completed", "skipped_optional"} for status in dependency_statuses):
            if nodes[node_id]["requires_approval"] and not state["approvals_revalidated"]:
                continue
            if nodes[node_id]["external_effect"] != "none" and not state["external_state_revalidated"]:
                continue
            ready.append(node_id)
    selected = bounded_wave(ready, nodes, cap)
    return {
        "ready": selected,
        "deferred_ready": [item for item in ready if item not in selected],
        "blocked_dependency": blocked,
        "capacity": cap,
    }


def validate_results(graph: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    nodes = {node["id"]: node for node in graph["nodes"]}
    counts = Counter(value["status"] for value in state["nodes"].values())
    cleanup_failed = sum(not value["cleanup_ok"] for value in state["nodes"].values())
    unfinished = sum(value["status"] in {"pending", "ready", "running"} for value in state["nodes"].values())
    missing_required = []
    for node_id, node in nodes.items():
        value = state["nodes"][node_id]
        if not node["optional"] and (
            value["status"] != "completed" or not value["output_contract_satisfied"]
        ):
            missing_required.append(node_id)
    approval_revalidation_required = any(
        node["requires_approval"]
        and state["nodes"][node_id]["status"] == "completed"
        for node_id, node in nodes.items()
    )
    external_revalidation_required = any(
        node["external_effect"] != "none"
        and state["nodes"][node_id]["status"] == "completed"
        for node_id, node in nodes.items()
    )
    complete = (
        not missing_required
        and cleanup_failed == 0
        and unfinished == 0
        and state["checkout_revalidated"]
        and (not approval_revalidation_required or state["approvals_revalidated"])
        and (not external_revalidation_required or state["external_state_revalidated"])
    )
    return {
        "synthesis_allowed": complete,
        "planned": len(nodes),
        "required": sum(not node["optional"] for node in nodes.values()),
        "completed": counts["completed"],
        "failed": counts["failed"],
        "cancelled": counts["cancelled"],
        "timed_out": counts["timed_out"],
        "blocked_dependency": counts["blocked_dependency"],
        "skipped_optional": counts["skipped_optional"],
        "cleanup_failed": cleanup_failed,
        "unfinished": unfinished,
        "missing_required_count": len(missing_required),
        "approval_revalidation_required": approval_revalidation_required,
        "external_revalidation_required": external_revalidation_required,
    }


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("validate", "next-wave"):
        command = sub.add_parser(name)
        command.add_argument("--graph", type=Path, required=True)
        command.add_argument("--capabilities", type=Path, required=True)
        if name == "next-wave":
            command.add_argument("--state", type=Path, required=True)
    results = sub.add_parser("validate-results")
    results.add_argument("--graph", type=Path, required=True)
    results.add_argument("--state", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        graph = load(args.graph)
        if args.command == "validate-results":
            validate_graph(graph, sys.maxsize)
            state = validate_state(load(args.state), graph)
            output = validate_results(graph, state)
        else:
            _, host_cap = validate_host(load(args.capabilities))
            validation = validate_graph(graph, host_cap)
            if args.command == "validate":
                output = validation
            else:
                state = validate_state(load(args.state), graph)
                output = next_wave(graph, state, validation["host_worker_cap"])
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, GraphError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
