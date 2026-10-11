#!/usr/bin/env python3
"""Regenerate the typed-decision contract fixtures (coordinator-owned).

    python3 tests/rhize-context-manager/fixtures/typed-decisions/make_fixtures.py

Expected values come from the Python reference (scripts/typed_decisions/) except the lexical
shortlist, whose reference is route-core.js (computed with node). The Node test
tests/skill-map/test_typed_decision_contract.js asserts byte-for-byte agreement, so any drift
between the two implementations fails CI. Never hand-edit the generated JSON.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / 'rhize-context-manager' / 'scripts'))

from typed_decisions import contract, instrument  # noqa: E402


def h(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def dump(name: str, value) -> None:
    (HERE / name).write_text(json.dumps(value, indent=1, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')


# ------------------------------------------------------------------ instrument requests
WORDS = ('deploy the nextjs site and check the sanity schema before we publish the release notes '
         'for the client tomorrow morning ')
REQUEST_CASES = [
    ('basic', 'Run an SEO audit for the Rhize homepage and summarize the top issues.', [
        {'skillId': 'skill:seo-aeo-geo/seo-site-audit', 'description': 'Full technical SEO audit of a site.'},
        {'skillId': 'skill:seo-aeo-geo/aeo-geo-optimization', 'description': 'Optimize content for AI answer engines.'},
        {'skillId': 'skill:rhize-devflow/test-evidence', 'description': 'Collect test evidence.'}]),
    ('single-null-description', 'write tests', [{'skillId': 'skill:rhize-devflow/test-evidence', 'description': None}]),
    ('five-long-descriptions', 'plan the sanity schema migration', [
        {'skillId': f'skill:rhize-devflow/skill-{i}',
         'description': ('Line one\twith\ttabs\n\nand   many    spaces ' * 8) + f' end {i}'} for i in range(5)]),
    ('long-prompt-whitespace-cut', (WORDS * 20), [
        {'skillId': 'skill:rhize-devflow/sanity-development', 'description': 'Sanity Studio development.'},
        {'skillId': 'skill:claude-plugins-official/vercel/vercel-functions', 'description': 'Vercel functions.'}]),
    ('long-prompt-no-whitespace', 'x' * 1300, [
        {'skillId': 'skill:rhize-devflow/sanity-development', 'description': 'Sanity Studio development.'}]),
    ('unicode-astral-combining', ('héllo wörld 🚀 é ' * 70) + '🚀' * 30, [
        {'skillId': 'skill:obsidian-second-brain/defuddle', 'description': 'Clip 🌐 web pages — café notes.'},
        {'skillId': 'skill:rhize-tasks/task-planner', 'description': '  \t  '}]),
    ('exact-limit', 'a' * 1200, [{'skillId': 'skill:rhize-ops/ops-x', 'description': 'd'}]),
    ('third-party-deep-id', 'clean up env vars on vercel', [
        {'skillId': 'skill:claude-plugins-official/vercel/env-vars', 'description': 'Manage Vercel env vars.'}]),
    ('trailing-whitespace-in-window', ('word ' * 239) + 'tail' + ' ' * 50 + 'z' * 100, [
        {'skillId': 'skill:rhize-ops/ops-y', 'description': 'y'}]),
]
INVALID_REQUEST_CASES = [
    ('no-candidates', 'p', []),
    ('six-candidates', 'p', [{'skillId': f'skill:a/s{i}', 'description': 'd'} for i in range(6)]),
    ('duplicate', 'p', [{'skillId': 'skill:a/s', 'description': 'd'}, {'skillId': 'skill:a/s', 'description': 'e'}]),
    ('bad-id', 'p', [{'skillId': 'command:a/s', 'description': 'd'}]),
    ('extra-key', 'p', [{'skillId': 'skill:a/s', 'description': 'd', 'score': 3}]),
]


def request_fixture():
    cases = []
    for name, prompt, candidates in REQUEST_CASES:
        built = instrument.build_choice_request(prompt, candidates)
        cases.append({'name': name, 'prompt': prompt, 'candidates': candidates, 'expected': {
            'canonicalRequest': instrument.canonical_json(built['request']), 'keyMap': built['keyMap'],
            'truncated': built['truncated'], 'promptLengthBucket': built['promptLengthBucket'],
            'criteriaSha256': built['criteriaSha256'], 'instrumentSha256': built['instrumentSha256']}})
    invalid = []
    for name, prompt, candidates in INVALID_REQUEST_CASES:
        try:
            instrument.build_choice_request(prompt, candidates)
        except ValueError:
            invalid.append({'name': name, 'prompt': prompt, 'candidates': candidates})
        else:
            raise SystemExit(f'invalid case {name} unexpectedly built')
    buckets = [{'length': n, 'prompt': ('é' if n % 2 else '🚀') * n, 'bucket': instrument.length_bucket(('é' if n % 2 else '🚀') * n)}
               for n in (0, 199, 200, 599, 600, 1200, 1201)]
    return {'instrumentSha256': instrument.instrument_sha256(), 'cases': cases, 'invalid': invalid,
            'lengthBuckets': buckets}


# ------------------------------------------------------------------ instrument responses
KEYMAP = {'s0': 'skill:seo-aeo-geo/seo-site-audit', 's1': 'skill:rhize-devflow/test-evidence'}


def response(choice='s1', probs=None, model='typed-decisions', answers=None):
    probs = probs if probs is not None else {'s0': 0.2, 's1': 0.7, 'none': 0.1}
    value = {'routing': {'model': model}, 'usage': {'input_tokens': 10, 'output_tokens': 1},
             'answers': answers if answers is not None else {'skill': {
                 'type': 'choice', 'choice': choice, 'probabilities': probs, 'confidence': 0.4}}}
    return value


RESPONSE_CASES = [
    ('ok-skill', response(), True),
    ('ok-none', response('none', {'s0': 0.1, 's1': 0.2, 'none': 0.7}), True),
    ('ok-integer-probability', response('s0', {'s0': 1, 's1': 0, 'none': 0}), True),
    ('wrong-model', response(model='other'), False),
    ('missing-probability', response(probs={'s0': 0.2, 's1': 0.8}), False),
    ('extra-probability', response(probs={'s0': 0.2, 's1': 0.7, 'none': 0.1, 's2': 0.0}), False),
    ('probability-out-of-range', response(probs={'s0': 1.2, 's1': 0.7, 'none': 0.1}), False),
    ('boolean-probability', response(probs={'s0': True, 's1': 0.7, 'none': 0.1}), False),
    ('choice-not-a-key', response('s7'), False),
    ('noul-type', response(answers={'skill': {'type': 'noul', 'noul': 0.5}}), False),
    ('extra-answer', response(answers={'skill': {'type': 'choice', 'choice': 's0', 'probabilities': {'s0': 1, 's1': 0, 'none': 0}},
                                       'other': {'type': 'noul', 'noul': 0.1}}), False),
    ('not-an-object', [], False),
]


def response_fixture():
    cases = []
    for name, value, ok in RESPONSE_CASES:
        entry = {'name': name, 'keyMap': KEYMAP, 'response': value}
        if ok:
            entry['expected'] = instrument.decode_choice_response(value, KEYMAP)
        else:
            try:
                instrument.decode_choice_response(value, KEYMAP)
            except ValueError:
                entry['error'] = 'invalid_response'
            else:
                raise SystemExit(f'response case {name} unexpectedly decoded')
        cases.append(entry)
    return {'cases': cases}


# ------------------------------------------------------------------ identities
S1, P1 = h('session-1'), h('prompt one')
S2, P2 = h('session-2'), h('prompt two')


def identities_fixture():
    occ = []
    for s, p, ts in ((S1, P1, '2026-10-11T17:51:05.818Z'), (S1, P1, '2026-10-11T17:51:59Z'),
                     (S1, P1, '2026-10-11T19:51:05+02:00'), (S2, P2, '2026-10-11T00:00:00.000Z')):
        occ.append({'sessionHash': s, 'promptHash': p, 'ts': ts, 'expected': contract.occurrence_key(s, p, ts)})
    arms = []
    for i in range(40):
        s, p = h(f'session-{i}'), h(f'prompt-{i}')
        for holdback in (0, 0.1, 0.5):
            arms.append({'sessionHash': s, 'promptHash': p, 'holdback': holdback,
                         'expected': contract.arm_for(s, p, holdback)})
    return {'policySha256': {'cosign-v1': contract.policy_sha256('cosign-v1')},
            'instrumentSha256': instrument.instrument_sha256(), 'occurrenceKeys': occ, 'arms': arms}


# ------------------------------------------------------------------ lexical shortlist (node reference)
SHORTLIST_INDEX = {'signals': {
    'skill:a/sanity-development': [{'kind': 'tag', 'facet': 'stack', 'weight': 2, 'label': 'sanity'},
                                   {'kind': 'name', 'weight': 1, 'label': 'sanity-development'}],
    'skill:a/seo-site-audit': [{'kind': 'tag', 'facet': 'topic', 'weight': 2, 'label': 'seo-audit'},
                               {'kind': 'tag', 'facet': 'topic', 'weight': 2, 'label': 'seo'},
                               {'kind': 'name', 'weight': 1, 'label': 'seo-site-audit'}],
    'skill:a/aeo-geo-optimization': [{'kind': 'tag', 'facet': 'topic', 'weight': 2, 'label': 'seo'},
                                     {'kind': 'name', 'weight': 1, 'label': 'aeo-geo-optimization'}],
    'skill:b/vercel-functions': [{'kind': 'tag', 'facet': 'stack', 'weight': 2, 'label': 'vercel'},
                                 {'kind': 'name', 'weight': 1, 'label': 'vercel-functions'}],
    'skill:b/env-vars': [{'kind': 'tag', 'facet': 'stack', 'weight': 2, 'label': 'vercel'},
                         {'kind': 'tag-inferred', 'weight': 0.5, 'label': 'deployment'},
                         {'kind': 'name', 'weight': 1, 'label': 'env-vars'}],
    'skill:c/test-evidence': [{'kind': 'tag', 'facet': 'topic', 'weight': 2, 'label': 'testing'},
                              {'kind': 'name', 'weight': 1, 'label': 'test-evidence'}],
    'skill:c/zz-testing-extra': [{'kind': 'tag', 'facet': 'topic', 'weight': 2, 'label': 'testing'}],
}}
SHORTLIST_CASES = [
    ('seo-ranking', 'run a seo audit of the site', 'skill:a/seo-site-audit', 5),
    ('ties-by-code-unit', 'testing on vercel with sanity', None, 5),
    ('k-limit-forces-incumbent', 'testing on vercel with sanity deployment', 'skill:a/aeo-geo-optimization', 3),
    ('no-match', 'hello there', None, 5),
    ('incumbent-without-match', 'hello there', 'skill:c/test-evidence', 5),
]


def shortlist_fixture():
    script = (
        "const core = require(process.argv[1]);"
        "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "const out = input.cases.map((c) => core.lexicalShortlist(input.index, core.tokenize(c.prompt), c.incumbentId, c.k));"
        "process.stdout.write(JSON.stringify(out));")
    cases = [{'name': n, 'prompt': p, 'incumbentId': i, 'k': k} for n, p, i, k in SHORTLIST_CASES]
    core = str(REPO / 'rhize-context-manager' / 'hooks' / 'lib' / 'route-core.js')
    result = subprocess.run(['node', '-e', script, core], input=json.dumps({'index': SHORTLIST_INDEX, 'cases': cases}),
                            capture_output=True, text=True, check=True, timeout=60)
    for case, expected in zip(cases, json.loads(result.stdout)):
        case['expected'] = expected
    return {'index': SHORTLIST_INDEX, 'cases': cases}


# ------------------------------------------------------------------ record / label / outcome / cohort / registry
POLICY = contract.policy_sha256()
INSTR = instrument.instrument_sha256()
CRIT = h('criteria')
INCUMBENT = 'skill:seo-aeo-geo/seo-site-audit'
OTHER = 'skill:seo-aeo-geo/aeo-geo-optimization'


def base_record(**overrides):
    record = {
        'schema': contract.RECORD_SCHEMA, 'decision': 'skill-fit', 'decisionId': '0' * 31 + '1',
        'occurrenceKey': '', 'ts': '2026-10-11T17:51:05.818Z', 'host': 'claude', 'basis': 'live',
        'sourceStratum': 'fired', 'sessionHash': S1, 'promptHash': P1, 'promptLengthBucket': 'lt200',
        'routerSourceSha256': h('router'), 'indexSha256': h('index'), 'registryRevision': 0,
        'policy': 'cosign-v1', 'policySha256': POLICY, 'instrument': instrument.INSTRUMENT,
        'instrumentSha256': INSTR, 'criteriaSha256': CRIT, 'layaRevision': '55cf4c4ebb4e',
        'mode': 'shadow', 'arm': 'treatment', 'propensity': 0.9,
        'incumbent': {'skillId': INCUMBENT, 'score': 5}, 'shortlist': [INCUMBENT, OTHER],
        'laya': {'status': 'ok', 'choice': INCUMBENT, 'probabilities': [0.6, 0.3, 0.1], 'latencyMs': 61.2,
                 'truncated': False},
        'emitted': INCUMBENT}
    for key, value in overrides.items():
        record[key] = value
    record['occurrenceKey'] = contract.occurrence_key(record['sessionHash'], record['promptHash'], record['ts'])
    return record


def records_fixture():
    valid = {
        'live-shadow-agree': base_record(),
        'live-shadow-disagree-still-emits': base_record(laya={'status': 'ok', 'choice': OTHER, 'probabilities': [0.2, 0.7, 0.1], 'latencyMs': 70, 'truncated': False}),
        'live-cosign-disagree-suppressed': base_record(mode='cosign', emitted=None, laya={'status': 'ok', 'choice': 'none', 'probabilities': [0.2, 0.1, 0.7], 'latencyMs': 55, 'truncated': True}),
        'live-cosign-holdback-emits': base_record(mode='cosign', arm='holdback', propensity=0.1, laya={'status': 'ok', 'choice': OTHER, 'probabilities': [0.2, 0.7, 0.1], 'latencyMs': 55, 'truncated': False}),
        'live-timeout-emits': base_record(mode='cosign', criteriaSha256=CRIT, laya={'status': 'timeout', 'choice': None, 'probabilities': None, 'latencyMs': 800, 'truncated': False}),
        'live-overlap-suppressed-in-shadow': base_record(emitted=None),
        'backfill-fired': base_record(basis='backfill', arm='none', propensity=None, emitted=None),
        'backfill-silent-skipped': base_record(basis='backfill', sourceStratum='silent_sample', arm='none', propensity=None, emitted=None,
                                               incumbent=None, shortlist=[], criteriaSha256=None,
                                               laya={'status': 'skipped', 'choice': None, 'probabilities': None, 'latencyMs': None, 'truncated': None}),
        'backfill-silent-laya-pick': base_record(basis='backfill', sourceStratum='silent_sample', arm='none', propensity=None, emitted=None,
                                                 incumbent=None, shortlist=[OTHER],
                                                 laya={'status': 'ok', 'choice': OTHER, 'probabilities': [0.8, 0.2], 'latencyMs': 40, 'truncated': False}),
    }
    def bad(name, **overrides):
        record = base_record()
        for key, value in overrides.items():
            if value is DELETE:
                record.pop(key)
            else:
                record[key] = value
        return {'name': name, 'record': record}
    invalid = [
        bad('extra-text-field', prompt='do the thing'),
        bad('missing-field', emitted=DELETE),
        bad('cosign-disagree-emitted', mode='cosign', laya={'status': 'ok', 'choice': OTHER, 'probabilities': [0.2, 0.7, 0.1], 'latencyMs': 1, 'truncated': False}),
        bad('probabilities-misaligned', laya={'status': 'ok', 'choice': INCUMBENT, 'probabilities': [0.6, 0.4], 'latencyMs': 1, 'truncated': False}),
        bad('choice-outside-shortlist', laya={'status': 'ok', 'choice': 'skill:x/y', 'probabilities': [0.6, 0.3, 0.1], 'latencyMs': 1, 'truncated': False}),
        bad('choice-on-timeout', laya={'status': 'timeout', 'choice': INCUMBENT, 'probabilities': None, 'latencyMs': 800, 'truncated': False}),
        bad('occurrence-key-mismatch', occurrenceKey=h('nope')),
        bad('policy-hash-mismatch', policySha256=h('nope')),
        bad('backfill-with-arm', basis='backfill', emitted=None),
        bad('live-without-incumbent', incumbent=None, emitted=None),
        bad('incumbent-not-in-shortlist', shortlist=[OTHER], laya={'status': 'ok', 'choice': OTHER, 'probabilities': [0.9, 0.1], 'latencyMs': 1, 'truncated': False}),
        bad('emitted-not-incumbent', emitted=OTHER),
        bad('mode-off', mode='off'),
        bad('bad-ts', ts='2026-10-11 17:51:05'),
        bad('too-many-shortlist', shortlist=[INCUMBENT] + [f'skill:z/s{i}' for i in range(5)],
            laya={'status': 'ok', 'choice': INCUMBENT, 'probabilities': [0.1] * 7, 'latencyMs': 1, 'truncated': False}),
    ]
    for case in invalid:
        try:
            contract.validate_record(case['record'])
        except ValueError as exc:
            case['reason'] = str(exc)
        else:
            raise SystemExit(f"record case {case['name']} unexpectedly valid")
    for name, record in valid.items():
        contract.validate_record(record)
    return {'valid': valid, 'invalid': invalid}


class _Delete:
    pass


DELETE = _Delete()


def base_label(**overrides):
    label = {'schema': contract.LABEL_SCHEMA, 'decisionId': '0' * 31 + '1', 'occurrenceKey': base_record()['occurrenceKey'],
             'basis': 'ai_model_reviewed', 'cohortId': 'a' * 32, 'stratum': 'disagreement', 'inclusionProbability': 0.25,
             'candidates': [INCUMBENT, OTHER], 'acceptable': [OTHER], 'bestSkill': OTHER, 'unlistedBetter': False,
             'ambiguous': False, 'annotators': ['claude-sonnet-5-5', 'gpt-5.6-sol'], 'reviewer': 'claude-fable-5-1',
             'evidenceSha256': h('evidence'), 'labeledAt': '2026-10-11T18:00:00Z'}
    label.update(overrides)
    return label


def labels_fixture():
    valid = {'disagreement-incumbent-wrong': base_label(),
             'none-acceptable': base_label(acceptable=[], bestSkill='none'),
             'ambiguous': base_label(acceptable=[], bestSkill='none', ambiguous=True),
             'harness': base_label(basis='harness', cohortId=None, inclusionProbability=None, stratum='harness',
                                   annotators=[], reviewer=None, evidenceSha256=None),
             'scoreboard-pool': base_label(cohortId=None, stratum='agreement', inclusionProbability=0.05)}
    invalid = [
        {'name': 'acceptable-outside-candidates', 'label': base_label(acceptable=['skill:x/y'], bestSkill='skill:x/y')},
        {'name': 'best-not-acceptable', 'label': base_label(bestSkill=INCUMBENT)},
        {'name': 'none-with-acceptable', 'label': base_label(bestSkill='none')},
        {'name': 'zero-inclusion', 'label': base_label(inclusionProbability=0)},
        {'name': 'harness-with-cohort', 'label': base_label(basis='harness', inclusionProbability=None)},
        {'name': 'extra-field', 'label': {**base_label(), 'note': 'free text'}},
    ]
    for case in invalid:
        try:
            contract.validate_label(case['label'])
        except ValueError as exc:
            case['reason'] = str(exc)
        else:
            raise SystemExit(f"label case {case['name']} unexpectedly valid")
    for value in valid.values():
        contract.validate_label(value)
    scoring = []
    for suggestion in (INCUMBENT, OTHER, None):
        for name, label in valid.items():
            scoring.append({'label': name, 'suggestion': suggestion, 'expected': contract.score_suggestion(suggestion, label)})
    return {'valid': valid, 'invalid': invalid, 'scoring': scoring}


def outcomes_fixture():
    occ = base_record()['occurrenceKey']
    common = {'schema': contract.OUTCOME_SCHEMA, 'decisionId': '0' * 31 + '1', 'occurrenceKey': occ,
              'joinedAt': '2026-10-11T19:00:00Z', 'transcriptSha256': h('transcript')}
    valid = {'invoked-emitted': {**common, 'outcome': 'invoked_emitted', 'skillInvoked': 'seo-aeo-geo:seo-site-audit', 'via': 'skill_tool', 'latencyTurns': 0},
             'slash-command': {**common, 'outcome': 'invoked_unlisted', 'skillInvoked': 'rhize-devflow:ship', 'via': 'slash_command', 'latencyTurns': 2},
             'none-invoked': {**common, 'outcome': 'none_invoked', 'skillInvoked': None, 'via': None, 'latencyTurns': None},
             'transcript-unavailable': {**common, 'outcome': 'transcript_unavailable', 'skillInvoked': None, 'via': None, 'latencyTurns': None, 'transcriptSha256': None}}
    invalid = [{'name': 'none-with-skill', 'outcome': {**valid['none-invoked'], 'skillInvoked': 'a:b'}},
               {'name': 'invoked-without-via', 'outcome': {**valid['invoked-emitted'], 'via': None}},
               {'name': 'missing-transcript-hash', 'outcome': {**valid['none-invoked'], 'transcriptSha256': None}}]
    for case in invalid:
        try:
            contract.validate_outcome(case['outcome'])
        except ValueError as exc:
            case['reason'] = str(exc)
        else:
            raise SystemExit(f"outcome case {case['name']} unexpectedly valid")
    for value in valid.values():
        contract.validate_outcome(value)
    return {'valid': valid, 'invalid': invalid}


def cohorts_fixture():
    keys = [h(f'occ-{i}') for i in range(60)]
    common = {'schema': contract.COHORT_SCHEMA, 'cohortId': 'b' * 32, 'decision': 'skill-fit', 'at': '2026-10-11T20:00:00Z'}
    valid = {'reserve': {**common, 'event': 'reserve', 'policy': 'cosign-v1', 'policySha256': POLICY, 'instrumentSha256': INSTR,
                         'layaRevision': '55cf4c4ebb4e', 'lambda': 1, 'alpha': 0.05, 'attempt': 1, 'target': 60,
                         'stratum': 'disagreement', 'occurrenceKeys': keys},
             'labeled': {**common, 'event': 'labeled', 'counts': {'labeled': 60, 'ambiguous': 4, 'hit': 18, 'notHit': 38}},
             'consumed': {**common, 'event': 'consumed', 'verdict': 'pass',
                          'statistic': {'n': 56, 'x': 38, 'bound': 0.5671, 'threshold': 0.5, 'alpha': 0.05},
                          'receiptSha256': h('receipt')}}
    invalid = [{'name': 'reserve-too-few-keys', 'event': {**valid['reserve'], 'occurrenceKeys': keys[:10]}},
               {'name': 'reserve-wrong-stratum', 'event': {**valid['reserve'], 'stratum': 'agreement'}},
               {'name': 'labeled-counts-mismatch', 'event': {**valid['labeled'], 'counts': {'labeled': 60, 'ambiguous': 0, 'hit': 1, 'notHit': 1}}},
               {'name': 'consumed-x-over-n', 'event': {**valid['consumed'], 'statistic': {'n': 3, 'x': 4, 'bound': None, 'threshold': 0.5, 'alpha': 0.05}}}]
    for case in invalid:
        try:
            contract.validate_cohort_event(case['event'])
        except ValueError as exc:
            case['reason'] = str(exc)
        else:
            raise SystemExit(f"cohort case {case['name']} unexpectedly valid")
    for value in valid.values():
        contract.validate_cohort_event(value)
    return {'valid': valid, 'invalid': invalid}


def registry_fixture():
    shipped = json.loads((REPO / 'rhize-context-manager' / 'catalog' / 'decision-registry.json').read_text())
    contract.validate_registry(shipped)
    def variant(name, mutate):
        value = copy.deepcopy(shipped)
        mutate(value)
        return {'name': name, 'registry': value}
    def crit(v):
        v['decisions']['skill-fit']['tier'] = 'critical'
    def wf_cosign(v):
        v['decisions']['workflow-fit']['reachableModes'] = ['shadow', 'cosign']
    def host(v):
        v['decisions']['skill-fit']['endpoint'] = 'http://localhost:8000'
    def default_unreachable(v):
        v['decisions']['skill-fit']['defaultMode'] = 'cosign'
        v['decisions']['skill-fit']['reachableModes'] = ['off', 'shadow']
    def unknown(v):
        v['decisions']['gsd-finish'] = copy.deepcopy(v['decisions']['workflow-fit'])
    invalid = [variant('critical-cosign', crit), variant('workflow-cosign', wf_cosign), variant('hostname-endpoint', host),
               variant('default-unreachable', default_unreachable), variant('unknown-decision', unknown)]
    for case in invalid:
        try:
            contract.validate_registry(case['registry'])
        except ValueError as exc:
            case['reason'] = str(exc)
        else:
            raise SystemExit(f"registry case {case['name']} unexpectedly valid")
    entry = {'mode': 'cosign', 'pinned': False, 'since': '2026-10-11T20:00:00Z', 'reason': 'gate_passed',
             'policySha256': POLICY, 'instrumentSha256': INSTR, 'layaRevision': '55cf4c4ebb4e', 'cohortId': 'b' * 32}
    valid_state = {'schemaVersion': 1, 'revision': 2, 'updatedAt': '2026-10-11T20:00:00Z', 'decisions': {'skill-fit': entry}}
    contract.validate_state(valid_state, shipped)
    pinned = copy.deepcopy(valid_state)
    pinned['decisions']['skill-fit'].update(mode='shadow', pinned=True, reason='manual_pin')
    contract.validate_state(pinned, shipped)
    invalid_states = [
        {'name': 'unreachable-mode', 'state': {**valid_state, 'decisions': {'workflow-fit': {**entry, 'mode': 'cosign'}}}},
        {'name': 'cosign-unbound', 'state': {**valid_state, 'decisions': {'skill-fit': {**entry, 'policySha256': None}}}},
        {'name': 'revision-zero', 'state': {**valid_state, 'revision': 0}},
        {'name': 'unknown-decision', 'state': {**valid_state, 'decisions': {'gsd-finish': entry}}},
    ]
    for case in invalid_states:
        try:
            contract.validate_state(case['state'], shipped)
        except ValueError as exc:
            case['reason'] = str(exc)
        else:
            raise SystemExit(f"state case {case['name']} unexpectedly valid")
    audit_intent = {'schema': contract.AUDIT_SCHEMA, 'phase': 'intent', 'revision': 2, 'previousRevision': 1,
                    'at': '2026-10-11T20:00:00Z', 'actor': 'cycle', 'decision': 'skill-fit', 'fromMode': 'shadow',
                    'toMode': 'cosign', 'pinned': False, 'reason': 'gate_passed', 'state': valid_state}
    audit_commit = {k: v for k, v in audit_intent.items() if k != 'state'}
    audit_commit['phase'] = 'commit'
    for line in (audit_intent, audit_commit):
        contract.validate_audit(line)
    invalid_audit = [{'name': 'revision-skip', 'line': {**audit_commit, 'revision': 3}},
                     {'name': 'intent-without-state', 'line': {**audit_commit, 'phase': 'intent'}}]
    for case in invalid_audit:
        try:
            contract.validate_audit(case['line'])
        except ValueError as exc:
            case['reason'] = str(exc)
        else:
            raise SystemExit(f"audit case {case['name']} unexpectedly valid")
    return {'invalidRegistries': invalid, 'validStates': {'cosign': valid_state, 'pinned-shadow': pinned},
            'invalidStates': invalid_states, 'validAudit': {'intent': audit_intent, 'commit': audit_commit},
            'invalidAudit': invalid_audit}


def main():
    dump('laya-choice-requests.json', request_fixture())
    dump('laya-choice-responses.json', response_fixture())
    dump('identities.json', identities_fixture())
    dump('lexical-shortlist.json', shortlist_fixture())
    dump('records.json', records_fixture())
    dump('labels.json', labels_fixture())
    dump('outcomes.json', outcomes_fixture())
    dump('cohorts.json', cohorts_fixture())
    dump('registry.json', registry_fixture())
    print('fixtures written to', HERE)


if __name__ == '__main__':
    main()
