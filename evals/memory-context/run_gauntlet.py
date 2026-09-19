#!/usr/bin/env python3
"""Run a pinned paired corpus, preserving every attempted trial and review artifact."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rhize-context-manager/scripts"))
from memory_context.core import sha256, utc_now, _write_private_replace
from memory_context.opportunities import aggregate, run_pair, tokens
from memory_context.model_evaluation import evaluate_answers, execute_answer
from memory_context.quality import grade_answer


def case_document(case):
    candidates = [{"sourceSystem":"canonical-file", "sourceId":s["id"], "sourceRevision":sha256(s["body"]),
        "tenant":"rhize", "project":"gauntlet", "trustClass":"verified", "contentRole":"data",
        "provenance":[s["id"]], "content":"# " + s["heading"] + "\n" + s["body"],
        "relevance": min(1, len(tokens(case["question"]) & tokens(s["body"] + s["heading"])) / max(1, len(tokens(case["question"]))))} for s in case["sources"]]
    return {"schemaVersion":1, "request":{"tenant":"rhize", "project":"gauntlet", "query":case["question"], "totalTokenBudget":6000},
            "adapters":[{"name":"canonical-files", "memoryType":"semantic", "status":"available", "candidates":candidates}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("claude", "codex", "host-neutral"), required=True)
    parser.add_argument("--model")
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--case", action="append")
    parser.add_argument("--corpus", type=Path, default=Path(__file__).with_name("gauntlet.json"))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--baseline-commit")
    parser.add_argument("--retain-review", action="store_true", help="keep private blinded answers for this curated corpus only")
    parser.add_argument("--empty-control", action="store_true", help="also probe an empty evidence packet; require abstention")
    parser.add_argument("--max-answer-calls", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.answers and (not args.model or args.host == "host-neutral" or not args.baseline_commit):
        parser.error("real answers require explicit host, model and confirmed baseline commit")
    if not 1 <= args.repetitions <= 10:
        parser.error("repetitions must be 1..10")
    corpus = json.loads(args.corpus.read_text())
    selected = [c for c in corpus["cases"] if not args.case or c["id"] in args.case]
    if not selected or (args.case and set(args.case) - {c["id"] for c in selected}):
        parser.error("unknown or empty case selection")
    # Validate all grading contracts before reserving or spending a model call.
    for case in selected:
        grade_answer("", [], {**case["rubric"], "requiredSourceHashes":[sha256(s) for s in case["rubric"].get("requiredSourceIds", [])]})
    calls = len(selected) * args.repetitions * (3 if args.empty_control else 2)
    if args.answers and calls > args.max_answer_calls:
        parser.error(f"requested {calls} answer calls exceeds explicit cap {args.max_answer_calls}")
    baseline_hash = None
    if args.baseline_commit:
        result = subprocess.run(["git", "show", f"{args.baseline_commit}:rhize-context-manager/scripts/memory_context/core.py"], cwd=ROOT, capture_output=True, timeout=15)
        if result.returncode or result.stdout != (ROOT/"rhize-context-manager/scripts/memory_context/core.py").read_bytes():
            parser.error("incumbent assembler differs from pinned baseline")
        baseline_hash = sha256(result.stdout)
    target = args.output.expanduser().absolute()
    if any(p.is_symlink() for p in (target, *target.parents)):
        parser.error("output cannot traverse symlinks")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    corpus_hash = sha256(args.corpus.read_bytes())
    report = {"schemaVersion":"memory-controlled-pilot-v1", "corpusHash":corpus_hash, "generatedAt":utc_now().isoformat(),
        "baseline":{"label":"legacy-direct-v1", "commit":args.baseline_commit,"assemblerHash":baseline_hash},
        "host":args.host,"model":args.model,"repetitions":args.repetitions,"plannedAnswerCalls":calls if args.answers else 0,
        "studyClass":"curated_pilot", "humanReview":"pending" if args.retain_review else "unavailable",
        "rows":[], "reservations":[{"caseId":c['id'],"repetition":rep,"status":"pending"} for c in selected for rep in range(1,args.repetitions+1)]}
    def persist():
        report['aggregate'] = aggregate(report['rows'])
        _write_private_replace(target, json.dumps(report,indent=2)+'\n')
    persist()
    for index, reservation in enumerate(report['reservations']):
        case = next(c for c in selected if c['id']==reservation['caseId'])
        required = {sha256(s) for s in case['rubric'].get('requiredSourceIds', [])}
        rubric = {**case['rubric'], 'requiredSourceHashes':sorted(required)}
        order = ['A','B'] if index % 2 == 0 else ['B','A']
        with tempfile.TemporaryDirectory(prefix='rhize-gauntlet-') as directory:
            root = Path(directory).resolve()
            row, contexts = run_pair(case_document(case),root,host=args.host,model=args.model,evidence_kind='curated')
            row.update(caseId=case['id'],corpusHash=corpus_hash,repetition=reservation['repetition'])
            for arm in ('A','B'):
                row['arms'][arm]['requiredSourceCoverage'] = len(required & set(row['arms'][arm].get('selectedSourceHashes',[])))/len(required) if required else None
            if args.answers:
                row['answerComparison'] = evaluate_answers(args.host,args.model,case['question'],contexts,root,rubric=rubric,
                    arm_order=order,review_dir=target.parent/(target.stem+'-review') if args.retain_review else None)
                row['answerStatus'] = row['answerComparison']['comparisonStatus']
                if args.empty_control:
                    control = execute_answer(args.host,args.model,case['question'],'',root/'control')
                    control['grading'] = grade_answer(control.get('answer',''),control.get('sourceIds',[]),{'expectedAbstention':True}) if control.get('status')=='completed' else {'passed':None,'status':'unavailable_answer'}
                    if 'answer' in control:
                        control['answerHash'] = sha256(control.pop('answer'))
                    row['emptyAnswerControl'] = control
                    row['emptyControlOrder'] = 'after_pair'
        report['rows'].append(row)
        reservation['status'] = 'complete' if row['comparisonStatus']=='complete' and (not args.answers or (row['answerStatus']=='complete' and (not args.empty_control or row['emptyAnswerControl'].get('status')=='completed'))) else 'incomplete'
        persist()
        print(json.dumps({'caseId':case['id'],'repetition':reservation['repetition'],'retrieval':row['comparisonStatus'],'answers':row.get('answerStatus','not_requested')}),flush=True)
    return 0 if all(r['status']=='complete' for r in report['reservations']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
