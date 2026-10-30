#!/usr/bin/env python3
"""Bounded local research loop for typed software-development decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# Laya requests carry redacted request text: the only transport is the loopback-IP-only, no-redirect, no-proxy one.
_SCRIPTS = str(Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts')
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from typed_advice import post_local
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from measurement import summarize


PILOT_COHORT = "workflow-pilot-v2"
PILOT_COHORT_V3 = "workflow-pilot-v3"  # one choice question 'route'; replayed from sealed request snapshots
PILOT_COHORTS = frozenset({PILOT_COHORT, PILOT_COHORT_V3})
# Model-reviewed labels are accepted only when an operator policy exported them; rows record which.
LABEL_BASES = frozenset({"human_adjudicated", "ai_model_reviewed"})
METRICS_SCHEMA = "rhize-typed-research-metrics-v2"


def decode_route(row, result, threshold):
    # A single decoder is shared with live shadow collection.
    scripts = str(Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from pilot_routing import decode_scores
    scores = {}
    for index, choice in enumerate(row['candidate_ids']):
        answer = result['answers'][f'c{index}']
        if answer.get('type') != 'noul':
            raise ValueError('provider answer type mismatch')
        scores[choice] = answer.get('noul')
    return decode_scores(scores, abstain_below=threshold, exclusions=row['state'].get('exclusions', []))


def decode_route_v3(row, result, threshold):
    """Decode the single v3 choice answer with the shared decoder; abstention uses the top probability."""
    scripts = str(Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from pilot_routing import decode_choice
    answer = result['answers']['route']
    if answer.get('type') != 'choice':
        raise ValueError('provider answer type mismatch')
    probabilities = answer.get('probabilities')
    if not isinstance(probabilities, dict) or set(probabilities) != set(row['candidate_ids']):
        raise ValueError('invalid choice probabilities')
    return decode_choice(probabilities, abstain_below=threshold, exclusions=row['state'].get('exclusions', [])), probabilities


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
            raise ValueError("every case requires an adjudicated label")
        if row.get("label_basis", "human_adjudicated") not in LABEL_BASES:
            raise ValueError("unsupported label basis")
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
        questions_for(row, {})
        if not isinstance(row.get("state"), (str, dict, list)):
            raise ValueError("state must be a string, object, or array")
    cohorts = {row.get('cohort_version') for row in rows}
    if cohorts & PILOT_COHORTS:
        if len(cohorts) != 1:
            raise ValueError('mixed pilot cohort')
        v3 = PILOT_COHORT_V3 in cohorts
        for row in rows:
            if (not isinstance(row.get('state'), dict)
                    or row.get('candidate_ids') != ['content', 'general', 'none']
                    or row.get('routing_choice') not in row['candidate_ids']
                    or row.get('arm_a_choice') not in [None, *row['candidate_ids']]):
                raise ValueError('invalid pilot routing label')
            if v3:
                if (set(row['questions']) != {'route'} or row['questions']['route'].get('type') != 'choice'
                        or row['labels'] != {'route': row['routing_choice']}):
                    raise ValueError('invalid pilot routing label')
            elif row['labels'] != {f'c{i}': choice == row['routing_choice']
                                   for i, choice in enumerate(row['candidate_ids'])}:
                raise ValueError('invalid pilot routing label')
            if row['routing_choice'] == 'content' and 'content_creation' in row['state'].get('exclusions', []):
                raise ValueError('label_contradicts_exclusions')
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


def local_call(base_url: str, request: dict, timeout: float = 20, *, admission_wait_ms: int = 0) -> tuple[dict, float]:
    result, latency = post_local(base_url, "/v1/systemone", request, timeout, admission_wait_ms=admission_wait_ms)
    if not isinstance(result.get("routing"), dict) or result["routing"].get("model") != request["model"]:
        raise ValueError("local provider routed a different checkpoint")
    if set(result.get("answers", {})) != set(request["questions"]):
        raise ValueError("provider answers do not match questions")
    return result, latency


def questions_for(row: dict, candidate: dict) -> dict:
    """Keep explicit menu order across canonical JSON storage without changing the provider schema."""
    orders = row.get('candidate_orders', {})
    if not isinstance(orders, dict) or set(orders) - set(row['questions']):
        raise ValueError('invalid candidate orders')
    questions = {}
    for name, question in row['questions'].items():
        value = {**question, 'instructions': candidate.get('instructions', {}).get(name, question['instructions'])}
        if name in orders:
            order = orders[name]
            if (question['type'] != 'choice' or not isinstance(order, list)
                    or any(not isinstance(k, str) for k in order)
                    or len(order) != len(question['criteria']) or set(order) != set(question['criteria'])):
                raise ValueError('invalid candidate order')
            value['criteria'] = {k: question['criteria'][k] for k in order}
        questions[name] = value
    return questions


def tuning_majority(rows: list[dict]) -> dict:
    from collections import Counter
    counts = defaultdict(Counter)
    for row in rows:
        labels = {'route': row['routing_choice']} if row.get('cohort_version') in PILOT_COHORTS else row['labels']
        for name, label in labels.items():
            counts[f"{row['decision_type']}:{name}"][json.dumps(label)] += 1
    return {'tuning_sha256': digest(rows), 'predictions': {
        key: json.loads(min(values, key=lambda label: (-values[label], label))) for key, values in counts.items()}}


def evaluate(rows: list[dict], candidate: dict, call, *, baseline: dict | None = None) -> dict:
    validate_candidate(candidate, rows)
    totals = defaultdict(lambda: {"count": 0, "correct": 0, "abstained": 0, "critical_misses": 0,
                                  "critical_false_negatives": 0, "brier_sum": 0.0, "brier_count": 0})
    critical_strata = {f"{row['decision_type']}:{row['stratum']}" for row in rows
                       if row['stratum'].startswith('critical')}
    latencies = []
    samples = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    for row in rows:
        def record(name, label, prediction, raw_prediction, confidence, cardinality):
            samples.append({'decision': row['decision_type'], 'question': name, 'label': label,
                            'prediction': prediction, 'raw_prediction': raw_prediction, 'confidence': confidence,
                            'cardinality': cardinality, 'group': row['group_id'],
                            'label_basis': row.get('label_basis', 'unspecified')})
        questions = questions_for(row, candidate)
        result, latency = call({"state": row["state"], "questions": questions, "model": candidate["model"]})
        latencies.append(latency)
        measured_usage = result.get("usage", {})
        for key in usage:
            if type(measured_usage.get(key)) is not int or measured_usage[key] < 0:
                usage[key] = None
            elif usage[key] is not None:
                usage[key] += measured_usage[key]
        if row.get('cohort_version') == PILOT_COHORT:
            decoded = decode_route(row, result, candidate.get('abstain_below', 0.0))
            record('route', row['routing_choice'], decoded['choice'], decoded['ranking'][0]['candidateId'], None, 3)
            score = totals[f"{row['decision_type']}:{row['stratum']}"]
            score['count'] += 1
            if decoded['choice'] is None:
                score['abstained'] += 1
                score['critical_misses'] += int(row['stratum'].startswith('critical'))
            elif decoded['choice'] == row['routing_choice']:
                score['correct'] += 1
            elif row['stratum'].startswith('critical'):
                score['critical_misses'] += 1
            # Independent relevance values are not calibrated route probabilities.
            continue
        if row.get('cohort_version') == PILOT_COHORT_V3:
            decoded, probabilities = decode_route_v3(row, result, candidate.get('abstain_below', 0.0))
            record('route', row['routing_choice'], decoded['choice'], decoded['ranking'][0]['candidateId'],
                   decoded['ranking'][0]['score'], len(probabilities))
            score = totals[f"{row['decision_type']}:{row['stratum']}"]
            score['count'] += 1
            score['brier_sum'] += sum((value - int(name == row['routing_choice'])) ** 2
                                      for name, value in probabilities.items()) / len(probabilities)
            score['brier_count'] += 1
            if decoded['choice'] is None:
                score['abstained'] += 1
                score['critical_misses'] += int(row['stratum'].startswith('critical'))
            elif decoded['choice'] == row['routing_choice']:
                score['correct'] += 1
            elif row['stratum'].startswith('critical'):
                score['critical_misses'] += 1
            continue
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
                record(name, label, None if confidence < candidate.get('abstain_below', 0.0) else prediction,
                       prediction, confidence, len(probabilities))
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
                record(name, label, None if confidence < candidate.get('abstain_below', 0.0) else probability >= .5,
                       probability >= .5, confidence, 2)
                if confidence < candidate.get("abstain_below", 0.0):
                    score["abstained"] += 1
                elif (probability >= 0.5) == label:
                    score["correct"] += 1
                elif label and row["stratum"].startswith("critical"):
                    score["critical_misses"] += 1
                    score["critical_false_negatives"] += 1
    # A missed critical decision is not evidence that an unsafe action was executed.
    for key, score in totals.items():
        critical = key in critical_strata
        score['critical_misses'] = score['count'] - score['correct'] if critical else 0
        score['critical_abstentions'] = score['abstained'] if critical else 0
        score['critical_wrong_answers'] = score['critical_misses'] - score['critical_abstentions']
    count = sum(item["count"] for item in totals.values())
    correct = sum(item["correct"] for item in totals.values())
    abstained = sum(item["abstained"] for item in totals.values())
    critical_misses = sum(item["critical_misses"] for item in totals.values())
    brier_sum = sum(item["brier_sum"] for item in totals.values())
    brier_count = sum(item["brier_count"] for item in totals.values())
    latencies.sort()
    return {"metrics_schema": METRICS_SCHEMA, "count": count,
            "independent_groups": len({row['group_id'] for row in rows}),
            "unit": "routing_case" if all(row.get('cohort_version') in PILOT_COHORTS for row in rows) else "question",
            "accuracy": correct / count, "abstention_rate": abstained / count,
            "critical_misses": critical_misses, "by_stratum": dict(sorted(totals.items())),
            "critical_abstentions": sum(s['critical_abstentions'] for s in totals.values()),
            "critical_wrong_answers": sum(s['critical_wrong_answers'] for s in totals.values()),
            "critical_false_negatives": sum(s['critical_false_negatives'] for s in totals.values()),
            "unsafe_actions": None,
            "diagnostics": summarize(samples),
            "majority_baseline": ({'basis': 'frozen_tuning', 'tuning_sha256': baseline['tuning_sha256'],
                                   'accuracy': sum(baseline['predictions'][f"{s['decision']}:{s['question']}"] == s['label']
                                                   for s in samples) / len(samples)}
                                  if baseline and all(f"{s['decision']}:{s['question']}" in baseline['predictions']
                                                      for s in samples) else 'unavailable'),
            "brier_convention": "choice mean squared error across candidates; scalar Noul squared error; v2 relevance excluded",
            "brier_mean": brier_sum / brier_count if brier_count else None,
            "latency_ms_p50": latencies[len(latencies) // 2],
            "latency_ms_p95": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
            "usage": usage}


def predict(rows: list[dict], candidate: dict, call) -> dict:
    """Per-case v3 routing predictions ({case_id: choice or None when abstaining}) for promotion scoring."""
    validate_candidate(candidate, rows)
    predictions = {}
    for row in rows:
        if row.get('cohort_version') != PILOT_COHORT_V3:
            raise ValueError('predict supports workflow-pilot-v3 cases only')
        questions = questions_for(row, candidate)
        result, _ = call({"state": row["state"], "questions": questions, "model": candidate["model"]})
        decoded, _ = decode_route_v3(row, result, candidate.get('abstain_below', 0.0))
        predictions[row['case_id']] = decoded['choice']
    return predictions


def arm_a_metrics(rows: list[dict]) -> dict | str:
    """Score recorded incumbent outcomes; absence stays unavailable, never zero."""
    if rows and all(row.get('cohort_version') in PILOT_COHORTS for row in rows):
        if any(row.get('arm_a_choice') is None for row in rows):
            return 'unavailable'
        by_stratum = defaultdict(lambda: {'count': 0, 'correct': 0, 'critical_misses': 0})
        for row in rows:
            score = by_stratum[f"{row['decision_type']}:{row['stratum']}"]
            score['count'] += 1
            correct = row['arm_a_choice'] == row['routing_choice']
            score['correct'] += int(correct)
            score['critical_misses'] += int(not correct and row['stratum'].startswith('critical'))
        return {'count': len(rows), 'accuracy': sum(s['correct'] for s in by_stratum.values()) / len(rows),
                'critical_misses': sum(s['critical_misses'] for s in by_stratum.values()),
                'by_stratum': dict(sorted(by_stratum.items())), 'unit': 'routing_case'}
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


def check_holdout_authority(ledger: list[dict], dataset_hash: str, seed_hash: str, candidate_hash: str,
                            metrics_schema: str | None = None) -> None:
    if not any(row.get("dataset_sha256") == dataset_hash and row.get("candidate_sha256") == candidate_hash
               and row.get("seed_sha256") == seed_hash and row.get("status") == "keep"
               and (metrics_schema is None or row.get('metrics_schema') == metrics_schema) for row in ledger):
        raise ValueError("candidate must be frozen from a recorded development keep")
    if any(row.get("dataset_sha256") == dataset_hash and row.get("status") == "holdout" for row in ledger):
        raise ValueError("locked holdout was already used for this dataset")


def prepare_corpus(rows: list[dict], seed: str, out_dir: Path, *, split_assignments=None,
                   names=('train', 'validation', 'holdout')) -> dict:
    """`names` lets a caller materialize tuning splits only; promotion rows never pass through here."""
    if split_assignments is None:
        splits = partition(rows, seed)
    else:
        if (set(split_assignments) != {row['group_id'] for row in rows}
                or set(split_assignments.values()) - set(names)):
            raise ValueError('invalid frozen split assignments')
        splits = {name: [row for row in rows if split_assignments[row['group_id']] == name] for name in names}
        seen = set()
        for values in splits.values():
            keys = {key for row in values for key in row.get('grouping_keys', [])}
            if seen & keys:
                raise ValueError('duplicate identity crosses split')
            seen.update(keys)
    if any(not values for values in splits.values()):
        raise ValueError("train, validation and holdout each need at least one task group")
    type_counts = {kind: sum(row["decision_type"] == kind for row in rows) for kind in {row["decision_type"] for row in rows}}
    holdout_counts = {kind: sum(row["decision_type"] == kind for row in splits.get("holdout", [])) for kind in type_counts}
    # Informational only: advise eligibility is decided by the typed_promotion baseline gate on a reserved promotion cohort.
    legacy_release_gate_met = all(count >= 200 and holdout_counts[kind] >= 50 and holdout_counts[kind] / count >= 0.25
                                  for kind, count in type_counts.items())
    manifest = {"schema": "rhize-typed-research-corpus-v1", "corpus_sha256": digest(rows),
                "seed_sha256": digest(seed), "split_sha256": {name: digest(values) for name, values in splits.items()},
                "split_counts": {name: len(values) for name, values in splits.items()},
                "type_counts": type_counts, "release_eligible": False,
                "legacy_release_gate_met": legacy_release_gate_met}
    if rows and all(row.get('cohort_version') == PILOT_COHORT for row in rows):
        manifest.update(cohort_version=PILOT_COHORT, normalization_version='workflow-input-v2',
                        holdout_grouping_keys=sorted({key for row in splits['holdout'] for key in row['grouping_keys']}))
    elif rows and all(row.get('cohort_version') == PILOT_COHORT_V3 for row in rows):
        manifest.update(cohort_version=PILOT_COHORT_V3, normalization_version='workflow-input-v3')
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
        train_keys = {key for row in splits['train'] for key in row.get('grouping_keys', [])}
        validation_keys = {key for row in splits['validation'] for key in row.get('grouping_keys', [])}
        if train_keys & validation_keys:
            raise ValueError('duplicate identity crosses train and validation')
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
    baseline = tuning_majority(splits['train']) if args.phase == 'search' else next((
        row.get('tuning_baseline') for row in reversed(ledger)
        if row.get('dataset_sha256') == dataset_hash and row.get('seed_sha256') == seed_hash
        and row.get('candidate_sha256') == digest(candidates[0]) and row.get('status') == 'keep'
        and row.get('metrics_schema') == METRICS_SCHEMA), None)
    if args.phase == "holdout":
        frozen = digest(candidates[0])
        if args.frozen_candidate_sha256 != frozen:
            raise ValueError("frozen candidate hash mismatch")
        check_holdout_authority(ledger, dataset_hash, seed_hash, frozen, METRICS_SCHEMA)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    prior = [entry for entry in ledger if entry.get("dataset_sha256") == dataset_hash
             and entry.get("seed_sha256") == seed_hash and entry.get("status") == "keep"
             and entry.get('metrics_schema') == METRICS_SCHEMA]
    best = min(((entry["validation"]["critical_misses"], -entry["validation"]["accuracy"],
                 entry["validation"]["abstention_rate"]) for entry in prior), default=None)
    for candidate in candidates:
        validate_candidate(candidate, rows)
        if args.phase == "search" and any(entry.get("candidate_sha256") == digest(candidate)
                                          and entry.get("dataset_sha256") == dataset_hash
                                          and entry.get("seed_sha256") == seed_hash
                                          and entry.get('metrics_schema') == METRICS_SCHEMA for entry in ledger):
            raise ValueError("candidate already evaluated on this dataset and split")
        if args.phase == "search":
            train = evaluate(splits["train"], candidate, lambda request: local_call(args.base_url, request, admission_wait_ms=2000), baseline=baseline)
            validation = evaluate(splits["validation"], candidate, lambda request: local_call(args.base_url, request, admission_wait_ms=2000), baseline=baseline)
            key = (validation["critical_misses"], -validation["accuracy"], validation["abstention_rate"])
            keep = best is None or key < best
            if keep:
                best = key
            status = "keep" if keep else "discard"
            holdout = "locked"
            arm_a = {"train": arm_a_metrics(splits["train"]), "validation": arm_a_metrics(splits["validation"])}
        else:
            train = validation = None
            holdout = evaluate(splits["holdout"], candidate, lambda request: local_call(args.base_url, request), baseline=baseline)
            arm_a = {"holdout": arm_a_metrics(splits["holdout"])}
            status = "holdout"
        entry = {"schema": "rhize-typed-research-v1", "metrics_schema": METRICS_SCHEMA,
                 "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 "measurement_sha256": hashlib.sha256(Path(__file__).with_name('measurement.py').read_bytes()).hexdigest(),
                 "tuning_baseline": baseline,
                 "at": time.time(), "dataset_sha256": dataset_hash,
                 "seed_sha256": seed_hash, "release_eligible": manifest["release_eligible"],
                 "candidate_sha256": digest(candidate), "candidate_id": candidate["id"], "model": candidate["model"],
                 "status": status, "split_counts": manifest["split_counts"],
                 "train": train, "validation": validation, "holdout": holdout, "arm_a": arm_a,
                 "arm_a_coverage": {name: {"recorded": sum(row.get('arm_a_choice') is not None for row in values),
                                           "total": len(values)}
                                    for name, values in splits.items()}
                 if manifest.get('cohort_version') in PILOT_COHORTS else None}
        with args.ledger.open("a") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        print(json.dumps({"candidate_id": candidate["id"], "candidate_sha256": digest(candidate),
                          "status": status, "validation": validation, "holdout": holdout}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
