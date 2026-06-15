#!/usr/bin/env python3
"""skill_safety.py — gate a skill on a SkillSpector security scan before adding it.

Wraps the NVIDIA SkillSpector CLI (https://github.com/NVIDIA/SkillSpector):
    skillspector scan <path|url|zip|git> --format json [--no-llm]
and turns its risk verdict into an allow / caution / block decision. Pairs with the skills.sh
partner audit (`skills_sh.py audit`) for a layered check: fast partner verdict + deep local scan.

Mapping (SkillSpector severity → verdict):
    LOW       → ALLOW    (SAFE)
    MEDIUM    → CAUTION  (allowed, with a warning)
    HIGH      → BLOCK    (DO NOT INSTALL)
    CRITICAL  → BLOCK    (DO NOT INSTALL)

Fails *safe*: if `skillspector` isn't installed it prints install guidance and returns verdict
UNKNOWN (exit 3) — it never pretends an unscanned skill is safe.

Usage:
    python3 skill_safety.py <target> [--no-llm] [--json]
Exit codes: 0 allowed · 1 blocked (HIGH/CRITICAL) · 2 usage · 3 skillspector unavailable/unparsable.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

BLOCK_SEVERITIES = {"HIGH", "CRITICAL"}

INSTALL_HINT = (
    "SkillSpector not found on PATH. Install it once (Python 3.12+):\n"
    "  git clone https://github.com/NVIDIA/skillspector.git && cd skillspector\n"
    "  uv venv .venv && source .venv/bin/activate && make install\n"
    "  # or: python3 -m venv .venv && source .venv/bin/activate && make install\n"
    "Static analysis needs no API key. For the optional LLM stage set SKILLSPECTOR_PROVIDER\n"
    "(openai|anthropic|nv_build) + the matching key, or pass --no-llm for static-only."
)


def have_skillspector() -> bool:
    return shutil.which("skillspector") is not None


def run_scan(target: str, no_llm: bool) -> "dict | None":
    cmd = ["skillspector", "scan", target, "--format", "json"]
    if no_llm:
        cmd.append("--no-llm")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)
    except Exception:  # noqa: BLE001 — surface raw output; never invent a verdict
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return None


def verdict_for(severity: str) -> str:
    sev = (severity or "").upper()
    if sev in BLOCK_SEVERITIES:
        return "BLOCK"
    if sev == "MEDIUM":
        return "CAUTION"
    return "ALLOW"


def main() -> None:
    ap = argparse.ArgumentParser(description="Gate a skill on a SkillSpector scan.")
    ap.add_argument("target", help="skill path / URL / zip / git repo to scan")
    ap.add_argument("--no-llm", action="store_true", help="static analysis only (no LLM key needed)")
    ap.add_argument("--json", action="store_true", help="emit JSON verdict")
    args = ap.parse_args()

    if not have_skillspector():
        sys.stderr.write(INSTALL_HINT + "\n")
        if args.json:
            print(json.dumps({"verdict": "UNKNOWN", "reason": "skillspector-not-installed"}))
        sys.exit(3)

    res = run_scan(args.target, args.no_llm)
    if res is None:
        sys.stderr.write("ERROR: could not parse SkillSpector JSON output.\n")
        sys.exit(3)

    score = res.get("risk_score")
    severity = (res.get("risk_severity") or "").upper()
    rec = res.get("risk_recommendation")
    findings = res.get("filtered_findings") or res.get("findings") or []
    verdict = verdict_for(severity)
    blocked = verdict == "BLOCK"

    out = {
        "verdict": verdict,
        "score": score,
        "severity": severity,
        "recommendation": rec,
        "findings": [
            {"severity": f.get("severity"), "rule": f.get("rule_id"), "message": f.get("message")}
            for f in findings
        ],
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"SkillSpector: {severity or '?'} (score {score}) → {verdict}  [{rec}]")
        for f in out["findings"][:10]:
            print(f"  - {f['severity']} {f['rule']}: {f['message']}")
        if verdict == "CAUTION":
            print("  ! MEDIUM risk — review findings before adding this skill.")
        if blocked:
            print("  x BLOCKED — do not add this skill without remediation.")

    sys.exit(1 if blocked else 0)


if __name__ == "__main__":
    main()
