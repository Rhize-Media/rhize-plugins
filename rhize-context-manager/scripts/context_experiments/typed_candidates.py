#!/usr/bin/env python3
"""Local Laya shadow ranking for bounded skill, graph, and retention candidates.

Callers generate and validate candidates first. This module never selects, drops,
loads, or executes a candidate; it records the incumbent and the model scores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_experiments.typed_relevance import local_call

SCHEMA = "rhize-typed-candidates-v1"
CAPABILITIES = {
    "skill_workflow": 5,
    "graph_memory": 8,
    "context_retention": 8,
}
TOKEN = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema", "capability", "sourceSha256", "taskSignals", "candidates", "incumbentIds"
    } or value["schema"] != SCHEMA:
        raise ValueError("invalid typed candidate envelope")
    capability = value["capability"]
    if capability not in CAPABILITIES or not isinstance(value["sourceSha256"], str) or not DIGEST.fullmatch(value["sourceSha256"]):
        raise ValueError("invalid capability or source digest")
    signals = value["taskSignals"]
    if (not isinstance(signals, list) or len(signals) > 8 or any(
        not isinstance(s, str) or not TOKEN.fullmatch(s) for s in signals
    )):
        raise ValueError("task signals must be bounded tokens")
    candidates = value["candidates"]
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= CAPABILITIES[capability]:
        raise ValueError("invalid candidate count")
    seen = set()
    for candidate in candidates:
        if (not isinstance(candidate, dict) or set(candidate) != {"id", "hints", "protected"}
                or not isinstance(candidate["id"], str) or not TOKEN.fullmatch(candidate["id"])
                or type(candidate["protected"]) is not bool
                or not isinstance(candidate["hints"], list) or len(candidate["hints"]) > 6
                or any(not isinstance(h, str) or not TOKEN.fullmatch(h) for h in candidate["hints"])):
            raise ValueError("invalid candidate metadata")
        if candidate["id"] in seen:
            raise ValueError("duplicate candidate id")
        seen.add(candidate["id"])
    incumbents = value["incumbentIds"]
    if (not isinstance(incumbents, list) or len(incumbents) > len(candidates)
            or len(set(incumbents)) != len(incumbents) or any(i not in seen for i in incumbents)):
        raise ValueError("invalid incumbent ids")
    if capability == "context_retention" and not any(candidate["protected"] for candidate in candidates):
        raise ValueError("retention requires a protected anchor")
    if capability == "context_retention" and any(
        candidate["protected"] and candidate["id"] not in incumbents for candidate in candidates
    ):
        raise ValueError("protected context must be present in incumbent set")
    return value


def assess(value: dict, model: str, base_url: str, call=local_call) -> dict:
    value = validate(value)
    if not isinstance(model, str) or not TOKEN.fullmatch(model):
        raise ValueError("pinned model must be a bounded token")
    capability = value["capability"]
    questions = {
        f"c{index}": {
            "type": "noul",
            "instructions": (
                f"For {capability}, is candidate {candidate['id']} relevant given only the "
                "bounded task signals and candidate hints? Do not infer permission or policy authority."
            ),
        }
        for index, candidate in enumerate(value["candidates"])
    }
    request = {"model": model, "state": {
        "capability": capability, "taskSignals": value["taskSignals"],
        "candidates": value["candidates"],
    }, "questions": questions}
    result, latency = call(base_url, request)
    usage = result.get("usage")
    if (not isinstance(usage, dict) or any(
        type(usage.get(key)) is not int or usage[key] < 0
        for key in ("input_tokens", "output_tokens")
    )):
        raise ValueError("Laya usage invalid")
    answers = result["answers"]
    ranking = sorted(({
        "candidateId": candidate["id"], "score": float(answers[f"c{index}"]["noul"]),
        "incumbentIncluded": candidate["id"] in value["incumbentIds"],
        "protected": candidate["protected"],
    } for index, candidate in enumerate(value["candidates"])),
        key=lambda row: (-row["score"], row["candidateId"]))
    return {
        "schema": SCHEMA, "status": "shadow", "variant": "B_local_laya",
        "capability": capability, "sourceSha256": value["sourceSha256"],
        "stateSha256": sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()),
        "requestSha256": sha(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()),
        "model": model, "routedModel": result["routing"]["model"],
        "incumbentIds": value["incumbentIds"], "ranking": ranking,
        "latencyMs": latency, "usage": usage, "incumbentAltered": False,
    }


def write_receipt(output: dict, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink():
        raise ValueError("receipt root is a symlink")
    path = root / (uuid.uuid4().hex + ".json")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(output, stream, sort_keys=True)
        stream.write("\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("disabled", "shadow"), default="disabled")
    parser.add_argument("--model", default="typed-decisions")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--evidence", type=Path, help="required source artifact for retention decisions")
    parser.add_argument("--receipt-root", type=Path,
                        default=Path.home() / ".local/share/rhize/typed-decisions/receipts")
    args = parser.parse_args()
    if args.mode == "disabled":
        print(json.dumps({"status": "disabled", "variant": "A_incumbent"}))
        return 0
    try:
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ValueError("candidate envelope too large")
        state = json.loads(raw)
        if isinstance(state, dict) and state.get("capability") == "context_retention":
            evidence = args.evidence
            if evidence is None or evidence.is_symlink() or not evidence.is_file() or evidence.stat().st_size > 1048576:
                raise ValueError("retention requires a regular source artifact <= 1 MiB")
            if sha(evidence.read_bytes()) != state.get("sourceSha256"):
                raise ValueError("retention source changed")
        output = assess(state, args.model, args.base_url)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        output = {"schema": SCHEMA, "status": "unavailable", "variant": "A_incumbent",
                  "reasonCode": type(exc).__name__, "incumbentAltered": False}
    try:
        receipt = str(write_receipt(output, args.receipt_root))
    except (OSError, ValueError):
        receipt = None
        output = {"schema": SCHEMA, "status": "unavailable", "variant": "A_incumbent",
                  "reasonCode": "receipt_unavailable", "incumbentAltered": False}
    print(json.dumps({**output, "receipt": receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
