#!/usr/bin/env python3
"""Native canary wrapper: execute the real guard; persist only bounded metadata."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    guard, receipt = sys.argv[1:]
    raw = sys.stdin.buffer.read(1024 * 1024 + 1)
    result = subprocess.run([sys.executable, "-B", guard], input=raw, capture_output=True, timeout=4)
    data = json.loads(raw)
    record = {"sessionId": data.get("session_id"), "tool": data.get("tool_name"),
              "event": data.get("hook_event_name"), "exitCode": result.returncode,
              "payloadSha256": hashlib.sha256(raw).hexdigest(),
              "guardSha256": hashlib.sha256(Path(guard).read_bytes()).hexdigest()}
    fd = os.open(receipt, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "a") as stream:
        stream.write(json.dumps(record) + "\n")
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    raise SystemExit(result.returncode)
