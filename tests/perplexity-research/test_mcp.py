"""Exercise the real stdio adapter and CLI with private local fixtures only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "perplexity-research/scripts/perplexity_research_mcp.py"
spec = importlib.util.spec_from_file_location("research_mcp", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def request(method, params=None, number=1):
    return {"jsonrpc": "2.0", "id": number, "method": method, "params": params or {}}


def run_server(tmp_path, messages):
    process = subprocess.run([sys.executable, "-I", str(SCRIPT), "--state-dir", str(tmp_path / "jobs"),
                              "--permission-reference", str(tmp_path / "unused-authorization")],
                             input="\n".join(json.dumps(x) for x in messages) + "\n", text=True,
                             capture_output=True, timeout=10)
    assert process.returncode == 0 and not process.stderr
    return [json.loads(line) for line in process.stdout.splitlines()]


def test_real_stdio_lifecycle_and_local_result_export(tmp_path):
    root = tmp_path / "jobs"
    root.mkdir(mode=0o700)
    job_id = str(uuid.uuid4())
    citation = {"id": 1, "url": "https://example.org/source", "title": "Source"}
    value = {"answer": "Summary [1]", "citations": [citation], "sources": [citation],
             "reports": [{"name": "Report", "markdown": "Report [1]", "citations": [citation], "final": True}],
             "thread_url": None, "server_status": "COMPLETED", "observed_model": "pplx_alpha", "observed_search_mode": "RESEARCH"}
    path = root / (job_id + ".json")
    path.write_text(json.dumps({"job_id": job_id, "status": "completed", "submitted": True,
                                "requested_model": "pplx_alpha", "result": value, "query": "Private query"}))
    path.chmod(0o600)
    messages = [request("server/discover"), request("initialize", {"protocolVersion": "2099-01-01"}),
                {"jsonrpc": "2.0", "method": "notifications/initialized"}, request("tools/list")]
    for name in ("research_status", "research_result", "research_export", "research_recover"):
        messages.append(request("tools/call", {"name": name, "arguments": {"job_id": job_id}}))
    messages.append(request("tools/call", {"name": "research_jobs"}))
    output = run_server(tmp_path, messages)
    assert output[0]["error"]["code"] == -32601
    assert output[1]["result"]["protocolVersion"] == "2025-11-25"
    assert 'transferSession' in output[1]['result']['instructions']
    assert len(output[2]["result"]["tools"]) == 11
    assert all(not row["result"]["isError"] for row in output[3:])
    assert json.loads(output[4]["result"]["content"][0]["text"])["result"] == value
    assert 'Report [1]' in output[5]["result"]["content"][0]["text"]
    assert 'https://example.org/source' in output[5]["result"]["content"][0]["text"]
    assert "Private query" not in json.dumps(output)


@pytest.mark.parametrize("args", [{"job_id": "../../escape"}, {"job_id": True},
    {"job_id": str(uuid.uuid4()), "path": "/etc/passwd"}, []])
def test_invalid_arguments_never_launch_cli(monkeypatch, args):
    run = Mock()
    monkeypatch.setattr(m.subprocess, "run", run)
    with pytest.raises((ValueError, TypeError)):
        m.invoke("research_result", args, "/state", "/authorization")
    run.assert_not_called()


def test_submit_uses_fixed_cli_query_stdin_and_sanitized_environment(monkeypatch):
    run = Mock(return_value=Mock(returncode=0, stdout=b'{"status":"queued"}'))
    monkeypatch.setattr(m.subprocess, "run", run)
    monkeypatch.setenv("PERPLEXITY_COOKIES", "never-forward")
    monkeypatch.setenv("OPENAI_API_KEY", "never-forward")
    query = "Public query $(false)"
    job_id = str(uuid.uuid4())
    result = m.invoke("research_submit", {"request_id": job_id, "query": query}, "/state", "/authorization")
    assert not result["isError"]
    command = run.call_args.args[0]
    assert command[:3] == [sys.executable, "-I", str(m.CLI)]
    assert command[-2:] == ["--timeout", "600"]
    assert query not in command and run.call_args.kwargs["input"] == query.encode()
    assert "never-forward" not in repr(run.call_args)
    assert run.call_count == 1


def test_timeout_does_not_retry_or_disclose_subprocess_input(monkeypatch):
    run = Mock(side_effect=subprocess.TimeoutExpired("private command", 40, output=b"secret"))
    monkeypatch.setattr(m.subprocess, "run", run)
    result = m.invoke("research_health", {}, "/state", "/authorization")
    assert result["isError"] and "secret" not in repr(result)
    assert run.call_count == 1


def test_search_follow_up_options_reach_cli(monkeypatch):
    run = Mock(return_value=Mock(returncode=0, stdout=b'{"status":"queued"}'))
    monkeypatch.setattr(m.subprocess, "run", run)
    parent_id = str(uuid.uuid4())
    args = {"request_id": str(uuid.uuid4()), "query": "Follow up", "mode": "search", "model": "thinking", "parent_job_id": parent_id}
    m.invoke("research_submit", args, "/state", "/authorization")
    assert run.call_args.args[0][-6:] == ["--mode", "search", "--model", "thinking", "--parent-job-id", parent_id]
    args["mode"] = "computer"
    with pytest.raises(ValueError): m.invoke("research_submit", args, "/state", "/authorization")
    assert run.call_count == 1


def test_missing_job_returns_safe_tool_error(tmp_path):
    output = run_server(tmp_path, [request("initialize"), request("tools/call", {
        "name": "research_result", "arguments": {"job_id": str(uuid.uuid4())}})])
    assert output[1]["result"]["isError"]
    assert "local_state_or_io_error" in output[1]["result"]["content"][0]["text"]


def test_notification_cannot_submit_and_invalid_protocol_is_rejected(tmp_path):
    output = run_server(tmp_path, [request("tools/list"), request("initialize"),
        {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "research_submit", "arguments": {}}},
        request("tools/call", {"name": "research_health", "arguments": {"password": "secret"}}), []])
    assert [r.get("error", {}).get("code") for r in output] == [-32602, None, -32602, -32600]
    assert "secret" not in repr(output)
    assert not (tmp_path / "jobs").exists()


def test_auth_tools_are_fixed_no_secret_arguments(monkeypatch):
    run = Mock(return_value=Mock(returncode=0, stdout=b'{"status":"not_started"}'))
    monkeypatch.setattr(m.subprocess, 'run', run)
    for name in ('research_auth_start', 'research_auth_status'):
        m.invoke(name, {}, '/state', '/authorization')
        assert run.call_args.args[0][-1] == name.replace('research_', '').replace('_', '-')
        with pytest.raises(ValueError): m.invoke(name, {'cookies': 'secret'}, '/state', '/authorization')
    annotations = {t['name']: t['annotations'] for t in m.schemas()}
    assert not annotations['research_auth_start']['readOnlyHint']


def test_native_codex_discovery_metadata(tmp_path):
    output = run_server(tmp_path, [request("initialize", {"protocolVersion": "2025-06-18"}),
        request("tools/list", {"_meta": {"progressToken": 0}}),
        request("tools/list", {"unexpected": True})])
    assert len(output[1]["result"]["tools"]) == 11
    assert output[2]["error"]["code"] == -32602
