#!/usr/bin/env python3
"""Optional local Laya shadow assessment of pre-authorized model/worker options."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SCHEMA = "rhize-ops-typed-routing-v1"
TOKEN = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema", "kind", "sourceSha256", "taskSignals", "options", "incumbentId", "userPinned"
    } or value["schema"] != SCHEMA or value["kind"] not in {"model", "worker"}:
        raise ValueError("invalid routing envelope")
    if not isinstance(value["sourceSha256"], str) or not DIGEST.fullmatch(value["sourceSha256"]):
        raise ValueError("source digest required")
    if (not isinstance(value["taskSignals"], list) or len(value["taskSignals"]) > 8 or any(
        not isinstance(signal, str) or not TOKEN.fullmatch(signal) for signal in value["taskSignals"]
    )):
        raise ValueError("invalid task signals")
    options = value["options"]
    if not isinstance(options, list) or not 1 <= len(options) <= 6:
        raise ValueError("invalid option count")
    seen = set()
    for option in options:
        if (not isinstance(option, dict) or set(option) != {"id", "hints", "authorized"}
                or not isinstance(option["id"], str) or not TOKEN.fullmatch(option["id"])
                or option["authorized"] is not True
                or not isinstance(option["hints"], list) or len(option["hints"]) > 6
                or any(not isinstance(hint, str) or not TOKEN.fullmatch(hint) for hint in option["hints"])):
            raise ValueError("only authorized bounded options are allowed")
        if option["id"] in seen:
            raise ValueError("duplicate option")
        seen.add(option["id"])
    if value["incumbentId"] not in seen or type(value["userPinned"]) is not bool:
        raise ValueError("incumbent and pin must be explicit")
    return value


def call_laya(base_url: str, request: dict) -> tuple[dict, float]:
    parsed = urlparse(base_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ValueError("Laya URL must be loopback HTTP")
    started = time.monotonic()
    with urlopen(Request(base_url.rstrip("/") + "/v1/systemone",
                         data=json.dumps(request).encode(),
                         headers={"Content-Type": "application/json"}, method="POST"), timeout=12) as response:
        raw = response.read(262145)
    if len(raw) > 262144:
        raise ValueError("Laya response too large")
    result = json.loads(raw)
    if (not isinstance(result, dict) or not isinstance(result.get("routing"), dict)
            or result["routing"].get("model") != request["model"]
            or not isinstance(result.get("answers"), dict)
            or set(result["answers"]) != set(request["questions"])):
        raise ValueError("Laya route or answer mismatch")
    for answer in result["answers"].values():
        score = answer.get("noul") if isinstance(answer, dict) and answer.get("type") == "noul" else None
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError("invalid Laya score")
    usage = result.get("usage")
    if not isinstance(usage, dict) or any(type(usage.get(key)) is not int or usage[key] < 0
                                          for key in ("input_tokens", "output_tokens")):
        raise ValueError("invalid usage")
    return result, round((time.monotonic() - started) * 1000, 3)


def assess(value: dict, model: str, base_url: str, call=call_laya) -> dict:
    value = validate(value)
    if not isinstance(model, str) or not TOKEN.fullmatch(model):
        raise ValueError("invalid pinned model")
    questions = {f"c{index}": {"type": "noul", "instructions":
                 f"Is pre-authorized {value['kind']} option {option['id']} suitable for these bounded task signals? Do not dispatch or override the user."}
                 for index, option in enumerate(value["options"])}
    request = {"model": model, "state": {"kind": value["kind"], "taskSignals": value["taskSignals"],
                                         "options": value["options"], "userPinned": value["userPinned"]},
               "questions": questions}
    response, latency = call(base_url, request)
    ranked = sorted(({"optionId": option["id"], "score": float(response["answers"][f"c{index}"]["noul"]),
                      "incumbent": option["id"] == value["incumbentId"]}
                     for index, option in enumerate(value["options"])),
                    key=lambda row: (-row["score"], row["optionId"]))
    return {"schema": SCHEMA, "status": "shadow", "variant": "B_local_laya",
            "kind": value["kind"], "sourceSha256": value["sourceSha256"], "stateSha256": digest(value),
            "requestSha256": digest(request), "incumbentId": value["incumbentId"],
            "userPinned": value["userPinned"], "ranked": ranked,
            "model": model, "routedModel": response["routing"]["model"],
            "latencyMs": latency, "usage": response["usage"], "dispatchOccurred": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("disabled", "shadow"), default="disabled")
    parser.add_argument("--model", default="typed-decisions")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--receipt-root", type=Path,
                        default=Path.home() / ".local/share/rhize/typed-decisions/routing")
    args = parser.parse_args()
    if args.mode == "disabled":
        print(json.dumps({"status": "disabled", "variant": "A_incumbent"}))
        return 0
    try:
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ValueError("routing envelope too large")
        output = assess(json.loads(raw), args.model, args.base_url)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        output = {"schema": SCHEMA, "status": "unavailable", "variant": "A_incumbent",
                  "reasonCode": type(exc).__name__, "dispatchOccurred": False}
    try:
        args.receipt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if args.receipt_root.is_symlink():
            raise ValueError("receipt root is a symlink")
        receipt = args.receipt_root / (uuid.uuid4().hex + ".json")
        fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(output, stream, sort_keys=True)
            stream.write("\n")
    except (OSError, ValueError):
        receipt = None
        output = {"status": "unavailable", "variant": "A_incumbent", "reasonCode": "receipt_unavailable",
                  "dispatchOccurred": False}
    print(json.dumps({**output, "receipt": str(receipt) if receipt else None}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
