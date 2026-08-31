#!/usr/bin/env python3
"""Rhize-side Skill Forge version, safety precision/recall, and latency harness."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def command_for(binary: Path) -> list[str]:
    return ["node", str(binary)] if binary.suffix == ".js" else [str(binary)]


def version(command: list[str]) -> str:
    result = subprocess.run(command + ["--version"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"Skill Forge version probe failed with exit {result.returncode}")
    return result.stdout.strip()


def resolve(checkout: Path | None, binary: Path | None) -> tuple[list[str], str | None, str]:
    checkout_version = None
    if checkout:
        package = json.loads((checkout / "package.json").read_text(encoding="utf-8"))
        checkout_version = package["version"]
    selected = binary or (checkout / "dist/cli.js" if checkout else None)
    if selected is None:
        raise ValueError("pass --binary or --checkout explicitly")
    if not selected.is_file():
        raise ValueError(f"Skill Forge executable not found: {selected}")
    command = command_for(selected)
    return command, checkout_version, version(command)


def inspect(args: argparse.Namespace) -> int:
    _, checkout_version, binary_version = resolve(args.checkout, args.binary)
    result = {
        "status": "ok",
        "checkout_version": checkout_version,
        "binary_version": binary_version,
        "version_match": checkout_version is None or checkout_version == binary_version,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["version_match"] else 1


def parse_gate_output(stdout: str) -> dict[str, Any]:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Skill Forge scan did not emit one JSON document") from exc


def safety(args: argparse.Namespace) -> int:
    command, checkout_version, binary_version = resolve(args.checkout, args.binary)
    if checkout_version is not None and checkout_version != binary_version:
        raise ValueError(f"checkout {checkout_version} does not match executable {binary_version}")
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    records = []
    with tempfile.TemporaryDirectory(prefix="skill-forge-eval-") as temporary:
        temp = Path(temporary)
        skills_root = temp / "skills"
        quarantine = temp / "quarantine"
        skills_root.mkdir()
        home = temp / "home"
        home.mkdir()
        (home / "config.json").write_text(json.dumps({
            "skillsRoots": [str(skills_root)], "defaultTarget": str(skills_root),
            "quarantineDir": str(quarantine), "strictness": corpus["strictness"]
        }))
        env = {**os.environ, "SKILL_FORGE_HOME": str(home)}
        for case in corpus["cases"]:
            fixture = ROOT / case["fixture"]
            latencies = []
            verdict = None
            for _ in range(args.repetitions):
                started = time.perf_counter_ns()
                completed = subprocess.run(command + ["scan", str(fixture), "--json"], capture_output=True, text=True, env=env, check=False)
                latencies.append((time.perf_counter_ns() - started) / 1_000_000)
                payload = parse_gate_output(completed.stdout)
                verdict = str(payload["safety"]["verdict"]).upper()
                predicted_block = verdict == "BLOCK"
                expected_exit = 1 if predicted_block else 0
                if completed.returncode != expected_exit:
                    raise ValueError(f"case {case['id']} exit/verdict mismatch")
            records.append({
                "id": case["id"], "expected_block": case["expected_block"],
                "predicted_block": verdict == "BLOCK", "verdict": verdict,
                "latency_ms_median": statistics.median(latencies),
                "latency_ms_max": max(latencies), "repetitions": args.repetitions,
            })
    tp = sum(row["expected_block"] and row["predicted_block"] for row in records)
    fp = sum(not row["expected_block"] and row["predicted_block"] for row in records)
    fn = sum(row["expected_block"] and not row["predicted_block"] for row in records)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    result = {
        "schema_version": 1, "status": "measured", "binary_version": binary_version,
        "corpus_cases": len(records), "repetitions": args.repetitions,
        "safety": {"true_positives": tp, "false_positives": fp, "false_negatives": fn, "precision": precision, "recall": recall},
        "performance": {"scan_latency_ms_median": statistics.median(row["latency_ms_median"] for row in records), "scan_latency_ms_max": max(row["latency_ms_max"] for row in records)},
        "cases": records,
        "limitations": ["Small hand-labeled static corpus; no LLM or network scanner is invoked.", "Latency is local process-plus-scan time and is not a cross-host claim."]
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("inspect")
    probe.add_argument("--checkout", type=Path)
    probe.add_argument("--binary", type=Path)
    scan = sub.add_parser("safety")
    scan.add_argument("--checkout", type=Path)
    scan.add_argument("--binary", type=Path)
    scan.add_argument("--corpus", type=Path, default=ROOT / "safety-corpus.json")
    scan.add_argument("--repetitions", type=int, default=3)
    scan.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        return inspect(args) if args.command == "inspect" else safety(args)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
