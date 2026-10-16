#!/usr/bin/env python3
"""Harmless MCP GUI stand-in: code is data, never evaluated and no apps opened."""
import json
from pathlib import Path
import sys


def handle(message, marker):
    method = message.get("method")
    if method == "initialize":
        return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "credential-gui-canary", "version": "1.0.0"}}
    if method == "tools/list":
        return {"tools": [{"name": "js", "description": (
            "Safe GUI guard probe. Records a marker for the supplied code string; "
            "NEVER evaluates code, opens apps, or reads credentials."),
            "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}},
                            "required": ["code"], "additionalProperties": False}}]}
    if method == "tools/call":
        code = message.get("params", {}).get("arguments", {}).get("code", "")
        kind = "keychain" if "keychain" in code.lower() else "allowed"
        with marker.open("a") as stream:
            stream.write(kind + "\n")
        return {"content": [{"type": "text", "text": "Marker recorded; no code was executed."}]}
    return {}


if __name__ == "__main__":
    target = Path(sys.argv[1])
    for raw in sys.stdin:
        message = json.loads(raw)
        if "id" not in message:
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"],
                          "result": handle(message, target)}), flush=True)
