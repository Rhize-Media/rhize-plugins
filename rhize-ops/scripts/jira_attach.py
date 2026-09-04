#!/usr/bin/env python3
"""jira_attach.py — upload one or more local files to a Jira issue's attachments.

  jira_attach.py --issue KEY --file PATH [--file PATH]... [--base-url URL]
                  [--config PATH] [--json]

--base-url overrides `jira.baseUrl` from --config (default
~/.claude/rhize-ops/delegate.config.json); either way a trailing "/" is stripped. Each
--file is uploaded as its own multipart/form-data POST to
{base-url}/rest/api/3/issue/{KEY}/attachments.

Credentials: the ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN environment variables when both
are set; otherwise each is read from the macOS Keychain via
`security find-generic-password -a "$USER" -s "claude-code:<NAME>" -w`.

Exit codes:
  0  every file attached
  1  at least one file failed with a non-auth error (HTTP status other than 401/403, a
     URLError, an unreadable local file, or a malformed Jira response) — the remaining
     files are still attempted
  2  a precondition failed before any upload was attempted (credentials missing/empty, no
     usable base URL, or a listed file does not exist), or an HTTP 401/403 was hit — upload
     stops at that point, but the results for every file attempted so far (and "not
     attempted" entries for the rest) are still printed before exiting

The token value and the Authorization header are never written to stdout, stderr, or
exception text.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path.home() / ".claude" / "rhize-ops" / "delegate.config.json"
CREDENTIAL_STORE_HINT = (
    'security add-generic-password -a "$USER" -s "claude-code:ATLASSIAN_API_TOKEN" '
    '-l "Atlassian API token" -U -w "$(pbpaste)"'
)

# Tests replace this with a fake so no real network call is ever made.
urlopen = urllib.request.urlopen


class AuthError(Exception):
    def __init__(self, code: int):
        super().__init__(f"HTTP {code}")
        self.code = code


class UploadError(Exception):
    pass


def credential_message(http_code: int | None = None) -> str:
    if http_code is None:
        return f"Atlassian credentials missing or rejected. Store the token with: {CREDENTIAL_STORE_HINT}"
    return (
        f"Atlassian credentials rejected, or attachments not permitted for this issue "
        f"(HTTP {http_code}). Store or refresh the token with: {CREDENTIAL_STORE_HINT}"
    )


def keychain_value(name: str) -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", f"claude-code:{name}", "-w"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def read_credentials_from_keychain() -> tuple[str, str]:
    return keychain_value("ATLASSIAN_EMAIL"), keychain_value("ATLASSIAN_API_TOKEN")


def read_credentials() -> tuple[str, str]:
    email = os.environ.get("ATLASSIAN_EMAIL")
    token = os.environ.get("ATLASSIAN_API_TOKEN")
    if email and token:
        return email, token
    return read_credentials_from_keychain()


def resolve_base_url(base_url: str | None, config_path: Path) -> str | None:
    if base_url:
        return base_url.rstrip("/")
    if not config_path.is_file():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(config, dict):
        return None
    configured = config.get("jira", {}).get("baseUrl") if isinstance(config.get("jira"), dict) else None
    if not configured:
        return None
    return configured.rstrip("/")


def sanitize_multipart_filename(filename: str) -> str:
    """Escape `"` (which would otherwise terminate the filename="..." header value early)
    and strip \\r/\\n (which would let the filename inject extra header lines)."""
    return filename.replace('"', "%22").replace("\r", "").replace("\n", "")


def build_multipart_body(file_path: Path, boundary: str) -> bytes:
    filename = file_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    data = file_path.read_bytes()
    safe_filename = sanitize_multipart_filename(filename)
    return b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="file"; filename="{safe_filename}"\r\n'.encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            data,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ],
    )


def upload_file(base_url: str, issue_key: str, file_path: Path, email: str, token: str) -> dict[str, Any]:
    boundary = uuid.uuid4().hex
    try:
        body = build_multipart_body(file_path, boundary)
    except OSError as exc:
        raise UploadError(str(exc)) from None
    url = f"{base_url}/rest/api/3/issue/{issue_key}/attachments"
    auth = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "X-Atlassian-Token": "no-check",
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )

    try:
        response = urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise AuthError(exc.code) from None
        raise UploadError(f"HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise UploadError(str(exc.reason)) from None

    try:
        payload = json.loads(response.read().decode("utf-8"))
        first = payload[0]
        return {
            "name": first["filename"],
            "bytes": first["size"],
            "ok": True,
            "id": first["id"],
            "url": first["content"],
            "error": None,
        }
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, UnicodeDecodeError) as exc:
        raise UploadError(f"malformed response from Jira: {exc}") from None


def cmd_attach(args: argparse.Namespace) -> int:
    files = [Path(f) for f in args.file]
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        print(f"file not found: {missing[0]}", file=sys.stderr)
        return 2

    base_url = resolve_base_url(args.base_url, Path(args.config).expanduser())
    if not base_url:
        print(
            "no Jira base URL configured: pass --base-url or set jira.baseUrl in --config",
            file=sys.stderr,
        )
        return 2

    email, token = read_credentials()
    if not email or not token:
        print(credential_message(), file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    auth_error: AuthError | None = None
    for index, file_path in enumerate(files):
        try:
            results.append(upload_file(base_url, args.issue, file_path, email, token))
        except AuthError as exc:
            auth_error = exc
            # Every file from this one onward (including the one that hit the auth
            # error) never completed — mark them all "not attempted" rather than going
            # stdout-silent, so partial progress from earlier files is still visible.
            for remaining_path in files[index:]:
                results.append(
                    {
                        "name": remaining_path.name,
                        "bytes": remaining_path.stat().st_size,
                        "ok": False,
                        "id": None,
                        "url": None,
                        "error": "not attempted",
                    },
                )
            break
        except UploadError as exc:
            results.append(
                {
                    "name": file_path.name,
                    "bytes": file_path.stat().st_size,
                    "ok": False,
                    "id": None,
                    "url": None,
                    "error": str(exc),
                },
            )

    attached = sum(1 for r in results if r["ok"])
    total = len(results)

    if args.json:
        print(json.dumps({"issue": args.issue, "results": results, "attached": attached, "total": total}))
    else:
        for r in results:
            if r["ok"]:
                print(f"attached {r['name']} ({r['bytes']} B) -> {r['url']}")
            else:
                print(f"failed {r['name']}: {r['error']}")
        print(f"attached {attached}/{total}")

    if auth_error is not None:
        print(credential_message(auth_error.code), file=sys.stderr)
        return 2

    return 0 if attached == total else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--file", action="append", required=True, dest="file")
    parser.add_argument("--base-url")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=cmd_attach)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
