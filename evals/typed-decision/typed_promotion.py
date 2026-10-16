#!/usr/bin/env python3
"""Earned-mode promotion check for typed decisions (stdlib only, Python 3.9 compatible).

A frozen candidate config is evaluated once per cycle on a promotion split the search never saw.
It earns `advise` only if it beats the always-baseline majority guess with statistical margin, covers
every non-trivial class, and makes no critical miss. State lives in modes.json and is keyed by config:
a different config starts from `shadow`. S1 writes and reports only; nothing consumes the mode yet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path

SCHEMA = 'rhize-typed-modes-v1'
DECISION_TYPE = 'workflow_fit'
Z_ONE_SIDED_90 = 1.2816
PRIOR_SHARE_FLOOR = 0.10      # classes below this share of the tuning split are not scored
MIN_CLASS_CASES = 3
MIN_CLASS_RECALL = 0.5
MIN_NEW_CASES = 10            # a re-attempt of the same config needs this many unseen promotion cases
DEMOTE_AFTER_CYCLES = 2


def sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def wilson_lower(k, n, z=Z_ONE_SIDED_90):
    """One-sided 90% Wilson lower bound for a binomial proportion."""
    if n <= 0:
        return 0.0
    p = k / n
    z2 = z * z
    centre = p + z2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (centre - margin) / (1 + z2 / n)


def config_sha256(candidate, normalization_version, candidate_ids, questions):
    """Digest of the frozen candidate; the display id is deliberately excluded.

    `questions` is a promotion row's question set; the candidate's instruction overrides are applied on top,
    so the digest covers the effective wording and criteria and a wording edit resets earned mode.
    """
    effective = {name: {**question, 'instructions': candidate.get('instructions', {}).get(name, question['instructions'])}
                 for name, question in questions.items()}
    return sha256({'model': candidate['model'], 'questions': effective,
                   'instructions': candidate.get('instructions', {}),
                   'abstain_below': candidate.get('abstain_below', 0.0),
                   'normalization_version': normalization_version, 'candidate_ids': list(candidate_ids)})


def evaluate(promotion_cases, predictions, baseline_choice, prior):
    """Score predictions ({case_id: choice or None}) on promotion cases and decide promotability.

    prior is the tuning split's class distribution (counts or shares); None predictions are abstentions
    and count as wrong. A miss on a stratum starting with 'critical_' is a critical miss.
    """
    total = float(sum(prior.values())) or 1.0
    shares = {name: value / total for name, value in prior.items()}
    scored = sorted(name for name, share in shares.items() if share >= PRIOR_SHARE_FLOOR)
    classes = {name: {'count': 0, 'correct': 0} for name in set(scored) | {case['routing_choice'] for case in promotion_cases}}
    correct = abstentions = critical_misses = 0
    for case in promotion_cases:
        guess = predictions.get(case['case_id'])
        hit = guess is not None and guess == case['routing_choice']
        classes[case['routing_choice']]['count'] += 1
        classes[case['routing_choice']]['correct'] += int(hit)
        correct += int(hit)
        abstentions += int(guess is None)
        critical_misses += int(not hit and str(case.get('stratum', '')).startswith('critical_'))
    n = len(promotion_cases)
    baseline_correct = sum(case['routing_choice'] == baseline_choice for case in promotion_cases)
    present = [name for name in scored if classes[name]['count'] > 0]
    recall = {name: (item['correct'] / item['count'] if item['count'] else None) for name, item in classes.items()}
    balanced = sum(recall[name] for name in present) / len(present) if present else 0.0
    baseline_balanced = sum(float(name == baseline_choice) for name in present) / len(present) if present else 0.0
    lower = wilson_lower(correct, n)
    accuracy = correct / n if n else 0.0
    baseline_accuracy = baseline_correct / n if n else 0.0
    blockers = []
    if n < 1:
        blockers.append('no_promotion_cases')
    if not lower > baseline_accuracy:
        blockers.append('wilson_lower_not_above_baseline')
    if not balanced > baseline_balanced:
        blockers.append('balanced_accuracy_not_above_baseline')
    for name in scored:
        if classes[name]['count'] < MIN_CLASS_CASES:
            blockers.append('class_coverage:' + name)
        elif recall[name] < MIN_CLASS_RECALL:
            blockers.append('class_recall:' + name)
    if critical_misses:
        blockers.append('critical_miss')
    return {'n': n, 'correct': correct, 'accuracy': accuracy, 'wilsonLower': lower,
            'baselineChoice': baseline_choice, 'baselineAccuracy': baseline_accuracy,
            'balancedAccuracy': balanced, 'baselineBalancedAccuracy': baseline_balanced,
            'scoredClasses': scored, 'priorShares': dict(sorted(shares.items())),
            'classes': {name: {'count': item['count'], 'correct': item['correct'], 'recall': recall[name]}
                        for name, item in sorted(classes.items())},
            'criticalMisses': critical_misses, 'abstentions': abstentions,
            'promote': not blockers, 'blockers': blockers}


def modes_path(root=None):
    base = root or os.environ.get('RHIZE_TYPED_DECISIONS_ROOT') or '~/.local/share/rhize/typed-decisions'
    return Path(base).expanduser() / 'modes.json'


def load_modes(root=None):
    path = modes_path(root)
    if path.is_symlink():
        raise ValueError('symlink modes file refused')
    if not path.is_file():
        return {'schema': SCHEMA, 'decisionTypes': {}}
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get('schema') != SCHEMA or not isinstance(value.get('decisionTypes'), dict):
        raise ValueError('invalid typed modes file')
    return value


def write_modes(value, root=None):
    """Atomic private write: temp file in the same directory, fsync, os.replace; dir 0700, file 0600."""
    path = modes_path(root)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('symlink modes path refused')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    handle, temporary = tempfile.mkstemp(prefix='.modes-', dir=path.parent)
    try:
        with os.fdopen(handle, 'w') as stream:
            stream.write(json.dumps(value, sort_keys=True, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def _id_hashes(case_ids):
    return sorted({hashlib.sha256(str(case_id).encode()).hexdigest() for case_id in case_ids})


def check_novelty(case_ids, config_sha, root=None):
    """(ok, new_case_count): a repeat attempt of the same config needs >= MIN_NEW_CASES unseen cases."""
    entry = load_modes(root)['decisionTypes'].get(DECISION_TYPE)
    previous = (entry or {}).get('lastAttempt') if entry and entry.get('configSha256') == config_sha else None
    if not previous:
        return True, len(set(case_ids))
    seen = set(previous.get('promotionCaseIdHashes', []))
    new = len(set(_id_hashes(case_ids)) - seen)
    return new >= MIN_NEW_CASES, new


def update(promotion_cases, predictions, baseline_choice, prior, config_sha, root=None, now=None):
    """Evaluate, apply the earned-mode rules and persist. Returns the decision, or a `held` result
    that leaves state untouched when the same config has too few new promotion cases."""
    case_ids = [case['case_id'] for case in promotion_cases]
    ok, new = check_novelty(case_ids, config_sha, root)
    if not ok:
        return {'status': 'held', 'reason': 'insufficient_new_promotion_cases', 'newCases': new,
                'required': MIN_NEW_CASES}
    modes = load_modes(root)
    entry = modes['decisionTypes'].get(DECISION_TYPE)
    if not entry or entry.get('configSha256') != config_sha:
        entry = {'earnedMode': 'shadow', 'configSha256': config_sha, 'belowBaselineStreak': 0}
    previous_mode = entry['earnedMode']
    metrics = evaluate(promotion_cases, predictions, baseline_choice, prior)
    streak = entry.get('belowBaselineStreak', 0)
    mode, reason = previous_mode, None
    if metrics['criticalMisses']:
        mode, streak, reason = 'shadow', 0, 'critical_miss'
    elif metrics['promote']:
        mode, streak = 'advise', 0
    else:
        streak = streak + 1 if metrics['accuracy'] < metrics['baselineAccuracy'] else 0
        if streak >= DEMOTE_AFTER_CYCLES and mode == 'advise':
            mode, streak, reason = 'shadow', 0, 'below_baseline_two_cycles'
    attempt = {**metrics, 'promotionCaseIds': sha256(sorted(case_ids)),
               'promotionCaseIdHashes': _id_hashes(case_ids), 'newCases': new}
    modes['decisionTypes'][DECISION_TYPE] = {
        'earnedMode': mode, 'configSha256': config_sha, 'lastAttempt': attempt,
        'belowBaselineStreak': streak, 'updatedAt': now if now is not None else time.time()}
    write_modes(modes, root)
    return {'status': 'updated', 'earnedMode': mode, 'previousMode': previous_mode,
            'promoted': mode == 'advise' and previous_mode != 'advise',
            'demoted': previous_mode == 'advise' and mode != 'advise', 'demotionReason': reason,
            'releaseEligible': mode == 'advise', 'belowBaselineStreak': streak, 'metrics': metrics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    status = sub.add_parser('status')
    status.add_argument('--root', help='override the typed-decisions state directory')
    args = parser.parse_args()
    print(json.dumps(load_modes(args.root), sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
