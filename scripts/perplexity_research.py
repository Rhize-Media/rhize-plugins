#!/usr/bin/env python3
"""Experimental local subscription Research CLI; no API billing or automatic retries.

Request/answer shapes adapted from anxkhn/perplexity-mcp, commit 356f7d0.
See docs/research/perplexity-upstream-LICENSE.txt and perplexity-local-bridge.md.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import queue
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ORIGIN = "https://www.perplexity.ai"
KEYCHAIN_SERVICE = "rhize:perplexity-cookies"
MAX_BYTES = 16 * 1024 * 1024
MAX_EVENT = 512 * 1024
ACTIVE = {"queued", "preflight", "submitting", "running"}
SCRIPT = Path(__file__).resolve()


class BridgeError(Exception):
    """Only constant, credential-free error codes may cross this boundary."""


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def private_root(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise BridgeError("symlink_state_path")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise BridgeError("state_requires_owner_and_mode_700")
    return path


def private_open(path, flags):
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1:
        os.close(fd)
        raise BridgeError("unsafe_state_file")
    return fd


def read_job(root, job_id):
    with os.fdopen(private_open(root / (job_id + ".json"), os.O_RDONLY), "rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise BridgeError("state_too_large")
    value = json.loads(data)
    if not isinstance(value, dict) or value.get("job_id") != job_id:
        raise BridgeError("invalid_job_state")
    return value


def save(root, job):
    fd, temporary = tempfile.mkstemp(dir=root, prefix=".write-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded(job))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / (job["job_id"] + ".json"))
        directory = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def locked(root):
    fd = private_open(root / ".lock", os.O_RDWR | os.O_CREAT)
    deadline = time.monotonic() + 5
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise BridgeError("state_busy") from None
                time.sleep(0.02)
        yield
    finally:
        os.close(fd)


def identity(value):
    try:
        if str(uuid.UUID(value)) == value:
            return value
    except (ValueError, AttributeError):
        pass
    raise BridgeError("request_id_must_be_canonical_uuid")


def worker_live(root, job_id):
    fd = private_open(root / (job_id + ".lock"), os.O_RDWR | os.O_CREAT)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False
    finally:
        os.close(fd)


def inspect_job(root, job_id):
    job = read_job(root, identity(job_id))
    if job["status"] in ACTIVE and not worker_live(root, job_id):
        job.update(status="submission_unknown" if job["submitted"] else "interrupted",
                   error="worker_ended_without_terminal_result")
        save(root, job)
    return job


def summary(job):
    return {k: v for k, v in job.items() if k not in {"query", "partial", "result"}} | {
        "partial_available": bool(job.get("partial")),
        "remote_may_be_running": job["submitted"] and job["status"] != "completed",
    }


def spawn(root, job_id, fd):
    env = {k: os.environ[k] for k in ("HOME", "USER", "LOGNAME", "PATH", "LANG") if k in os.environ}
    return subprocess.Popen([sys.executable, "-I", str(SCRIPT), "--state-dir", str(root),
                             "_worker", job_id, str(fd)], pass_fds=(fd,), env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def submit(root, job_id, query_text, permission_digest, timeout, launch=spawn):
    identity(job_id)
    if not isinstance(query_text, str) or not query_text.strip() or len(query_text.encode()) > 10000:
        raise BridgeError("query_requires_1_to_10000_bytes")
    if not re.fullmatch(r"[a-f0-9]{64}", permission_digest) or not 1 <= timeout <= 1800:
        raise BridgeError("invalid_permission_digest_or_deadline")
    fingerprint = sha(encoded([query_text, permission_digest, timeout]))
    with locked(root):
        path = root / (job_id + ".json")
        if path.exists() or path.is_symlink():
            job = inspect_job(root, job_id)
            if job["input_sha256"] != fingerprint:
                raise BridgeError("request_id_conflict")
            return summary(job)
        for path in root.glob("*.json"):
            inspect_job(root, path.stem)
            if worker_live(root, path.stem):
                raise BridgeError("worker_busy")
        fd = private_open(root / (job_id + ".lock"), os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            job = {"schema": 1, "job_id": job_id, "status": "queued", "query": query_text,
                   "input_sha256": fingerprint, "permission_sha256": permission_digest,
                   "source_sha256": sha(SCRIPT.read_bytes()), "timeout_seconds": timeout,
                   "created_at": time.time(), "submitted": False, "cancel_requested": False,
                   "verification": {"actual_research_mode": None, "subscription_quota_used": None,
                                    "web_answer_and_citations_match": None}}
            save(root, job)
            try:
                launch(root, job_id, fd)
            except Exception:
                job.update(status="failed", error="worker_launch_failed")
                save(root, job)
            return summary(job)
        finally:
            # The child inherits this open file description; do not unlock it here.
            os.close(fd)


def cookies_from_keychain():
    result = subprocess.run(["/usr/bin/security", "find-generic-password", "-a",
                             pwd.getpwuid(os.getuid()).pw_name, "-s", KEYCHAIN_SERVICE, "-w"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    if result.returncode or len(result.stdout) > 65536:
        raise BridgeError("keychain_credentials_unavailable")
    try:
        cookies = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise BridgeError("invalid_cookie_json") from None
    if not isinstance(cookies, dict) or not cookies:
        raise BridgeError("invalid_cookie_json")
    for key, value in cookies.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
            raise BridgeError("invalid_cookie_name")
        if not isinstance(value, str) or not value or not re.fullmatch(r"[\x21-\x7e]+", value) or ";" in value:
            raise BridgeError("invalid_cookie_value")
    account = cookies.get("__Host-pplx-last-active-account", "")
    allowed = {"__Host-pplx-last-active-account", "__Secure-pplx.session." + account,
               "next-auth.session-token", "__Secure-next-auth.session-token",
               "next-auth.csrf-token", "__Host-next-auth.csrf-token"}
    if set(cookies) - allowed or not any("session" in key for key in cookies):
        raise BridgeError("unsupported_cookie_set")
    return cookies


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise BridgeError("redirect_refused")


class WebClient:
    def __init__(self, cookies):
        self.cookies = cookies
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, data=None):
        headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items()),
                   "User-Agent": "RhizeResearchLocal/0.1", "Accept": "text/event-stream" if data else "application/json"}
        if "__Host-pplx-last-active-account" in self.cookies:
            headers["x-pplx-account"] = self.cookies["__Host-pplx-last-active-account"]
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(ORIGIN + path, data=encoded(data) if data is not None else None, headers=headers)
        try:
            response = self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise BridgeError({401: "authentication_required", 403: "access_or_challenge_refused",
                               429: "quota_or_rate_limit"}.get(code, "http_error")) from None
        expected = "text/event-stream" if data is not None else "application/json"
        if response.geturl() != ORIGIN + path or response.status != 200 or response.headers.get_content_type() != expected:
            response.close()
            raise BridgeError("unexpected_response_or_challenge")
        return response

    def get_json(self, path):
        with self.request(path) as response:
            raw = response.read(MAX_EVENT + 1)
        if len(raw) > MAX_EVENT:
            raise BridgeError("response_too_large")
        return json.loads(raw)

    def safe(self, value):
        def strings(item):
            if isinstance(item, str):
                yield item
            elif isinstance(item, dict):
                for child in item.values():
                    yield from strings(child)
            elif isinstance(item, list):
                for child in item:
                    yield from strings(child)
        if any(secret in text for text in strings(value) for secret in self.cookies.values()):
            raise BridgeError("credential_echo_refused")
        return value


def events(response):
    """Bound SSE lines/events/total bytes; never discard malformed or error events."""
    event, data, size, total = "message", [], 0, 0
    while True:
        line = response.readline(MAX_EVENT + 1)
        if not line:
            if data:
                raise BridgeError("truncated_sse_event")
            return
        size += len(line)
        total += len(line)
        if size > MAX_EVENT or total > MAX_BYTES:
            raise BridgeError("stream_too_large")
        line = line.decode("utf-8").rstrip("\r\n")
        if not line:
            if data or event != "message":
                yield event, "\n".join(data)
            event, data, size = "message", [], 0
        elif line.startswith(":"):
            continue
        else:
            field, _, value = line.partition(":")
            value = value.removeprefix(" ")
            if field == "event":
                event = value
            elif field == "data":
                data.append(value)


def snapshot(payload):
    """Adapt the upstream FINAL/block shapes without discarding citation metadata."""
    if not isinstance(payload, dict) or payload.get("error"):
        raise BridgeError("server_error_or_invalid_payload")
    blocks = payload.get("blocks") or []
    answer, sources = payload.get("answer"), payload.get("web_results") or payload.get("citations") or []
    steps = payload.get("text")
    if isinstance(steps, str):
        steps = json.loads(steps)
    for step in steps or []:
        if isinstance(step, dict) and step.get("step_type") == "FINAL":
            content = json.loads(step["content"]["answer"])
            answer = content.get("answer")
    for block in blocks:
        if block.get("intended_usage") == "ask_text" and not answer:
            answer = block.get("markdown_block", {}).get("answer")
        if block.get("intended_usage") == "web_results":
            sources = block.get("web_result_block", {}).get("web_results", [])
    if not isinstance(answer, (str, type(None))) or not isinstance(sources, list):
        raise BridgeError("unsupported_answer_shape")
    citations = []
    for source in sources:
        if not isinstance(source, dict):
            raise BridgeError("explicit_citation_ids_required")
        number = source.get("citation_id", source.get("id"))
        url = source.get("url")
        title = source.get("title", source.get("name", ""))
        if isinstance(number, bool) or not re.fullmatch(r"[1-9][0-9]{0,3}", str(number)):
            raise BridgeError("explicit_citation_ids_required")
        if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 33 for c in url):
            raise BridgeError("invalid_citation_url")
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise BridgeError("invalid_citation_url")
        if not isinstance(title, str) or len(title) > 2000:
            raise BridgeError("invalid_citation_title")
        citations.append({"id": int(number), "url": url, "title": title})
    backend = payload.get("backend_uuid")
    if backend is not None:
        identity(backend)
    observed = payload.get("model_preference")
    if observed is not None and (not isinstance(observed, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", observed)):
        raise BridgeError("invalid_observed_model")
    thread_url = payload.get("thread_url")
    if thread_url is not None:
        if not isinstance(thread_url, str) or len(thread_url) > 4096 or any(ord(c) < 33 for c in thread_url):
            raise BridgeError("invalid_thread_url")
        parsed = urllib.parse.urlsplit(thread_url)
        if parsed.scheme != "https" or parsed.netloc not in {"www.perplexity.ai", "perplexity.ai"} or not parsed.path.startswith("/search/"):
            raise BridgeError("invalid_thread_url")
    return {"answer": answer or "", "citations": citations, "backend_uuid": backend,
            "thread_url": thread_url, "observed_model": observed, "server_status": payload.get("status")}


def validate_final(value, requested_model):
    if value["server_status"] != "COMPLETED" or not value["answer"].strip() or not value["citations"]:
        raise BridgeError("incomplete_answer_or_sources")
    ids = [item["id"] for item in value["citations"]]
    labels = re.findall(r"\[(\d[^\]\n]*)\]", value["answer"])
    if any(not label.isascii() or not label.isdecimal() for label in labels):
        raise BridgeError("unsupported_citation_marker")
    markers = {int(n) for n in labels}
    if len(ids) != len(set(ids)) or not markers or not markers.issubset(ids):
        raise BridgeError("citation_mapping_unverified")
    if value["observed_model"] not in {None, requested_model}:
        raise BridgeError("research_model_mismatch")
    return value


def research(query_text, emit):
    client = WebClient(cookies_from_keychain())
    session = client.get_json("/api/auth/session")
    user = session.get("user", {})
    tier = user.get("subscription_tier")
    if user.get("subscription_status") not in {"active", "trialing"} or tier not in {"pro", "max"}:
        raise BridgeError("active_subscription_not_verified")
    config = client.get_json("/rest/models/config/v2?version=2.18&source=default")
    model = config.get("default_models", {}).get("research")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", model):
        raise BridgeError("research_workflow_unavailable")
    if config.get("organization_model_policy") is not None or config.get("models", {}).get(model, {}).get("mode") != "research":
        raise BridgeError("research_workflow_unavailable")
    emit("preflight", client.safe({"subscription_tier": tier, "requested_model": model}))
    permit = threading.Event()
    emit("intent", permit)
    if not permit.wait(15):
        raise BridgeError("submission_not_acknowledged_locally")
    params = {"attachments": [], "frontend_context_uuid": str(uuid.uuid4()),
              "frontend_uuid": str(uuid.uuid4()), "is_incognito": False, "language": "en-US",
              "last_backend_uuid": None, "mode": "copilot", "model_preference": model,
              "source": "default", "sources": ["web"], "version": "2.18"}
    latest = None
    with client.request("/rest/sse/perplexity_ask", {"query_str": query_text, "params": params}) as response:
        for event, data in events(response):
            if event == "end_of_stream":
                if latest is None:
                    raise BridgeError("empty_stream")
                return validate_final(latest, model)
            if event != "message":
                raise BridgeError("unsupported_or_error_sse_event")
            latest = client.safe(snapshot(json.loads(data)))
            emit("progress", latest)
    raise BridgeError("missing_end_of_stream")


def work(root, job_id, fd, perform=research):
    held, expected = os.fstat(fd), os.stat(root / (job_id + ".lock"), follow_symlinks=False)
    if (held.st_dev, held.st_ino) != (expected.st_dev, expected.st_ino):
        raise BridgeError("invalid_worker_lock")
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with locked(root):
        job = read_job(root, job_id)
        if job["status"] != "queued" or job["source_sha256"] != sha(SCRIPT.read_bytes()):
            raise BridgeError("worker_source_or_state_changed")
    messages = queue.Queue(maxsize=8)
    stop = threading.Event()
    deadline = time.monotonic() + max(0, job["created_at"] + job["timeout_seconds"] - time.time())

    def target():
        try:
            messages.put(("done", perform(job["query"], lambda kind, value: messages.put((kind, value)))))
        except Exception as exc:
            messages.put(("error", str(exc) if isinstance(exc, BridgeError) else "transport_or_protocol_error"))

    def interrupted(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    if not job["cancel_requested"] and time.monotonic() < deadline:
        threading.Thread(target=target, daemon=True).start()
    while True:
        try:
            kind, value = messages.get(timeout=0.1)
        except queue.Empty:
            kind, value = None, None
        with locked(root):
            job = read_job(root, job_id)
            if stop.is_set() or job["cancel_requested"]:
                job.update(status="cancelled_local", error="remote_cancellation_unconfirmed")
            elif time.monotonic() >= deadline:
                job.update(status="timed_out", error="overall_deadline_exceeded")
            elif kind == "preflight":
                job.update(value, status="preflight")
            elif kind == "intent":
                job.update(status="submitting", submitted=True)
                save(root, job)
                value.set()
                continue
            elif kind == "progress":
                job.update(status="running", partial=value)
            elif kind == "done":
                job.update(status="completed", result=value)
                job.pop("partial", None)
            elif kind == "error":
                job.update(status=("incomplete" if job.get("partial") else "submission_unknown")
                           if job["submitted"] else "failed", error=value)
            else:
                continue
            save(root, job)
            if job["status"] not in ACTIVE:
                return


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".rhize" / "perplexity-research")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("submit", help="Read a public query from stdin; submit once with a durable ID")
    add.add_argument("--request-id", required=True)
    add.add_argument("--permission-reference", type=Path, required=True)
    add.add_argument("--timeout", type=int, default=600)
    for command in ("status", "result", "cancel", "_worker"):
        sub = commands.add_parser(command)
        sub.add_argument("job_id")
        if command == "_worker":
            sub.add_argument("lock_fd", type=int)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        root = private_root(args.state_dir)
        if args.command == "_worker":
            if os.getpgrp() != os.getpid():
                raise BridgeError("worker_requires_own_process_group")
            try:
                work(root, identity(args.job_id), args.lock_fd)
            finally:
                # Terminate blocked HTTP and any Keychain child after persisting terminal state.
                os.killpg(os.getpid(), signal.SIGKILL)
            return 0
        if args.command == "submit":
            with os.fdopen(private_open(args.permission_reference, os.O_RDONLY), "rb") as stream:
                permission = stream.read(65537)
            if not permission.strip() or len(permission) > 65536:
                raise BridgeError("permission_reference_requires_1_to_65536_bytes")
            output = submit(root, args.request_id, sys.stdin.read(10001), sha(permission), args.timeout)
        else:
            with locked(root):
                job = inspect_job(root, args.job_id)
                if args.command == "cancel" and job["status"] in ACTIVE:
                    job["cancel_requested"] = True
                    save(root, job)
                output = summary(job)
                if args.command == "result":
                    key = "result" if job["status"] == "completed" else "partial"
                    output[key] = job.get(key)
        print(json.dumps(output, ensure_ascii=False))
        return 0 if args.command != "result" or output["status"] == "completed" else 3
    except Exception as exc:
        print(json.dumps({"error": str(exc) if isinstance(exc, BridgeError) else "local_state_or_io_error"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
