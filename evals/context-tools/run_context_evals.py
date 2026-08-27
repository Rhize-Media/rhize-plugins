#!/usr/bin/env python3
"""Run real-provider Context Compiler cases against real repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
FIXTURE_ROOT = EVAL_ROOT / "fixtures" / "context-compiler"
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
    cases = value["contextCompiler"]
    expected_keys = {
        "id",
        "kind",
        "repository",
        "fixture",
        "target",
        "maxHops",
        "maxTokens",
        "expectAccepted",
        "requiredEntries",
        "criticalEntries",
        "requiredWarnings",
    }
    seen_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != expected_keys:
            raise ValueError("every contextCompiler case must use the exact v1 case shape")
        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError("contextCompiler case ids must be unique non-empty strings")
        seen_ids.add(case_id)
        if case["kind"] not in {"supported", "adversarial"}:
            raise ValueError(f"{case_id}: kind must be supported or adversarial")
        if case["repository"] not in {"fixture", "rhize", "upstream"}:
            raise ValueError(f"{case_id}: unsupported repository selector")
        fixture = case["fixture"]
        if case["repository"] == "fixture":
            if not isinstance(fixture, str) or not fixture:
                raise ValueError(f"{case_id}: fixture repository requires a fixture name")
            resolved = (FIXTURE_ROOT / fixture).resolve()
            if FIXTURE_ROOT.resolve() not in resolved.parents or not resolved.is_dir():
                raise ValueError(f"{case_id}: fixture is missing or outside the fixture root")
        elif fixture is not None:
            raise ValueError(f"{case_id}: non-fixture repository must use fixture=null")
        if not isinstance(case["target"], str) or Path(case["target"]).is_absolute():
            raise ValueError(f"{case_id}: target must be repository-relative")
        if isinstance(case["expectAccepted"], bool) is False:
            raise ValueError(f"{case_id}: expectAccepted must be a boolean")
        for field in ("requiredEntries", "criticalEntries", "requiredWarnings"):
            if not isinstance(case[field], list) or not all(
                isinstance(item, str) and item for item in case[field]
            ):
                raise ValueError(f"{case_id}: {field} must contain strings")
    return cases


def fixture_snapshot(repo: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(repo.rglob("*.py")):
        digest.update(path.relative_to(repo).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"fixture-{digest.hexdigest()}"


@contextmanager
def resolve_repository(
    case: dict[str, Any], upstream: Path
) -> Iterator[tuple[Path, str]]:
    if case["repository"] == "upstream":
        yield upstream, git_snapshot(upstream)
        return
    if case["repository"] == "rhize":
        yield REPO_ROOT, git_snapshot(REPO_ROOT)
        return
    source = (FIXTURE_ROOT / case["fixture"]).resolve(strict=True)
    templates = list(source.rglob("*.py.fixture"))
    if not templates:
        yield source, fixture_snapshot(source)
        return
    with tempfile.TemporaryDirectory(prefix=f"rhize-context-eval-{case['id']}-") as directory:
        repo = Path(directory) / source.name
        shutil.copytree(source, repo)
        for template in repo.rglob("*.py.fixture"):
            template.rename(template.with_suffix(""))
        yield repo, fixture_snapshot(repo)


def stable_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "buildMilliseconds"}


def run_case(
    case: dict[str, Any], provider: ContextCompilerProvider, upstream: Path
) -> dict[str, Any]:
    with resolve_repository(case, upstream) as (repo, snapshot):
        return run_case_in_repository(case, provider, repo, snapshot)


def run_case_in_repository(
    case: dict[str, Any],
    provider: ContextCompilerProvider,
    repo: Path,
    snapshot: str,
) -> dict[str, Any]:
    target = repo / case["target"]
    task_hash = hashlib.sha256(case["id"].encode()).hexdigest()
    pack = provider.compile(
        repo,
        target,
        snapshot=snapshot,
        task_hash=task_hash,
        max_hops=case["maxHops"],
        max_tokens=case["maxTokens"],
    )
    repeated = provider.compile(
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
    critical_missing = sorted(set(case["criticalEntries"]) - entries)
    missing_warnings = sorted(set(case["requiredWarnings"]) - set(manifest["warnings"]))
    accepted = manifest["policy"]["acceptedForInjection"]
    reproducible = (
        manifest["packId"] == repeated.manifest["packId"]
        and pack.prompt == repeated.prompt
        and stable_manifest(manifest) == stable_manifest(repeated.manifest)
    )
    passed = (
        not missing
        and accepted is case["expectAccepted"]
        and not missing_warnings
        and reproducible
        and (not accepted or not critical_missing)
    )
    return {
        "id": case["id"],
        "kind": case["kind"],
        "repository": case["repository"],
        "snapshot": snapshot,
        "target": case["target"],
        "passed": passed,
        "expectedAccepted": case["expectAccepted"],
        "acceptedForInjection": accepted,
        "packId": manifest["packId"],
        "missingRequiredEntries": missing,
        "criticalEntriesMissing": critical_missing,
        "missingRequiredWarnings": missing_warnings,
        "reproduciblePack": reproducible,
        "armsExecuted": {
            "A": {
                "variant": "baseline-naive-repository",
                "contextTokens": manifest["naiveDumpTokens"],
                "filesPresented": manifest["totalRepoFiles"],
            },
            "B": {
                "variant": "context-compiler-pack",
                "contextTokens": manifest["compiledTokens"],
                "filesPresented": len(manifest["entries"]),
            },
        },
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
            "dynamicDispatchFiles": manifest["diagnostics"]["dynamicDispatchFileCount"],
            "decoratorHintFiles": manifest["diagnostics"]["decoratorHintFileCount"],
            "callbackRegistrationFiles": manifest["diagnostics"][
                "callbackRegistrationFileCount"
            ],
            "syntaxErrorFiles": manifest["diagnostics"]["syntaxErrorFileCount"],
        },
        "warnings": manifest["warnings"],
    }


def evaluate_gate(results: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [result["id"] for result in results if not result["passed"]]
    supported = [result for result in results if result["kind"] == "supported"]
    adversarial = [result for result in results if result["kind"] == "adversarial"]
    supported_ready = bool(supported) and all(
        result["acceptedForInjection"] and result["reproduciblePack"]
        for result in supported
    )
    adversarial_safe = bool(adversarial) and all(
        not result["acceptedForInjection"] or not result["criticalEntriesMissing"]
        for result in adversarial
    )
    reasons = []
    if failed:
        reasons.append(f"failed_cases:{','.join(failed)}")
    if not supported_ready:
        reasons.append("supported_cases_not_accepted_and_reproducible")
    if not adversarial_safe:
        reasons.append("adversarial_cases_neither_complete_nor_rejected")
    return {
        "id": "context-compiler-phase-3-v1",
        "decision": "continue_to_phase_4" if not reasons else "pause",
        "reasons": reasons,
        "supportedCasesAcceptedAndReproducible": supported_ready,
        "adversarialCasesSafelyWidenedOrRejected": adversarial_safe,
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
    gate = evaluate_gate(results)
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
        "gate": gate,
        "results": results,
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if gate["decision"] == "continue_to_phase_4" else 1


if __name__ == "__main__":
    raise SystemExit(main())
