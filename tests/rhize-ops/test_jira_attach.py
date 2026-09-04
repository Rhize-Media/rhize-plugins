"""test_jira_attach.py — jira_attach.py file-upload CLI per task-1-brief.md Contract B.
Hermetic: `read_credentials` (or the Keychain helper it calls) and `urlopen` are always
monkeypatched; `security` and the real network are never invoked. Files live under tmp_path.
"""
import base64
import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-ops" / "scripts" / "jira_attach.py"
SPEC = importlib.util.spec_from_file_location("jira_attach", SCRIPT)
jira_attach = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(jira_attach)

# Captured before any test monkeypatches jira_attach.read_credentials, so the
# credentials-override test can restore the real (env-first) implementation.
REAL_READ_CREDENTIALS = jira_attach.read_credentials


@pytest.fixture(autouse=True)
def clear_atlassian_env(monkeypatch):
    monkeypatch.delenv("ATLASSIAN_EMAIL", raising=False)
    monkeypatch.delenv("ATLASSIAN_API_TOKEN", raising=False)


@pytest.fixture(autouse=True)
def stub_credentials(monkeypatch):
    # Every test that doesn't care about credential resolution itself gets a working
    # (email, token) pair without touching the Keychain; tests exercising credential
    # resolution override this with their own monkeypatch.
    monkeypatch.setattr(jira_attach, "read_credentials", lambda: ("jim@rhize.media", "TEST-TOKEN"))


def run(argv: list[str], capsys):
    code = jira_attach.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def write_file(tmp_path: Path, name: str, content: bytes = b"file bytes") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


class FakeResponse:
    def __init__(self, payload: list[dict]):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body


def attachment_payload(filename: str, size: int, attachment_id: str = "10001") -> list[dict]:
    return [
        {
            "id": attachment_id,
            "filename": filename,
            "size": size,
            "content": f"https://example.atlassian.net/rest/api/3/attachment/content/{attachment_id}",
        },
    ]


def test_uploads_each_file_as_one_multipart_post_with_required_headers(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, "one.txt", b"hello one")
    file2 = write_file(tmp_path, "two.txt", b"hello two")

    requests: list = []

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        name = "one.txt" if len(requests) == 1 else "two.txt"
        size = len(b"hello one") if len(requests) == 1 else len(b"hello two")
        return FakeResponse(attachment_payload(name, size))

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, out, _err = run(
        [
            "--issue", "PROJ-1", "--file", str(file1), "--file", str(file2),
            "--base-url", "https://example.atlassian.net",
        ],
        capsys,
    )

    assert code == 0
    assert len(requests) == 2
    for request, expected_name, expected_bytes in (
        (requests[0], "one.txt", b"hello one"),
        (requests[1], "two.txt", b"hello two"),
    ):
        assert request.get_method() == "POST"
        assert request.full_url == "https://example.atlassian.net/rest/api/3/issue/PROJ-1/attachments"
        expected_auth = "Basic " + base64.b64encode(b"jim@rhize.media:TEST-TOKEN").decode()
        assert request.get_header("Authorization") == expected_auth
        assert request.get_header("X-atlassian-token") == "no-check"
        assert request.get_header("Accept") == "application/json"
        content_type = request.get_header("Content-type", "")
        assert content_type.startswith("multipart/form-data; boundary=")
        assert f'name="file"; filename="{expected_name}"'.encode() in request.data
        assert expected_bytes in request.data

    assert "attached one.txt (9 B) -> https://example.atlassian.net/rest/api/3/attachment/content/10001" in out
    assert "attached two.txt (9 B) -> https://example.atlassian.net/rest/api/3/attachment/content/10001" in out
    assert out.strip().splitlines()[-1] == "attached 2/2"


def test_json_output_shape(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, "report.pdf", b"pdf bytes here")

    def fake_urlopen(request, timeout=None):
        return FakeResponse(attachment_payload("report.pdf", len(b"pdf bytes here"), attachment_id="55"))

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, out, _err = run(
        ["--issue", "PROJ-2", "--file", str(file1), "--base-url", "https://example.atlassian.net", "--json"],
        capsys,
    )
    assert code == 0
    payload = json.loads(out)
    assert payload == {
        "issue": "PROJ-2",
        "results": [
            {
                "name": "report.pdf",
                "bytes": len(b"pdf bytes here"),
                "ok": True,
                "id": "55",
                "url": "https://example.atlassian.net/rest/api/3/attachment/content/55",
                "error": None,
            },
        ],
        "attached": 1,
        "total": 1,
    }


def test_one_failing_upload_gives_exit_1_and_continues(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, "fails.txt", b"nope")
    file2 = write_file(tmp_path, "ok.txt", b"fine")

    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(request.full_url, 500, "Internal Server Error", {}, None)
        return FakeResponse(attachment_payload("ok.txt", len(b"fine")))

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, out, _err = run(
        [
            "--issue", "PROJ-3", "--file", str(file1), "--file", str(file2),
            "--base-url", "https://example.atlassian.net", "--json",
        ],
        capsys,
    )
    assert code == 1
    assert calls["n"] == 2
    payload = json.loads(out)
    assert payload["results"][0]["ok"] is False
    assert isinstance(payload["results"][0]["error"], str) and payload["results"][0]["error"]
    assert payload["results"][1]["ok"] is True
    assert payload["attached"] == 1
    assert payload["total"] == 2


def test_401_gives_exit_2_with_store_hint_and_no_token_in_output(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, "secret.txt", b"data")
    monkeypatch.setattr(jira_attach, "read_credentials", lambda: ("jim@rhize.media", "SECRET-TOKEN-VALUE"))

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, out, err = run(
        ["--issue", "PROJ-4", "--file", str(file1), "--base-url", "https://example.atlassian.net"],
        capsys,
    )
    assert code == 2
    assert "SECRET-TOKEN-VALUE" not in out
    assert "SECRET-TOKEN-VALUE" not in err
    assert (
        "Atlassian credentials rejected, or attachments not permitted for this issue "
        "(HTTP 401). Store or refresh the token with: security add-generic-password "
        '-a "$USER" -s "claude-code:ATLASSIAN_API_TOKEN" -l "Atlassian API token" -U '
        '-w "$(pbpaste)"'
    ) in err


def test_missing_credentials_exit_2_before_any_upload(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, "a.txt", b"data")
    monkeypatch.setattr(jira_attach, "read_credentials", lambda: ("", ""))

    def fake_urlopen(request, timeout=None):
        raise AssertionError("urlopen must not be called when credentials are missing")

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, out, err = run(
        ["--issue", "PROJ-5", "--file", str(file1), "--base-url", "https://example.atlassian.net"],
        capsys,
    )
    assert code == 2
    assert out == ""
    assert err.strip() != ""


def test_missing_file_exit_2_before_any_upload(tmp_path, capsys, monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise AssertionError("urlopen must not be called when a file is missing")

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, out, err = run(
        [
            "--issue", "PROJ-6", "--file", str(tmp_path / "does-not-exist.txt"),
            "--base-url", "https://example.atlassian.net",
        ],
        capsys,
    )
    assert code == 2
    assert out == ""
    assert err.strip() != ""


def test_base_url_from_config_file_and_trailing_slash_stripped(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, "a.txt", b"data")
    config_path = tmp_path / "delegate.config.json"
    config_path.write_text(
        json.dumps({"jira": {"baseUrl": "https://example.atlassian.net/"}}), encoding="utf-8",
    )

    requests: list = []

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        return FakeResponse(attachment_payload("a.txt", len(b"data")))

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, _out, _err = run(
        ["--issue", "PROJ-7", "--file", str(file1), "--config", str(config_path)], capsys,
    )
    assert code == 0
    assert requests[0].full_url == "https://example.atlassian.net/rest/api/3/issue/PROJ-7/attachments"


def test_env_credentials_override_keychain(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, "a.txt", b"data")
    monkeypatch.setenv("ATLASSIAN_EMAIL", "env@rhize.media")
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "ENV-TOKEN")

    def keychain_must_not_be_called() -> tuple[str, str]:
        raise AssertionError("Keychain helper must not be called when env credentials are set")

    monkeypatch.setattr(jira_attach, "read_credentials_from_keychain", keychain_must_not_be_called)
    # Undo the autouse stub_credentials monkeypatch so the real read_credentials()
    # (env-first) runs and is exercised by this test.
    monkeypatch.setattr(jira_attach, "read_credentials", REAL_READ_CREDENTIALS)

    requests: list = []

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        return FakeResponse(attachment_payload("a.txt", len(b"data")))

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, _out, _err = run(
        ["--issue", "PROJ-8", "--file", str(file1), "--base-url", "https://example.atlassian.net"], capsys,
    )
    assert code == 0
    assert len(requests) == 1


class FakeRawResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body


def test_non_utf8_response_gives_failed_result_and_exit_1_continues(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, "bad.txt", b"data one")
    file2 = write_file(tmp_path, "good.txt", b"data two")

    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeRawResponse(b"\xff\xfe not utf-8")
        return FakeResponse(attachment_payload("good.txt", len(b"data two")))

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, out, _err = run(
        [
            "--issue", "PROJ-9", "--file", str(file1), "--file", str(file2),
            "--base-url", "https://example.atlassian.net", "--json",
        ],
        capsys,
    )
    assert code == 1
    assert calls["n"] == 2
    payload = json.loads(out)
    assert payload["results"][0]["ok"] is False
    assert isinstance(payload["results"][0]["error"], str) and payload["results"][0]["error"]
    assert payload["results"][1]["ok"] is True
    assert payload["attached"] == 1
    assert payload["total"] == 2


def test_read_bytes_oserror_during_upload_gives_failed_result_and_exit_1(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, "vanishes.txt", b"data")

    original_read_bytes = Path.read_bytes

    def failing_read_bytes(self):
        if self == file1:
            raise OSError("file vanished before upload")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", failing_read_bytes)

    def fake_urlopen(request, timeout=None):
        raise AssertionError("urlopen must not be called when read_bytes fails")

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, out, _err = run(
        [
            "--issue", "PROJ-10", "--file", str(file1),
            "--base-url", "https://example.atlassian.net", "--json",
        ],
        capsys,
    )
    assert code == 1
    payload = json.loads(out)
    assert payload["results"][0]["ok"] is False
    assert "file vanished before upload" in payload["results"][0]["error"]


def test_filename_with_double_quote_is_escaped_in_multipart_header(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, 'weird"name.txt', b"data")

    requests: list = []

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        return FakeResponse(attachment_payload(file1.name, len(b"data")))

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, _out, _err = run(
        ["--issue", "PROJ-11", "--file", str(file1), "--base-url", "https://example.atlassian.net"], capsys,
    )
    assert code == 0
    assert b'filename="weird%22name.txt"' in requests[0].data
    assert b'filename="weird"name.txt"' not in requests[0].data


def test_mid_run_401_prints_results_so_far_and_marks_remaining_not_attempted(tmp_path, capsys, monkeypatch):
    file1 = write_file(tmp_path, "one.txt", b"ok")
    file2 = write_file(tmp_path, "two.txt", b"blocked")
    monkeypatch.setattr(jira_attach, "read_credentials", lambda: ("jim@rhize.media", "SECRET-TOKEN-VALUE"))

    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(attachment_payload("one.txt", len(b"ok")))
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(jira_attach, "urlopen", fake_urlopen)

    code, out, err = run(
        [
            "--issue", "PROJ-12", "--file", str(file1), "--file", str(file2),
            "--base-url", "https://example.atlassian.net", "--json",
        ],
        capsys,
    )
    assert code == 2
    assert calls["n"] == 2
    assert "SECRET-TOKEN-VALUE" not in out
    assert "SECRET-TOKEN-VALUE" not in err
    payload = json.loads(out)
    assert payload["results"][0] == {
        "name": "one.txt",
        "bytes": len(b"ok"),
        "ok": True,
        "id": "10001",
        "url": "https://example.atlassian.net/rest/api/3/attachment/content/10001",
        "error": None,
    }
    assert payload["results"][1]["ok"] is False
    assert payload["results"][1]["error"] == "not attempted"
    assert "Atlassian credentials rejected, or attachments not permitted for this issue (HTTP 401)" in err
