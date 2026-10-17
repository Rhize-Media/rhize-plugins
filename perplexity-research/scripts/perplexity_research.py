#!/usr/bin/env python3
"""Experimental local subscription Research CLI; no API billing or automatic retries.

Request/answer shapes adapted from anxkhn/perplexity-mcp, commit 356f7d0.
See docs/research/perplexity-upstream-LICENSE.txt and perplexity-local-bridge.md.
"""
from __future__ import annotations

import argparse
import base64
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
KEYCHAIN_SERVICE = "perplexity-research-cookies"
MAX_BYTES = 16 * 1024 * 1024
MAX_JSON = 512 * 1024
MAX_THREAD = 4 * 1024 * 1024
MAX_EVENT = 4 * 1024 * 1024
MAX_STREAM = 64 * 1024 * 1024
ACTIVE = {"queued", "preflight", "submitting", "running"}
THREAD_BLOCKS = ["answer_modes", "media_items", "inline_entity_cards", "place_widgets", "finance_widgets",
                 "news_widgets", "shopping_widgets", "search_result_widgets", "inline_images", "inline_assets",
                 "placeholder_cards", "diff_blocks", "entity_group_v2", "refinement_filters", "canvas_mode",
                 "maps_preview", "answer_tabs", "preserve_latex", "in_context_suggestions", "pending_followups",
                 "inline_claims", "unified_assets", "workflow_steps", "workflow_widgets", "navigation_results",
                 "background_agents"]
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
    data = encoded(job)
    if len(data) > MAX_BYTES:
        raise BridgeError("state_too_large")
    fd, temporary = tempfile.mkstemp(dir=root, prefix=".write-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
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
    return {k: v for k, v in job.items() if k not in {"query", "partial", "result", "parent"}} | {
        "parent_job_id": (job.get("parent") or {}).get("job_id"),
        "partial_available": bool(job.get("partial")),
        "remote_may_be_running": job["submitted"] and job["status"] != "completed",
    }


def spawn(root, job_id, fd):
    env = {k: os.environ[k] for k in ("HOME", "USER", "LOGNAME", "PATH", "LANG") if k in os.environ}
    return subprocess.Popen([sys.executable, "-I", str(SCRIPT), "--state-dir", str(root), "--keychain-service", KEYCHAIN_SERVICE,
                             "_worker", job_id, str(fd)], pass_fds=(fd,), env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def submit(root, job_id, query_text, permission_digest, timeout, launch=spawn, *, mode="research", model=None, parent_id=None):
    identity(job_id)
    if not isinstance(query_text, str) or not query_text.strip() or len(query_text.encode()) > 10000:
        raise BridgeError("query_requires_1_to_10000_bytes")
    if not re.fullmatch(r"[a-f0-9]{64}", permission_digest) or not 1 <= timeout <= 1800:
        raise BridgeError("invalid_permission_digest_or_deadline")
    if mode not in {"research", "search"} or (model is not None and
            (not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", model))):
        raise BridgeError("invalid_mode_or_model")
    if parent_id is not None:
        identity(parent_id)
    inputs = [query_text, permission_digest, timeout]
    if (mode, model, parent_id) != ("research", None, None):
        inputs += [mode, model, parent_id]
    fingerprint = sha(encoded(inputs))
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
        parent = None
        if parent_id:
            previous = inspect_job(root, parent_id)
            if previous["status"] != "completed" or not previous.get("result", {}).get("thread_url"):
                raise BridgeError("follow_up_requires_completed_parent_with_thread")
            result = validate_final(previous["result"], previous["requested_model"], previous.get("mode", "research"))
            parent = {"job_id": parent_id, "backend_uuid": identity(result["backend_uuid"]),
                      "thread_id": identity(urllib.parse.urlsplit(result["thread_url"]).path.removeprefix("/search/")),
                      "query": previous["query"], "model": previous["requested_model"],
                      "mode": previous.get("mode", "research")}
        fd = private_open(root / (job_id + ".lock"), os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            job = {"schema": 1, "job_id": job_id, "status": "queued", "query": query_text,
                   "input_sha256": fingerprint, "permission_sha256": permission_digest,
                   "source_sha256": sha(SCRIPT.read_bytes()), "timeout_seconds": timeout,
                   "created_at": time.time(), "submitted": False, "cancel_requested": False,
                   "mode": mode, "selected_model": model, "parent": parent,
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
    return validate_cookies(cookies)


def validate_cookies(cookies):
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
    if len(encoded(cookies)) > 65536:
        raise BridgeError("cookie_set_too_large")
    return cookies


def store_cookies(cookies):
    value = encoded(validate_cookies(cookies))
    account = pwd.getpwuid(os.getuid()).pw_name
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", account):
        raise BridgeError("unsupported_local_account_name")
    command = f'add-generic-password -a {account} -s {KEYCHAIN_SERVICE} -l "Perplexity local bridge" -U -X {value.hex()}\n'
    result = subprocess.run(["/usr/bin/security", "-i"], input=command.encode(),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    if result.returncode or cookies_from_keychain() != cookies:
        raise BridgeError("keychain_write_or_verification_failed")


def auth_crypto():
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return hashes, serialization, padding, rsa, AESGCM
    except ImportError:
        raise BridgeError("auth_requires_python_cryptography") from None


def auth_status(root):
    if not (root / "session.json").exists():
        return {"status": "not_started"}
    state = read_job(root, "session")
    if state["status"] in {"starting", "waiting"} and not worker_live(root, "session"):
        state = {"job_id": "session", "status": "failed", "error": "auth_worker_interrupted"}
        save(root, state)
        (root / "payload.json").unlink(missing_ok=True)
    return state


def auth_root(state_root):
    # Fixed OS temp path keeps CLI/MCP handoffs shared despite sanitized TMPDIR environments.
    name = f"perplexity-auth-{os.getuid()}-{sha(str(state_root).encode())[:16]}"
    return private_root(Path("/tmp").resolve() / name)


def auth_start(root):
    auth_crypto()
    with locked(root):
        state = auth_status(root)
        if worker_live(root, "session"):
            return state
        (root / "payload.json").unlink(missing_ok=True)
        fd = private_open(root / "session.lock", os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = {"job_id": "session", "status": "starting"}
            save(root, state)
            env = {k: os.environ[k] for k in ("HOME", "USER", "LOGNAME", "PATH", "LANG") if k in os.environ}
            subprocess.Popen([sys.executable, "-I", str(SCRIPT), "--state-dir", str(root), "--keychain-service", KEYCHAIN_SERVICE,
                              "_auth-worker", str(fd)], pass_fds=(fd,), env=env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception:
            save(root, {"job_id": "session", "status": "failed", "error": "auth_worker_launch_failed"})
            raise BridgeError("auth_worker_launch_failed") from None
        finally:
            os.close(fd)
    return state


def auth_worker(root, fd, *, store=store_cookies, lifetime=300):
    payload_path = root / "payload.json"
    try:
        hashes, serialization, padding, rsa, AESGCM = auth_crypto()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        transfer_id = str(uuid.uuid4())
        deadline = time.monotonic() + lifetime
        save(root, {"job_id": "session", "status": "waiting", "transfer_id": transfer_id,
                    "expires_at": time.time() + lifetime, "origin": ORIGIN,
                    "browser_adapter": SCRIPT.with_name("perplexity_session_transfer.mjs").as_uri(),
                    "payload_path": str(payload_path), "public_key": key.public_key().public_bytes(
                        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()})
        while not payload_path.exists():
            if time.monotonic() >= deadline:
                raise BridgeError("auth_transfer_expired")
            time.sleep(0.1)
        with os.fdopen(private_open(payload_path, os.O_RDONLY), "rb") as stream:
            raw = stream.read(131073)
        if len(raw) > 131072 or time.monotonic() >= deadline:
            raise BridgeError("auth_invalid_or_expired_payload")
        payload = json.loads(raw)
        if set(payload) != {"transfer_id", "key", "iv", "ciphertext"} or payload["transfer_id"] != transfer_id:
            raise BridgeError("auth_transfer_identity_mismatch")
        decode = lambda name: base64.b64decode(payload[name], validate=True)
        secret = key.decrypt(decode("key"), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                                        algorithm=hashes.SHA256(), label=None))
        cookies = json.loads(AESGCM(secret).decrypt(decode("iv"), decode("ciphertext"), transfer_id.encode()))
        store(validate_cookies(cookies))
        save(root, {"job_id": "session", "status": "stored", "service": KEYCHAIN_SERVICE})
    except Exception as exc:
        save(root, {"job_id": "session", "status": "failed",
                    "error": str(exc) if isinstance(exc, BridgeError) else "auth_transfer_failed"})
    finally:
        payload_path.unlink(missing_ok=True)
        os.close(fd)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise BridgeError("redirect_refused")


class WebClient:
    def __init__(self, cookies):
        self.cookies = cookies
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, data=None):
        headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items()),
                   "User-Agent": "PerplexityResearchLocal/0.2", "Accept": "text/event-stream" if data else "application/json"}
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

    def get_json(self, path, *, max_bytes=MAX_JSON):
        with self.request(path) as response:
            raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
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
        if size > MAX_EVENT:
            raise BridgeError("sse_event_too_large")
        if total > MAX_STREAM:
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


def source_record(source, number=None):
    if not isinstance(source, dict):
        raise BridgeError("invalid_source")
    if number is None:
        number = source.get("citation_id", source.get("id"))
    if number is not None and (isinstance(number, bool) or not re.fullmatch(r"[1-9][0-9]{0,3}", str(number))):
        raise BridgeError("explicit_citation_ids_required")
    url = source.get("url")
    title = source.get("title", source.get("name", ""))
    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 33 for c in url):
        raise BridgeError("invalid_citation_url")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise BridgeError("invalid_citation_url")
    if not isinstance(title, str) or len(title) > 2000:
        raise BridgeError("invalid_citation_title")
    return {"id": int(number) if number is not None else None, "url": url, "title": title}


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
    rows, reports = None, []
    for block in blocks:
        if block.get("intended_usage") == "ask_text" and not answer:
            answer = block.get("markdown_block", {}).get("answer")
        if block.get("intended_usage") == "web_results":
            sources = block.get("web_result_block", {}).get("web_results", [])
        if block.get("intended_usage") == "sources_answer_mode":
            rows = block.get("sources_mode_block", {}).get("rows", [])
        if block.get("intended_usage") == "unified_assets":
            for asset in block.get("unified_assets_block", {}).get("assets", []):
                report = asset.get("research_report")
                if report is not None:
                    if not isinstance(report.get("source_content"), str) or not isinstance(report.get("name"), str):
                        raise BridgeError("invalid_research_report")
                    reports.append({"name": report["name"], "markdown": report["source_content"],
                                    "final": report.get("final") is True})
    if not isinstance(answer, (str, type(None))) or not isinstance(sources, list):
        raise BridgeError("unsupported_answer_shape")
    source_list = [source_record(source) for source in sources]
    citations = [source for source in source_list if source["id"] is not None]
    if rows is not None:
        citations = []
        for row in rows:
            if row.get("citation") is not None:
                citations.append(source_record(row["web_result"], row["citation"]))
            elif row.get("status") == "SELECTED":
                raise BridgeError("selected_source_missing_citation")
    for report in reports:
        # v2.18 report markers address the ordered web_results list, verified against the web UI.
        report["citations"] = [{**source, "id": n} for n, source in enumerate(source_list, 1)]
        report["citation_basis"] = "ordered_web_results_v2_18"
    backend = payload.get("backend_uuid")
    if backend is not None:
        identity(backend)
    observed = payload.get("model_preference", payload.get("user_selected_model"))
    if observed is not None and (not isinstance(observed, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", observed)):
        raise BridgeError("invalid_observed_model")
    thread_url = payload.get("thread_url")
    if thread_url is not None:
        if not isinstance(thread_url, str) or len(thread_url) > 4096 or any(ord(c) < 33 for c in thread_url):
            raise BridgeError("invalid_thread_url")
        parsed = urllib.parse.urlsplit(thread_url)
        if parsed.scheme != "https" or parsed.netloc not in {"www.perplexity.ai", "perplexity.ai"} or not parsed.path.startswith("/search/"):
            raise BridgeError("invalid_thread_url")
    mode = payload.get("search_mode")
    if mode is not None and mode not in {"RESEARCH", "SEARCH"}:
        raise BridgeError("unknown_search_mode")
    return {"answer": answer or "", "citations": citations, "sources": source_list, "reports": reports,
            "backend_uuid": backend, "thread_url": thread_url, "observed_model": observed,
            "observed_search_mode": mode, "server_status": payload.get("status")}


def validate_citations(markdown, citations):
    ids = [item["id"] for item in citations]
    labels = re.findall(r"\[(\d[^\]\n]*)\](?!\()", markdown)
    if any(not label.isascii() or not label.isdecimal() for label in labels):
        raise BridgeError("unsupported_citation_marker")
    markers = {int(n) for n in labels}
    if len(ids) != len(set(ids)) or not markers or not markers.issubset(ids):
        raise BridgeError("citation_mapping_unverified")


def validate_final(value, requested_model, mode="research"):
    if value["server_status"] != "COMPLETED" or not value["answer"].strip() or (mode == "research" and not value["citations"]):
        raise BridgeError("incomplete_answer_or_sources")
    if value["citations"] or re.search(r"\[\d[^\]\n]*\](?!\()", value["answer"]):
        validate_citations(value["answer"], value["citations"])
    for report in value.get("reports", []):
        if not report["final"] or not report["markdown"].strip():
            raise BridgeError("incomplete_research_report")
        validate_citations(report["markdown"], report["citations"])
    if "artifact:" in value["answer"] and not value.get("reports"):
        raise BridgeError("missing_research_report")
    if value["observed_model"] not in {None, requested_model}:
        raise BridgeError("research_model_mismatch")
    if value.get("observed_search_mode") not in {None, mode.upper()}:
        raise BridgeError("research_mode_mismatch")
    return value


def read_thread(client, backend, query_text, requested_model, mode="research", thread_id=None):
    identity(backend)
    thread_id = identity(thread_id or backend)
    # shortcut: first/latest 20 entries only; add pagination if older-parent recovery is needed.
    params = {"with_schematized_response": "true", "version": "2.18", "source": "default",
              "limit": "20", "offset": "0", "from_first": "false", "with_first_entry": "true",
              # Broad Research capabilities suppress ask_text in Search thread responses.
              "supported_block_use_cases": THREAD_BLOCKS if mode == "research" else ["answer_modes", "unified_assets"]}
    response = client.get_json("/rest/thread/" + thread_id + "?" + urllib.parse.urlencode(params, doseq=True),
                               max_bytes=MAX_THREAD)
    entries = [entry for entry in response.get("entries", []) if entry.get("backend_uuid") == backend]
    if len(entries) != 1 or entries[0].get("query_str") != query_text:
        raise BridgeError("recovery_thread_or_query_mismatch")
    entry = entries[0]
    slug = entry.get("thread_url_slug")
    if slug != thread_id or entry.get("search_mode") != mode.upper():
        raise BridgeError("recovery_thread_or_mode_unverified")
    return client.safe(validate_final(snapshot({**entry, "thread_url": ORIGIN + "/search/" + slug}), requested_model, mode))


def recover(root, job_id):
    """Read the persisted remote thread once; never resubmit the query."""
    with locked(root):
        job = inspect_job(root, job_id)
        if worker_live(root, job_id):
            raise BridgeError("worker_busy")
        if job["status"] == "completed":
            return summary(job)
        backend = (job.get("partial") or {}).get("backend_uuid")
        if not job["submitted"] or not backend:
            raise BridgeError("recovery_requires_recorded_submission_and_backend")
        identity(backend)
        original = sha(encoded(job))
    client = WebClient(cookies_from_keychain())
    value = read_thread(client, backend, job["query"], job["requested_model"], job.get("mode", "research"),
                        (job.get("parent") or {}).get("thread_id"))
    with locked(root):
        if sha(encoded(read_job(root, job_id))) != original or worker_live(root, job_id):
            raise BridgeError("recovery_state_changed")
        job["recovery"] = {"prior_status": job["status"], "prior_error": job.get("error"),
                           "at": time.time(), "source_sha256": sha(SCRIPT.read_bytes()), "method": "GET"}
        job.update(status="completed", result=value)
        job.pop("partial", None)
        job.pop("error", None)
        save(root, job)
    return summary(job)


def model_catalog(client):
    session = client.get_json("/api/auth/session")
    user = session.get("user", {})
    tier = user.get("subscription_tier")
    if user.get("subscription_status") not in {"active", "trialing"} or tier not in {"pro", "max"}:
        raise BridgeError("active_subscription_not_verified")
    config = client.get_json("/rest/models/config/v2?version=2.18&source=default")
    if config.get("config_schema") != "v2":
        raise BridgeError("unsupported_model_config")
    if config.get("organization_model_policy") is not None:
        raise BridgeError("research_workflow_unavailable")
    available = {"research": set(), "search": set()}
    defaults = {}
    metadata = config.get("models", {})
    for mode in available:
        model = config.get("default_models", {}).get(mode)
        if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", model) and metadata.get(model, {}).get("mode") == mode:
            defaults[mode] = model
            available[mode].add(model)
    rank = {"free": 0, "pro": 1, "max": 2}
    for row in config.get("search_config", []):
        if rank.get(row.get("subscription_tier"), 99) > rank[tier] or row.get("audience") is not None:
            continue
        for field in ("non_reasoning_model", "reasoning_model"):
            model = row.get(field)
            if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", model) and metadata.get(model, {}).get("mode") == "search":
                available["search"].add(model)
    return client.safe({"subscription_tier": tier, "defaults": defaults,
                        "models": {mode: sorted(ids) for mode, ids in available.items()},
                        "subscription_quota_remaining": None})


def preflight(client, mode="research", selected_model=None):
    catalog = model_catalog(client)
    model = selected_model or catalog["defaults"].get(mode)
    if model not in catalog["models"][mode]:
        raise BridgeError("research_workflow_unavailable" if mode == "research" else "search_model_unavailable")
    return {"subscription_tier": catalog["subscription_tier"], "requested_model": model}


def research(query_text, emit, *, mode="research", model=None, parent=None):
    client = WebClient(cookies_from_keychain())
    checked = preflight(client, mode, model)
    model = checked["requested_model"]
    if parent:
        read_thread(client, parent["backend_uuid"], parent["query"], parent["model"], parent["mode"], parent["thread_id"])
    emit("preflight", checked)
    permit = threading.Event()
    emit("intent", permit)
    if not permit.wait(15):
        raise BridgeError("submission_not_acknowledged_locally")
    params = {"attachments": [], "frontend_context_uuid": str(uuid.uuid4()),
              "frontend_uuid": str(uuid.uuid4()), "is_incognito": False, "language": "en-US",
              "last_backend_uuid": parent["backend_uuid"] if parent else None, "mode": "copilot", "model_preference": model,
              "source": "default", "sources": ["web"], "version": "2.18"}
    latest = None
    with client.request("/rest/sse/perplexity_ask", {"query_str": query_text, "params": params}) as response:
        for event, data in events(response):
            if event == "end_of_stream":
                if latest is None:
                    raise BridgeError("empty_stream")
                if latest["backend_uuid"] and (parent or not latest["thread_url"] or not latest["citations"] or ("artifact:" in latest["answer"] and not latest["reports"])):
                    return read_thread(client, latest["backend_uuid"], query_text, model, mode, parent["thread_id"] if parent else None)
                return validate_final(latest, model, mode)
            if event != "message":
                raise BridgeError("unsupported_or_error_sse_event")
            latest = client.safe(snapshot(json.loads(data)))
            emit("progress", latest)
    raise BridgeError("missing_end_of_stream")


def work(root, job_id, fd, perform=None):
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
            execute = perform or (lambda query, emit: research(query, emit, mode=job.get("mode", "research"),
                                  model=job.get("selected_model"), parent=job.get("parent")))
            messages.put(("done", execute(job["query"], lambda kind, value: messages.put((kind, value)))))
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


def export_markdown(job):
    if job["status"] != "completed":
        raise BridgeError("export_requires_completed_job")
    result = validate_final(job["result"], job["requested_model"], job.get("mode", "research"))
    sections = ["# " + job.get("mode", "research").capitalize() + " result", "Thread: " + (result["thread_url"] or "unavailable"),
                "Subscription quota used: unknown."]
    for answer in [{"markdown": result["answer"], "citations": result["citations"]}, *result.get("reports", [])]:
        markdown = re.sub(r"\[([^\]]+)\]\(artifact:[^)]+\)", r"\1 (included below)", answer["markdown"])
        sections.extend([markdown, "### Sources for this section",
                         "\n".join(f'[{s["id"]}] {s["url"]}' for s in answer["citations"])])
    return "\n\n".join(sections) + "\n"


def main(argv=None):
    global KEYCHAIN_SERVICE
    import runpy
    try:
        settings = runpy.run_path(str(SCRIPT.with_name("perplexity_config.py")))["load_config"]()
    except Exception:
        print(json.dumps({"error": "invalid_local_configuration"}))
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path(settings["stateDir"]))
    parser.add_argument("--keychain-service", default=settings["keychainService"])
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("submit", help="Read a public query from stdin; submit once with a durable ID")
    add.add_argument("--request-id", required=True)
    add.add_argument("--permission-reference", type=Path, default=Path(settings["authorizationReference"]))
    add.add_argument("--timeout", type=int, default=600)
    add.add_argument("--mode", choices=("research", "search"), default="research")
    add.add_argument("--model")
    add.add_argument("--parent-job-id")
    commands.add_parser("models", help="Read current plan-filtered Search and Research model IDs; no submission")
    commands.add_parser("health", help="Check Keychain, subscription and Research configuration with GETs only")
    commands.add_parser("auth-start", help="Begin an explicitly requested browser-to-Keychain setup or refresh")
    commands.add_parser("auth-status", help="Read the public transfer descriptor or completion status")
    commands.add_parser("_auth-worker").add_argument("lock_fd", type=int)
    jobs = commands.add_parser("jobs", help="List local job summaries, ordered by UUID")
    jobs.add_argument("--after", default="")
    jobs.add_argument("--limit", type=int, default=20)
    for command in ("status", "result", "cancel", "recover", "export", "_worker"):
        sub = commands.add_parser(command)
        sub.add_argument("job_id")
        if command == "_worker":
            sub.add_argument("lock_fd", type=int)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", args.keychain_service):
            raise BridgeError("invalid_keychain_service")
        KEYCHAIN_SERVICE = args.keychain_service
        root = private_root(args.state_dir)
        if args.command in {"auth-start", "auth-status", "_auth-worker"}:
            if args.command == "_auth-worker":
                auth_worker(root, args.lock_fd)
                return 0
            transfer_root = auth_root(root)
            output = auth_start(transfer_root) if args.command == "auth-start" else auth_status(transfer_root)
            print(json.dumps(output))
            return 2 if output["status"] == "failed" else 0
        if args.command == "_worker":
            if os.getpgrp() != os.getpid():
                raise BridgeError("worker_requires_own_process_group")
            try:
                work(root, identity(args.job_id), args.lock_fd)
            finally:
                # Terminate blocked HTTP and any Keychain child after persisting terminal state.
                os.killpg(os.getpid(), signal.SIGKILL)
            return 0
        if args.command in {"recover", "health", "models"}:
            def recovery_timeout(_signum, _frame):
                raise BridgeError("read_deadline_exceeded")
            previous = signal.signal(signal.SIGALRM, recovery_timeout)
            signal.alarm(30)
            try:
                if args.command == "recover":
                    output = recover(root, args.job_id)
                elif args.command == "models":
                    output = model_catalog(WebClient(cookies_from_keychain()))
                else:
                    output = {"status": "ready", **preflight(WebClient(cookies_from_keychain())),
                              "subscription_quota_remaining": None}
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous)
        elif args.command == "jobs":
            if not 1 <= args.limit <= 100:
                raise BridgeError("limit_requires_1_to_100")
            if args.after:
                identity(args.after)
            with locked(root):
                paths = sorted(p for p in root.glob("*.json") if p.stem > args.after)
                output = {"jobs": [summary(inspect_job(root, p.stem)) for p in paths[:args.limit]],
                          "next_after": paths[args.limit - 1].stem if len(paths) > args.limit else None}
        elif args.command == "submit":
            with os.fdopen(private_open(args.permission_reference, os.O_RDONLY), "rb") as stream:
                permission = stream.read(65537)
            if not permission.strip() or len(permission) > 65536:
                raise BridgeError("permission_reference_requires_1_to_65536_bytes")
            output = submit(root, args.request_id, sys.stdin.read(10001), sha(permission), args.timeout,
                            mode=args.mode, model=args.model, parent_id=args.parent_job_id)
        else:
            with locked(root):
                job = inspect_job(root, args.job_id)
                if args.command == "export":
                    print(export_markdown(job), end="")
                    return 0
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
