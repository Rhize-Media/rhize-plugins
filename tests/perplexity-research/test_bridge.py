"""Synthetic local acceptance tests. Never contact Perplexity or the user's Keychain."""
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid
from email.message import Message
from unittest.mock import Mock
import urllib.error

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/perplexity_research.py"
spec = importlib.util.spec_from_file_location("perplexity_research", SCRIPT)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
SECRET = "synthetic-session-secret-never-use-live"


@pytest.fixture
def root(tmp_path):
    return b.private_root(tmp_path.resolve() / "jobs")


@pytest.fixture
def payload():
    return {"status": "COMPLETED", "model_preference": "pplx_alpha", "backend_uuid": str(uuid.uuid4()),
            "blocks": [{"intended_usage": "ask_text", "markdown_block": {"answer": "Public answer [1]"}},
                       {"intended_usage": "web_results", "web_result_block": {"web_results": [
                           {"id": 1, "url": "https://example.org/doc", "name": "Public source"}]}}]}


def wire(payload, end=True, newline="\n"):
    text = "event: message" + newline + "data: " + json.dumps(payload) + newline * 2
    if end:
        text += "event: end_of_stream" + newline + "data: {}" + newline * 2
    return text.encode()


class Response(io.BytesIO):
    def __init__(self, data, url, content_type="application/json", status=200):
        super().__init__(data)
        self.url, self.status = url, status
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def geturl(self):
        return self.url


def network(monkeypatch, payload, raw=None, tier="pro", model_mode="research"):
    calls = []
    client = b.WebClient({"__Secure-next-auth.session-token": SECRET})

    def open_request(request, timeout):
        calls.append(request)
        assert timeout == 15
        assert SECRET in request.get_header("Cookie")
        if request.full_url.endswith("/api/auth/session"):
            data = {"user": {"subscription_tier": tier, "subscription_status": "active"}}
        elif "/models/" in request.full_url:
            data = {"default_models": {"research": "pplx_alpha"}, "models": {"pplx_alpha": {"mode": model_mode}}}
        else:
            return Response(wire(payload) if raw is None else raw, request.full_url, "text/event-stream")
        return Response(json.dumps(data).encode(), request.full_url)

    client.opener = Mock(open=open_request)
    monkeypatch.setattr(b, "WebClient", lambda cookies: client)
    monkeypatch.setattr(b, "cookies_from_keychain", lambda: client.cookies)
    return calls


def emit(kind, value):
    if kind == "intent":
        value.set()


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_research_complete_preserves_citations_and_request(monkeypatch, payload, newline):
    calls = network(monkeypatch, payload, wire(payload, newline=newline))
    result = b.research("Public test", emit)
    assert result["answer"] == "Public answer [1]"
    assert result["citations"] == [{"id": 1, "url": "https://example.org/doc", "title": "Public source"}]
    body = json.loads(calls[-1].data)
    assert body["params"]["model_preference"] == "pplx_alpha"
    assert body["params"]["mode"] == "copilot"
    assert len([x for x in calls if x.data]) == 1


@pytest.mark.parametrize("status,end,error", [
    ("PENDING", True, "incomplete_answer_or_sources"),
    ("COMPLETED", False, "missing_end_of_stream"),
    ("FAILED", True, "incomplete_answer_or_sources"),
])
def test_partial_stream_is_not_success(monkeypatch, payload, status, end, error):
    payload["status"] = status
    calls = network(monkeypatch, payload, wire(payload, end=end))
    with pytest.raises(b.BridgeError, match=error):
        b.research("Public test", emit)
    assert len([x for x in calls if x.data]) == 1


@pytest.mark.parametrize("raw", [b'event: error\ndata: {}\n\n', b'data: broken\n\n', b'data: {}'])
def test_bad_sse_refused(monkeypatch, payload, raw):
    network(monkeypatch, payload, raw)
    with pytest.raises((b.BridgeError, ValueError)):
        b.research("Public test", emit)


def test_multiline_heartbeat_and_bounds(monkeypatch):
    raw = b':ping\n\nevent: message\ndata: {\ndata: "status":"PENDING"}\n\n'
    assert list(b.events(io.BytesIO(raw))) == [("message", '{\n"status":"PENDING"}')]
    monkeypatch.setattr(b, "MAX_EVENT", 10)
    with pytest.raises(b.BridgeError, match="stream_too_large"):
        list(b.events(io.BytesIO(b'data: ' + b'x' * 20)))


@pytest.mark.parametrize("tier,mode", [("free", "research"), ("unknown", "research"), ("pro", "search"), ("pro", "agentic_research")])
def test_preflight_fails_without_submission(monkeypatch, payload, tier, mode):
    calls = network(monkeypatch, payload, tier=tier, model_mode=mode)
    with pytest.raises(b.BridgeError):
        b.research("Public test", emit)
    assert not any(x.data for x in calls)


@pytest.mark.parametrize("code,error", [(401, "authentication_required"), (403, "access_or_challenge_refused"),
                                       (429, "quota_or_rate_limit"), (500, "http_error")])
def test_http_errors_do_not_leak_or_retry(code, error):
    client = b.WebClient({"token": SECRET})
    client.opener = Mock()
    client.opener.open.side_effect = urllib.error.HTTPError(b.ORIGIN, code, SECRET, {}, io.BytesIO(SECRET.encode()))
    with pytest.raises(b.BridgeError, match=error) as caught:
        client.request("/api/auth/session")
    assert SECRET not in str(caught.value)
    assert client.opener.open.call_count == 1


def test_redirect_html_and_credential_echo_refused():
    with pytest.raises(b.BridgeError, match="redirect_refused"):
        b.NoRedirect().redirect_request(None, None, None, None, None, None)
    client = b.WebClient({"token": SECRET})
    client.opener = Mock()
    client.opener.open.return_value = Response(b"challenge", b.ORIGIN + "/api/auth/session", "text/html")
    with pytest.raises(b.BridgeError, match="unexpected_response_or_challenge"):
        client.request("/api/auth/session")
    with pytest.raises(b.BridgeError, match="credential_echo_refused"):
        client.safe({"answer": SECRET})
    client.cookies = {"token": SECRET + '"\\'}
    with pytest.raises(b.BridgeError, match="credential_echo_refused"):
        client.safe({"citations": [{"title": SECRET + '"\\'}]})


@pytest.mark.parametrize("cookies", [{}, [], {"irrelevant": "x"}, {"next-auth.session-token": "bad\nvalue"},
                                    {"next-auth.session-token": "good", "other": "x"}])
def test_invalid_keychain_cookie_shapes(monkeypatch, cookies):
    monkeypatch.setattr(b.subprocess, "run", lambda *a, **k: Mock(returncode=0, stdout=json.dumps(cookies).encode()))
    with pytest.raises(b.BridgeError):
        b.cookies_from_keychain()


def test_keychain_credential_never_in_argv(monkeypatch):
    run = Mock(return_value=Mock(returncode=0, stdout=json.dumps({"next-auth.session-token": SECRET}).encode()))
    monkeypatch.setattr(b.subprocess, "run", run)
    assert b.cookies_from_keychain()["next-auth.session-token"] == SECRET
    assert SECRET not in repr(run.call_args)
    assert run.call_args.kwargs["timeout"] == 10


@pytest.mark.parametrize("answer", ["No markers", "Missing [2]", "Grouped [1,2]", "Mixed [1] [2,3]"])
def test_citation_mapping_is_required(payload, answer):
    value = b.snapshot(payload)
    value["answer"] = answer
    with pytest.raises(b.BridgeError):
        b.validate_final(value, "pplx_alpha")


def test_unsupported_ids_urls_and_model_refused(payload):
    value = b.snapshot(payload)
    value["observed_model"] = "generic_search"
    with pytest.raises(b.BridgeError, match="research_model_mismatch"):
        b.validate_final(value, "pplx_alpha")
    source = payload["blocks"][1]["web_result_block"]["web_results"][0]
    source["url"] = "file:///etc/passwd"
    with pytest.raises(b.BridgeError, match="invalid_citation_url"):
        b.snapshot(payload)
    source["url"] = "https://example.org"
    del source["id"]
    with pytest.raises(b.BridgeError, match="explicit_citation_ids_required"):
        b.snapshot(payload)


def hold_launch():
    holders = []
    def launch(root, job_id, fd):
        holders.append(os.dup(fd))
    return holders, launch


def test_durable_dedupe_conflict_busy_and_orphan(root):
    holders, launch = hold_launch()
    job_id = str(uuid.uuid4())
    try:
        first = b.submit(root, job_id, "Public", "a" * 64, 60, launch)
        assert b.submit(root, job_id, "Public", "a" * 64, 60, launch) == first
        assert len(holders) == 1
        with pytest.raises(b.BridgeError, match="request_id_conflict"):
            b.submit(root, job_id, "Different", "a" * 64, 60, launch)
        with pytest.raises(b.BridgeError, match="worker_busy"):
            b.submit(root, str(uuid.uuid4()), "Public", "a" * 64, 60, launch)
        job = b.read_job(root, job_id)
        job.update(submitted=True, status="submitting")
        b.save(root, job)
    finally:
        for fd in holders:
            os.close(fd)
    recovered = b.submit(root, job_id, "Public", "a" * 64, 60, launch)
    assert recovered["status"] == "submission_unknown" and recovered["remote_may_be_running"]
    assert len(holders) == 1


def test_terminal_job_blocks_new_worker_until_exit(root):
    holders, launch = hold_launch()
    job_id = str(uuid.uuid4())
    try:
        b.submit(root, job_id, "Public", "a" * 64, 60, launch)
        job = b.read_job(root, job_id)
        job["status"] = "completed"
        b.save(root, job)
        with pytest.raises(b.BridgeError, match="worker_busy"):
            b.submit(root, str(uuid.uuid4()), "Public", "a" * 64, 60, launch)
        assert len(holders) == 1
    finally:
        for fd in holders:
            os.close(fd)


def test_permissions_symlinks_and_request_ids(root, tmp_path):
    holders, launch = hold_launch()
    job_id = str(uuid.uuid4())
    b.submit(root, job_id, "Public", "a" * 64, 60, launch)
    for fd in holders:
        os.close(fd)
    assert root.stat().st_mode & 0o777 == 0o700
    assert (root / (job_id + ".json")).stat().st_mode & 0o777 == 0o600
    with pytest.raises(b.BridgeError):
        b.submit(root, "../escape", "Public", "a" * 64, 60, launch)
    link = tmp_path / "linked"
    link.symlink_to(root)
    with pytest.raises(b.BridgeError, match="symlink_state_path"):
        b.private_root(link)
    (root / (job_id + ".json")).chmod(0o644)
    with pytest.raises(b.BridgeError, match="unsafe_state_file"):
        b.read_job(root, job_id)


def execute(root, perform, timeout=2, cancel=False):
    job_id = str(uuid.uuid4())
    holders, launch = hold_launch()
    b.submit(root, job_id, "Public", "a" * 64, timeout, launch)
    if cancel:
        job = b.read_job(root, job_id)
        job["cancel_requested"] = True
        b.save(root, job)
    before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        b.work(root, job_id, holders[0], perform)
    finally:
        os.close(holders[0])
        for sig, handler in before.items():
            signal.signal(sig, handler)
    return b.read_job(root, job_id)


def test_worker_success_and_cli_result(root, payload, capsys):
    result = b.snapshot(payload)
    def perform(query, send):
        permit = threading.Event()
        send("intent", permit)
        assert permit.wait(1)
        assert b.read_job(root, next(root.glob("*.json")).stem)["submitted"]
        send("progress", result)
        return result
    job = execute(root, perform)
    assert job["status"] == "completed" and "partial" not in job
    assert all(v is None for v in job["verification"].values())
    assert b.main(["--state-dir", str(root), "result", job["job_id"]]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["result"] == result and "query" not in output


def test_timeout_and_precancel_do_not_claim_remote_cancel(root):
    release = threading.Event()
    def blocked(query, send):
        permit = threading.Event()
        send("intent", permit)
        permit.wait(1)
        release.wait(3)
        raise b.BridgeError("late_failure")
    started = time.monotonic()
    job = execute(root, blocked, timeout=1)
    release.set()
    assert time.monotonic() - started < 2
    assert job["status"] == "timed_out" and job["submitted"]
    never = Mock()
    job = execute(root, never, cancel=True)
    never.assert_not_called()
    assert job["status"] == "cancelled_local" and not job["submitted"]


def test_partial_failure_persisted_without_exception_text(root, payload, capsys):
    def perform(query, send):
        permit = threading.Event()
        send("intent", permit)
        permit.wait(1)
        send("progress", b.snapshot(payload))
        raise RuntimeError(SECRET)
    job = execute(root, perform)
    assert job["status"] == "incomplete" and SECRET not in json.dumps(job)
    assert b.main(["--state-dir", str(root), "result", job["job_id"]]) == 3
    assert json.loads(capsys.readouterr().out)["partial"]


def test_real_detached_worker_isolated_and_retrievable(root, tmp_path):
    # Substitute research before main; the production CLI has no fake/live switch.
    fixture = tmp_path / "worker_fixture.py"
    fixture.write_text("import importlib.util,sys\n"
                       f"s=importlib.util.spec_from_file_location('b',{str(SCRIPT)!r})\n"
                       "b=importlib.util.module_from_spec(s);s.loader.exec_module(b)\n"
                       "original=b.work\n"
                       "def fail(q,emit): raise b.BridgeError('fixture_preflight_refused')\n"
                       "b.work=lambda root,jid,fd: original(root,jid,fd,fail)\n"
                       "sys.exit(b.main())\n")
    children = []
    def launch(state, job_id, fd):
        children.append(subprocess.Popen([sys.executable, "-I", str(fixture), "--state-dir", str(state),
                                          "_worker", job_id, str(fd)], pass_fds=(fd,),
                                         start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    job_id = str(uuid.uuid4())
    b.submit(root, job_id, "Public fixture only", "a" * 64, 3, launch)
    try:
        out, err = children[0].communicate(timeout=5)
        assert not out and not err
        with b.locked(root):
            job = b.inspect_job(root, job_id)
        assert job["status"] == "failed" and job["error"] == "fixture_preflight_refused"
        assert not job["submitted"]
    finally:
        if children[0].poll() is None:
            children[0].kill()
            children[0].wait(timeout=3)


def test_network_to_durable_result_without_secrets(root, monkeypatch, payload):
    payload["thread_url"] = "https://www.perplexity.ai/search/public-fixture"
    calls = network(monkeypatch, payload)
    job = execute(root, b.research)
    assert job["status"] == "completed"
    assert job["result"]["thread_url"] == payload["thread_url"]
    assert job["result"]["citations"][0]["url"] == "https://example.org/doc"
    assert len([x for x in calls if x.data]) == 1
    assert SECRET not in (root / (job["job_id"] + ".json")).read_text()
    assert job["verification"]["subscription_quota_used"] is None


def test_production_spawn_drops_ambient_secrets(root, monkeypatch):
    monkeypatch.setenv("PERPLEXITY_COOKIES", SECRET)
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    monkeypatch.setenv("HTTPS_PROXY", "http://example.org")
    popen = Mock()
    monkeypatch.setattr(b.subprocess, "Popen", popen)
    b.spawn(root, str(uuid.uuid4()), 9)
    assert SECRET not in repr(popen.call_args)
    assert "HTTPS_PROXY" not in popen.call_args.kwargs["env"]
    assert "-I" in popen.call_args.args[0]
    assert popen.call_args.kwargs["start_new_session"]


def test_cancel_running_job_wins_over_late_completion(root, capsys):
    def perform(query, send):
        permit = threading.Event()
        send("intent", permit)
        permit.wait(1)
        job_id = next(root.glob("*.json")).stem
        assert b.main(["--state-dir", str(root), "cancel", job_id]) == 0
        return {"answer": "too late"}
    job = execute(root, perform)
    assert job["status"] == "cancelled_local" and job["submitted"]
    assert "result" not in job
    assert json.loads(capsys.readouterr().out)["cancel_requested"]


@pytest.mark.parametrize("thread", ["https://evil.example/search/a", "javascript:alert(1)", "https://perplexity.ai/account"])
def test_thread_urls_not_invented_or_redirected(payload, thread):
    payload["thread_url"] = thread
    with pytest.raises(b.BridgeError, match="invalid_thread_url"):
        b.snapshot(payload)


def test_detached_timeout_stops_descendants(root, tmp_path):
    sentinel = tmp_path / "should-not-exist"
    fixture = tmp_path / "timeout_fixture.py"
    child = f"import time;from pathlib import Path;time.sleep(3);Path({str(sentinel)!r}).touch()"
    fixture.write_text("import importlib.util,sys,subprocess,threading,time\n"
                       f"s=importlib.util.spec_from_file_location('b',{str(SCRIPT)!r})\n"
                       "b=importlib.util.module_from_spec(s);s.loader.exec_module(b)\n"
                       "original=b.work\n"
                       "def block(q,emit):\n"
                       " p=threading.Event();emit('intent',p);p.wait(1)\n"
                       f" subprocess.Popen([sys.executable,'-c',{child!r}])\n"
                       " time.sleep(30)\n"
                       "b.work=lambda root,jid,fd: original(root,jid,fd,block)\n"
                       "sys.exit(b.main())\n")
    children = []
    def launch(state, job_id, fd):
        children.append(subprocess.Popen([sys.executable, "-I", str(fixture), "--state-dir", str(state),
                                          "_worker", job_id, str(fd)], pass_fds=(fd,), start_new_session=True,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    job_id = str(uuid.uuid4())
    b.submit(root, job_id, "Public", "a" * 64, 1, launch)
    try:
        children[0].wait(timeout=4)
        assert b.read_job(root, job_id)["status"] == "timed_out"
        time.sleep(3)
        assert not sentinel.exists()
    finally:
        if children[0].poll() is None:
            os.killpg(children[0].pid, signal.SIGKILL)
            children[0].wait(timeout=3)
