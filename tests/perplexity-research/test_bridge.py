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
    backend = str(uuid.uuid4())
    return {"status": "COMPLETED", "model_preference": "pplx_alpha", "backend_uuid": backend,
            "thread_url": b.ORIGIN + "/search/" + backend,
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


def network(monkeypatch, payload, raw=None, tier="pro", model_mode="research", thread=None, config=None):
    calls = []
    client = b.WebClient({"__Secure-next-auth.session-token": SECRET})

    def open_request(request, timeout):
        calls.append(request)
        assert timeout == 15
        assert SECRET in request.get_header("Cookie")
        if request.full_url.endswith("/api/auth/session"):
            data = {"user": {"subscription_tier": tier, "subscription_status": "active"}}
        elif "/models/" in request.full_url:
            data = config or {"config_schema": "v2", "default_models": {"research": "pplx_alpha"}, "models": {"pplx_alpha": {"mode": model_mode}}}
        elif "/rest/thread/" in request.full_url:
            assert request.data is None
            data = {"entries": thread if isinstance(thread, list) else [thread]}
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
    value = b.snapshot(payload)
    assert value["sources"][0]["id"] is None and not value["citations"]
    with pytest.raises(b.BridgeError, match="incomplete_answer_or_sources"):
        b.validate_final(value, "pplx_alpha")


@pytest.fixture
def modern_payload(payload):
    payload["search_mode"] = "RESEARCH"
    payload["query_str"] = "Public"
    payload["thread_url_slug"] = payload["backend_uuid"]
    sources = [{"url": "https://example.org/first", "name": "First"},
               {"url": "https://example.org/second", "name": "Second"}]
    payload["blocks"][0]["markdown_block"]["answer"] = "Summary [1] [Full report](artifact:fixture)"
    payload["blocks"][1]["web_result_block"]["web_results"] = sources
    payload["blocks"].extend([
        {"intended_usage": "sources_answer_mode", "sources_mode_block": {"rows": [
            {"status": "SELECTED", "citation": 1, "web_result": sources[1]},
            {"status": "REVIEWED", "web_result": sources[0]}]}},
        {"intended_usage": "unified_assets", "unified_assets_block": {"assets": [
            {"research_report": {"name": "Report", "source_content": "Full first [1], second [2].", "final": True},
             "download_info": {"token": SECRET}}]}}])
    return payload


def test_modern_report_and_main_citations_have_distinct_mappings(modern_payload):
    value = b.validate_final(b.snapshot(modern_payload), "pplx_alpha")
    assert value["citations"] == [{"id": 1, "url": "https://example.org/second", "title": "Second"}]
    assert [x["url"] for x in value["reports"][0]["citations"]] == ["https://example.org/first", "https://example.org/second"]
    assert value["reports"][0]["markdown"] == "Full first [1], second [2]."
    assert SECRET not in json.dumps(value)


def test_uncited_stream_sources_can_arrive_before_numbered_rows(modern_payload):
    modern_payload["blocks"] = modern_payload["blocks"][:2]
    modern_payload["status"] = "PENDING"
    value = b.snapshot(modern_payload)
    assert len(value["sources"]) == 2 and not value["citations"]
    with pytest.raises(b.BridgeError, match="incomplete_answer_or_sources"):
        b.validate_final(value, "pplx_alpha")


def test_numeric_markdown_link_label_is_not_a_citation(modern_payload):
    modern_payload["blocks"][3]["unified_assets_block"]["assets"][0]["research_report"]["source_content"] += " [2018 announcement](https://example.org/news)"
    b.validate_final(b.snapshot(modern_payload), "pplx_alpha")


def test_explicit_row_citation_is_separate_from_source_identity(modern_payload):
    modern_payload["blocks"][2]["sources_mode_block"]["rows"][0]["web_result"]["id"] = 2
    assert b.validate_final(b.snapshot(modern_payload), "pplx_alpha")["citations"][0]["id"] == 1


@pytest.mark.parametrize("end", [True, False])
def test_modern_stream_uses_one_get_after_end_only(monkeypatch, modern_payload, end):
    partial = {**modern_payload, "blocks": modern_payload["blocks"][:2]}
    calls = network(monkeypatch, partial, raw=wire(partial, end=end), thread=modern_payload)
    if end:
        result = b.research("Public", emit)
        assert result["reports"][0]["markdown"] == "Full first [1], second [2]."
        assert result["observed_search_mode"] == "RESEARCH"
    else:
        with pytest.raises(b.BridgeError, match="missing_end_of_stream"):
            b.research("Public", emit)
    reads = [r for r in calls if "/rest/thread/" in r.full_url]
    assert len(reads) == int(end)
    if reads:
        assert "supported_block_use_cases=unified_assets" in reads[0].full_url
    assert len([r for r in calls if r.data]) == 1


def test_health_checks_subscription_without_post(root, monkeypatch, payload, capsys):
    calls = network(monkeypatch, payload)
    assert b.main(["--state-dir", str(root), "health"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ready" and output["subscription_quota_remaining"] is None
    assert len(calls) == 2 and not any(r.data for r in calls)


def test_markdown_export_keeps_separate_citation_lists(modern_payload):
    job = {"status": "completed", "requested_model": "pplx_alpha",
           "result": b.snapshot(modern_payload)}
    exported = b.export_markdown(job)
    assert '[1] https://example.org/second' in exported
    assert '[1] https://example.org/first\n[2] https://example.org/second' in exported
    assert SECRET not in exported
    assert "artifact:" not in exported and "Full report (included below)" in exported
    job["status"] = "incomplete"
    with pytest.raises(b.BridgeError, match="export_requires_completed_job"):
        b.export_markdown(job)


def test_jobs_pagination_omits_query(root, capsys):
    ids = sorted(str(uuid.uuid4()) for _ in range(3))
    for job_id in ids:
        b.save(root, {"job_id": job_id, "status": "failed", "submitted": False, "query": SECRET})
    assert b.main(["--state-dir", str(root), "jobs", "--limit", "2"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert [j["job_id"] for j in first["jobs"]] == ids[:2] and first["next_after"] == ids[1]
    assert SECRET not in json.dumps(first)
    assert b.main(["--state-dir", str(root), "jobs", "--after", ids[1]]) == 0
    last = json.loads(capsys.readouterr().out)
    assert [j["job_id"] for j in last["jobs"]] == ids[2:] and last["next_after"] is None


@pytest.fixture
def search_config():
    return {"config_schema": "v2", "default_models": {"research": "pplx_alpha", "search": "best"},
            "models": {"pplx_alpha": {"mode": "research"}, "best": {"mode": "search"},
                       "fast": {"mode": "search"}, "thinking": {"mode": "search"},
                       "max_only": {"mode": "search"}, "agent": {"mode": "browser_agent"},
                       "internal": {"mode": "search"}},
            "search_config": [{"subscription_tier": "pro", "non_reasoning_model": "fast", "reasoning_model": "thinking"},
                              {"subscription_tier": "max", "reasoning_model": "max_only"},
                              {"subscription_tier": "pro", "non_reasoning_model": "agent"},
                              {"subscription_tier": "pro", "audience": "internal", "reasoning_model": "internal"}]}


def test_models_filter_tier_mode_and_audience_without_submission(monkeypatch, payload, search_config):
    calls = network(monkeypatch, payload, config=search_config)
    catalog = b.model_catalog(b.WebClient({}))
    assert catalog["models"] == {"research": ["pplx_alpha"], "search": ["best", "fast", "thinking"]}
    assert len(calls) == 2 and not any(r.data for r in calls)


@pytest.mark.parametrize("selected", [None, "thinking", "max_only", "agent", "internal", "missing"])
def test_search_model_is_checked_before_post(monkeypatch, payload, search_config, selected):
    payload.update(model_preference=selected or "best", search_mode="SEARCH")
    calls = network(monkeypatch, payload, config=search_config)
    if selected in {None, "thinking"}:
        value = b.research("Public", emit, mode="search", model=selected)
        assert value["observed_search_mode"] == "SEARCH"
        posted = [json.loads(r.data) for r in calls if r.data]
        assert len(posted) == 1 and posted[0]["params"]["model_preference"] == (selected or "best")
    else:
        with pytest.raises(b.BridgeError, match="search_model_unavailable"):
            b.research("Public", emit, mode="search", model=selected)
        assert not any(r.data for r in calls)


def test_follow_up_verifies_parent_then_reads_new_entry_on_same_thread(monkeypatch, modern_payload, search_config):
    parent = {"backend_uuid": modern_payload["backend_uuid"], "thread_id": modern_payload["backend_uuid"],
              "query": "Public", "model": "pplx_alpha", "mode": "research"}
    child = {"backend_uuid": str(uuid.uuid4()), "thread_url_slug": parent["thread_id"],
             "query_str": "Follow up", "model_preference": "fast", "search_mode": "SEARCH", "status": "COMPLETED",
             "answer": "A plain answer without web claims", "web_results": []}
    calls = network(monkeypatch, child, thread=[modern_payload, child], config=search_config)
    value = b.research("Follow up", emit, mode="search", model="fast", parent=parent)
    assert value["thread_url"] == b.ORIGIN + "/search/" + parent["thread_id"]
    assert value["backend_uuid"] == child["backend_uuid"] and not value["citations"]
    posts = [r for r in calls if r.data]
    assert len(posts) == 1 and json.loads(posts[0].data)["params"]["last_backend_uuid"] == parent["backend_uuid"]
    reads = [i for i,r in enumerate(calls) if "/rest/thread/" in r.full_url]
    assert len(reads) == 2 and reads[0] < calls.index(posts[0]) < reads[1]
    assert all("/rest/thread/" + parent["thread_id"] + "?" in calls[i].full_url for i in reads)


def test_follow_up_parent_mismatch_never_submits(monkeypatch, modern_payload, search_config):
    calls = network(monkeypatch, modern_payload, thread=modern_payload, config=search_config)
    parent = {"backend_uuid": modern_payload["backend_uuid"], "thread_id": modern_payload["backend_uuid"],
              "query": "Wrong query", "model": "pplx_alpha", "mode": "research"}
    with pytest.raises(b.BridgeError, match="recovery_thread_or_query_mismatch"):
        b.research("Follow up", emit, parent=parent)
    assert not any(r.data for r in calls)


def test_search_unmapped_marker_and_wrong_mode_are_not_success(payload):
    value = b.snapshot(payload)
    value["citations"] = []
    with pytest.raises(b.BridgeError, match="citation_mapping_unverified"):
        b.validate_final(value, "pplx_alpha", "search")
    value["answer"] = "No citations"
    value["observed_search_mode"] = "RESEARCH"
    with pytest.raises(b.BridgeError, match="research_mode_mismatch"):
        b.validate_final(value, "pplx_alpha", "search")


def test_submit_binds_mode_model_and_parent_and_hides_parent_query(root, modern_payload):
    parent_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
    b.save(root, {"job_id": parent_id, "status": "completed", "submitted": True, "query": SECRET,
                  "requested_model": "pplx_alpha", "result": b.snapshot(modern_payload)})
    holders, launch = hold_launch()
    try:
        result = b.submit(root, job_id, "Follow up", "a" * 64, 60, launch,
                          mode="search", model="thinking", parent_id=parent_id)
        assert result["parent_job_id"] == parent_id and SECRET not in json.dumps(result)
        b.submit(root, job_id, "Follow up", "a" * 64, 60, launch, mode="search", model="thinking", parent_id=parent_id)
        assert len(holders) == 1
        with pytest.raises(b.BridgeError, match="request_id_conflict"):
            b.submit(root, job_id, "Follow up", "a" * 64, 60, launch, mode="search", model="fast", parent_id=parent_id)
        with pytest.raises(b.BridgeError, match="request_id_conflict"):
            b.submit(root, job_id, "Follow up", "a" * 64, 60, launch, mode="research", model="thinking", parent_id=parent_id)
    finally:
        for fd in holders: os.close(fd)


def test_worker_forwards_persisted_search_options(root, monkeypatch, payload, search_config):
    payload.update(model_preference="thinking", search_mode="SEARCH")
    calls = network(monkeypatch, payload, config=search_config)
    holders, launch = hold_launch()
    job_id = str(uuid.uuid4())
    b.submit(root, job_id, "Public", "a" * 64, 60, launch, mode="search", model="thinking")
    before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        b.work(root, job_id, holders[0])
    finally:
        os.close(holders[0])
        for sig, handler in before.items(): signal.signal(sig, handler)
    job = b.read_job(root, job_id)
    assert job["status"] == "completed" and job["requested_model"] == "thinking"
    assert job["result"]["observed_search_mode"] == "SEARCH"
    assert len([r for r in calls if r.data]) == 1


def test_legacy_request_fingerprint_remains_replay_safe(root):
    job_id = str(uuid.uuid4())
    old = {"job_id": job_id, "status": "failed", "submitted": False,
           "input_sha256": b.sha(b.encoded(["Public", "a" * 64, 60]))}
    b.save(root, old)
    launch = Mock()
    assert b.submit(root, job_id, "Public", "a" * 64, 60, launch)["status"] == "failed"
    launch.assert_not_called()


def test_legacy_completed_result_still_exports(payload):
    value = b.snapshot(payload)
    for key in ("sources", "reports", "observed_search_mode"):
        del value[key]
    result = b.export_markdown({"status": "completed", "requested_model": "pplx_alpha", "result": value})
    assert 'Public answer [1]' in result and 'https://example.org/doc' in result


@pytest.mark.parametrize("change,error", [("unfinished", "incomplete_research_report"),
    ("out_of_range", "citation_mapping_unverified"), ("missing_report", "missing_research_report"),
    ("missing_number", "selected_source_missing_citation"), ("search", "research_mode_mismatch")])
def test_modern_report_refuses_unverified_completion(modern_payload, change, error):
    report = modern_payload["blocks"][3]["unified_assets_block"]["assets"][0]["research_report"]
    if change == "unfinished": report["final"] = False
    if change == "out_of_range": report["source_content"] = "Missing [3]"
    if change == "missing_report": modern_payload["blocks"].pop()
    if change == "missing_number": del modern_payload["blocks"][2]["sources_mode_block"]["rows"][0]["citation"]
    if change == "search": modern_payload["search_mode"] = "SEARCH"
    with pytest.raises(b.BridgeError, match=error):
        b.validate_final(b.snapshot(modern_payload), "pplx_alpha")


@pytest.mark.parametrize("mismatch", [None, "query", "backend", "mode", "pending"])
def test_recovery_only_reads_exact_saved_thread(root, monkeypatch, modern_payload, mismatch):
    holders, launch = hold_launch()
    job_id = str(uuid.uuid4())
    b.submit(root, job_id, "Public", "a" * 64, 60, launch)
    for fd in holders: os.close(fd)
    job = b.read_job(root, job_id)
    job.update(status="incomplete", submitted=True, requested_model="pplx_alpha",
               error="explicit_citation_ids_required", partial={"backend_uuid": modern_payload["backend_uuid"]})
    b.save(root, job)
    original = (root / (job_id + ".json")).read_bytes()
    if mismatch == "query": modern_payload["query_str"] = "Other query"
    if mismatch == "backend": modern_payload["backend_uuid"] = str(uuid.uuid4())
    if mismatch == "mode": modern_payload["search_mode"] = "SEARCH"
    if mismatch == "pending": modern_payload["status"] = "PENDING"
    client = Mock()
    client.get_json.return_value = {"entries": [modern_payload]}
    client.safe.side_effect = lambda value: value
    monkeypatch.setattr(b, "cookies_from_keychain", lambda: {})
    monkeypatch.setattr(b, "WebClient", lambda _cookies: client)
    if mismatch:
        with pytest.raises(b.BridgeError): b.recover(root, job_id)
        assert (root / (job_id + ".json")).read_bytes() == original
    else:
        assert b.recover(root, job_id)["status"] == "completed"
        saved = b.read_job(root, job_id)
        assert saved["recovery"]["prior_error"] == "explicit_citation_ids_required"
        assert saved["result"]["reports"][0]["final"]
        assert b.recover(root, job_id)["status"] == "completed"
    client.get_json.assert_called_once()
    assert client.get_json.call_args.args[0].startswith("/rest/thread/" + job["partial"]["backend_uuid"] + "?")
    client.request.assert_not_called()


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
