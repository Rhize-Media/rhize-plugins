#!/usr/bin/env python3
"""Bounded measurement child; native/direct callers use the observable runtime."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def main():
    from memory_context.opportunities import MAX_BYTES, PairStore, default_root, handle_event
    if os.environ.get("RHIZE_MEMORY_EVAL_CHILD") == "1":
        return "child_ignored"
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return "payload_too_large"
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeError):
        return "invalid_event"
    if not isinstance(event, dict):
        return "invalid_event"
    if event.get("hook_event_name") != sys.argv[2]:
        return "invalid_event"
    host = "codex" if os.environ.get("PLUGIN_ROOT") else "claude"
    store = PairStore(default_root())
    result = handle_event(store, host, event.get("hook_event_name", ""), event)
    return result["status"]


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--supervised":
        print(json.dumps({"outcome": main()}))
    else:
        from memory_context.hook_runtime import main as supervise
        event = sys.argv[2] if len(sys.argv) == 3 and sys.argv[1] == "--event" else "UserPromptSubmit"
        raise SystemExit(supervise([event]))
