#!/usr/bin/env python3
"""Read-only inventory of existing evidence; never launch or repair a benchmark."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys


def native_summary(value):
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list) or "claudeVersion" not in value:
        raise ValueError("not a native Claude eval result")
    rows = []
    errors = []
    for case in value["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("arms"), dict):
            errors.append("case_missing_arms")
            continue
        for arm, runs in case["arms"].items():
            if arm not in {"with", "without"} or not isinstance(runs, list):
                errors.append("unknown_arm_shape")
                continue
            for run in runs:
                if not isinstance(run, dict):
                    errors.append("invalid_run")
                    continue
                graders = run.get("graders") or []
                error = run.get("error")
                invalid = bool(error and run.get("turns") == 0 and not graders)
                truncated = bool(error and "maximum number of turns" in str(error).lower())
                rows.append({"case": case.get("name"), "arm": arm, "environmentInvalid": invalid,
                    "truncated": truncated, "errorPresent": bool(error), "passed": run.get("passed"),
                    "score": run.get("score"), "turns": run.get("turns"),
                    "skippedPaidGraders": run.get("skippedPaidGraders"),
                    "scoredGraders": sum(g.get("scored") is True for g in graders if isinstance(g, dict)),
                    "costUsd": run.get("costUsd"), "durationSeconds": run.get("durationSeconds")})
    return {"evidenceClass": "native_plugin_ablation", "host": "claude", "claudeVersion": value["claudeVersion"],
        "model": value.get("suite", {}).get("modelOverride"), "judgeModel": value.get("suite", {}).get("judgeModel"),
        "startedAt": value.get("startedAt"), "declaredPartial": value.get("partial"), "actualRuns": len(rows),
        "arms": {arm: {"attempts": len(xs), "environmentInvalid": sum(r["environmentInvalid"] for r in xs),
            "truncated": sum(r["truncated"] for r in xs),
            "reportedPasses": sum(r["passed"] is True and not r["environmentInvalid"] for r in xs)}
            for arm in ("with", "without") for xs in [[r for r in rows if r["arm"] == arm]]},
        "rows": rows, "errors": errors, "benefitClaim": "requires_task_quality_and_confirmed_incumbent"}


def read_records(root, pattern):
    rows, errors = [], []
    for path in sorted(root.glob(pattern)) if root.exists() else []:
        try:
            raw = path.read_bytes()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("record_not_object")
            rows.append(value)
        except (OSError, ValueError):
            errors.append({"file": path.name, "reason": "unreadable_or_invalid_json"})
    return rows, errors


def memory_summary(rows):
    hosts = {}
    groups = defaultdict(list)
    for row in rows:
        answer = row.get("answerComparison") or {}
        key = json.dumps([row.get("host"), row.get("model"), row.get("implementationHashes"), answer.get("driverHash"), row.get("evidenceKind")], sort_keys=True)
        groups[key].append(row)
    for host in ("claude", "codex"):
        selected = [r for r in rows if r.get("host") == host]
        complete = [r for r in selected if answer_complete(r)]
        hosts[host] = {"capturedPairs": len(selected), "answerStatus": dict(Counter(r.get("answerStatus", "unavailable") for r in selected)),
            "answerCompletePairs": len(complete), "gradedCompletePairs": sum(graded(r) for r in complete),
            "eligibility": dict(Counter(r.get("answerEligibility", "legacy_unclassified") for r in selected))}
    summaries = []
    for key, selected in groups.items():
        complete = [r for r in selected if answer_complete(r)]
        # Latest record for a repeated source/task snapshot; repeats do not increase diversity.
        unique = {r.get("snapshotHash", r.get("pairId")): r for r in sorted(complete, key=lambda r: r.get("createdAt", ""))}
        deltas = []
        for r in unique.values():
            arms = r["answerComparison"]["arms"]
            a, b = [(arms[x].get("usage") or {}).get("totalInputTokens") for x in ("A", "B")]
            if type(a) is int and type(b) is int and a > 0:
                deltas.append(100 * (a-b) / a)
        summaries.append({"stratum": json.loads(key), "capturedPairs": len(selected), "completePairs": len(complete),
            "uniqueCompleteSnapshots": len(unique), "gradedUniqueSnapshots": sum(graded(r) for r in unique.values()),
            "measuredInputPairs": len(deltas), "medianInputReductionPercent": statistics.median(deltas) if deltas else None,
            "inputRegressions": sum(x < 0 for x in deltas)})
    return {"hosts": hosts, "strata": summaries, "qualityBenefit": "requires_reviewed_outcomes", "opportunityCoverage": "captured_only_not_all_eligible_work"}


def answer_complete(row):
    answer = row.get("answerComparison") or {}
    arms = answer.get("arms") or {}
    return (answer.get("comparisonStatus") == "complete" and all(
        arms.get(a, {}).get("actuallyRan") is True and arms[a].get("status") == "completed" for a in ("A", "B"))
        and arms["A"].get("model") is not None and arms["A"].get("model") == arms["B"].get("model"))


def graded(row):
    return all(type(row["answerComparison"]["arms"][a].get("rubricPass")) is bool for a in ("A", "B"))


def build_report(repo, memory_root, routine_root, central_root):
    memory, me = read_records(memory_root / "receipts", "*.json")
    routines, re = read_records(routine_root, "*.json")
    native, errors = [], []
    for path in sorted(repo.glob("*/evals/results/*/aggregate-result.json")):
        try:
            raw = path.read_bytes()
            native.append({"source": str(path.relative_to(repo)), "sha256": hashlib.sha256(raw).hexdigest(), **native_summary(json.loads(raw))})
        except (OSError, ValueError, TypeError):
            errors.append({"source": str(path.relative_to(repo)), "reason": "invalid_native_result"})
    strict = [r for r in routines if r.get("schemaVersion") == 2]
    health = {}
    for host in ("claude", "codex"):
        records, failures = read_records(memory_root / "health", f"{host}.json")
        health[host] = records[0] if records else None
        me.extend(failures)
    config = central_root / "config.json"
    return {"schemaVersion": "rhize-evidence-inventory-v1", "generatedAt": datetime.now(timezone.utc).isoformat(),
        "memory": {"available": (memory_root / "receipts").is_dir(), "errors": me,
            "summary": memory_summary(memory) if (memory_root / "receipts").is_dir() else None,
            "health": health},
        "routines": {"available": routine_root.is_dir(), "errors": re, "receipts": len(routines) if routine_root.is_dir() else None,
            "arms": dict(Counter(r.get("arm", "unknown") for r in routines)),
            "strictReceipts": len(strict) if routine_root.is_dir() else None, "declaredComparableByArm": dict(Counter(r.get("arm") for r in strict if r.get("comparable") is True)),
            "noncomparabilityReasons": dict(Counter(reason for r in strict for reason in r.get("comparability_reasons", []))),
            "controlledPairStatus": "not_established_by_individual_receipt_flags"},
        "central": {"configurationAvailable": config.is_file(), "status": "configured_requires_adapter_audit" if config.is_file() else "unavailable_at_requested_location"},
        "native": native, "errors": errors,
        "claimRule": "Keep observed, synthetic, native ablation and confirmed controlled cohorts separate; missing is never zero."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--memory-root", type=Path, default=Path.home()/".local/share/rhize/context-manager/memory-context/paired-opportunities-v1")
    parser.add_argument("--routine-root", type=Path, default=Path.home()/".rhize/procedural-memory/benchmark-receipts")
    parser.add_argument("--central-root", type=Path, default=Path.home()/".rhize/evals")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = build_report(args.repo, args.memory_root, args.routine_root, args.central_root)
    content = json.dumps(value, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    else:
        print(content, end="")
    return 2 if value["errors"] or value["memory"]["errors"] or value["routines"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
