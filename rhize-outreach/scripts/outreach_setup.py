#!/usr/bin/env python3
"""Local-only setup, doctor and handoff tooling for the Rhize Outreach plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = Path.home() / "Library" / "Application Support" / "Rhize Outreach"
CONFIG_PATH = APP_ROOT / "config.json"
INSTALL_PATH = APP_ROOT / "installation.json"
HANDOFF_ROOT = APP_ROOT / "handoff"
TEMPLATE_MANIFEST = PLUGIN_ROOT / "assets" / "templates" / "manifest.json"
SETUP_HTML = PLUGIN_ROOT / "assets" / "setup-wizard.html"

STAGES = ["platform", "profile", "variables", "supabase", "agent", "adapters", "dry_run"]
ADAPTER_STATES = {"disabled", "draft_only", "ready", "degraded"}
SECRET_NAMES = {
    "SUPABASE_ANON_KEY",
    "SUPABASE_USER_REFRESH_TOKEN",
    "DATAFORSEO_AUTHORIZATION",
    "GHL_ACCESS_TOKEN",
    "GMAIL_OAUTH_CLIENT_ID",
    "GMAIL_OAUTH_CLIENT_SECRET",
    "VERCEL_TOKEN",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return {} if default is None else default.copy()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def setup_manifest() -> dict:
    return read_json(PLUGIN_ROOT / "setup" / "manifest.json")


def runtime_dependency() -> dict:
    for dependency in setup_manifest().get("dependencies", []):
        if dependency.get("name") == "rhize-outreach runtime":
            return dependency
    raise ValueError("setup manifest omits rhize-outreach runtime dependency")


def command_version(command: str, args: list[str]) -> str | None:
    executable = shutil.which(command)
    if not executable:
        return None
    result = subprocess.run([executable, *args], capture_output=True, text=True, timeout=10, check=False)
    text = (result.stdout or result.stderr).strip().splitlines()
    return text[0] if text else "present"


def runtime_path(pin: str) -> Path:
    return APP_ROOT / "source" / pin


def bootstrap_plan() -> dict:
    dependency = runtime_dependency()
    pin = str(dependency["pin"])
    target = runtime_path(pin)
    return {
        "schema": "rhize-outreach-bootstrap-v1",
        "platform": platform.system(),
        "git": command_version("git", ["--version"]),
        "node": command_version("node", ["--version"]),
        "source": dependency["source"],
        "pin": pin,
        "target": str(target),
        "alreadyPresent": target.exists(),
        "mutates": [str(target), str(INSTALL_PATH)],
        "doesNot": ["contact providers", "deploy Supabase", "publish a site", "send email"],
    }


def bootstrap(check_only: bool) -> dict:
    plan = bootstrap_plan()
    if plan["platform"] != "Darwin":
        raise RuntimeError("Rhize Outreach setup requires macOS because it stores secrets in Keychain")
    if not plan["git"] or not plan["node"]:
        raise RuntimeError("git and Node.js are required")
    if check_only:
        return plan
    target = Path(plan["target"])
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = target.with_name(f".{target.name}.{secrets.token_hex(6)}")
        subprocess.run(["git", "clone", str(plan["source"]), str(temporary)], check=True)
        subprocess.run(["git", "-C", str(temporary), "checkout", "--detach", str(plan["pin"])], check=True)
        os.replace(temporary, target)
    head = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if head != plan["pin"]:
        raise RuntimeError(f"runtime checkout mismatch: expected {plan['pin']}, found {head}")
    node_modules = target / "node_modules"
    if not node_modules.is_dir():
        subprocess.run(["npm", "ci", "--ignore-scripts"], cwd=target, check=True)
    installation = {
        "schema": "rhize-outreach-installation-v1",
        "installedAt": utc_now(),
        "pluginVersion": setup_manifest_version(),
        "source": plan["source"],
        "sourceCommit": head,
        "runtimePath": str(target),
        "cliPath": str(target / "src" / "cli.ts"),
        "dependenciesInstalled": node_modules.is_dir(),
        "templateManifest": str(TEMPLATE_MANIFEST),
    }
    atomic_json(INSTALL_PATH, installation)
    return {**plan, "installed": True, "sourceCommit": head}


def setup_manifest_version() -> str:
    return read_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")["version"]


def keychain_service(name: str) -> str:
    if name not in SECRET_NAMES:
        raise ValueError("unsupported secret name")
    return f"Rhize Outreach {name}"


def keychain_has(name: str) -> bool:
    if platform.system() != "Darwin" or not shutil.which("security"):
        return False
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", keychain_service(name)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def keychain_store(name: str, value: str) -> None:
    if name not in SECRET_NAMES or not value.strip():
        raise ValueError("secret name and value are required")
    subprocess.run(
        [
            "security", "add-generic-password", "-a", os.environ.get("USER", ""),
            "-s", keychain_service(name), "-l", keychain_service(name), "-w", value, "-U",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )


def keychain_read(name: str) -> str:
    if name not in SECRET_NAMES:
        raise ValueError("unsupported secret name")
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", keychain_service(name), "-w"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.rstrip("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def template_status() -> dict:
    manifest = read_json(TEMPLATE_MANIFEST, {"templates": []})
    rows = []
    for item in manifest.get("templates", []):
        path = TEMPLATE_MANIFEST.parent / str(item.get("path", ""))
        actual = sha256(path) if path.is_file() else None
        rows.append({"id": item.get("id"), "path": item.get("path"), "ok": actual == item.get("sha256")})
    return {"ok": bool(rows) and all(row["ok"] for row in rows), "templates": rows}


def doctor() -> dict:
    config = read_json(CONFIG_PATH, {"schema": "rhize-outreach-config-v1", "stages": {}})
    installation = read_json(INSTALL_PATH)
    dependency = runtime_dependency()
    expected = dependency["pin"]
    runtime = Path(str(installation.get("runtimePath", ""))) if installation else None
    actual = None
    if runtime and runtime.is_dir() and (runtime / ".git").exists():
        result = subprocess.run(["git", "-C", str(runtime), "rev-parse", "HEAD"], capture_output=True, text=True)
        if result.returncode == 0:
            actual = result.stdout.strip()
    secret_states = {name: keychain_has(name) for name in sorted(SECRET_NAMES)}
    stages = config.get("stages", {}) if isinstance(config.get("stages"), dict) else {}
    templates = template_status()
    compatibility = {}
    if runtime:
        compatibility = read_json(runtime / "config" / "plugin-compatibility.json")
    expected_manifest_hash = sha256(TEMPLATE_MANIFEST)
    compatibility_ok = bool(
        compatibility.get("schema") == "rhize-outreach-plugin-compatibility-v1"
        and compatibility.get("pluginVersion") == setup_manifest_version()
        and compatibility.get("templateManifestSha256") == expected_manifest_hash
    )
    adapters = config.get("adapters", {}) if isinstance(config.get("adapters"), dict) else {}
    required_secrets = ["SUPABASE_ANON_KEY", "SUPABASE_USER_REFRESH_TOKEN"]
    outcome = "ready" if actual == expected and templates["ok"] and compatibility_ok and all(secret_states[n] for n in required_secrets) else "degraded"
    return {
        "schema": "rhize-outreach-doctor-v1",
        "observedAt": utc_now(),
        "outcome": outcome,
        "platform": platform.system(),
        "pluginVersion": setup_manifest_version(),
        "runtime": {"expectedCommit": expected, "actualCommit": actual, "matches": actual == expected},
        "templates": templates,
        "compatibility": {
            "ok": compatibility_ok,
            "pluginVersion": setup_manifest_version(),
            "templateManifestSha256": expected_manifest_hash,
        },
        "config": {"present": CONFIG_PATH.is_file(), "completedStages": [stage for stage in STAGES if stages.get(stage)]},
        "workspace": {"configured": bool(config.get("workspaceSlug")), "supabaseUrlConfigured": bool(config.get("supabaseUrl"))},
        "secrets": secret_states,
        "adapters": adapters,
        "releaseBoundary": "no provider send or publish was performed",
    }


def no_send_dry_run() -> dict:
    installation = read_json(INSTALL_PATH)
    runtime = Path(str(installation.get("runtimePath", "")))
    cli = runtime / "src" / "cli.ts"
    if not cli.is_file() or not CONFIG_PATH.is_file():
        raise RuntimeError("install the pinned runtime and save setup configuration first")
    environment = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL")
        if key in os.environ
    }
    secret_values = []
    for name in SECRET_NAMES:
        if keychain_has(name):
            value = keychain_read(name)
            environment[name] = value
            secret_values.append(value)
    environment["OUTREACH_CONFIG_PATH"] = str(CONFIG_PATH)

    def run(command: str) -> dict:
        result = subprocess.run(
            ["node", str(cli), command, "--config", str(CONFIG_PATH)],
            cwd=runtime,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        combined = result.stdout + result.stderr
        if any(value and value in combined for value in secret_values):
            raise RuntimeError("runtime output included a secret value; output was discarded")
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "runtime dry run failed").strip()[:1000])
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise RuntimeError("runtime dry run returned an invalid result")
        return value

    return {
        "schema": "rhize-outreach-no-send-dry-run-v1",
        "observedAt": utc_now(),
        "outcome": "ready",
        "runtime": run("doctor"),
        "skills": run("skills-doctor"),
        "externalEffects": [],
        "releaseBoundary": "No provider request, email send or site publish was performed.",
    }


def validate_config_patch(patch: dict) -> dict:
    allowed = {"operatorName", "workspaceSlug", "supabaseUrl", "agentHost", "adapters"}
    if set(patch) - allowed:
        raise ValueError("config contains unsupported fields")
    cleaned: dict = {}
    for key in ("operatorName", "workspaceSlug", "supabaseUrl", "agentHost"):
        if key in patch:
            value = str(patch[key]).strip()
            if len(value) > 300:
                raise ValueError(f"{key} is too long")
            cleaned[key] = value
    if "adapters" in patch:
        if not isinstance(patch["adapters"], dict):
            raise ValueError("adapters must be an object")
        adapters = {}
        for name in ("gmail", "ghl", "vercel"):
            value = patch["adapters"].get(name, "disabled")
            if value not in ADAPTER_STATES:
                raise ValueError(f"invalid adapter state for {name}")
            adapters[name] = value
        cleaned["adapters"] = adapters
    return cleaned


def update_config(patch: dict) -> dict:
    config = read_json(CONFIG_PATH, {"schema": "rhize-outreach-config-v1", "revision": 0, "stages": {}})
    config.update(validate_config_patch(patch))
    config["revision"] = int(config.get("revision", 0)) + 1
    config["updatedAt"] = utc_now()
    atomic_json(CONFIG_PATH, config)
    return config


def complete_stage(stage: str) -> dict:
    if stage not in STAGES:
        raise ValueError("unknown setup stage")
    config = read_json(CONFIG_PATH, {"schema": "rhize-outreach-config-v1", "revision": 0, "stages": {}})
    stages = config.setdefault("stages", {})
    stages[stage] = utc_now()
    config["revision"] = int(config.get("revision", 0)) + 1
    config["updatedAt"] = utc_now()
    atomic_json(CONFIG_PATH, config)
    return config


def generate_handoff() -> dict:
    HANDOFF_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    email = HANDOFF_ROOT / "tom-setup-email.md"
    prompt = HANDOFF_ROOT / "tom-setup-prompt.md"
    email.write_text(
        """Subject: Rhize Outreach plugin setup\n\nHi Tom,\n\nWe've packaged the prospect research, website/audit and email-review workflow as the internal Rhize Outreach plugin. Install it from the Rhize plugin marketplace, then run `/rhize-outreach:setup`.\n\nAt **Input environment variables**, enter the values supplied through our approved secret-sharing channel or complete the provider OAuth prompt on your Mac. The wizard will request only the variables your enabled adapters need:\n\n- `SUPABASE_ANON_KEY` and `SUPABASE_USER_REFRESH_TOKEN`\n- `DATAFORSEO_AUTHORIZATION`\n- `GHL_ACCESS_TOKEN`\n- `GMAIL_OAUTH_CLIENT_ID` and `GMAIL_OAUTH_CLIENT_SECRET`\n- `VERCEL_TOKEN`\n\nThe values are stored in your macOS Keychain. Do not reply with them or paste them into Claude/Codex chat. The Supabase service-role key and database password are not part of your setup.\n\nAfter the no-send dry run, run `/rhize-outreach:doctor` and send me only its redacted result if anything is degraded. Gmail and GHL remain in draft/preparation mode until we review a real delivery together.\n\nThanks,\nJim\n""",
        encoding="utf-8",
    )
    prompt.write_text(
        """Set up the installed Rhize Outreach plugin on this Mac. Invoke the plugin's setup skill, resume the first incomplete stage, and use the local loopback wizard for all configuration. At “Input environment variables,” let me enter values locally; never ask me to paste a secret into chat and never print a Keychain value. Verify the pinned runtime and template digests, connect my authenticated Supabase workspace, leave Gmail and GHL in draft-only mode, keep Vercel disabled unless already configured, and finish with the no-send dry run plus a redacted doctor report. Do not publish a site or send an email.\n""",
        encoding="utf-8",
    )
    os.chmod(email, 0o600)
    os.chmod(prompt, 0o600)
    return {"email": str(email), "prompt": str(prompt), "containsSecretValues": False}


class WizardHandler(BaseHTTPRequestHandler):
    server_version = "RhizeOutreachSetup/1"

    def _authorized(self) -> bool:
        parsed = urlparse(self.path)
        query_token = parse_qs(parsed.query).get("token", [None])[0]
        header_token = self.headers.get("X-Rhize-Setup-Token")
        return secrets.compare_digest(str(query_token or header_token or ""), self.server.token)  # type: ignore[attr-defined]

    def _json(self, status: int, value: dict) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 65536:
            raise ValueError("invalid request size")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("request body must be an object")
        return value

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._authorized():
            self._json(HTTPStatus.FORBIDDEN, {"error": "invalid setup session"})
            return
        if parsed.path == "/":
            body = SETUP_HTML.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/status":
            self._json(HTTPStatus.OK, doctor())
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._authorized():
            self._json(HTTPStatus.FORBIDDEN, {"error": "invalid setup session"})
            return
        try:
            payload = self._payload()
            if parsed.path == "/api/config":
                config = update_config(payload)
                result = {"revision": config["revision"]}
            elif parsed.path == "/api/secret":
                keychain_store(str(payload.get("name", "")), str(payload.get("value", "")))
                result = {"stored": True, "name": payload.get("name")}
            elif parsed.path == "/api/stage":
                config = complete_stage(str(payload.get("stage", "")))
                result = {"revision": config["revision"], "stage": payload.get("stage")}
            elif parsed.path == "/api/handoff":
                result = generate_handoff()
            elif parsed.path == "/api/dry-run":
                result = no_send_dry_run()
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._json(HTTPStatus.OK, result)
        except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)[:500]})

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(port: int, no_open: bool) -> None:
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", port), WizardHandler)
    server.token = token  # type: ignore[attr-defined]
    url = f"http://127.0.0.1:{server.server_port}/?token={token}"
    print(json.dumps({"url": url, "pid": os.getpid(), "noSend": True}), flush=True)
    if not no_open:
        webbrowser.open(url)
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    bootstrap_parser = sub.add_parser("bootstrap")
    bootstrap_parser.add_argument("--check", action="store_true")
    sub.add_parser("doctor").add_argument("--json", action="store_true")
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--port", type=int, default=0)
    serve_parser.add_argument("--no-open", action="store_true")
    sub.add_parser("handoff")
    args = parser.parse_args()
    if args.command == "bootstrap":
        print(json.dumps(bootstrap(args.check), indent=2))
    elif args.command == "doctor":
        result = doctor()
        print(json.dumps(result, indent=2) if args.json else f"Rhize Outreach doctor: {result['outcome']}")
        return 0 if result["outcome"] == "ready" else 1
    elif args.command == "serve":
        serve(args.port, args.no_open)
    elif args.command == "handoff":
        print(json.dumps(generate_handoff(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
