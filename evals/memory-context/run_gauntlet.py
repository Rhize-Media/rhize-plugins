#!/usr/bin/env python3
"""Run a pinned paired corpus, preserving every attempted trial and review artifact."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rhize-context-manager/scripts"))
from memory_context.core import sha256, utc_now, _write_private_replace
from memory_context.opportunities import aggregate, run_pair, tokens
from memory_context.model_evaluation import evaluate_answers, execute_answer
from memory_context.quality import grade_answer


def load_corpus(path, rubrics_path=None):
    content = path.read_bytes()
    corpus = json.loads(content)
    cases = corpus.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("corpus must contain nonempty cases")
    ids = [case.get("id") for case in cases]
    if any(not isinstance(identifier, str) or not identifier for identifier in ids) or len(set(ids)) != len(ids):
        raise ValueError("case IDs must be nonempty and unique")
    binding = {"corpusHash": sha256(content), "rubricsHash": None, "decisionRule": None}
    if rubrics_path is not None:
        grading_bytes = rubrics_path.read_bytes()
        grading = json.loads(grading_bytes)
        if set(corpus) != {"schemaVersion", "name", "provenance", "cases"} or corpus["schemaVersion"] != 1:
            raise ValueError("separate task corpus has an invalid shape")
        if set(grading) != {"schemaVersion", "corpusHash", "decisionRule", "cases"} or grading["schemaVersion"] != 1 or grading["corpusHash"] != binding["corpusHash"]:
            raise ValueError("grading file must bind the exact task corpus")
        if not isinstance(grading["decisionRule"], str) or not grading["decisionRule"].strip():
            raise ValueError("declare decisionRule before running")
        grading_cases = grading["cases"]
        if not isinstance(grading_cases, list) or any(not isinstance(case, dict) or set(case) != {"id", "rubric", "reviewCriteria"} for case in grading_cases):
            raise ValueError("grading cases need id, rubric and reviewCriteria")
        by_id = {case["id"]: case for case in grading_cases}
        if len(by_id) != len(grading_cases) or set(by_id) != set(ids):
            raise ValueError("grading cases must match task cases exactly")
        for case in cases:
            if set(case) != {"id", "question", "sources"}:
                raise ValueError("task input must not contain rubric, answers or grader fields")
            if not isinstance(case["question"], str) or not case["question"].strip() or not isinstance(case["sources"], list):
                raise ValueError("case question/sources is invalid")
            for source in case["sources"]:
                if not isinstance(source, dict) or set(source) != {"id", "heading", "body"} or not all(isinstance(value, str) and value for value in source.values()):
                    raise ValueError("task sources need only nonempty id, heading and body")
            if len({source["id"] for source in case["sources"]}) != len(case["sources"]):
                raise ValueError("source IDs must be unique within a case")
            grade = by_id[case["id"]]
            if not isinstance(grade["reviewCriteria"], list) or not grade["reviewCriteria"] or not all(isinstance(value, str) and value for value in grade["reviewCriteria"]):
                raise ValueError("reviewCriteria must contain nonempty checks")
            if not isinstance(grade["rubric"], dict) or set(grade["rubric"]) - {"requiredTerms", "forbiddenTerms", "requiredSourceIds", "expectedAbstention"}:
                raise ValueError("grading rubric has unknown fields")
            required = grade["rubric"].get("requiredSourceIds", [])
            if not isinstance(required, list) or not all(isinstance(value, str) for value in required) or not set(required) <= {source["id"] for source in case["sources"]}:
                raise ValueError("required source IDs must belong to the same case")
            case.update(rubric=grade["rubric"], reviewCriteria=grade["reviewCriteria"])
        binding.update(rubricsHash=sha256(grading_bytes), decisionRule=grading["decisionRule"])
    for case in cases:
        rubric = case["rubric"]
        grade_answer("", [], {**rubric, "requiredSourceHashes": [sha256(source) for source in rubric.get("requiredSourceIds", [])]})
    return corpus, binding


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
    parser.add_argument("--rubrics", type=Path, help="Separate grading file bound to the exact private task corpus")
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
    corpus, binding = load_corpus(args.corpus, args.rubrics)
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
    corpus_hash = binding["corpusHash"]
    report = {"schemaVersion":"memory-controlled-pilot-v1", "corpusHash":corpus_hash, "generatedAt":utc_now().isoformat(),
        "baseline":{"label":"legacy-direct-v1", "commit":args.baseline_commit,"assemblerHash":baseline_hash},
        "host":args.host,"model":args.model,"repetitions":args.repetitions,"plannedAnswerCalls":calls if args.answers else 0,
        "studyClass":"curated_pilot", "humanReview":"pending" if args.retain_review else "unavailable",
        "evaluationContract":binding,
        "rows":[], "reservations":[{"caseId":c['id'],"repetition":rep,"status":"pending"} for c in selected for rep in range(1,args.repetitions+1)]}
    def persist():
        report['aggregate'] = aggregate(report['rows'])
        _write_private_replace(target, json.dumps(report,indent=2)+'\n')
    persist()
    for index, reservation in enumerate(report['reservations']):
        started = time.perf_counter_ns()
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
                if args.retain_review and args.rubrics:
                    bundle = row['answerComparison']['reviewBundle']
                    path = target.parent/(target.stem+'-review')/bundle['file']
                    packet = json.loads(path.read_text())
                    packet.update(sourceEvidence=case['sources'], reviewCriteria=case['reviewCriteria'],
                                  sourceBinding={key: binding[key] for key in ('corpusHash', 'rubricsHash')})
                    content = json.dumps(packet, indent=2)+'\n'
                    _write_private_replace(path, content)
                    bundle['sha256'] = sha256(content)
                if args.empty_control:
                    control = execute_answer(args.host,args.model,case['question'],'',root/'control')
                    control['grading'] = grade_answer(control.get('answer',''),control.get('sourceIds',[]),{'expectedAbstention':True}) if control.get('status')=='completed' else {'passed':None,'status':'unavailable_answer'}
                    if 'answer' in control:
                        control['answerHash'] = sha256(control.pop('answer'))
                    row['emptyAnswerControl'] = control
                    row['emptyControlOrder'] = 'after_pair'
        row['endToEndElapsedMs'] = round((time.perf_counter_ns() - started) / 1e6, 3)
        row['refreshCost'] = None
        report['rows'].append(row)
        reservation['status'] = 'complete' if row['comparisonStatus']=='complete' and (not args.answers or (row['answerStatus']=='complete' and (not args.empty_control or row['emptyAnswerControl'].get('status')=='completed'))) else 'incomplete'
        persist()
        print(json.dumps({'caseId':case['id'],'repetition':reservation['repetition'],'retrieval':row['comparisonStatus'],'answers':row.get('answerStatus','not_requested')}),flush=True)
    return 0 if all(r['status']=='complete' for r in report['reservations']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
