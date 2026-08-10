#!/usr/bin/env python3
"""eval_disclosure.py — Eval 3: disclosure cost/benefit.

(a) Runs rhize-context-manager/hooks/session-disclosure.js headlessly (as a
    subprocess, feeding its SessionStart stdin contract `{"cwd": "<repo>"}`)
    against a small set of real local repos, and measures the injected byte
    size (and a rough token estimate, bytes/4) per repo — including honesty
    about SILENCE (a repo with no detected stack tag must print nothing).

(b) Compares that against a FIXED baseline: the summed byte size of the
    retired per-plugin SessionStart banners that session-disclosure.js
    replaced (see PROVENANCE below for exactly which ones and why).

Candidate repos are discovered, not hardcoded: this repo itself
(rhize-plugins, expected to be SILENT — no stack markers), plus any Next.js
repos found under ~/dev-local (session-disclosure.js's stack markers are
next.config.*/sanity.config.*/vercel.json/.obsidian — see that file's
STACK_MARKERS). If discovery finds none, that is reported honestly rather
than substituting a fabricated repo.

PROVENANCE — the "4 retired banners" baseline.
docs/superpowers/specs/2026-08-10-skill-graph-evals-design.md's eval #3 cites
"the 4 retired banners" (seo-aeo-geo, obsidian-second-brain, project-launcher,
rhize-devflow) as the fixed disclosure baseline. Checking git history
(commit 15a50fb, "release(skill-map): phases 3-5 ... delete the three orphaned
*-context.md banner[s]") only recovers THREE static banner files that were
genuinely fixed-text SessionStart output:
    obsidian-second-brain/hooks/obsidian-context.md   (2403 bytes)
    project-launcher/hooks/launcher-context.md        ( 997 bytes)
    seo-aeo-geo/hooks/seo-context.md                  (1787 bytes)
rhize-devflow's SessionStart hook at the same point in history
(rhize-devflow/hooks/context-engineering__session-init.sh, retired in
ffb18a5) is a DYNAMIC freshness-checking script (reads CURRENT_SPRINT.md
mtimes, echoes a variable-length report) — not a fixed banner, so it has no
well-defined "byte size" to sum in. Rather than fabricate a number for it,
this eval sums the three confirmed banners (5187 bytes total) and documents
the gap explicitly. Recovery commands used:
    git show 15a50fb^:obsidian-second-brain/hooks/obsidian-context.md | wc -c
    git show 15a50fb^:project-launcher/hooks/launcher-context.md | wc -c
    git show 15a50fb^:seo-aeo-geo/hooks/seo-context.md | wc -c
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DISCLOSURE_HOOK = REPO_ROOT / "rhize-context-manager" / "hooks" / "session-disclosure.js"

# See PROVENANCE above. Recovered via `git show 15a50fb^:<path> | wc -c`.
RETIRED_BANNERS = {
    "obsidian-second-brain/hooks/obsidian-context.md": 2403,
    "project-launcher/hooks/launcher-context.md": 997,
    "seo-aeo-geo/hooks/seo-context.md": 1787,
}
BANNER_BASELINE_BYTES = sum(RETIRED_BANNERS.values())
BANNER_NOTE = (
    "3 of the 4 banners named in the design spec were recovered as fixed-text "
    "SessionStart output (see this script's PROVENANCE docstring); "
    "rhize-devflow's equivalent hook was a dynamic freshness-checker with no "
    "fixed byte size, so it is excluded from this sum rather than estimated."
)


def discover_repos():
    """Returns a list of (label, path) candidate repos: this repo (expected
    silent) plus up to 2 Next.js repos discovered under ~/dev-local."""
    repos = [("rhize-plugins (this repo, no stack markers expected)", str(REPO_ROOT))]

    dev_local = os.path.expanduser("~/dev-local")
    next_configs = sorted(
        set(
            glob.glob(os.path.join(dev_local, "*", "*", "next.config.*"))
            + glob.glob(os.path.join(dev_local, "*", "next.config.*"))
        )
    )
    next_configs = [p for p in next_configs if "node_modules" not in p]
    seen_dirs = set()
    for cfg in next_configs:
        repo_dir = os.path.dirname(cfg)
        if repo_dir in seen_dirs:
            continue
        seen_dirs.add(repo_dir)
        repos.append((f"{os.path.basename(repo_dir)} (Next.js repo, discovered)", repo_dir))
        if len(repos) >= 3:  # this repo + 2 discovered Next.js repos is enough signal
            break

    return repos


def run_disclosure(cwd):
    try:
        proc = subprocess.run(
            ["node", str(DISCLOSURE_HOOK)],
            input=json.dumps({"cwd": cwd}),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, str(exc)
    out = proc.stdout.strip()
    if not out:
        return None, None  # silence
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None, f"unparseable hook output: {out[:200]}"
    msg = (data.get("hookSpecificOutput") or {}).get("additionalContext")
    return msg, None


def main():
    if not DISCLOSURE_HOOK.exists():
        print(f"error: {DISCLOSURE_HOOK} not found")
        return

    repos = discover_repos()
    print(f"Discovered {len(repos)} candidate repo(s):")
    for label, path in repos:
        print(f"  - {label}: {path}")
    print()

    print(f"Baseline: {BANNER_BASELINE_BYTES} bytes ({BANNER_BASELINE_BYTES / 4:.0f} est. tokens)")
    print(f"  {BANNER_NOTE}")
    for name, size in RETIRED_BANNERS.items():
        print(f"    {name}: {size} bytes")
    print()

    print("Per-repo disclosure injection:")
    for label, path in repos:
        msg, err = run_disclosure(path)
        if err:
            print(f"  {label}: ERROR — {err}")
            continue
        if msg is None:
            print(f"  {label}: SILENCE (0 bytes) — correct if no stack marker present")
            continue
        size = len(msg.encode("utf-8"))
        est_tokens = size / 4
        delta = size - BANNER_BASELINE_BYTES
        pct = (size / BANNER_BASELINE_BYTES * 100) if BANNER_BASELINE_BYTES else float("nan")
        n_skills = msg.count("\n- ") + (1 if msg.strip().startswith("- ") else 0)
        print(
            f"  {label}: {size} bytes (~{est_tokens:.0f} tokens), {n_skills} skill line(s), "
            f"{pct:.0f}% of banner baseline ({delta:+d} bytes vs baseline)"
        )


if __name__ == "__main__":
    main()
