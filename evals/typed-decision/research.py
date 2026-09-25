#!/usr/bin/env python3
"""Bounded local research loop for typed software-development decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("labeled cases must be nonempty JSON objects")
    ids = set()
    for row in rows:
        for key in ("case_id", "group_id", "decision_type", "stratum", "label_source"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError(f"case missing {key}")
        if row["case_id"] in ids:
            raise ValueError("duplicate case_id")
        ids.add(row["case_id"])
        if row.get("adjudicated") is not True:
            raise ValueError("every case requires an adjudicated human label")
        questions, labels = row.get("questions"), row.get("labels")
        if not isinstance(questions, dict) or not questions or not isinstance(labels, dict) or set(questions) != set(labels):
            raise ValueError("questions and labels must be matching nonempty objects")
        for name, question in questions.items():
            if not isinstance(question, dict) or not isinstance(question.get("instructions"), str) or not question["instructions"].strip():
                raise ValueError("every question requires instructions")
            kind = question.get("type")
            label = labels[name]
            if kind == "choice" and (not isinstance(question.get("criteria"), dict)
                                      or not isinstance(label, str) or label not in question["criteria"]):
                raise ValueError("choice label must name an option")
            if kind == "noul" and not isinstance(label, bool):
                raise ValueError("noul label must be boolean")
            if kind not in {"choice", "noul"}:
                raise ValueError("research runner supports choice and noul only")
        if not isinstance(row.get("state"), (str, dict, list)):
            raise ValueError("state must be a string, object, or array")
    return rows


def partition(rows: list[dict], seed: str) -> dict[str, list[dict]]:
    """Group-stable 50/25/25 train/validation/holdout partition."""
    splits = {"train": [], "validation": [], "holdout": []}
    for row in rows:
        bucket = int(hashlib.sha256(f"{seed}:{row['group_id']}".encode()).hexdigest()[:8], 16) % 4
        splits["train" if bucket < 2 else "validation" if bucket == 2 else "holdout"].append(row)
    return splits


def validate_candidate(candidate: dict, rows: list[dict]) -> None:
    if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str) or not candidate["id"]:
        raise ValueError("candidate id required")
    if not isinstance(candidate.get("model"), str) or not candidate["model"]:
        raise ValueError("candidate model required")
    overrides = candidate.get("instructions", {})
    if not isinstance(overrides, dict) or any(not isinstance(v, str) or not v.strip() or len(v) > 1000 for v in overrides.values()):
        raise ValueError("instruction overrides must be nonempty strings <= 1000 characters")
    known = {name for row in rows for name in row["questions"]}
    if set(overrides) - known:
        raise ValueError("candidate overrides unknown question ids")
    threshold = candidate.get("abstain_below", 0.0)
    if isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not 0 <= threshold <= 1:
        raise ValueError("abstain_below must be a probability")


def local_call(base_url: str, request: dict) -> tuple[dict, float]:
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
        raise ValueError("research endpoint must be local loopback HTTP")
    started = time.monotonic()
    payload = json.dumps(request).encode()
    with urlopen(Request(base_url.rstrip("/") + "/v1/systemone", data=payload,
                         headers={"Content-Type": "application/json"}, method="POST"), timeout=20) as response:
        raw = response.read(262145)
    if len(raw) > 262144:
        raise ValueError("provider response too large")
    result = json.loads(raw)
    if not isinstance(result, dict) or not isinstance(result.get("routing"), dict) or result["routing"].get("model") != request["model"]:
        raise ValueError("local provider routed a different checkpoint")
    if set(result.get("answers", {})) != set(request["questions"]):
        raise ValueError("provider answers do not match questions")
    return result, (time.monotonic() - started) * 1000


def evaluate(rows: list[dict], candidate: dict, call) -> dict:
    validate_candidate(candidate, rows)
    totals = defaultdict(lambda: {"count": 0, "correct": 0, "abstained": 0, "critical_misses": 0,
                                  "brier_sum": 0.0, "brier_count": 0})
    latencies = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    for row in rows:
        questions = {name: {**question, "instructions": candidate.get("instructions", {}).get(name, question["instructions"])}
                     for name, question in row["questions"].items()}
        result, latency = call({"state": row["state"], "questions": questions, "model": candidate["model"]})
        latencies.append(latency)
        measured_usage = result.get("usage", {})
        for key in usage:
            if not isinstance(measured_usage.get(key), int):
                usage[key] = None
            elif usage[key] is not None:
                usage[key] += measured_usage[key]
        for name, question in questions.items():
            answer = result["answers"][name]
            label = row["labels"][name]
            if answer.get("type") != question["type"]:
                raise ValueError("provider answer type mismatch")
            score = totals[f"{row['decision_type']}:{row['stratum']}"]
            score["count"] += 1
            if question["type"] == "choice":
                confidence = answer.get("answer_confidence", answer.get("confidence"))
                prediction = answer.get("choice")
                if not isinstance(prediction, str) or prediction not in question["criteria"] or not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
                    raise ValueError("invalid choice answer")
                probabilities = answer.get("probabilities")
                if not isinstance(probabilities, dict) or set(probabilities) != set(question["criteria"]):
                    raise ValueError("invalid choice probabilities")
                if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1
                       for value in probabilities.values()):
                    raise ValueError("invalid choice probability")
                score["brier_sum"] += sum((value - int(option == label)) ** 2
                                          for option, value in probabilities.items()) / len(probabilities)
                score["brier_count"] += 1
                correct = prediction == label
                if confidence < candidate.get("abstain_below", 0.0):
                    score["abstained"] += 1
                elif correct:
                    score["correct"] += 1
                elif row["stratum"].startswith("critical"):
                    score["critical_misses"] += 1
            else:
                probability = answer.get("noul")
                if not isinstance(probability, (int, float)) or isinstance(probability, bool) or not 0 <= probability <= 1:
                    raise ValueError("invalid noul answer")
                score["brier_sum"] += (probability - int(label)) ** 2
                score["brier_count"] += 1
                confidence = max(probability, 1 - probability)
                if confidence < candidate.get("abstain_below", 0.0):
                    score["abstained"] += 1
                elif (probability >= 0.5) == label:
                    score["correct"] += 1
                elif label and row["stratum"].startswith("critical"):
                    score["critical_misses"] += 1
    count = sum(item["count"] for item in totals.values())
    correct = sum(item["correct"] for item in totals.values())
    abstained = sum(item["abstained"] for item in totals.values())
    critical_misses = sum(item["critical_misses"] for item in totals.values())
    brier_sum = sum(item["brier_sum"] for item in totals.values())
    brier_count = sum(item["brier_count"] for item in totals.values())
    latencies.sort()
    return {"count": count, "accuracy": correct / count, "abstention_rate": abstained / count,
            "critical_misses": critical_misses, "by_stratum": dict(sorted(totals.items())),
            "brier_mean": brier_sum / brier_count if brier_count else None,
            "latency_ms_p50": latencies[len(latencies) // 2],
            "latency_ms_p95": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
            "usage": usage}


def arm_a_metrics(rows: list[dict]) -> dict | str:
    """Score recorded incumbent outcomes; absence stays unavailable, never zero."""
    if any(not isinstance(row.get("arm_a"), dict) or set(row["arm_a"]) != set(row["labels"]) for row in rows):
        return "unavailable"
    count = correct = critical_misses = 0
    by_stratum = defaultdict(lambda: {"count": 0, "correct": 0, "critical_misses": 0})
    for row in rows:
        for name, label in row["labels"].items():
            prediction = row["arm_a"][name]
            valid = (isinstance(prediction, bool) if row["questions"][name]["type"] == "noul"
                     else isinstance(prediction, str) and prediction in row["questions"][name]["criteria"])
            if not valid:
                raise ValueError("invalid Arm A prediction")
            score = by_stratum[f"{row['decision_type']}:{row['stratum']}"]
            score["count"] += 1
            count += 1
            if prediction == label:
                score["correct"] += 1
                correct += 1
            elif label is True and prediction is False and row["stratum"].startswith("critical"):
                score["critical_misses"] += 1
                critical_misses += 1
    return {"count": count, "accuracy": correct / count, "critical_misses": critical_misses,
            "by_stratum": dict(sorted(by_stratum.items()))}


def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check_holdout_authority(ledger: list[dict], dataset_hash: str, seed_hash: str, candidate_hash: str) -> None:
    if not any(row.get("dataset_sha256") == dataset_hash and row.get("candidate_sha256") == candidate_hash
               and row.get("seed_sha256") == seed_hash and row.get("status") == "keep" for row in ledger):
        raise ValueError("candidate must be frozen from a recorded development keep")
    if any(row.get("dataset_sha256") == dataset_hash and row.get("status") == "holdout" for row in ledger):
        raise ValueError("locked holdout was already used for this dataset")


def prepare_corpus(rows: list[dict], seed: str, out_dir: Path) -> dict:
    splits = partition(rows, seed)
    if any(not values for values in splits.values()):
        raise ValueError("train, validation and holdout each need at least one task group")
    type_counts = {kind: sum(row["decision_type"] == kind for row in rows) for kind in {row["decision_type"] for row in rows}}
    holdout_counts = {kind: sum(row["decision_type"] == kind for row in splits["holdout"]) for kind in type_counts}
    release_eligible = all(count >= 200 and holdout_counts[kind] >= 50 and holdout_counts[kind] / count >= 0.25
                           for kind, count in type_counts.items())
    manifest = {"schema": "rhize-typed-research-corpus-v1", "corpus_sha256": digest(rows),
                "seed_sha256": digest(seed), "split_sha256": {name: digest(values) for name, values in splits.items()},
                "split_counts": {name: len(values) for name, values in splits.items()},
                "type_counts": type_counts, "release_eligible": release_eligible}
    out_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, values in splits.items():
        path = out_dir / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in values))
        path.chmod(0o600)
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)
    return manifest


def verified_split(path: Path, manifest: dict, split: str) -> list[dict]:
    rows = read_jsonl(path)
    if digest(rows) != manifest.get("split_sha256", {}).get(split):
        raise ValueError(f"{split} split does not match frozen manifest")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, help="raw labeled corpus for prepare only")
    parser.add_argument("--out-dir", type=Path, help="new private split directory for prepare")
    parser.add_argument("--train", type=Path)
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--holdout", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--seed", help="frozen seed for prepare only")
    parser.add_argument("--max-candidates", type=int, default=12)
    parser.add_argument("--max-requests", type=int, default=2400)
    parser.add_argument("--phase", choices=("prepare", "search", "holdout"), required=True)
    parser.add_argument("--frozen-candidate-sha256")
    args = parser.parse_args()
    if args.phase == "prepare":
        if not args.cases or not args.out_dir or not args.seed:
            parser.error("prepare requires --cases, --out-dir and --seed")
        print(json.dumps(prepare_corpus(read_jsonl(args.cases), args.seed, args.out_dir), sort_keys=True))
        return 0
    if not args.manifest or not args.candidates or not args.ledger:
        parser.error("search/holdout require --manifest, --candidates and --ledger")
    manifest = json.loads(args.manifest.read_text())
    if not isinstance(manifest, dict) or manifest.get("schema") != "rhize-typed-research-corpus-v1":
        raise ValueError("invalid frozen corpus manifest")
    if args.phase == "search":
        if not args.train or not args.validation or args.holdout:
            parser.error("search requires --train and --validation only")
        splits = {"train": verified_split(args.train, manifest, "train"),
                  "validation": verified_split(args.validation, manifest, "validation")}
        if {row["group_id"] for row in splits["train"]} & {row["group_id"] for row in splits["validation"]}:
            raise ValueError("task group crosses train and validation")
    else:
        if not args.holdout or args.train or args.validation:
            parser.error("holdout requires --holdout only")
        splits = {"holdout": verified_split(args.holdout, manifest, "holdout")}
    rows = [row for values in splits.values() for row in values]
    candidates = json.loads(args.candidates.read_text())
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= args.max_candidates:
        raise ValueError("candidate count exceeds experiment ceiling")
    if args.phase == "holdout" and len(candidates) != 1:
        raise ValueError("holdout requires exactly one frozen candidate")
    if len(candidates) * len(rows) > args.max_requests:
        raise ValueError("request ceiling exceeded")
    dataset_hash = manifest["corpus_sha256"]
    seed_hash = manifest["seed_sha256"]
    ledger = read_ledger(args.ledger)
    if args.phase == "holdout":
        frozen = digest(candidates[0])
        if args.frozen_candidate_sha256 != frozen:
            raise ValueError("frozen candidate hash mismatch")
        check_holdout_authority(ledger, dataset_hash, seed_hash, frozen)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    prior = [entry for entry in ledger if entry.get("dataset_sha256") == dataset_hash
             and entry.get("seed_sha256") == seed_hash and entry.get("status") == "keep"]
    best = min(((entry["validation"]["critical_misses"], -entry["validation"]["accuracy"],
                 entry["validation"]["abstention_rate"]) for entry in prior), default=None)
    for candidate in candidates:
        validate_candidate(candidate, rows)
        if args.phase == "search" and any(entry.get("candidate_sha256") == digest(candidate)
                                          and entry.get("dataset_sha256") == dataset_hash
                                          and entry.get("seed_sha256") == seed_hash for entry in ledger):
            raise ValueError("candidate already evaluated on this dataset and split")
        if args.phase == "search":
            train = evaluate(splits["train"], candidate, lambda request: local_call(args.base_url, request))
            validation = evaluate(splits["validation"], candidate, lambda request: local_call(args.base_url, request))
            key = (validation["critical_misses"], -validation["accuracy"], validation["abstention_rate"])
            keep = best is None or key < best
            if keep:
                best = key
            status = "keep" if keep else "discard"
            holdout = "locked"
            arm_a = {"train": arm_a_metrics(splits["train"]), "validation": arm_a_metrics(splits["validation"])}
        else:
            train = validation = None
            holdout = evaluate(splits["holdout"], candidate, lambda request: local_call(args.base_url, request))
            arm_a = {"holdout": arm_a_metrics(splits["holdout"])}
            status = "holdout"
        entry = {"schema": "rhize-typed-research-v1", "at": time.time(), "dataset_sha256": dataset_hash,
                 "seed_sha256": seed_hash, "release_eligible": manifest["release_eligible"],
                 "candidate_sha256": digest(candidate), "candidate_id": candidate["id"], "model": candidate["model"],
                 "status": status, "split_counts": manifest["split_counts"],
                 "train": train, "validation": validation, "holdout": holdout, "arm_a": arm_a}
        with args.ledger.open("a") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        print(json.dumps({"candidate_id": candidate["id"], "candidate_sha256": digest(candidate),
                          "status": status, "validation": validation, "holdout": holdout}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
