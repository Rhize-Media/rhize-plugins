#!/usr/bin/env python3
"""Observe bounded tool-risk and legal browser-action candidates with local Laya.

Shadow mode only observes. `--mode advise` (browser_qa only) asks the shared typed_advice client for
one advisory pick among the approved surfaces plus `none`; the registry decides whether it is shown.
Neither mode grants permissions, clicks, blocks, reorders, or clears an existing policy finding. The
current deterministic Dev Flow gate remains A.
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

import typed_advice
from typed_checkpoint import advice_fields, call_laya, outcome_main

SCHEMA = "rhize-devflow-typed-selection-v1"
PROFILES = {"tool_trace_risk": 6, "browser_qa": 8}
TOKEN = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
DECISION = "browser-qa-selection"
QUESTION = ("Given only the bounded task signals and approved test-surface metadata, which surface should the "
            "browser QA scenario exercise first? Advice only: it never grants permission or approves an action.")
# shortcut: the shortlist is dynamic, so the policy binds its construction rule rather than candidate ids.
POLICY = {"construction": "approved legal browser_qa surfaces from the deterministic evidence, then none",
          "max_surfaces": PROFILES["browser_qa"], "version": 1}


def hash_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(state: object) -> dict:
    if not isinstance(state, dict) or set(state) != {
        "schema", "capability", "sourceSha256", "taskSignals", "candidates", "incumbentIds", "policy"
    } or state["schema"] != SCHEMA:
        raise ValueError("invalid typed selection envelope")
    capability = state["capability"]
    if capability not in PROFILES or not isinstance(state["sourceSha256"], str) or not DIGEST.fullmatch(state["sourceSha256"]):
        raise ValueError("invalid capability or source digest")
    if (not isinstance(state["taskSignals"], list) or len(state["taskSignals"]) > 8 or any(
        not isinstance(item, str) or not TOKEN.fullmatch(item) for item in state["taskSignals"]
    )):
        raise ValueError("invalid task signals")
    candidates = state["candidates"]
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= PROFILES[capability]:
        raise ValueError("invalid candidate count")
    ids = set()
    for candidate in candidates:
        if (not isinstance(candidate, dict) or set(candidate) != {"id", "hints", "legal"}
                or not isinstance(candidate["id"], str) or not TOKEN.fullmatch(candidate["id"])
                or type(candidate["legal"]) is not bool or not candidate["legal"]
                or not isinstance(candidate["hints"], list) or len(candidate["hints"]) > 6
                or any(not isinstance(h, str) or not TOKEN.fullmatch(h) for h in candidate["hints"])):
            raise ValueError("only bounded legal candidate metadata is allowed")
        if candidate["id"] in ids:
            raise ValueError("duplicate candidate")
        ids.add(candidate["id"])
    incumbents = state["incumbentIds"]
    if (not isinstance(incumbents, list) or len(incumbents) > len(candidates)
            or len(set(incumbents)) != len(incumbents) or any(item not in ids for item in incumbents)):
        raise ValueError("invalid incumbent ids")
    policy = state["policy"]
    if (not isinstance(policy, dict) or set(policy) != {"hardBlocked", "approvalSatisfied", "testSurface"}
            or any(type(value) is not bool for value in policy.values())):
        raise ValueError("invalid deterministic policy facts")
    if capability == "browser_qa" and not policy["testSurface"]:
        raise ValueError("browser selection requires an approved test surface")
    return state


def assess(state: dict, model: str, base_url: str, call=call_laya) -> dict:
    state = validate(state)
    if not isinstance(model, str) or not TOKEN.fullmatch(model):
        raise ValueError("invalid pinned model")
    risk = state["capability"] == "tool_trace_risk"
    questions = {
        f"c{index}": {"type": "noul", "instructions": (
            f"Given only the bounded metadata, does candidate {candidate['id']} "
            + ("need additional risk or injection review?" if risk else "advance the browser QA scenario safely?")
            + " Do not infer permission or approve an action."
        )}
        for index, candidate in enumerate(state["candidates"])
    }
    request = {"model": model, "state": {
        "capability": state["capability"], "taskSignals": state["taskSignals"],
        "candidates": state["candidates"], "policy": state["policy"],
    }, "questions": questions}
    response, latency = call(base_url, request)
    rows = [{"candidateId": candidate["id"], "score": float(response["answers"][f"c{index}"]["noul"]),
             "incumbentIncluded": candidate["id"] in state["incumbentIds"]}
            for index, candidate in enumerate(state["candidates"])]
    rows.sort(key=lambda row: (-row["score"], row["candidateId"]))
    return {"schema": SCHEMA, "status": "shadow", "variant": "B_local_laya",
            "capability": state["capability"], "sourceSha256": state["sourceSha256"],
            "stateSha256": hash_json(state), "requestSha256": hash_json(request),
            "incumbentIds": state["incumbentIds"], "ranked": rows,
            "policy": state["policy"], "model": model, "routedModel": response["routing"]["model"],
            "latencyMs": latency, "usage": response["usage"], "actionTaken": False,
            "hardGateChanged": False}


def advise_selection(state: dict) -> dict:
    state = validate(state)
    if state["capability"] != "browser_qa":
        raise ValueError("advice is only available for browser_qa")
    candidates = [{"id": item["id"], "criterion": (
        f"Exercise approved surface {item['id']}" + (f" ({', '.join(item['hints'])})" if item["hints"] else "")
        + " first.")} for item in state["candidates"]]
    candidates.append({"id": "none", "criterion": "None of the listed surfaces fits the task signals."})
    request = (f"Browser QA. task signals: {', '.join(state['taskSignals']) or 'none'}. surfaces: "
               + "; ".join(f"{item['id']}[{','.join(item['hints'])}]" for item in state["candidates"]))
    result = typed_advice.advise(DECISION, request, candidates, f"{state['sourceSha256']}:browser_qa",
                                 critical_if_wrong=False, question=QUESTION, policy=POLICY)
    return {"schema": SCHEMA, **advice_fields(DECISION, result, "browser QA surface"),
            "capability": state["capability"], "sourceSha256": state["sourceSha256"],
            "incumbentIds": state["incumbentIds"], "actionTaken": False, "hardGateChanged": False}


def write_receipt(value: dict, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink():
        raise ValueError("receipt root is a symlink")
    path = root / (uuid.uuid4().hex + ".json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
    return path


def main() -> int:
    if sys.argv[1:2] == ["outcome"]:
        return outcome_main(sys.argv[2:], DECISION)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True, help="current source-bound deterministic evidence file")
    parser.add_argument("--model", default="typed-decisions")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=("disabled", "shadow", "advise"), default="disabled")
    parser.add_argument("--receipt-root", type=Path,
                        default=Path.home() / ".local/share/rhize/typed-decisions/devflow-selection")
    args = parser.parse_args()
    if args.mode == "disabled":
        print(json.dumps({"status": "disabled", "variant": "A_incumbent"}))
        return 0
    try:
        if args.evidence.is_symlink() or not args.evidence.is_file() or args.evidence.stat().st_size > 1048576:
            raise ValueError("evidence must be regular and <= 1 MiB")
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ValueError("state too large")
        state = json.loads(raw)
        evidence_hash = hashlib.sha256(args.evidence.read_bytes()).hexdigest()
        if not isinstance(state, dict) or state.get("sourceSha256") != evidence_hash:
            raise ValueError("evidence digest mismatch")
        output = (advise_selection(state) if args.mode == "advise" and state.get("capability") == "browser_qa"
                  else assess(state, args.model, args.base_url))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        output = {"schema": SCHEMA, "status": "unavailable", "variant": "A_incumbent",
                  "reasonCode": type(exc).__name__, "actionTaken": False, "hardGateChanged": False}
    try:
        receipt = str(write_receipt(output, args.receipt_root))
    except (OSError, ValueError):
        receipt = None
        output = {"status": "unavailable", "variant": "A_incumbent",
                  "reasonCode": "receipt_unavailable", "actionTaken": False, "hardGateChanged": False}
    print(json.dumps({**output, "receipt": receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
