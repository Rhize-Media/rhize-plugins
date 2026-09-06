"""Every measured opportunity is a pair, including failures and duplicate events."""
import copy
import json
from datetime import datetime, timezone

import pytest

from memory_context.opportunities import PairStore, run_pair, handle_event, aggregate

NOW = datetime(2026, 9, 6, 16, tzinfo=timezone.utc)


def document():
    return {"schemaVersion": 1, "request": {"tenant": "rhize", "project": "plugins", "query": "release validation policy", "totalTokenBudget": 4000},
            "adapters": [{"name": "canonical-files", "memoryType": "semantic", "status": "available", "candidates": [
                {"sourceSystem": "canonical-file", "sourceId": "release", "sourceRevision": "r1", "tenant": "rhize", "project": "plugins",
                 "trustClass": "verified", "content": "# Release validation\nVerify source data, tests and deployed revision before declaring completion.",
                 "relevance": 1, "contentRole": "data", "provenance": ["release"]}]}]}


def test_every_pair_runs_both_without_oracle(tmp_path):
    pair, contexts = run_pair(document(), tmp_path, host="codex", model="any-model", evidence_kind="curated", now=NOW)
    assert pair["armsRequested"] == ["A", "B"]
    assert pair["comparisonStatus"] == "complete"
    assert all(pair["arms"][arm]["actuallyRan"] for arm in ("A", "B"))
    assert pair["selectionMethod"] == "catalog-keyword-overlap-v1"
    assert set(contexts) == {"A", "B"}
    assert pair["arms"]["A"]["taskCorrectness"] is None
    assert "Verify source data" not in json.dumps(pair)


def test_first_arm_failure_does_not_skip_second(tmp_path, monkeypatch):
    from memory_context import opportunities
    original = opportunities._run_arm
    seen = []
    def fail_a(arm, *args, **kwargs):
        seen.append(arm)
        if arm == "A": raise ValueError("private sensitive input")
        return original(arm, *args, **kwargs)
    monkeypatch.setattr(opportunities, "_run_arm", fail_a)
    pair, _ = run_pair(document(), tmp_path, host="claude", model="anything", evidence_kind="curated", now=NOW)
    assert set(seen) == {"A", "B"}
    assert pair["arms"]["A"]["status"] == "failed"
    assert pair["arms"]["B"]["status"] == "completed"
    assert pair["comparisonStatus"] == "incomplete"
    assert "private sensitive" not in json.dumps(pair)


def test_scope_filtering_and_no_memory(tmp_path):
    value = document()
    denied = copy.deepcopy(value["adapters"][0]["candidates"][0])
    denied.update(sourceId="other-client", tenant="elsewhere", content="secret client content")
    value["adapters"][0]["candidates"].append(denied)
    pair, contexts = run_pair(value, tmp_path, host="codex", model=None, evidence_kind="curated", now=NOW)
    assert all("secret client" not in text for text in contexts.values())
    assert pair["model"] is None
    assert pair["emptyMemoryControl"]["actuallyRan"] is True
    assert pair["emptyMemoryControl"]["estimatedTokens"] == 0


def test_hooks_capture_once_count_tools_and_stop_without_correctness(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "STATE.md").write_text("# Release policy\nRun tests and verify source data before release.")
    store = PairStore(tmp_path / "state")
    store.configure([workspace], answer_pairs_per_day=0)
    event = {"session_id": "test-session", "turn_id": "turn-1", "cwd": str(workspace), "model": "model-x", "prompt": "Recall the previous release policy and verification requirements"}
    one = handle_event(store, "codex", "UserPromptSubmit", event, now=NOW)
    two = handle_event(store, "codex", "UserPromptSubmit", event, now=NOW)
    assert one["pairId"] == two["pairId"]
    assert len(store.receipts()) == 1
    handle_event(store, "codex", "PostToolUse", {**event, "tool_use_id": "tool-1", "tool_response": {"is_error": True}}, now=NOW)
    handle_event(store, "codex", "PostToolUse", {**event, "tool_use_id": "tool-1", "tool_response": {"is_error": True}}, now=NOW)
    handle_event(store, "codex", "Stop", event, now=NOW)
    result = store.receipts()[0]
    assert result["observation"]["toolCalls"] == 1
    assert result["observation"]["toolErrors"] == 1
    assert result["observation"]["ended"] is True
    assert result["observation"]["correctness"] is None
    assert event["prompt"] not in json.dumps(result)
    assert str(workspace) not in json.dumps(result)
    assert set(result["arms"]) == {"A", "B"}


def test_scope_symlinks_missing_sources_and_recursive_child(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("secret")
    (workspace / "STATE.md").symlink_to(outside)
    store = PairStore(tmp_path / "state")
    store.configure([workspace], answer_pairs_per_day=0)
    event = {"session_id": "session", "cwd": str(workspace), "prompt": "Recall the prior project decision"}
    assert handle_event(store, "claude", "UserPromptSubmit", event, now=NOW)["status"] == "unavailable"
    monkeypatch.setenv("RHIZE_MEMORY_EVAL_CHILD", "1")
    assert handle_event(store, "claude", "UserPromptSubmit", event, now=NOW)["status"] == "child_ignored"


def test_aggregate_never_pools_hosts_models_or_incomplete_pairs(tmp_path):
    a, _ = run_pair(document(), tmp_path / "a", host="claude", model="m1", evidence_kind="curated", now=NOW)
    b = copy.deepcopy(a)
    b["host"] = "codex"
    b["arms"]["B"]["actuallyRan"] = False
    b["comparisonStatus"] = "incomplete"
    report = aggregate([a, b])
    assert len(report["groups"]) == 2
    assert report["completePairs"] == 1
    assert report["incompletePairs"] == 1


def test_later_unmeasured_turn_does_not_receive_previous_turn_metrics(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "STATE.md").write_text("# Release policy\nRun tests.")
    store = PairStore(tmp_path / "state")
    store.configure([workspace], 0)
    event = {"session_id":"s", "turn_id":"t1", "cwd":str(workspace), "model":"m", "prompt":"Recall the release policy"}
    handle_event(store, "codex", "UserPromptSubmit", event, now=NOW)
    assert handle_event(store, "codex", "Stop", {**event, "turn_id":"old"}, now=NOW)["status"] == "stale_turn_ignored"
    handle_event(store, "codex", "UserPromptSubmit", {**event, "turn_id":"t2", "prompt":"Hello"}, now=NOW)
    assert handle_event(store, "codex", "Stop", {**event, "turn_id":"t2"}, now=NOW)["status"] == "no_pending_pair"
    assert not store.receipts()[0]["observation"]["ended"]


def test_concurrent_duplicate_delivery_is_one_pair(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "STATE.md").write_text("# Release policy\nRun tests.")
    store = PairStore(tmp_path / "state")
    store.configure([workspace], 0)
    event = {"session_id":"s", "turn_id":"t1", "cwd":str(workspace), "model":"m", "prompt":"Recall the release policy"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: handle_event(store, "codex", "UserPromptSubmit", event, now=NOW), range(4)))
    assert sum(r["status"] == "complete" for r in results) == 1
    assert len(store.receipts()) == 1


def test_native_hook_entrypoint_both_hosts_is_silent(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "STATE.md").write_text("# Release policy\nRun tests.")
    context_home = tmp_path / "context"
    store = PairStore(context_home / "memory-context/paired-opportunities-v1")
    store.configure([workspace], 0)
    hook = Path(__file__).resolve().parents[3] / "rhize-context-manager/hooks/memory-opportunity.py"
    for host in ("claude", "codex"):
        env = dict(os.environ, RHIZE_CONTEXT_HOME=str(context_home))
        env.pop("RHIZE_MEMORY_EVAL_CHILD", None)
        env.pop("PLUGIN_ROOT", None)
        if host == "codex": env["PLUGIN_ROOT"] = str(hook.parent.parent)
        event = {"hook_event_name":"UserPromptSubmit", "session_id":host, "turn_id":"1", "cwd":str(workspace), "model":"m", "prompt":"Recall the release policy"}
        result = subprocess.run([sys.executable, str(hook)], input=json.dumps(event), text=True, capture_output=True, env=env, timeout=10)
        assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    assert {r["host"] for r in store.receipts()} == {"claude", "codex"}
    assert all(set(r["arms"]) == {"A", "B"} for r in store.receipts())


def test_secret_docs_and_outside_workspace_are_not_read(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "STATE.md").write_text("# Memory\napi_key=" + "x" * 40)
    store = PairStore(tmp_path / "state")
    store.configure([workspace], 0)
    event = {"session_id":"s", "cwd":str(workspace), "prompt":"Recall prior memory"}
    assert handle_event(store, "claude", "UserPromptSubmit", event, now=NOW)["status"] == "unavailable"
    assert handle_event(store, "claude", "UserPromptSubmit", {**event,"cwd":str(tmp_path)}, now=NOW)["status"] == "scope_denied"
