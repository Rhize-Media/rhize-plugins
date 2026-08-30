#!/usr/bin/env python3
"""Run the real Rhize-native provider against the fixed mixed-language corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
sys.path.insert(0, str(REPO_ROOT / "rhize-context-manager" / "scripts"))

from context_experiments.providers.native_context_pack import (  # noqa: E402
    PROVIDER_REVISION,
    NativeContextPackProvider,
)


def load_cases(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schemaVersion") != 1 or document.get("providerRevision") != PROVIDER_REVISION:
        raise ValueError("native corpus version or provider revision is invalid")
    if not isinstance(document.get("cases"), list) or not document["cases"]:
        raise ValueError("native corpus has no cases")
    return document


def fixture_snapshot(repo: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in repo.rglob("*") if item.is_file()):
        digest.update(path.relative_to(repo).as_posix().encode())
        digest.update(path.read_bytes())
    return f"fixture-{digest.hexdigest()[:32]}"


def evaluate_case(case: dict[str, Any], provider: NativeContextPackProvider) -> dict[str, Any]:
    source = EVAL_ROOT / "fixtures" / "native-context" / case["fixture"]
    with tempfile.TemporaryDirectory(prefix=f"rhize-native-{case['id']}-") as temporary:
        repo = Path(temporary) / "repo"
        shutil.copytree(source, repo)
        snapshot = fixture_snapshot(repo)
        task_hash = hashlib.sha256(case["id"].encode()).hexdigest()
        targets = tuple(repo / value for value in case["targets"])
        started = time.monotonic()
        first = provider.compile(repo, snapshot=snapshot, task_hash=task_hash, targets=targets)
        build_milliseconds = round((time.monotonic() - started) * 1000, 3)
        second = provider.compile(repo, snapshot=snapshot, task_hash=task_hash, targets=targets)
        manifest = first.manifest
        actual_entries = [entry["path"] for entry in manifest["entries"]]
        missing = sorted(set(case["expectedEntries"]) - set(actual_entries))
        warnings_missing = sorted(set(case["expectedWarnings"]) - set(manifest["warnings"]))
        reproducible = (
            first.prompt == second.prompt
            and manifest["packId"] == second.manifest["packId"]
        )
        passed = (
            not missing
            and not warnings_missing
            and manifest["policy"]["acceptedForUse"] is case["expectedAccepted"]
            and reproducible
        )
        return {
            "id": case["id"],
            "provider": "rhize-native",
            "providerRevision": PROVIDER_REVISION,
            "languageClass": case["languageClass"],
            "taskClass": case["taskClass"],
            "snapshot": snapshot,
            "armsExecuted": ["A", "B"],
            "armA": {
                "variant": "baseline-naive-supported-source",
                "contextTokens": manifest["naiveDumpTokens"],
                "filesPresented": manifest["totalSourceFiles"],
            },
            "armB": {
                "variant": PROVIDER_REVISION,
                "contextTokens": manifest["compiledTokens"],
                "filesPresented": len(manifest["entries"]),
                "buildMilliseconds": build_milliseconds,
            },
            "reductionPercent": manifest["reductionPercent"],
            "acceptedForUse": manifest["policy"]["acceptedForUse"],
            "warnings": manifest["warnings"],
            "criticalEntriesMissing": missing,
            "expectedWarningsMissing": warnings_missing,
            "reproduciblePack": reproducible,
            "passed": passed,
        }


def evaluate_gate(results: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [row for row in results if row["acceptedForUse"]]
    adversarial = [row for row in results if not row["acceptedForUse"]]
    median_reduction = round(statistics.median(row["reductionPercent"] for row in accepted), 3)
    passed = (
        len(accepted) >= 4
        and bool(adversarial)
        and all(row["passed"] for row in results)
        and all(not row["criticalEntriesMissing"] for row in results)
        and median_reduction >= 25
    )
    return {
        "gateVersion": "native-context-phase-4-v1",
        "decision": "continue_to_explicit_dogfood" if passed else "pause",
        "caseCount": len(results),
        "acceptedCaseCount": len(accepted),
        "fallbackCaseCount": len(adversarial),
        "medianAcceptedReductionPercent": median_reduction,
        "criticalMissCount": sum(len(row["criticalEntriesMissing"]) for row in results),
    }


def build_report(cases_path: Path) -> dict[str, Any]:
    document = load_cases(cases_path)
    provider = NativeContextPackProvider()
    health = provider.doctor()
    if not health.ready:
        raise RuntimeError(health.note)
    results = [evaluate_case(case, provider) for case in document["cases"]]
    upstream_case_count = len(
        json.loads((EVAL_ROOT / "cases.json").read_text())["contextCompiler"]
    )
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider": health.to_dict(),
        "corpus": {
            "nativeCaseCount": len(results),
            "upstreamCaseCount": upstream_case_count,
            "totalCompiledContextCaseCount": len(results) + upstream_case_count,
        },
        "results": results,
        "gate": evaluate_gate(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=EVAL_ROOT / "native_cases.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.cases)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["gate"]["decision"] != "pause" else 2


if __name__ == "__main__":
    raise SystemExit(main())
