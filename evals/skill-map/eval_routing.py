#!/usr/bin/env python3
"""eval_routing.py — Eval 1: routing accuracy (golden set + baseline comparison).

Runs the golden set mined by mine_golden_set.py through the LIVE map router
(rhize-context-manager/hooks/skill-router.js, invoked headlessly as a
subprocess, replicating its UserPromptSubmit stdin contract: `{"prompt": ...}`
on stdin, `hookSpecificOutput.additionalContext` parsed from stdout) and
through the retired grep-keyword baseline (evals/skill-map/baseline/
skill-suggester.sh, vendored — see that file's header for provenance).

Metrics (per spec, "1 — silence precision outranks hit rate"):
  - top-1 hit rate on positives: suggested skill id == golden label.
  - silence precision on negatives: hook stayed silent (no suggestion).
Both are reported for the router and the baseline side by side.

REPRODUCIBILITY (spec: "set env so it reads the repo's committed indexes, not
the resolved overlay"): the hooks honor RHIZE_CONTEXT_MANAGER_DIR. This script
stages the repo's committed generated/skill-map*.json artifacts into a private
temp dir under the standard installed filenames and points the hook there via
that env var — the machine's real installed maps under
~/.claude/context-manager/ are never touched, so a crashed eval run can't
leave another session's hooks reading eval-pinned data.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = Path(__file__).resolve().parent / "data" / "golden-routing.jsonl"
ROUTER_HOOK = REPO_ROOT / "rhize-context-manager" / "hooks" / "skill-router.js"
BASELINE_SCRIPT = Path(__file__).resolve().parent / "baseline" / "skill-suggester.sh"

# Filenames the hooks look for inside their context-manager dir; each staged
# from the repo's committed artifacts into a temp dir handed to the hook via
# RHIZE_CONTEXT_MANAGER_DIR.
PINNED_FILES = {
    "skill-map.resolved.json": REPO_ROOT / "generated" / "skill-map.static.json",
    "skill-map.static.json": REPO_ROOT / "generated" / "skill-map.static.json",
    "skill-map.indexes.resolved.json": REPO_ROOT / "generated" / "skill-map.indexes.json",
    "skill-map.indexes.json": REPO_ROOT / "generated" / "skill-map.indexes.json",
}

ROUTER_MSG_RE = re.compile(r"Consider the ([\w.-]+):([\w./-]+) skill")
# The baseline's "Suggested: X" token is a placeholder slug like "/skill:done"
# or a caller-configurable env var default — never a real skill-map id. It is
# matched loosely and almost never resolves to a first-party skill id, which
# is itself part of what this eval demonstrates.
BASELINE_MSG_RE = re.compile(r"Suggested:\s*(\S+)")


def load_golden():
    if not GOLDEN_PATH.exists():
        return []
    rows = []
    with open(GOLDEN_PATH) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@contextlib.contextmanager
def _pin_repo_map():
    """Stage the repo's committed generated/ artifacts into a private temp
    dir under the installed filenames and export RHIZE_CONTEXT_MANAGER_DIR so
    the hook subprocesses read them. The machine's real installed maps are
    never touched — no restore step, nothing to corrupt on a hard crash."""
    with tempfile.TemporaryDirectory(prefix="skill-map-eval-") as tmp:
        for name, source in PINNED_FILES.items():
            shutil.copyfile(source, Path(tmp) / name)
        prior = os.environ.get("RHIZE_CONTEXT_MANAGER_DIR")
        os.environ["RHIZE_CONTEXT_MANAGER_DIR"] = tmp
        try:
            yield
        finally:
            if prior is None:
                os.environ.pop("RHIZE_CONTEXT_MANAGER_DIR", None)
            else:
                os.environ["RHIZE_CONTEXT_MANAGER_DIR"] = prior


def run_router(prompt):
    try:
        proc = subprocess.run(
            ["node", str(ROUTER_HOOK)],
            input=json.dumps({"prompt": prompt}),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    out = proc.stdout.strip()
    if not out:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    msg = (data.get("hookSpecificOutput") or {}).get("additionalContext")
    if not isinstance(msg, str):
        return None
    m = ROUTER_MSG_RE.search(msg)
    if not m:
        return None
    plugin, name = m.groups()
    return f"skill:{plugin}/{name}"


def run_baseline(prompt):
    try:
        proc = subprocess.run(
            ["bash", str(BASELINE_SCRIPT)],
            input=json.dumps({"prompt": prompt}),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    out = proc.stdout.strip()
    if not out:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    msg = (data.get("hookSpecificOutput") or {}).get("additionalContext")
    if not isinstance(msg, str):
        return None
    m = BASELINE_MSG_RE.search(msg)
    return m.group(1) if m else None


def score(golden, predict_fn):
    positives = [g for g in golden if g.get("label")]
    negatives = [g for g in golden if not g.get("label")]

    hits = 0
    for g in positives:
        predicted = predict_fn(g["prompt"])
        if predicted == g["label"]:
            hits += 1
    top1 = hits / len(positives) if positives else None

    silent = 0
    for g in negatives:
        predicted = predict_fn(g["prompt"])
        if predicted is None:
            silent += 1
    silence_precision = silent / len(negatives) if negatives else None

    return {
        "n_positives": len(positives),
        "n_negatives": len(negatives),
        "top1_hit_rate": top1,
        "silence_precision": silence_precision,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Router-only, prints a single-line JSON {top1_hit_rate, silence_precision} "
        "for the weekly audit's metrics line. Skips the baseline run and full report.",
    )
    args = parser.parse_args()

    golden = load_golden()
    if not golden:
        if args.quick:
            # Weekly audit's guard: absent golden set -> skip silently, no output.
            return
        print(f"No golden set at {GOLDEN_PATH} — run mine_golden_set.py first.")
        sys.exit(1)

    with _pin_repo_map():
        router_result = score(golden, run_router)

        if args.quick:
            print(
                json.dumps(
                    {
                        "top1_hit_rate": router_result["top1_hit_rate"],
                        "silence_precision": router_result["silence_precision"],
                    }
                )
            )
            return

        baseline_result = score(golden, run_baseline) if BASELINE_SCRIPT.exists() else None

    print(f"Golden set: {GOLDEN_PATH}")
    print(f"  positives: {router_result['n_positives']}  negatives: {router_result['n_negatives']}")
    print()
    print("Router (rhize-context-manager/hooks/skill-router.js):")
    print(f"  top-1 hit rate:      {_fmt(router_result['top1_hit_rate'])}")
    print(f"  silence precision:   {_fmt(router_result['silence_precision'])}")
    print()
    if baseline_result:
        print("Baseline (retired grep skill-suggester.sh):")
        print(f"  top-1 hit rate:      {_fmt(baseline_result['top1_hit_rate'])}")
        print(f"  silence precision:   {_fmt(baseline_result['silence_precision'])}")
    else:
        print(f"Baseline script not found at {BASELINE_SCRIPT} — skipped.")


def _fmt(value):
    if value is None:
        return "n/a (no examples in this bucket)"
    return f"{value:.3f} ({value * 100:.1f}%)"


if __name__ == "__main__":
    main()
