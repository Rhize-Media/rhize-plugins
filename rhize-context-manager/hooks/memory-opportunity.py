#!/usr/bin/env python3
"""Silent, bounded native Claude/Codex paired-measurement entry point."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from memory_context.opportunities import MAX_BYTES, PairStore, default_root, handle_event


def main():
    if os.environ.get("RHIZE_MEMORY_EVAL_CHILD") == "1":
        return
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return
    event = json.loads(raw)
    if not isinstance(event, dict):
        return
    host = "codex" if os.environ.get("PLUGIN_ROOT") else "claude"
    store = PairStore(default_root())
    result = handle_event(store, host, event.get("hook_event_name", ""), event)
    if result.get("status") in {"complete", "observed"}:
        runner = Path(__file__).resolve().parents[1] / "scripts/memory_context/runner.py"
        subprocess.Popen([sys.executable, str(runner), "opportunity-drain", "--limit", "2"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError):
        pass  # Measurement failure cannot block the user's task or print private input.
