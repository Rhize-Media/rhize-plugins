import copy
import json
from datetime import datetime, timezone

from memory_context.model_evaluation import evaluate_answers, parse_output, driver_command, drain
from memory_context.opportunities import PairStore


def test_both_answer_arms_attempted_after_failure(tmp_path):
    calls = []
    def executor(host, model, question, context, directory):
        calls.append(context)
        if context == "A": return {"actuallyRan": True, "status": "failed", "model": model}
        return {"actuallyRan": True, "status": "completed", "model": model, "answer": "verified", "sourceIds": [], "usage": None}
    result = evaluate_answers("codex", "arbitrary-model", "question", {"A": "A", "B": "B"}, tmp_path, executor=executor)
    assert set(calls) == {"A", "B"}
    assert result["comparisonStatus"] == "incomplete"
    assert result["arms"]["B"]["usage"] is None


def test_actual_usage_and_different_models_are_not_comparable(tmp_path):
    def executor(host, model, question, context, directory):
        return {"actuallyRan": True, "status": "completed", "model": model + context, "answer": "verified", "sourceIds": [], "usage": {"inputTokens": 5, "cachedInputTokens": 2, "outputTokens": 1}}
    result = evaluate_answers("claude", "model", "question", {"A": "A", "B": "B"}, tmp_path, executor=executor)
    assert result["comparisonStatus"] == "incomplete"
    assert result["reason"] == "model_identity_mismatch_or_unavailable"


def test_native_output_parsers_do_not_invent_usage():
    claude = {"type": "result", "subtype": "success", "is_error": False, "result": '{"answer":"verified","sourceIds":[]}',
              "modelUsage": {"claude-any-version": {"inputTokens": 10, "cacheReadInputTokens": 20, "cacheCreationInputTokens": 4, "outputTokens": 5}}}
    result = parse_output("claude", json.dumps(claude), "requested-alias")
    assert result["model"] == "claude-any-version"
    assert result["usage"]["cachedInputTokens"] == 20
    assert result["usage"]["cacheCreationInputTokens"] == 4
    codex = '\n'.join(json.dumps(x) for x in [
        {"type":"item.completed", "item":{"type":"agent_message","text":'{"answer":"verified","sourceIds":[]}'}},
        {"type":"turn.completed", "usage":{"input_tokens":30,"cached_input_tokens":20,"output_tokens":5}},
    ])
    result = parse_output("codex", codex, "gpt-arbitrary")
    assert result["model"] == "gpt-arbitrary"
    assert result["modelIdentitySource"] == "explicit_pinned_cli_argument"
    assert result["usage"] == {"inputTokens":30,"cachedInputTokens":20,"outputTokens":5,"cacheCreationInputTokens":None,"totalInputTokens":30}


def test_drivers_have_no_permission_bypass_and_disable_tooling(tmp_path):
    for host in ("claude", "codex"):
        command = driver_command(host, "model-name", tmp_path)
        assert not any("bypass" in arg or "skip-permissions" in arg for arg in command)
        assert "--model" in command
    assert "--tools" in driver_command("claude", "m", tmp_path)
    assert "--ephemeral" in driver_command("codex", "m", tmp_path)


def test_pair_budget_defers_whole_pair(tmp_path):
    store = PairStore(tmp_path / "store")
    store.configure([tmp_path], answer_pairs_per_day=0)
    store.write("queue/test.json", {"pairId":"test", "host":"codex", "model":"model", "contexts":{"A":"a","B":"b"}})
    result = drain(store)
    assert result["executedPairs"] == 0
    assert result["deferredPairs"] == 1
    assert store.read("queue/test.json") is not None


def test_claude_auxiliary_model_usage_preserves_primary_identity():
    value = {"subtype":"success", "structured_output":{"answer":"unavailable", "sourceIds":[]}, "modelUsage": {
        "primary": {"inputTokens":10, "outputTokens":2, "cacheReadInputTokens":3, "cacheCreationInputTokens":4},
        "auxiliary": {"inputTokens":5, "outputTokens":1, "cacheReadInputTokens":0, "cacheCreationInputTokens":0}}}
    result = parse_output("claude", json.dumps(value), "primary")
    assert result["model"] == "primary"
    assert result["usage"]["totalInputTokens"] == 22
    assert result["usageModels"] == ["auxiliary", "primary"]


def test_missing_arm_cannot_be_requested(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="both A and B"):
        evaluate_answers("codex", "m", "question", {"A":"one"}, tmp_path)


def test_actual_pair_uses_fresh_directory_and_grades_separately(tmp_path):
    seen = []
    def executor(host, model, question, context, directory):
        assert not (directory / "state").exists()
        (directory / "state").write_text("arm state")
        seen.append(directory)
        return {"actuallyRan":True, "status":"completed", "model":model, "answer":context, "sourceIds":["source"], "usage":None}
    result = evaluate_answers("codex", "m", "question", {"A":"unavailable", "B":"failed"}, tmp_path,
                              rubric={"requiredTerms":["unavailable"], "requiredSourceHashes":["source"]}, executor=executor)
    assert seen[0] != seen[1] and all(not p.exists() for p in seen)
    assert result["arms"]["A"]["rubricPass"] is True
    assert result["arms"]["B"]["rubricPass"] is False
    assert result["comparisonStatus"] == "complete"


def test_worker_lock_prevents_overlapping_drains(tmp_path):
    import fcntl
    store = PairStore(tmp_path / "store")
    store.configure([tmp_path])
    with (store.root / "worker.lock").open("w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        assert drain(store)["workerAlreadyRunning"] == 1


def test_codex_advisory_item_does_not_masquerade_as_failed_turn():
    text = "\n".join(json.dumps(item) for item in [
        {"type":"item.completed", "item":{"type":"error", "message":"Under-development features enabled"}},
        {"type":"item.completed", "item":{"type":"agent_message", "text":'{"answer":"unavailable","sourceIds":[]}'}},
        {"type":"turn.completed", "usage":{"input_tokens":30,"cached_input_tokens":3,"cache_write_input_tokens":4,"output_tokens":2}}])
    result = parse_output("codex", text, "m")
    assert result["status"] == "completed"
    assert result["usage"]["cacheCreationInputTokens"] == 4


def test_worker_completes_both_and_removes_private_packet(tmp_path, monkeypatch):
    from memory_context import model_evaluation
    from memory_context.opportunities import handle_event
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "STATE.md").write_text("# Release policy\nVerify tests.")
    store = PairStore(tmp_path / "store")
    store.configure([workspace])
    event = {"session_id":"s", "turn_id":"t", "cwd":str(workspace), "model":"m", "prompt":"Recall the release policy"}
    pair = handle_event(store, "codex", "UserPromptSubmit", event)
    seen = []
    def evaluate(host, model, question, contexts, root, **kwargs):
        seen.extend(contexts)
        return {"comparisonStatus":"complete", "armsRequested":["A","B"], "arms":{a:{"status":"completed","actuallyRan":True,"model":model} for a in contexts}}
    monkeypatch.setattr(model_evaluation, "evaluate_answers", evaluate)
    assert drain(store)["executedPairs"] == 1
    assert set(seen) == {"A","B"}
    assert not store.read(f"queue/{pair['pairId']}.json")
    assert store.receipts()[0]["answerStatus"] == "complete"
    assert drain(store)["executedPairs"] == 0


def test_interrupted_worker_is_incomplete_even_with_exhausted_budget(tmp_path):
    from memory_context.core import format_time, utc_now
    store = PairStore(tmp_path / "store")
    store.configure([tmp_path], 0)
    store.write("queue/pair.json", {"pairId":"pair", "host":"claude", "createdAt":format_time(utc_now())})
    store.write("answer-claims/pair.json", {"status":"running"})
    store.write("receipts/pair.json", {"answerStatus":"queued"})
    drain(store)
    row = store.read("receipts/pair.json")
    assert row["answerStatus"] == "incomplete"
    assert all(r["actuallyRan"] is None for r in row["answerComparison"]["arms"].values())
    assert store.read("queue/pair.json") is None


def test_expired_private_packet_removed_even_at_zero_budget(tmp_path):
    store = PairStore(tmp_path / "store")
    store.configure([tmp_path], 0)
    store.write("queue/pair.json", {"pairId":"pair", "host":"claude", "createdAt":"2020-01-01T00:00:00Z"})
    store.write("receipts/pair.json", {"answerStatus":"queued"})
    drain(store)
    assert store.read("queue/pair.json") is None
    assert store.read("receipts/pair.json")["answerStatus"] == "incomplete"


def test_source_drift_defers_neither_single_arm_nor_stale_answer(tmp_path, monkeypatch):
    from memory_context import model_evaluation
    from memory_context.opportunities import handle_event
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "STATE.md"
    source.write_text("# Release policy\nVerify tests.")
    store = PairStore(tmp_path / "store")
    store.configure([workspace])
    event = {"session_id":"s", "turn_id":"t", "cwd":str(workspace), "model":"m", "prompt":"Recall the release policy"}
    pair = handle_event(store, "claude", "UserPromptSubmit", event)
    source.write_text("# Release policy\nChanged source revision.")
    def forbidden(*args, **kwargs):
        raise AssertionError("stale sources must not reach a model")
    monkeypatch.setattr(model_evaluation, "evaluate_answers", forbidden)
    drain(store)
    result = store.read(f"receipts/{pair['pairId']}.json")["answerComparison"]
    assert result["comparisonStatus"] == "incomplete"
    assert set(result["arms"]) == {"A","B"}
    assert all(row["actuallyRan"] is False for row in result["arms"].values())


def test_symlink_queue_cannot_remove_outside_json(tmp_path):
    import pytest
    store = PairStore(tmp_path / "store")
    store.configure([tmp_path], 0)
    outside = tmp_path / "outside"
    outside.mkdir()
    packet = outside / "pair.json"
    packet.write_text(json.dumps({"pairId":"pair", "host":"claude", "createdAt":"2020-01-01T00:00:00Z"}))
    (store.root / "queue").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        drain(store)
    assert packet.exists()
