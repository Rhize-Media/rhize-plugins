#!/usr/bin/env python3
"""Run one bounded development search when a reviewed workflow corpus changes.

Never consumes holdout, labels cases, changes a live candidate, or runs an agent.
"""
from __future__ import annotations
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'rhize-context-manager/scripts'))
from decision_pilot import export_cases, inventory, DEFAULT_ROOT, read_json, locked_update, digest


def candidates():
    result = [{'id': 'baseline', 'model': 'typed-decisions', 'instructions': {}, 'abstain_below': 0.0}]
    templates = [
        {},
        {f'c{i}': {'content': 'Is this specifically a RHIZE resource article task? A mention of research alone is insufficient.',
                  'general': 'Does this task call for an existing repeatable executable workflow rather than a simple explanation?',
                  'none': 'Is there insufficient evidence of a suitable executable workflow? Prefer uncertainty to inventing a match.'}[choice]
         for i, choice in enumerate(('content', 'general', 'none'))}]
    for wording, instructions in enumerate(templates):
        for threshold in (.65, .8):
            result.append({'id': f'wording-{wording}-threshold-{threshold}', 'model': 'typed-decisions',
                           'instructions': instructions, 'abstain_below': threshold})
    return result


def private_write(path, value):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)


def cycle(root, receipts, research_root, minimum=200, deadline=180, run=subprocess.run):
    if minimum < 20 or minimum > 10000 or not 1 <= deadline <= 1800:
        raise ValueError('invalid research bounds')
    labels = inventory(root / 'labels')
    if len(labels) < minimum:
        return {'status': 'held', 'reason': 'insufficient_human_labels', 'labels': len(labels), 'required': minimum}
    research_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if research_root.is_symlink() or root.is_symlink():
        raise ValueError('symlink research root refused')
    # Same lock as background inference: live pending observations remain durable.
    fd = os.open(root / 'worker.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'held', 'reason': 'inference_busy'}
        evaluator = Path(__file__).with_name('research.py')
        evaluator_hash = digest(evaluator.read_bytes())
        key = digest(json.dumps({'labels': labels, 'candidates': candidates(), 'evaluator': evaluator_hash,
                                 'coordinator': digest(Path(__file__).read_bytes())}, sort_keys=True))
        run_dir = research_root / key
        if run_dir.exists():
            status = run_dir / 'status.json'
            return {'status': 'unchanged', 'previous': read_json(status) if status.is_file() else {'status': 'interrupted'}, 'runId': key}
        run_dir.mkdir(mode=0o700)
        state = {'status': 'started', 'runId': key, 'evaluatorSha256': evaluator_hash, 'at': time.time()}
        def finish(value):
            private_write(run_dir / 'status.json', value)
            return value
        try:
            exported = export_cases(root, receipts, run_dir / 'cases.jsonl')
            if exported['status'] != 'exported':
                return finish({**state, 'status': 'held', 'reason': exported['reason']})
            if exported['count'] < minimum:
                return finish({**state, 'status': 'held', 'reason': 'insufficient_bound_labels', 'labels': exported['count']})
            # Stable group split across successive corpora: held-out groups never become training cases.
            spec = importlib.util.spec_from_file_location('typed_research', evaluator)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            rows = module.read_jsonl(run_dir / 'cases.jsonl')
            manifest = module.prepare_corpus(rows, 'workflow-pilot-v1', run_dir / 'split')
            count = manifest['split_counts']['train'] + manifest['split_counts']['validation']
            options = candidates()
            if count * len(options) > 2400:
                return finish({**state, 'status': 'held', 'reason': 'request_budget_exceeded', 'requests': count * len(options)})
            private_write(run_dir / 'candidates.json', options)
            command = [sys.executable, str(evaluator), '--phase', 'search', '--manifest', str(run_dir / 'split/manifest.json'),
                       '--train', str(run_dir / 'split/train.jsonl'), '--validation', str(run_dir / 'split/validation.jsonl'),
                       '--candidates', str(run_dir / 'candidates.json'), '--ledger', str(run_dir / 'ledger.jsonl')]
            started = time.monotonic()
            completed = run(command, capture_output=True, text=True, timeout=deadline)
            if completed.returncode:
                return finish({**state, 'status': 'failed', 'reason': 'evaluator_failed', 'exitCode': completed.returncode})
            if digest(evaluator.read_bytes()) != evaluator_hash:
                raise ValueError('evaluator changed during search')
            ledger = module.read_ledger(run_dir / 'ledger.jsonl')
            kept = [row for row in ledger if row['status'] == 'keep']
            if not kept:
                raise ValueError('no kept candidate receipt')
            winner = kept[-1]
            selected = next(c for c in options if module.digest(c) == winner['candidate_sha256'])
            private_write(run_dir / 'frozen-candidate.json', [selected])
            return finish({**state, 'status': 'review_required', 'candidateId': selected['id'],
                           'candidateSha256': winner['candidate_sha256'], 'corpusSha256': exported['sha256'],
                           'releaseEligible': manifest['release_eligible'], 'holdout': 'not_run', 'promotion': 'not_performed',
                           'wallMs': round((time.monotonic() - started) * 1000)})
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            return finish({**state, 'status': 'failed', 'reason': type(exc).__name__})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT / 'pilot')
    ap.add_argument('--receipts', type=Path, default=DEFAULT_ROOT / 'receipts')
    ap.add_argument('--research-root', type=Path, required=True)
    ap.add_argument('--minimum-labels', type=int, default=200)
    ap.add_argument('--deadline-seconds', type=int, default=180)
    args = ap.parse_args()
    result = cycle(args.root, args.receipts, args.research_root, args.minimum_labels, args.deadline_seconds)
    print(json.dumps(result, sort_keys=True))
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
