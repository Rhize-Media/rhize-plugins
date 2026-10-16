"""Synthetic typed-decision data for the L3 tests: records/labels/state built from the contract fixtures.

Every object is a deep copy of a fixture shape with recomputed identities, so it validates against
typed_decisions.contract. Nothing here touches a real data root; callers pass tmp roots.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'rhize-context-manager' / 'scripts'
FIXTURES = REPO / 'tests' / 'rhize-context-manager' / 'fixtures' / 'typed-decisions'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from typed_decisions import cohorts, contract, decision_registry, records  # noqa: E402

INC = 'skill:seo-aeo-geo/seo-site-audit'
ALT1 = 'skill:seo-aeo-geo/aeo-geo-optimization'
ALT2 = 'skill:rhize-devflow/test-evidence'
SHORTLIST = [INC, ALT1, ALT2]
LAYA_REV = '55cf4c4ebb4e'
NOW = '2026-10-12T12:00:00Z'


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def sha(text) -> str:
    return hashlib.sha256(str(text).encode('utf-8')).hexdigest()


def load_cycle_module():
    path = REPO / 'evals' / 'typed-decision' / 'decision_cycle.py'
    spec = importlib.util.spec_from_file_location('decision_cycle_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def small_registry(cohort_size=20, min_labeled=10):
    registry = copy.deepcopy(decision_registry.load_registry())
    registry['decisions']['skill-fit']['gates']['promote']['cohortSize'] = cohort_size
    registry['decisions']['skill-fit']['gates']['demote']['minLabeled'] = min_labeled
    return contract.validate_registry(registry)


def probs_for(shortlist, choice, p=0.7):
    rest = (1 - p) / max(1, len(shortlist))
    out = [rest] * (len(shortlist) + 1)
    out[len(shortlist) if choice == 'none' else shortlist.index(choice)] = p
    return out


def make_record(i, *, session=None, basis='live', mode='shadow', arm='treatment', score=5.0, incumbent=INC,
                choice=ALT1, status='ok', latency=60.0, ts=None, stratum='fired', bucket='lt200', laya_revision=None,
                shortlist=None, probs=None, instrument_sha=None, emitted='auto'):
    """One valid record. `choice` is Laya's answer ('none' allowed); incumbent=None makes a router-silent backfill row."""
    rec = copy.deepcopy(fixture('records.json')['valid']['live-shadow-agree'])
    shortlist = list(shortlist if shortlist is not None else SHORTLIST)
    session_hash = sha(f'session-{i if session is None else session}')
    prompt_hash = sha(f'prompt-{i}')
    ts = ts or f'2026-10-10T{(i // 60) % 24:02d}:{i % 60:02d}:05.000Z'
    rec.update({'decisionId': f'{i:032x}', 'sessionHash': session_hash, 'promptHash': prompt_hash, 'ts': ts,
                'occurrenceKey': contract.occurrence_key(session_hash, prompt_hash, ts), 'basis': basis,
                'mode': mode, 'arm': arm, 'sourceStratum': stratum, 'promptLengthBucket': bucket,
                'shortlist': shortlist, 'incumbent': None if incumbent is None else {'skillId': incumbent, 'score': score}})
    if laya_revision:
        rec['layaRevision'] = laya_revision
    if instrument_sha:
        rec['instrumentSha256'] = instrument_sha
    if status == 'ok':
        rec['laya'] = {'status': 'ok', 'choice': choice, 'latencyMs': latency,
                       'probabilities': probs if probs is not None else probs_for(shortlist, choice), 'truncated': False}
    elif status == 'skipped':
        rec['laya'] = {'status': 'skipped', 'choice': None, 'probabilities': None, 'latencyMs': None, 'truncated': None}
        rec['criteriaSha256'] = None
    else:
        rec['laya'] = {'status': status, 'choice': None, 'probabilities': None, 'latencyMs': latency, 'truncated': False}
    if basis == 'backfill':
        rec.update({'arm': 'none', 'propensity': None, 'mode': 'shadow', 'emitted': None})
    else:
        rec['propensity'] = 0.9 if arm == 'treatment' else 0.1
        if emitted == 'auto':
            suppressed = (mode == 'cosign' and arm == 'treatment' and status == 'ok' and incumbent is not None
                          and choice != incumbent)
            rec['emitted'] = None if suppressed else incumbent
        else:
            rec['emitted'] = emitted
    policy = contract.POLICY_ADVISE if rec['mode'] == 'advise' else contract.POLICY_COSIGN
    rec.update({'policy': policy, 'policySha256': contract.policy_sha256(policy)})
    return contract.validate_record(rec)


def make_label(rec, *, acceptable, cohort_id=None, stratum='disagreement', inclusion=0.25, ambiguous=False,
               labeled_at='2026-10-11T18:00:00Z'):
    label = copy.deepcopy(fixture('labels.json')['valid']['disagreement-incumbent-wrong'])
    candidates = list(rec['shortlist'])
    acceptable = [] if ambiguous else list(acceptable)
    label.update({'decisionId': rec['decisionId'], 'occurrenceKey': rec['occurrenceKey'], 'cohortId': cohort_id,
                  'stratum': stratum, 'inclusionProbability': inclusion, 'candidates': candidates,
                  'acceptable': acceptable, 'bestSkill': acceptable[0] if acceptable else 'none',
                  'ambiguous': ambiguous, 'labeledAt': labeled_at})
    return contract.validate_label(label)


def write_records(root, recs):
    for rec in recs:
        records.append(root, 'skill-fit', 'records', rec)
    return recs


def write_labels(root, labels):
    for label in labels:
        records.append(root, 'skill-fit', 'labels', label)
    return labels


def disagreements(n, *, start=0, **kwargs):
    """n disagreement records in n distinct sessions (Laya answers ALT1, the incumbent is INC)."""
    return [make_record(start + k, **kwargs) for k in range(n)]


def label_cohort(root, reserve_event, recs_by_key, *, not_hit, ambiguous=0):
    """Label every reserved case: `ambiguous` ambiguous, then `not_hit` incumbent-wrong, the rest incumbent-right."""
    labels = []
    for index, key in enumerate(sorted(reserve_event['occurrenceKeys'])):
        rec = recs_by_key[key]
        if index < ambiguous:
            labels.append(make_label(rec, acceptable=[], ambiguous=True, cohort_id=reserve_event['cohortId']))
        elif index < ambiguous + not_hit:
            labels.append(make_label(rec, acceptable=[ALT1], cohort_id=reserve_event['cohortId']))
        else:
            labels.append(make_label(rec, acceptable=[INC], cohort_id=reserve_event['cohortId']))
    write_labels(root, labels)
    return labels


def min_pass_x(n, alpha=0.05, lam=1.0):
    """Smallest x whose CP lower bound clears the threshold."""
    threshold = cohorts.threshold_for(lam)
    for x in range(n + 1):
        if cohorts.cp_lower(x, n, alpha) > threshold:
            return x
    raise AssertionError('no passing x')


def reserve_cohort(root, registry, *, seed=1, now='2026-10-11T00:00:00Z'):
    result = cohorts.reserve(root, registry, now, seed)
    assert result['status'] == 'reserved', result
    event = cohorts.cohort_ledger(root)[result['cohortId']]['reserve']
    return result, event


def passed_cohort(root, registry, recs, *, seed=1, now='2026-10-11T00:00:00Z', eval_now='2026-10-11T06:00:00Z'):
    """Reserve, label (all incumbent-wrong except the boundary share) and evaluate a cohort that passes."""
    write_records(root, recs)
    result, event = reserve_cohort(root, registry, seed=seed, now=now)
    by_key = {r['occurrenceKey']: r for r in recs}
    label_cohort(root, event, by_key, not_hit=len(event['occurrenceKeys']) - 1)
    verdict = cohorts.evaluate(root, registry, event['cohortId'], eval_now)
    assert verdict['verdict'] == 'pass', verdict
    return event, verdict


# ---------------------------------------------------------------- generic choice records (advise decisions)

CHOICE_CANDIDATES = [{'id': 'alpha', 'criterion': 'pick alpha when the request is about alpha'},
                     {'id': 'beta', 'criterion': 'pick beta when the request is about beta'},
                     {'id': 'gamma', 'criterion': 'pick gamma otherwise'}]
CHOICE_QUESTION = 'Which option fits this request?'
CHOICE_POLICY = 'alpha|beta|gamma'
CHOICE_IDS = [c['id'] for c in CHOICE_CANDIDATES]


def choice_answer(choice, status='ok'):
    if status != 'ok':
        return {'status': status, 'choice': None, 'probabilities': None, 'latencyMs': 9.0}
    rest = 0.3 / (len(CHOICE_IDS) - 1)
    return {'status': 'ok', 'choice': choice, 'latencyMs': 5.0,
            'probabilities': {c: (0.7 if c == choice else rest) for c in CHOICE_IDS}}


def write_choice(root, decision, i, *, laya, group=None, critical=False, status='ok', text=None, snapshot=True,
                 policy=CHOICE_POLICY):
    """One advise() record (mode from the registry state at the root) with a fake Laya answer; returns the result."""
    import typed_advice
    return typed_advice.advise(decision, text or f'request {i}', CHOICE_CANDIDATES, f'key-{i}', critical_if_wrong=critical,
                               question=CHOICE_QUESTION, policy=policy, group=group or f'group-{i}',
                               files=['src/a.py'], store=root, snapshot=snapshot,
                               call=lambda *a, **k: choice_answer(laya, status))


def write_choice_label(root, decision, decision_id, label, *, ambiguous=False):
    import typed_advice
    return typed_advice._write_once(Path(root), decision, 'label', decision_id, {
        'schema': 'rhize-typed-choice-label-v1', 'decision': decision, 'decisionId': decision_id,
        'label': None if ambiguous else label, 'ambiguous': ambiguous, 'basis': 'ai_model_reviewed',
        'rubricVersion': 'choice-rubric-v1', 'annotators': ['claude-sonnet-5-5', 'gpt-5.6-sol'], 'reviewer': None,
        'evidenceSha256': sha(decision_id), 'redactor': sha('r'), 'labeledAt': NOW})
