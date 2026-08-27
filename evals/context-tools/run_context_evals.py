#!/usr/bin/env python3
"""Run real-provider Context Compiler cases against real repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
sys.path.insert(0, str(REPO_ROOT / "rhize-context-manager" / "scripts"))

from context_experiments.providers.context_compiler import (  # noqa: E402
    ContextCompilerProvider,
)


def git_snapshot(repo: Path) -> str:
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain=v1", "-z"],
        capture_output=True,
        check=True,
    ).stdout
    return commit if not status else f"{commit}-dirty-{hashlib.sha256(status).hexdigest()[:16]}"


def load_cases(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schemaVersion") != 1 or not isinstance(value.get("contextCompiler"), list):
        raise ValueError("cases file must contain schemaVersion 1 contextCompiler cases")
    return value["contextCompiler"]


def run_case(
    case: dict[str, Any], provider: ContextCompilerProvider, upstream: Path
) -> dict[str, Any]:
    repo = upstream if case["repository"] == "upstream" else REPO_ROOT
    target = repo / case["target"]
    snapshot = git_snapshot(repo)
    task_hash = hashlib.sha256(case["id"].encode()).hexdigest()
    pack = provider.compile(
        repo,
        target,
        snapshot=snapshot,
        task_hash=task_hash,
        max_hops=case["maxHops"],
        max_tokens=case["maxTokens"],
    )
    manifest = pack.manifest
    entries = {entry["path"] for entry in manifest["entries"]}
    missing = sorted(set(case["requiredEntries"]) - entries)
    accepted = manifest["policy"]["acceptedForInjection"]
    passed = not missing and accepted is case["expectAccepted"]
    return {
        "id": case["id"],
        "repository": case["repository"],
        "snapshot": snapshot,
        "target": case["target"],
        "passed": passed,
        "expectedAccepted": case["expectAccepted"],
        "acceptedForInjection": accepted,
        "missingRequiredEntries": missing,
        "metrics": {
            "totalRepoFiles": manifest["totalRepoFiles"],
            "filesPresented": len(manifest["entries"]),
            "naiveDumpTokens": manifest["naiveDumpTokens"],
            "compiledTokens": manifest["compiledTokens"],
            "reductionPercent": manifest["reductionPercent"],
            "buildMilliseconds": manifest["buildMilliseconds"],
            "entryCoverage": manifest["policy"]["observedEntryCoverage"],
            "nameCollisions": manifest["diagnostics"]["nameCollisionCount"],
            "unresolvedCalls": manifest["diagnostics"]["unresolvedCallCount"],
        },
        "warnings": manifest["warnings"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=EVAL_ROOT / "cases.json")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    checkout = args.checkout.expanduser().resolve(strict=True)
    provider = ContextCompilerProvider(checkout)
    health = provider.doctor()
    if not health.ready:
        print(f"ERROR: {health.note}", file=sys.stderr)
        return 2
    cases = load_cases(args.cases)
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case["id"] in selected]
        missing = selected - {case["id"] for case in cases}
        if missing:
            raise ValueError(f"unknown case ids: {sorted(missing)}")
    results = [run_case(case, provider, checkout) for case in cases]
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider": {
            "name": "context-compiler",
            "revision": health.version,
            "sourceVerified": True,
        },
        "summary": {
            "cases": len(results),
            "passed": sum(result["passed"] for result in results),
            "failed": sum(not result["passed"] for result in results),
        },
        "results": results,
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
