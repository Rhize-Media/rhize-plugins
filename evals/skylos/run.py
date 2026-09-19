#!/usr/bin/env python3
"""Paired local static-evidence experiment; never executes fixture source."""
import argparse
import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "rhize-devflow/scripts/skylos_evidence.py"
spec = importlib.util.spec_from_file_location("skylos_adapter_eval", SCRIPT)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def matching(expected, findings):
    return any(item["rule_id"] == expected["rule_id"] and item["file"] == expected["file"]
               and item["start_line"] <= expected["line"] <= item["end_line"] for item in findings)


def summarize_expected(expected, findings, available):
    return [{**item, "outcome": ("detected" if matching(item, findings) else "missed")
             if available else "unavailable"} for item in expected]


def run(python):
    corpus_path = Path(__file__).with_name("fixtures.json")
    corpus_bytes = corpus_path.read_bytes()
    corpus = json.loads(corpus_bytes)
    rows = []
    for fixture in corpus["fixtures"]:
        with tempfile.TemporaryDirectory(prefix="rhize-skylos-eval-") as directory:
            repo = Path(directory).resolve()
            adapter.prepare_copy(repo, {n: s.encode() for n, s in fixture["before"].items()},
                                 {n: s.encode() for n, s in fixture["after"].items()})
            before = adapter.snapshot(repo, "HEAD")[0]
            started = time.monotonic()
            result = subprocess.run([sys.executable, str(ROOT / "rhize-devflow/scripts/devflow.py"),
                                     "evidence", "--json", "--repo", str(repo), "--base", "HEAD"],
                                    capture_output=True, timeout=30, text=True)
            elapsed = round((time.monotonic() - started) * 1000)
            baseline = json.loads(result.stdout)
            baseline_ran = result.returncode in (0, 1) and baseline.get("schema_version") == "devflow-evidence-v1"
            common = {"fixture": fixture["id"], "fixture_hash": adapter.digest(fixture),
                      "expected_count": len(fixture["expected"])}
            rows.append({**common, "arm": "A", "variant": "devflow-deterministic-evidence",
                         "ran": baseline_ran, "elapsed_ms": elapsed, "scanner_status": "not_requested",
                         "test_candidate_count": len(baseline.get("test_evidence_candidates", [])),
                         "expected": summarize_expected(fixture["expected"], [], baseline_ran),
                         "note": "Baseline inventories evidence; it has no Skylos defect detector."})
            report = adapter.scan(repo, "HEAD", python)
            # Consume through the same public evidence CLI used by check/review.
            with tempfile.TemporaryDirectory(prefix="rhize-skylos-report-") as reports:
                path = Path(reports).resolve() / "report.json"
                path.write_text(json.dumps(report))
                consumed = subprocess.run([sys.executable, str(ROOT / "rhize-devflow/scripts/devflow.py"),
                                          "evidence", "--json", "--repo", str(repo), "--base", "HEAD",
                                          "--skylos-report", str(path)], capture_output=True, timeout=30, text=True)
                acceptance = json.loads(consumed.stdout)["skylos"]["accepted"]
            unchanged = adapter.snapshot(repo, "HEAD")[0] == before
            rows.append({**common, "arm": "B", "variant": "devflow-plus-skylos-static",
                         "ran": report["status"] != "unavailable", "scanner_status": report["status"],
                         "elapsed_ms": elapsed + report["elapsed_ms"], "scanner_elapsed_ms": report["elapsed_ms"],
                         "coverage": report["coverage"], "reasons": report["reasons"],
                         "scope": report["scope"], "findings": report["findings"],
                         "report_accepted": acceptance, "source_unchanged": unchanged,
                         "expected": summarize_expected(fixture["expected"], report["findings"],
                                                        report["status"] != "unavailable"),
                         "note": fixture["notes"]})
            if not unchanged or not acceptance:
                raise RuntimeError("fixture integrity or packet consumption failed")
    return {"schema_version": "rhize-skylos-eval-v1", "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
            "adapter_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(), "scanner_version": adapter.VERSION,
            "host": platform.system(), "python_version": platform.python_version(), "rows": rows,
            "limits": ["Single host and one trial per fixture; no statistical or productivity claim.",
                       "Arm A is deterministic evidence inventory, not a complete agent review.",
                       "Unmatched findings need manual classification; do not infer false positives.",
                       "Incomplete execution can detect hints but does not establish clean coverage."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path, help="Dedicated pinned Skylos interpreter")
    args = parser.parse_args()
    print(json.dumps(run(args.python), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
