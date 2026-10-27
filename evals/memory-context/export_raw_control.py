#!/usr/bin/env python3
"""Export an offline full-source control beside, never instead of, paired memory arms."""
import argparse
import json
import os
from pathlib import Path
import time

from run_gauntlet import case_document, load_corpus
from memory_context.awareness import canonical, estimated_tokens, render_context
from memory_context.core import MemoryContextAssembler, sha256, utc_now
from memory_context.model_evaluation import INSTRUCTIONS


def prepare_raw_control(document, now=None):
    started = time.perf_counter_ns()
    assembler = MemoryContextAssembler()
    request = assembler._validate_request(document["request"])
    stamp = now or utc_now()
    candidates, excluded, statuses = [], {}, []
    for adapter in document["adapters"]:
        status, admitted, rejected = assembler._normalize_adapter(adapter, request, stamp)
        statuses.append(status)
        candidates.extend(admitted)
        for reason, count in rejected.items():
            excluded[reason] = excluded.get(reason, 0) + count
    context = render_context({"candidates": [item.envelope for item in candidates]},
                             {"payloads": {item.envelope["payloadRef"]: item.content for item in candidates}})
    input_bytes = len((INSTRUCTIONS + "\n" + canonical({"question": document["request"]["query"], "evidence": context})).encode())
    row = {"condition": "full_admissible_source_control", "sourceSnapshotHash": sha256(canonical(document)),
           "selectedSourceHashes": [item.envelope["sourceIdHash"] for item in candidates],
           "sourceInputBytes": len(canonical(document).encode()), "nativeInputBytes": input_bytes,
           "estimatedTokens": estimated_tokens(context), "excluded": excluded, "adapterStatuses": statuses,
           "buildElapsedMs": round((time.perf_counter_ns() - started) / 1e6, 3),
           "refreshCost": None, "modelUsage": None, "taskCorrectness": None, "actuallyRanModel": False}
    if input_bytes > 64_000:
        row.update(status="unavailable", reason="raw_source_input_too_large")
    else:
        row.update(status="prepared", context=context)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--rubrics", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        corpus, binding = load_corpus(args.corpus, args.rubrics)
        report = {"schemaVersion": "memory-raw-source-control-v1", "corpusHash": binding["corpusHash"],
                  "createdAt": utc_now().isoformat(), "role": "offline_control_only", "cases": []}
        for case in corpus["cases"]:
            report["cases"].append({"caseId": case["id"], **prepare_raw_control(case_document(case))})
        target = args.output.expanduser().absolute()
        if any(path.is_symlink() for path in (target, *target.parents)):
            raise ValueError("control output cannot traverse symlinks")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        print(json.dumps({"cases": len(report["cases"]), "prepared": sum(row["status"] == "prepared" for row in report["cases"]),
                          "modelCalls": 0, "corpusHash": binding["corpusHash"]}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"ERROR: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
