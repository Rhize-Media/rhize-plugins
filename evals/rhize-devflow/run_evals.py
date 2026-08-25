#!/usr/bin/env python3
"""evals/rhize-devflow/run_evals.py -- deterministic control-plane evals for
the rhize-devflow plugin (Task 9, .claude/plans/rhize-devflow-v3-engineering-
control-plane.md, "Add evals, usage measures, and release enforcement").

Two eval kinds, both fixture-driven and offline -- neither invokes `claude -p`
or any other live/paid model call, unlike evals/run_evals.py's house harness
(the plan forbids live paid-service calls in automated tests):

1. Trigger precision (trigger_cases.json): should-trigger / should-not-trigger
   prompt cases for each retained skill and canonical command, scored against
   a deterministic keyword-substring heuristic (keywords.json) -- NOT the real
   Claude Skill-invocation decision. See README.md "Method" for what this
   measures and its limits.

2. Quality assertions (quality_cases.json): deterministic text/regex checks
   against the check/review command contracts and canonical simplify skill for exact-
   verdict vocabulary, evidence-table presence, safety rules, scope preservation,
   behavior preservation, React conventions, and authority boundaries. Reuses
   evals/assertions.py's evaluate_all(), the same engine
   the house harness uses to grade live output -- here it grades static
   contract text instead.

Usage:
    python3 evals/rhize-devflow/run_evals.py            # human-readable report
    python3 evals/rhize-devflow/run_evals.py --json      # machine-readable report

Exit code is non-zero if any keyword has drifted out of its source file, any
quality case fails, or overall trigger precision falls below the ≥90% target
measure from the plan's Task 9 "Target measures after the observation window".

Naming note: fixtures are named trigger_cases.json / quality_cases.json, NOT
trigger_evals.json / quality_evals.json like evals/seo-aeo-geo and
evals/obsidian. That is deliberate, not a typo -- the top-level
evals/run_evals.py auto-discovers any subdirectory containing files with the
house names and would sweep this directory into its live `claude -p` run
(and crash on the schema difference below), which is exactly what this
directory exists to avoid. See README.md "Why this directory is invisible to
the house run_evals.py harness".
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).resolve().parent
DEVFLOW = REPO_ROOT / "rhize-devflow"
RESULTS_DIR = EVAL_DIR.parent / "results"  # evals/results/ -- gitignored

sys.path.insert(0, str(EVAL_DIR.parent))
from assertions import evaluate_all  # noqa: E402  (path insert must precede this import)

TRIGGER_PRECISION_THRESHOLD = 0.90


def target_source_path(target_id: str) -> Path:
    """Resolve a `skill:<name>` / `command:<name>` id to its live source file."""
    kind, _, name = target_id.partition(":")
    if kind == "skill":
        return DEVFLOW / "skills" / name / "SKILL.md"
    if kind == "command":
        return DEVFLOW / "commands" / f"{name}.md"
    raise ValueError(f"unknown target id (expected 'skill:<name>' or 'command:<name>'): {target_id!r}")


def load_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_keyword_drift(keywords: dict) -> list[str]:
    """Every curated keyword must still appear verbatim (case-insensitive) in
    its target's live source file. Catches keywords.json silently going stale
    when a SKILL.md/command.md `description:` is edited after this eval's
    keyword list was curated -- see README.md "Method"."""
    problems = []
    for target_id, phrases in keywords.items():
        if target_id.startswith("_"):  # e.g. "_comment"
            continue
        path = target_source_path(target_id)
        if not path.exists():
            problems.append(f"{target_id}: source file missing: {path.relative_to(REPO_ROOT)}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for phrase in phrases:
            if phrase.lower() not in text:
                problems.append(
                    f"{target_id}: keyword {phrase!r} no longer found in {path.relative_to(REPO_ROOT)}"
                )
    return problems


def predict(prompt: str, keywords: dict, target_id: str) -> bool:
    prompt_l = prompt.lower()
    return any(phrase.lower() in prompt_l for phrase in keywords.get(target_id, []))


def run_trigger_evals(cases: list[dict], keywords: dict) -> dict:
    per_target: dict[str, dict] = {}
    for case in cases:
        target = case["target"]
        predicted = predict(case["prompt"], keywords, target)
        expected = case["should_trigger"]
        bucket = per_target.setdefault(
            target, {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "cases": []}
        )
        if expected and predicted:
            bucket["tp"] += 1
        elif expected and not predicted:
            bucket["fn"] += 1
        elif not expected and predicted:
            bucket["fp"] += 1
        else:
            bucket["tn"] += 1
        bucket["cases"].append(
            {
                "id": case["id"],
                "prompt": case["prompt"],
                "predicted": predicted,
                "expected": expected,
                "correct": predicted == expected,
            }
        )

    summary = {}
    total_tp = total_fp = total_fn = 0
    for target, bucket in per_target.items():
        tp, fp, fn = bucket["tp"], bucket["fp"], bucket["fn"]
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        summary[target] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": bucket["tn"],
            "false_negatives": fn,
            "cases": bucket["cases"],
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn

    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 1.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 1.0
    return {
        "per_target": summary,
        "overall_precision": round(overall_precision, 3),
        "overall_recall": round(overall_recall, 3),
        "total_cases": len(cases),
    }


def run_quality_evals(cases: list[dict]) -> dict:
    results = []
    for case in cases:
        path = REPO_ROOT / case["target_file"]
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        grading = evaluate_all(case.get("assertions", []), text, [])
        results.append(
            {
                "id": case["id"],
                "target_file": case["target_file"],
                "fully_passed": grading["pass_rate"] == 1.0,
                **grading,
            }
        )
    total = len(results)
    fully_passed = sum(1 for r in results if r["fully_passed"])
    return {"cases": results, "total": total, "fully_passed": fully_passed}


def print_report(drift: list[str], trigger: dict, quality: dict) -> None:
    print("=" * 60)
    print("Dev Flow control-plane evals")
    print("=" * 60)

    print("\n-- Keyword drift check --")
    if drift:
        for problem in drift:
            print(f"  DRIFT: {problem}")
    else:
        print("  OK: every curated keyword still found in its target's source file.")

    print("\n-- Trigger precision (heuristic, not a live model call) --")
    for target, stats in sorted(trigger["per_target"].items()):
        print(
            f"  {target}: precision={stats['precision']:.2f} recall={stats['recall']:.2f} "
            f"(TP={stats['true_positives']} FP={stats['false_positives']} "
            f"TN={stats['true_negatives']} FN={stats['false_negatives']})"
        )
        for case in stats["cases"]:
            if not case["correct"]:
                print(f"    FAIL {case['id']}: predicted={case['predicted']} expected={case['expected']}")
    print(
        f"\n  OVERALL precision={trigger['overall_precision']:.3f} "
        f"recall={trigger['overall_recall']:.3f} "
        f"(target: >= {TRIGGER_PRECISION_THRESHOLD:.0%}) over {trigger['total_cases']} cases"
    )

    print("\n-- Quality assertions (check / review / simplify contract text) --")
    for case in quality["cases"]:
        status = "PASS" if case["fully_passed"] else "FAIL"
        print(f"  [{status}] {case['id']} ({case['passed']}/{case['total']} assertions)")
        if not case["fully_passed"]:
            for r in case["results"]:
                if not r["passed"]:
                    print(f"      - {r['name']}: {r['evidence']}")
    print(f"\n  {quality['fully_passed']}/{quality['total']} quality cases fully passed (target: 100%)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable JSON report instead of text")
    args = parser.parse_args()

    keywords = load_json(EVAL_DIR / "keywords.json")
    trigger_cases = load_json(EVAL_DIR / "trigger_cases.json")
    quality_cases = load_json(EVAL_DIR / "quality_cases.json")

    drift = check_keyword_drift(keywords)
    trigger = run_trigger_evals(trigger_cases, keywords)
    quality = run_quality_evals(quality_cases)

    ok = (
        not drift
        and trigger["overall_precision"] >= TRIGGER_PRECISION_THRESHOLD
        and quality["fully_passed"] == quality["total"]
    )

    if args.json:
        print(json.dumps({"drift": drift, "trigger": trigger, "quality": quality, "ok": ok}, indent=2))
    else:
        print_report(drift, trigger, quality)
        print("\n" + "=" * 60)
        print("RESULT:", "PASS" if ok else "FAIL")
        print("=" * 60)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    (RESULTS_DIR / f"rhize-devflow-{timestamp}.json").write_text(
        json.dumps({"drift": drift, "trigger": trigger, "quality": quality, "ok": ok}, indent=2)
    )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
