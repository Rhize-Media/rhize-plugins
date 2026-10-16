#!/usr/bin/env python3
"""Laya signal at existing Dev Flow checkpoints: shadow observation or an earned, advisory next action.

Neither mode changes a gate, obligation, approval or required check; the deterministic Dev Flow
contracts stay authoritative. Advice comes from the shared typed_advice client and only shows once
the decision registry says `advise` for `devflow-next-action`.
"""
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import typed_advice  # noqa: E402 - shared byte-identical island module, sibling of this script

DECISION = "devflow-next-action"
ACTIONS = {
    "continue": "Proceed with the planned next step; the evidence shows no open failure, stale source or missing verification.",
    "investigate": "Stop and diagnose first: a failing test, stale source, off-track or stuck work needs a root cause before more changes.",
    "verify": "Run or repeat verification (tests, review, requirement mapping) before proceeding; the evidence is insufficient.",
    "escalate": "Ask a person: a protected file, missing approval or genuine ambiguity needs a human decision.",
}
QUESTION = ("Given only the bounded Dev Flow checkpoint observations, which next action fits best? "
            "This is advice only: it never approves, skips or satisfies a required check.")
POLICY = {"candidates": list(ACTIONS), "version": 1}
CANDIDATES = [{"id": key, "criterion": text} for key, text in ACTIONS.items()]
MAX_SIDE_FILE = 65536

CHECKS = {
    "impact-map": ("scope_complete", "source_stale", "needs_human"),
    "check": ("tests_sufficient", "work_off_track", "worker_stuck", "needs_human"),
    "test-evidence": ("test_signal_meaningful", "missed_regression", "needs_human"),
    "review": ("requirements_satisfied", "needs_verification", "needs_human"),
    "completion": ("ready_to_finish", "needs_verification", "needs_human"),
}
SIGNALS = {
    "test_failed", "test_passed", "requirements_unmapped", "diff_large",
    "unresolved_dependency", "review_pending", "stuck_repeat", "protected_file",
    "source_stale", "none",
}
HARD_FIELDS = ("required_checks_passed", "independent_review_passed", "approval_satisfied")


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_state(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"signals", *HARD_FIELDS}:
        raise ValueError("state must contain only bounded signals and hard gate booleans")
    signals = value["signals"]
    if (not isinstance(signals, list) or not 1 <= len(signals) <= 10
            or len(set(signals)) != len(signals) or any(item not in SIGNALS for item in signals)):
        raise ValueError("invalid observation signals")
    if any(type(value[key]) is not bool for key in HARD_FIELDS):
        raise ValueError("hard gate fields must be booleans")
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
            or result["routing"].get("model") != request["model"]):
        raise ValueError("Laya checkpoint mismatch")
    answers = result.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(request["questions"]):
        raise ValueError("Laya answers mismatch")
    for answer in answers.values():
        value = answer.get("noul") if isinstance(answer, dict) and answer.get("type") == "noul" else None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError("Laya answer invalid")
    usage = result.get("usage")
    if not isinstance(usage, dict) or any(
        isinstance(usage.get(key), bool) or not isinstance(usage.get(key), int) or usage[key] < 0
        for key in ("input_tokens", "output_tokens")
    ):
        raise ValueError("Laya usage invalid")
    return result, round((time.monotonic() - started) * 1000, 3)


def directive(stage: str, answers: dict, state: dict) -> str:
    def yes(name: str, threshold: float) -> bool:
        return answers.get(name, {}).get("noul", 0) >= threshold
    if yes("needs_human", 0.80):
        return "escalate"
    if any(yes(name, 0.80) for name in ("source_stale", "work_off_track", "worker_stuck", "missed_regression")):
        return "investigate"
    if yes("needs_verification", 0.65) or ("tests_sufficient" in answers and not yes("tests_sufficient", 0.75)):
        return "verify"
    if (stage == "completion" and yes("ready_to_finish", 0.75)
            and all(state[key] for key in HARD_FIELDS)):
        return "finish_candidate"
    return "continue"


def read_side_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SIDE_FILE:
        raise ValueError("side file must be regular and <= 64 KiB")
    return path.read_text(encoding="utf-8", errors="replace")


def advise_checkpoint(stage: str, state: dict, evidence_sha256: str, summary: str = "",
                      files: tuple = ()) -> dict:
    """Ask Laya for an advisory next action. The deterministic hard gates only decide how critical a wrong
    answer would be (for the baseline gate's critical-miss rule); they never read Laya's output."""
    validate_state(state)
    if stage not in CHECKS:
        raise ValueError("unknown Dev Flow checkpoint")
    gates = {key: state[key] for key in HARD_FIELDS}
    critical = not all(gates.values())
    request = (f"Dev Flow {stage}. signals: {', '.join(state['signals'])}. "
               + " ".join(f"{key}={str(value).lower()}" for key, value in gates.items())
               + (f". {summary}" if summary else ""))
    result = typed_advice.advise(DECISION, request, CANDIDATES, f"{evidence_sha256}:{stage}",
                                 critical_if_wrong=critical, question=QUESTION, policy=POLICY,
                                 files=list(files))
    return {"decisionId": result["decisionId"], "mode": result["mode"], "holdback": result["holdback"],
            "recommendation": result["recommendation"],
            "advice": typed_advice.advice_line(DECISION, result, "next action"),
            "stage": stage, "criticalIfWrong": critical, "gates": gates, "gateChanged": False}


def outcome_main(argv: list, decision: str) -> int:
    parser = argparse.ArgumentParser(prog="outcome", description="Record what the agent actually did.")
    parser.add_argument("--decision-id", required=True)
    parser.add_argument("--chosen", required=True)
    args = parser.parse_args(argv)
    print(json.dumps({"decision": decision, "decisionId": args.decision_id, "chosen": args.chosen,
                      "recorded": typed_advice.record_outcome(decision, args.decision_id, args.chosen)},
                     sort_keys=True))
    return 0


def assess(stage: str, state: dict, source_sha256: str, model: str, base_url: str,
           call=call_laya) -> dict:
    validate_state(state)
    if stage not in CHECKS:
        raise ValueError("unknown Dev Flow checkpoint")
    if len(source_sha256) != 64 or any(char not in "0123456789abcdef" for char in source_sha256):
        raise ValueError("source_sha256 must be a lowercase SHA-256")
    if not model or len(model) > 80:
        raise ValueError("pinned checkpoint required")
    questions = {name: {"type": "noul", "instructions": f"At Dev Flow {stage}, is {name.replace('_', ' ')} true based only on the bounded observations?"}
                 for name in CHECKS[stage]}
    request = {"model": model, "state": {"checkpoint": stage, **state}, "questions": questions}
    result, latency = call(base_url, request)
    answers = result["answers"]
    return {"schema": "rhize-devflow-typed-checkpoint-v1", "variant": "B_local_laya",
            "status": "shadow", "stage": stage, "evidenceSha256": source_sha256,
            "stateSha256": digest(state), "questionIds": list(questions),
            "requestedModel": model, "routedModel": result["routing"]["model"],
            "assessment": {name: answers[name]["noul"] for name in questions},
            "candidateDirective": directive(stage, answers, state),
            "latencyMs": latency, "usage": result["usage"], "gateChanged": False}


def main() -> int:
    if sys.argv[1:2] == ["outcome"]:
        return outcome_main(sys.argv[2:], DECISION)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=tuple(CHECKS), required=True)
    parser.add_argument("--evidence", type=Path, required=True, help="current deterministic evidence packet")
    parser.add_argument("--model", default="typed-decisions")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=("disabled", "shadow", "advise"), default="disabled",
                        help="advise: the registry decides whether Laya's pick is shown; shadow until earned")
    parser.add_argument("--summary-file", type=Path, help="advise: optional bounded summary text (scrubbed)")
    parser.add_argument("--files-from", type=Path, help="advise: optional repo-relative file hints, one per line")
    parser.add_argument("--receipt", type=Path, help="private output path outside the repo")
    args = parser.parse_args()
    if args.mode == "disabled":
        output = {"status": "disabled", "variant": "A_incumbent"}
    else:
        try:
            if args.evidence.is_symlink() or not args.evidence.is_file() or args.evidence.stat().st_size > 1048576:
                raise ValueError("evidence file must be regular and <= 1 MiB")
            evidence_bytes = args.evidence.read_bytes()
            evidence_hash = hashlib.sha256(evidence_bytes).hexdigest()
            observed = json.load(sys.stdin)
            if args.mode == "advise":
                output = advise_checkpoint(
                    args.stage, observed, evidence_hash,
                    read_side_file(args.summary_file) if args.summary_file else "",
                    read_side_file(args.files_from).splitlines() if args.files_from else ())
            else:
                output = assess(args.stage, observed, evidence_hash, args.model, args.base_url)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            output = {"status": "unavailable", "variant": "A_incumbent",
                      "stage": args.stage, "reasonCode": type(exc).__name__, "gateChanged": False}
            if args.mode == "advise":
                output.update({"recommendation": None, "advice": ""})
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(args.receipt, flags, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(output, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
