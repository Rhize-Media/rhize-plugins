#!/usr/bin/env python3
"""evals/skill-map/run.py — thin harness-integration entry point for the
skill-map evals (docs/superpowers/specs/2026-08-10-skill-graph-evals-design.md).

These evals are offline analyses of local transcripts and hook subprocesses,
not `claude -p` trigger/quality runs, so they don't fit evals/run_evals.py's
plugin-discovery contract (which looks for trigger_evals.json/
quality_evals.json). Per the design spec's "Harness integration" section this
script is the fallback: it does NOT fork assertions.py's assertion engine —
it just runs eval_routing.py, eval_disclosure.py, and eval_remediation.py in
sequence and writes one result file into evals/results/ (gitignored, same as
run_evals.py's output) with a schema compatible with that harness's top-level
shape (timestamp + per-plugin results).

Eval 2 (suggestion acceptance) and eval 5 (curation gate regression) are
intentionally NOT run here — per the territory split in this task, eval 2's
suggestion-log/report lives in a concurrent lane, and eval 5 lives in
skill-forge's own test suite. Eval 6 (drift signal quality) is wired into the
weekly audit's own step 0, not this harness.

Usage:
    python3 evals/skill-map/run.py
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR.parent / "results"
GOLDEN_PATH = EVAL_DIR / "data" / "golden-routing.jsonl"
CORPUS_PATH = EVAL_DIR / "data" / "failure-corpus.jsonl"


def run_script(name, *args):
    """Runs an eval script as a subprocess (own process, own sys.path — same
    isolation the eval scripts get when run directly) and returns
    (returncode, stdout)."""
    proc = subprocess.run(
        [sys.executable, str(EVAL_DIR / name), *args],
        capture_output=True,
        text=True,
        timeout=300,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    results = {}

    if GOLDEN_PATH.exists():
        code, out, err = run_script("eval_routing.py")
        results["routing"] = {"ok": code == 0, "stdout": out, "stderr": err}
    else:
        results["routing"] = {"ok": None, "skipped": f"no golden set at {GOLDEN_PATH}"}

    code, out, err = run_script("eval_disclosure.py")
    results["disclosure"] = {"ok": code == 0, "stdout": out, "stderr": err}

    if CORPUS_PATH.exists():
        code, out, err = run_script("eval_remediation.py")
        results["remediation"] = {"ok": code == 0, "stdout": out, "stderr": err}
    else:
        results["remediation"] = {"ok": None, "skipped": f"no failure corpus at {CORPUS_PATH}"}

    full_results = {
        "timestamp": timestamp,
        "config": {"plugin": "skill-map"},
        "plugins": {
            "skill-map": {
                "trigger": None,  # not a claude -p trigger/quality eval; see module docstring
                "quality": None,
                "skill_map_evals": results,
            }
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"skill-map-benchmark-{timestamp}.json"
    with open(out_path, "w") as f:
        json.dump(full_results, f, indent=2)

    for name, r in results.items():
        status = "SKIPPED" if r.get("ok") is None else ("PASS" if r["ok"] else "ERROR")
        print(f"[{status}] {name}")
        if r.get("stdout"):
            print(r["stdout"])
        if r.get("stderr"):
            print(r["stderr"], file=sys.stderr)

    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
