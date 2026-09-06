#!/usr/bin/env python3
"""Run every selected case as A+B, optionally with real subscription answers."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rhize-context-manager/scripts"))
from memory_context.core import sha256, utc_now
from memory_context.opportunities import aggregate, run_pair, tokens
from memory_context.model_evaluation import evaluate_answers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("claude", "codex", "host-neutral"), required=True)
    parser.add_argument("--model")
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--case", action="append")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.answers and (not args.model or args.host == "host-neutral"):
        parser.error("real answers require an explicit host and model")
    corpus_path = Path(__file__).with_name("gauntlet.json")
    corpus = json.loads(corpus_path.read_text())
    selected = [c for c in corpus["cases"] if not args.case or c["id"] in args.case]
    if not selected or (args.case and set(args.case) - {c["id"] for c in selected}):
        parser.error("unknown or empty case selection")
    rows = []
    for case in selected:
        candidates = [{"sourceSystem":"canonical-file", "sourceId":s["id"], "sourceRevision":sha256(s["body"]),
            "tenant":"rhize", "project":"gauntlet", "trustClass":"verified", "contentRole":"data",
            "provenance":[s["id"]], "content":"# " + s["heading"] + "\n" + s["body"],
            "relevance": min(1, len(tokens(case["question"]) & tokens(s["body"] + s["heading"])) / max(1, len(tokens(case["question"]))))} for s in case["sources"]]
        document = {"schemaVersion":1, "request":{"tenant":"rhize", "project":"gauntlet", "query":case["question"], "totalTokenBudget":6000},
                    "adapters":[{"name":"canonical-files", "memoryType":"semantic", "status":"available", "candidates":candidates}]}
        with tempfile.TemporaryDirectory(prefix="rhize-gauntlet-") as directory:
            root = Path(directory).resolve()
            row, contexts = run_pair(document, root, host=args.host, model=args.model, evidence_kind="curated")
            row["caseId"] = case["id"]
            row["corpusHash"] = sha256(corpus_path.read_bytes())
            required = {sha256(s) for s in case["rubric"]["requiredSourceIds"]}
            for arm in ("A", "B"):
                row["arms"][arm]["requiredSourceCoverage"] = len(required & set(row["arms"][arm].get("selectedSourceHashes", []))) / len(required) if required else None
            if args.answers:
                rubric = {**case["rubric"], "requiredSourceHashes":sorted(required)}
                row["answerComparison"] = evaluate_answers(args.host, args.model, case["question"], contexts, root, rubric=rubric)
                row["answerStatus"] = row["answerComparison"]["comparisonStatus"]
            rows.append(row)
        print(json.dumps({"caseId":case["id"], "retrieval":row["comparisonStatus"], "answers":row.get("answerStatus", "not_requested")}), flush=True)
    report = {"corpusHash":sha256(corpus_path.read_bytes()), "generatedAt":utc_now().isoformat(), "rows":rows, "aggregate":aggregate(rows)}
    target = Path(args.output).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return 0 if all(r["comparisonStatus"] == "complete" and (not args.answers or r["answerStatus"] == "complete") for r in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
