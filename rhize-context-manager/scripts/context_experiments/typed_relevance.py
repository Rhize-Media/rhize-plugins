#!/usr/bin/env python3
"""Shadow-only local Laya relevance score for a verified native context pack."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_experiments.providers.native_context_pack import NativeContextPackProvider
from context_experiments.runner import git_snapshot


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def local_call(base_url: str, request: dict, timeout: float = 12) -> tuple[dict, float]:
    parsed = urlparse(base_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ValueError("Laya URL must be loopback HTTP without credentials or path")
    started = time.monotonic()
    with urlopen(Request(base_url.rstrip("/") + "/v1/systemone", data=json.dumps(request).encode(),
                         headers={"Content-Type": "application/json"}, method="POST"), timeout=timeout) as response:
        raw = response.read(262145)
    if len(raw) > 262144:
        raise ValueError("Laya response too large")
    result = json.loads(raw)
    if (not isinstance(result, dict) or not isinstance(result.get("routing"), dict)
            or result["routing"].get("model") != request["model"]):
        raise ValueError("Laya checkpoint mismatch")
    answers = result.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(request["questions"]):
        raise ValueError("Laya answers mismatch")
    for answer in answers.values():
        value = answer.get("noul") if isinstance(answer, dict) and answer.get("type") == "noul" else None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError("Laya relevance answer invalid")
    return result, round((time.monotonic() - started) * 1000, 3)


def rank_pack(repo: Path, manifest_path: Path, prompt_path: Path, task: str, model: str,
              base_url: str, call=local_call) -> dict:
    if not task.strip() or len(task) > 500 or "\n" in task:
        raise ValueError("task must be a redacted one-line summary <= 500 characters")
    if not model or len(model) > 80:
        raise ValueError("pinned Laya checkpoint required")
    manifest = json.loads(manifest_path.read_text())
    snapshot = git_snapshot(repo)
    if snapshot is None:
        raise ValueError("repository snapshot unavailable")
    verification = NativeContextPackProvider().verify_pack(manifest, repo, snapshot, prompt_path)
    if not verification.valid or not manifest["policy"]["acceptedForUse"]:
        raise ValueError("native context pack is stale or rejected")
    entries = manifest["entries"]
    if not entries:
        raise ValueError("native context pack has no entries")
    selected = entries[:8]
    metadata = []
    questions = {}
    for index, entry in enumerate(selected):
        candidate_id = sha(entry["path"].encode())[:16]
        metadata.append({"id": candidate_id, "fileHint": Path(entry["path"]).stem[:48],
                         "role": entry["role"], "reason": entry["reason"]})
        questions[f"c{index}"] = {
            "type": "noul",
            "instructions": f"Does candidate {candidate_id} materially help with the stated software task?"
        }
    request = {"model": model, "state": {"task": task, "candidates": metadata}, "questions": questions}
    result, latency = call(base_url, request)
    usage = result.get("usage")
    if not isinstance(usage, dict) or any(
        isinstance(usage.get(key), bool) or not isinstance(usage.get(key), int) or usage[key] < 0
        for key in ("input_tokens", "output_tokens")
    ):
        raise ValueError("Laya usage invalid")
    ranked = sorted(({"candidateId": metadata[index]["id"], "role": selected[index]["role"],
                      "reason": selected[index]["reason"], "score": result["answers"][f"c{index}"]["noul"],
                      "incumbentIncluded": True}
                     for index in range(len(selected))),
                    key=lambda item: (-item["score"], item["candidateId"]))
    return {"schema": "rhize-typed-relevance-v1", "status": "shadow", "variant": "B_local_laya",
            "sourceSnapshot": snapshot, "packId": manifest["packId"],
            "manifestSha256": sha(manifest_path.read_bytes()),
            "requestSha256": sha(json.dumps(request, sort_keys=True).encode()),
            "model": model, "routedModel": result["routing"]["model"],
            "candidatesEvaluated": len(selected), "candidatesDeferred": len(entries) - len(selected),
            "ranked": ranked, "latencyMs": latency, "usage": usage, "packAltered": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--task", required=True, help="redacted one-line task summary")
    parser.add_argument("--model", default="typed-decisions")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=("disabled", "shadow"), default="disabled")
    parser.add_argument("--receipt", type=Path, help="private output path for shadow receipt")
    args = parser.parse_args()
    if args.mode == "disabled":
        print(json.dumps({"status": "disabled", "variant": "A_incumbent"}))
        return 0
    try:
        output = rank_pack(args.repo.resolve(strict=True), args.manifest, args.prompt,
                           args.task, args.model, args.base_url)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        output = {"status": "unavailable", "variant": "A_incumbent", "reasonCode": type(exc).__name__, "packAltered": False}
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(args.receipt, flags, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(output, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
    return 0 if output["status"] == "shadow" else 2


if __name__ == "__main__":
    raise SystemExit(main())
