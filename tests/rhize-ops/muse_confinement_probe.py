#!/usr/bin/env python3
"""Offline Muse Code worker-confinement probe (docs: rhize-ops/docs/agent-bridge.md, Muse readiness).

Runs a pinned `muse-bin-*` with the local `echo` provider (no account, no model call) in a disposable,
network-denied home seeded with canaries, then reads the runtime's own record of the composed model
request (`model_request_configured` in the session log) and its local trace counts. It proves what the
runtime composes, not what the meta provider sends: provider-hosted tools and base instructions are
out of reach of the echo provider.

Usage: python3 tests/rhize-ops/muse_confinement_probe.py ~/.local/bin/muse-bin-<version>
Exit: 0 confined, 1 not confined, 3 probe broken (a control did not load its canaries).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

NO_NETWORK = "(version 1)\n(allow default)\n(deny network-outbound (remote ip))\n"
SKILL = "---\nname: canary-{0}\ndescription: CANARY_{0} skill.\n---\nCANARY_{0}\n"
MCP_SERVER = """import json, os, sys
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "MCP_STARTED"), "a").write("x")
for line in sys.stdin:
    m = json.loads(line)
    if m.get("id") is None:
        continue
    r = {}
    if m.get("method") == "initialize":
        r = {"protocolVersion": m["params"].get("protocolVersion", "2025-06-18"),
             "capabilities": {"tools": {}}, "serverInfo": {"name": "canary", "version": "1"}}
    elif m.get("method") == "tools/list":
        r = {"tools": [{"name": "canary_tool", "description": "CANARY_MCP", "inputSchema": {"type": "object"}}]}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}) + "\\n")
    sys.stdout.flush()
"""
CANARIES = {
    ".config/muse/AGENTS.md": "CANARY_USER_RULES\n",
    ".config/muse/skills/canary-user/SKILL.md": SKILL.format("user"),
    ".claude/CLAUDE.md": "CANARY_FOREIGN_CLAUDE_RULES\n",
    ".claude/skills/canary-claude/SKILL.md": SKILL.format("claude"),
    ".codex/AGENTS.md": "CANARY_FOREIGN_CODEX_RULES\n",
    ".codex/skills/canary-codex/SKILL.md": SKILL.format("codex"),
    "ws/AGENTS.md": "CANARY_PROJECT_RULES\n",
    "ws/.muse/skills/canary-project/SKILL.md": SKILL.format("project"),
    "canary/mcp_canary.py": MCP_SERVER,
}
# Strongest user-reachable flag set found for Muse Code 1.4.15 (none of them removes bundled context).
HARDENED = ["--preset", "empty", "--disable-reminders", "--disable-web-tools", "--disable-request-user-input",
            "--no-foreign-personal-context", "--disable-shell", "--disable-write", "--approval-mode", "never",
            "--contributor-mode", "off", "-c", "run.toolset=[]"]
# Posture notes generated from the run's own flags; everything else in the composed context is ambient.
POSTURE_CONTEXT = {"security_mode", "capability_policy"}
TRACE_EVENTS = ("plugin_capability_snapshot.compose", "rules.context_load", "skills.catalog_load", "hook.admission")


def trace_counts(text):
    counts = {}
    for name in TRACE_EVENTS:
        line = re.search(rf'event="{re.escape(name)}"([^\n]*)', text)
        if line:
            counts[name] = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)\b", line.group(1)) if k != "duration_ms"}
    surfaces = re.findall(r"registered_tool_count=(\d+) active_tool_count=(\d+)", text)
    counts["lead_tool_surface"] = [int(x) for x in surfaces[0]] if surfaces else None
    return counts


def summarize(home):
    """Facts recorded by the runtime itself; contains no prompt text and no paths."""
    lead, subruns = None, 0
    for path in sorted(glob.glob(home + "/.local/share/muse/sessions/**/session.jsonl", recursive=True)):
        for line in open(path, encoding="utf-8"):
            event = (json.loads(line).get("payload") or {}).get("event")
            if not (isinstance(event, dict) and event.get("kind") == "model_request_configured"):
                continue
            if "/subagent/" in path:
                subruns += 1
            elif lead is None:
                lead = {"active_tools": (event.get("toolset") or {}).get("active_tools"),
                        "delegation": (event.get("delegation_posture") or {}).get("state"),
                        "reminders": [a["id"] for a in (event.get("reminder_roster") or {}).get("agents", [])],
                        "context": {m["id"]: len(m.get("text", "")) for m in event.get("run_context_messages", [])}}
    trace = "".join(open(p, encoding="utf-8", errors="replace").read()
                    for p in glob.glob(home + "/.local/share/muse/**/cli-*.log", recursive=True))
    return {"lead": lead, "subagent_runs": subruns, "trace": trace_counts(trace),
            "mcp_started": os.path.exists(home + "/canary/MCP_STARTED")}


def run_case(muse_bin, args, trusted, root=None):
    home = tempfile.mkdtemp(prefix="muse-probe-", dir=root)
    try:
        for rel, text in CANARIES.items():
            os.makedirs(os.path.dirname(os.path.join(home, rel)), exist_ok=True)
            with open(os.path.join(home, rel), "w", encoding="utf-8") as f:
                f.write(text)
        mcp = {"canary": {"command": "/usr/bin/python3", "args": ["-I", home + "/canary/mcp_canary.py"]}}
        with open(home + "/.config/muse/settings.json", "w", encoding="utf-8") as f:
            json.dump({"schema_version": 1, "mcpServers": mcp}, f)
        with open(home + "/no-network.sb", "w", encoding="utf-8") as f:
            f.write(NO_NETWORK)
        os.makedirs(home + "/tmp")
        env = {"HOME": home, "PATH": "/usr/bin:/bin", "TMPDIR": home + "/tmp", "MUSE_NO_AUTO_UPDATE": "1",
               "XDG_CONFIG_HOME": home + "/.config", "XDG_DATA_HOME": home + "/.local/share",
               "XDG_CACHE_HOME": home + "/.cache", "XDG_STATE_HOME": home + "/.local/state"}
        command = ["sandbox-exec", "-f", home + "/no-network.sb", muse_bin, "exec", "--provider", "echo", "--json",
                   *args, *(["--trust-workspace"] if trusted else []), "Reply OK."]
        done = subprocess.run(command, cwd=home + "/ws", env=env, capture_output=True, text=True, timeout=180)
        return {"args": args, "trusted": trusted, "exit": done.returncode, **summarize(home)}
    finally:
        shutil.rmtree(home, ignore_errors=True)


def classify(control, hardened_runs):
    """Return (verdict, reasons). A control that did not load its canaries makes the probe broken."""
    lead = control.get("lead") or {}
    broken = []
    if control.get("exit") != 0 or not lead:
        broken.append("control did not complete")
    if not control.get("mcp_started") or not any(t.startswith("mcp__canary__") for t in lead.get("active_tools") or []):
        broken.append("control did not start the canary MCP server")
    if "rules_file" not in lead.get("context", {}):
        broken.append("control did not load the canary rules")
    if (control["trace"].get("skills.catalog_load") or {}).get("user_skills", 0) < 1:
        broken.append("control did not load the canary skills")
    if broken:
        return "probe_broken", broken
    reasons = []
    for run in hardened_runs:
        tag = "trusted" if run["trusted"] else "untrusted"
        lead = run.get("lead")
        if run.get("exit") != 0 or not lead:
            reasons.append(f"{tag}: hardened run did not complete")
            continue
        if lead["active_tools"]:
            reasons.append(f"{tag}: active tools {lead['active_tools']}")
        if run["mcp_started"]:
            reasons.append(f"{tag}: user MCP server started")
        if run["subagent_runs"] or lead["reminders"] or lead["delegation"] not in (None, "inactive"):
            reasons.append(f"{tag}: subagents or reminders present")
        ambient = sorted(set(lead["context"]) - POSTURE_CONTEXT)
        if ambient:
            reasons.append(f"{tag}: ambient context {ambient}")
        counts = run["trace"]
        if (counts.get("hook.admission") or {}).get("handlers", 0):
            reasons.append(f"{tag}: hook handlers admitted")
        for key in ("user_sources", "project_sources", "foreign_sources"):
            if (counts.get("rules.context_load") or {}).get(key, 0):
                reasons.append(f"{tag}: rules {key}")
        for key in ("skills", "developer_prompts", "hooks", "mcp_servers"):
            if (counts.get("plugin_capability_snapshot.compose") or {}).get(key, 0):
                reasons.append(f"{tag}: bundled {key}")
    return ("not_confined", reasons) if reasons else ("confined", [])


def probe(muse_bin, root=None):
    real = os.path.realpath(muse_bin)
    with open(real, "rb") as f:
        if f.read(2) == b"#!":
            raise SystemExit("pass the pinned muse-bin-<version> binary, not the auto-updating launcher script")
    control = run_case(real, [], trusted=True, root=root)
    hardened = [run_case(real, HARDENED, trusted=False, root=root), run_case(real, HARDENED, trusted=True, root=root)]
    verdict, reasons = classify(control, hardened)
    return {"binary": os.path.basename(real), "verdict": verdict, "reasons": reasons,
            "control": control, "hardened": hardened}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    result = probe(sys.argv[1])
    print(json.dumps(result, indent=1))
    sys.exit({"confined": 0, "not_confined": 1, "probe_broken": 3}[result["verdict"]])
