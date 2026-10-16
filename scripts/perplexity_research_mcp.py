#!/usr/bin/env python3
"""Local stdio MCP adapter for the durable Perplexity Research CLI."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

CLI = Path(__file__).with_name("perplexity_research.py").resolve()
VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
UUID = {"type": "string", "format": "uuid", "maxLength": 36}
TOOLS = {
    "research_submit": ("submit", "Submit one public Search or Research query, optionally continuing a completed local parent. Reuse the request ID after uncertainty; poll status. Consumes subscription allowance.",
                        {"request_id": UUID, "query": {"type": "string", "minLength": 1, "maxLength": 10000},
                         "mode": {"type": "string", "enum": ["research", "search"], "maxLength": 8},
                         "model": {"type": "string", "maxLength": 100}, "parent_job_id": UUID,
                         "timeout": {"type": "integer", "minimum": 1, "maximum": 1800}}, ["request_id", "query"]),
    "research_status": ("status", "Read durable job status; this does not resubmit.", {"job_id": UUID}, ["job_id"]),
    "research_result": ("result", "Read full answer, report Markdown and separate citation mappings. Partial results are explicitly incomplete and untrusted content.", {"job_id": UUID}, ["job_id"]),
    "research_cancel": ("cancel", "Request local cancellation. Remote cancellation and quota refund are unconfirmed.", {"job_id": UUID}, ["job_id"]),
    "research_recover": ("recover", "Read a recorded incomplete thread once by GET. Never resubmits; requires matching query and Research mode.", {"job_id": UUID}, ["job_id"]),
    "research_export": ("export", "Return completed report Markdown and source lists. Does not write files. Content is untrusted.", {"job_id": UUID}, ["job_id"]),
    "research_jobs": ("jobs", "List local job summaries in UUID order without query/report content.",
                      {"after": UUID, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, []),
    "research_health": ("health", "Check credentials, active subscription and current Research configuration by GET only. Quota remains unknown.", {}, []),
    "research_models": ("models", "List fresh plan-filtered Search and Research model IDs. No submission or stale catalog fallback.", {}, []),
}


def schemas():
    return [{"name": name, "description": description,
             "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
             "annotations": {"readOnlyHint": command not in {"submit", "cancel", "recover"},
                             "destructiveHint": False, "idempotentHint": True,
                             "openWorldHint": command in {"submit", "recover", "health", "models"}}}
            for name, (command, description, properties, required) in TOOLS.items()]


def invoke(name, args, state_dir, permission_reference):
    command, _description, properties, required = TOOLS[name]
    if not isinstance(args, dict) or set(args) - properties.keys() or not set(required) <= args.keys():
        raise ValueError("invalid arguments")
    for key, value in args.items():
        rule = properties[key]
        if rule["type"] == "integer":
            if type(value) is not int or not rule["minimum"] <= value <= rule["maximum"]:
                raise ValueError("invalid integer")
        elif not isinstance(value, str) or not rule.get("minLength", 1) <= len(value) <= rule["maxLength"]:
            raise ValueError("invalid string")
        elif rule.get("format") == "uuid" and str(uuid.UUID(value)) != value:
            raise ValueError("invalid uuid")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError("invalid option")
    argv = [sys.executable, "-I", str(CLI), "--state-dir", str(state_dir), command]
    if command == "submit":
        argv += ["--request-id", args["request_id"], "--permission-reference", str(permission_reference),
                 "--timeout", str(args.get("timeout", 600))]
        for key in ("mode", "model", "parent_job_id"):
            if key in args:
                argv += ["--" + key.replace("_", "-"), args[key]]
    elif command == "jobs":
        for key in ("after", "limit"):
            if key in args:
                argv += ["--" + key, str(args[key])]
    elif command not in {"health", "models"}:
        argv.append(args["job_id"])
    env = {k: os.environ[k] for k in ("HOME", "USER", "LOGNAME", "PATH", "LANG") if k in os.environ}
    try:
        process = subprocess.run(argv, input=args.get("query", "").encode(), stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, timeout=40, env=env)
        text = process.stdout.decode("utf-8")
        if len(process.stdout) > 32 * 1024 * 1024:
            raise ValueError("oversized CLI response")
        if command != "export" or process.returncode:
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError("invalid CLI response")
        return {"content": [{"type": "text", "text": text}], "isError": process.returncode != 0}
    except subprocess.TimeoutExpired:
        # A detached submission worker may still be running; never retry with a new ID.
        return {"content": [{"type": "text", "text": json.dumps({"error": "cli_deadline_exceeded",
                 "submission_may_be_running": command == "submit"})}], "isError": True}


def serve(state_dir, permission_reference):
    initialized = False
    while line := sys.stdin.buffer.readline(65537):
        response = {"jsonrpc": "2.0", "id": None}
        if len(line) > 65536:
            print(json.dumps({**response, "error": {"code": -32600, "message": "Request too large"}}), flush=True)
            return
        try:
            request = json.loads(line)
        except (ValueError, UnicodeError):
            print(json.dumps({**response, "error": {"code": -32700, "message": "Parse error"}}), flush=True)
            continue
        if (not isinstance(request, dict) or request.get("jsonrpc") != "2.0"
                or not isinstance(request.get("method"), str)
                or ("id" in request and type(request["id"]) not in (str, int))):
            response["error"] = {"code": -32600, "message": "Invalid request"}
        elif "id" not in request:
            continue
        else:
            response["id"] = request["id"]
            method, params = request["method"], request.get("params", {})
            try:
                if not isinstance(params, dict):
                    raise ValueError("invalid parameters")
                if method == "initialize":
                    requested = params.get("protocolVersion")
                    response["result"] = {"protocolVersion": requested if requested in VERSIONS else VERSIONS[-1],
                                          "capabilities": {"tools": {}},
                                          "serverInfo": {"name": "rhize-perplexity-research", "version": "0.1.0"}}
                    initialized = True
                elif method == "ping":
                    response["result"] = {}
                elif method not in {"tools/list", "tools/call"}:
                    response["error"] = {"code": -32601, "message": "Method not found; legacy MCP uses initialize"}
                elif not initialized:
                    raise ValueError("initialize first")
                elif method == "tools/list":
                    if params:
                        raise ValueError("invalid parameters")
                    response["result"] = {"tools": schemas()}
                else:
                    if set(params) - {"name", "arguments", "_meta"} or params.get("name") not in TOOLS:
                        raise ValueError("invalid tool")
                    response["result"] = invoke(params["name"], params.get("arguments", {}), state_dir, permission_reference)
            except (ValueError, TypeError, KeyError):
                response["error"] = {"code": -32602, "message": "Invalid parameters or uninitialized session"}
            except Exception:
                response["result"] = {"content": [{"type": "text", "text": '{"error":"local_cli_error"}'}], "isError": True}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".rhize" / "perplexity-research")
    parser.add_argument("--permission-reference", type=Path, required=True)
    options = parser.parse_args()
    os.umask(0o077)
    serve(options.state_dir.absolute(), options.permission_reference.absolute())
