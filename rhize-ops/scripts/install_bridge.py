#!/usr/bin/env python3
"""Install, re-activate or roll back a pinned rhize-bridge release in Claude and Codex.

A release is an immutable copy at ~/.rhize/agent-bridge-releases/<version>/agent_bridge.py.
Activating one changes only the script path (args[0]) of each host's rhize-bridge entry; any
other configuration change is an error and the previous state is restored. Procedure and
rationale: rhize-ops/docs/agent-bridge.md.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import uuid
from pathlib import Path

NAME = "rhize-bridge"
TOOLS = {"request_review", "request_task", "job_status", "cancel_job"}
SOURCE = "rhize-ops/scripts/agent_bridge.py"
MANIFEST = "rhize-ops/.claude-plugin/plugin.json"


class InstallError(Exception):
    pass


def releases():
    return Path.home() / ".rhize" / "agent-bridge-releases"


def claude_json():
    return Path.home() / ".claude.json"


def codex_toml():
    return Path.home() / ".codex" / "config.toml"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(argv, timeout=60, text=True):
    try:
        r = subprocess.run(argv, capture_output=True, text=text, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise InstallError(f"{' '.join(map(str, argv[:3]))} timed out after {timeout}s")
    if r.returncode:
        err = r.stderr if text else r.stderr.decode(errors="replace")
        raise InstallError(f"{' '.join(map(str, argv[:3]))} failed (exit {r.returncode}): {err.strip()[:300]}")
    return r.stdout


def private_mkdir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def release_version(script):
    script = Path(script)
    return script.parent.name if script.parent.parent == releases() else None


def mcp_entries(doc):
    """Every Claude MCP entry keyed by (scope, name): user scope plus each project scope."""
    out = {("user", k): v for k, v in (doc.get("mcpServers") or {}).items()}
    for project, data in (doc.get("projects") or {}).items():
        out.update({(project, k): v for k, v in ((data or {}).get("mcpServers") or {}).items()})
    return out


def registrations():
    claude = json.loads(claude_json().read_text()).get("mcpServers", {}).get(NAME)
    codex = tomllib.loads(codex_toml().read_text()).get("mcp_servers", {}).get(NAME)
    missing = [h for h, e in (("Claude", claude), ("Codex", codex)) if not e]
    if missing:
        raise InstallError(f"{NAME} is not registered in {' and '.join(missing)}; do the first install "
                           "by hand (rhize-ops/docs/agent-bridge.md)")
    if claude["args"][0] != codex["args"][0]:
        raise InstallError(f"hosts disagree: Claude runs {claude['args'][0]}, Codex runs "
                           f"{codex['args'][0]}; repair one entry by hand first")
    return {"claude": claude, "codex": codex}


def swap_codex_text(text, old, new):
    """Replace rhize-bridge's script path; any other parsed change is an error."""
    if text.count(old) != 1:
        raise InstallError(f"expected the old script path once in config.toml, found {text.count(old)}")
    result = text.replace(old, new)
    expect = tomllib.loads(text)
    expect["mcp_servers"][NAME]["args"][0] = new
    if tomllib.loads(result) != expect:
        raise InstallError("config.toml would change outside rhize-bridge args[0]")
    return result


def check_claude_entries(before, after, entry):
    want = mcp_entries(before)
    want[("user", NAME)] = entry
    got = mcp_entries(after)
    changed = sorted(k for k in want.keys() | got.keys() if want.get(k) != got.get(k))
    if changed:
        raise InstallError(f"Claude MCP entries differ from the expected result: {changed}")


def set_claude_entry(claude_bin, entry):
    # The entry is already gone when restoring after a failed add-json.
    if NAME in json.loads(claude_json().read_text()).get("mcpServers", {}):
        run([claude_bin, "mcp", "remove", NAME, "-s", "user"])
    run([claude_bin, "mcp", "add-json", NAME, "-s", "user", json.dumps(entry)])


class Server:
    """Minimal JSON-RPC stdio client for the handshake and optional live review."""

    def __init__(self, argv, stderr):
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=stderr, text=True)
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.seq = 0

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def call(self, method, params=None, timeout=30):
        self.seq += 1
        self.send({"jsonrpc": "2.0", "id": self.seq, "method": method, "params": params or {}})
        deadline = time.monotonic() + timeout
        while True:
            try:
                line = self.lines.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                raise InstallError(f"bridge did not answer {method} within {timeout}s")
            if line is None:
                raise InstallError(f"bridge exited before answering {method}")
            msg = json.loads(line)
            if msg.get("id") == self.seq:
                if "error" in msg:
                    raise InstallError(f"{method} failed: {msg['error']}")
                return msg["result"]

    def tool(self, name, arguments):
        return json.loads(self.call("tools/call", {"name": name, "arguments": arguments})["content"][0]["text"])

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            raise InstallError("bridge did not exit within 30s of stdin closing")


def probe(entry, origin, evidence, model):
    """Handshake (and, with a model, one synthetic review) against the registered argv."""
    argv = [entry["command"], *entry["args"], "--state-dir", str(evidence / f"state-{origin}")]
    with open(evidence / f"probe-{origin}.stderr", "w") as stderr:
        server = Server(argv, stderr)
        try:
            init = server.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                              "clientInfo": {"name": "install-bridge", "version": "1"}})
            server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            tools = {t["name"] for t in server.call("tools/list")["tools"]}
            if tools != TOOLS:
                raise InstallError(f"{origin} bridge lists tools {sorted(tools)}, expected {sorted(TOOLS)}")
            result = {"handshake": f"initialize {init['protocolVersion']}; {len(tools)} tools"}
            if model:
                result["live_review"] = live_review(server, "codex" if origin == "claude" else "claude", model)
        finally:
            server.close()
    return result


def live_review(server, target, model):
    job = server.tool("request_review", {
        "request_id": str(uuid.uuid4()), "target": target, "model": model, "effort": "low",
        "prompt": "Review this function for a bug and answer in one sentence: def add(a, b): return a - b",
        "authority": "Synthetic install verification of the bridge release; no files are involved.",
        "timeout_seconds": 180})
    job_id = job.get("job_id") or job.get("id")
    deadline = time.monotonic() + 240
    while True:
        status = server.tool("job_status", {"job_id": job_id})
        if status.get("status") not in ("queued", "running"):
            break
        if time.monotonic() > deadline:
            raise InstallError(f"live review to {target} still {status.get('status')} after 240s")
        time.sleep(3)
    if status.get("status") != "completed":
        raise InstallError(f"live review to {target} ended {status.get('status')}")
    meta = status.get("metadata") or {}
    return {"target": target, "status": "completed",
            **{k: meta.get(k, status.get(k)) for k in ("requested_model", "observed_model", "model_identity_status")}}


def resolve_source(repo, ref, version):
    commit = run(["git", "-C", repo, "rev-parse", "--verify", f"{ref}^{{commit}}"]).strip()
    found = json.loads(run(["git", "-C", repo, "show", f"{commit}:{MANIFEST}"]))["version"]
    if found != version:
        raise InstallError(f"{ref} ({commit[:12]}) is rhize-ops {found}, not {version}")
    data = run(["git", "-C", repo, "show", f"{commit}:{SOURCE}"], text=False)
    tags = run(["git", "-C", repo, "tag", "--points-at", commit]).split()
    return {"commit": commit, "tags": tags, "data": data, "sha256": sha256(data)}


def preflight():
    bins = {h: shutil.which(h) for h in ("claude", "codex")}
    if not all(bins.values()):
        raise InstallError(f"not on PATH: {[h for h, b in bins.items() if not b]}")
    auth = json.loads(run([bins["claude"], "auth", "status", "--json"]))
    if not auth.get("loggedIn") or auth.get("authMethod") != "claude.ai":
        raise InstallError("Claude must be logged in with its claude.ai subscription login")
    login = subprocess.run([bins["codex"], "login", "status"], capture_output=True, text=True, timeout=60)
    if "ChatGPT" not in login.stdout + login.stderr:
        raise InstallError("Codex must be logged in with ChatGPT")
    return bins, {h: run([b, "--version"]).strip() for h, b in bins.items()}


def activate(version, opts):
    regs = registrations()
    old = regs["claude"]["args"][0]
    target = releases() / version
    script = target / "agent_bridge.py"
    manifest = target / "installation.json"
    if manifest.exists():
        recorded = json.loads(manifest.read_text()).get("script_sha256")
        if sha256(script.read_bytes()) != recorded:
            raise InstallError(f"{script} no longer matches the SHA-256 in its installation.json")
        source = None
        print(f"{version}: installed copy verified ({recorded[:12]})")
    else:
        source = resolve_source(opts.repo, opts.ref, version)
        if script.exists() and sha256(script.read_bytes()) != source["sha256"]:
            raise InstallError(f"{script} exists with different content and no installation.json; inspect it")
        tags = f" ({', '.join(source['tags'])})" if source["tags"] else ""
        print(f"{version}: {opts.ref} = {source['commit'][:12]}{tags}, sha256 {source['sha256'][:12]} "
              "(the script does not fetch; fetch first if this ref is stale)")
    if str(script) == old:
        print(f"{NAME} already runs {script}; nothing to change")
        return 0
    print(f"claude, codex: {old} -> {script}")
    live = {"codex": opts.codex_model, "claude": opts.claude_model}
    print("live review: " + ", ".join(f"to {t} {m or 'not run'}" for t, m in live.items()))
    if opts.dry_run:
        print("dry run: no files written")
        return 0

    bins, versions = preflight()
    private_mkdir(releases())
    private_mkdir(target)
    if source and not script.exists():
        with os.fdopen(os.open(script, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
            f.write(source["data"])
    new = {h: copy.deepcopy(e) for h, e in regs.items()}
    for entry in new.values():
        entry["args"][0] = str(script)
    evidence = private_mkdir(target / "evidence")
    validation = {o: probe(new[o], o, evidence, live["codex" if o == "claude" else "claude"])
                  for o in ("claude", "codex")}

    backup = private_mkdir(target / f"config-before-{datetime.datetime.now(datetime.UTC):%Y%m%dT%H%M%S.%fZ}")
    for path in (claude_json(), codex_toml()):
        shutil.copy2(path, backup / path.name)
        os.chmod(backup / path.name, 0o600)
    codex_text = codex_toml().read_text()
    claude_before = json.loads(claude_json().read_text())
    codex_toml().write_text(swap_codex_text(codex_text, old, str(script)))
    try:
        set_claude_entry(bins["claude"], new["claude"])
        check_claude_entries(claude_before, json.loads(claude_json().read_text()), new["claude"])
    except InstallError:
        codex_toml().write_text(codex_text)
        try:
            set_claude_entry(bins["claude"], regs["claude"])
        except InstallError as restore:
            print(f"could not restore the Claude entry; restore it from {backup}: {restore}", file=sys.stderr)
        raise

    if source:
        manifest.write_text(json.dumps({
            "plugin_version": version, "script_sha256": source["sha256"], "script": str(script),
            "source_commit": source["commit"], "release_tags": source["tags"],
            "previous_release": release_version(old), "installed_at": datetime.date.today().isoformat(),
            "host_versions": versions, "registrations": new, "backup_directory": str(backup),
            "validation": {"stdio_probe": validation,
                           "live_parent_delegation": "not run (manual: docs/agent-bridge.md step 4)"},
        }, indent=1) + "\n")
        os.chmod(manifest, 0o600)
    for origin, result in validation.items():
        print(f"{origin}: {result}")
    print(f"backups: {backup}\nRestart Claude Code and Codex sessions to load {version}; running sessions "
          f"keep {old} until then. Nothing was deleted.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("version", nargs="?", help="rhize-ops version to install or re-activate")
    target.add_argument("--rollback", action="store_true",
                        help="re-activate the previous_release recorded by the active version")
    parser.add_argument("--ref", default="origin/main", help="git ref to copy a new version from")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]),
                        help="rhize-plugins checkout (default: the one holding this script)")
    parser.add_argument("--codex-model", help="also run a live review from Claude to Codex with this model")
    parser.add_argument("--claude-model", help="also run a live review from Codex to Claude with this model")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; write nothing")
    opts = parser.parse_args(argv)
    try:
        version = opts.version
        if opts.rollback:
            active = release_version(registrations()["claude"]["args"][0])
            manifest = releases() / str(active) / "installation.json"
            version = json.loads(manifest.read_text()).get("previous_release") if manifest.exists() else None
            if not version:
                raise InstallError(f"no previous_release recorded for the active version ({active})")
        return activate(version, opts)
    except InstallError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
