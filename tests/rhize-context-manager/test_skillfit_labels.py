"""skillfit_labels (lane L2): AI labels for skill-fit gate cohorts and the daily scoreboard pool.

Invented transcripts and records, a fake runner standing in for the two model CLIs, temp directories only. No test
starts a model or touches the network.
"""
from __future__ import annotations

import copy
import hashlib
import json
import stat
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'rhize-context-manager' / 'scripts'
FIX = REPO / 'tests' / 'rhize-context-manager' / 'fixtures' / 'typed-decisions'
sys.path.insert(0, str(SCRIPTS))

import pilot_autolabel as auto  # noqa: E402
from typed_decisions import contract, evidence_fs, instrument, records, skillfit_labels as sl  # noqa: E402

SEO = 'skill:seo-aeo-geo/seo-site-audit'
GEO = 'skill:seo-aeo-geo/aeo-geo-optimization'
SHIP = 'skill:rhize-devflow/ship'
SEO_NAME, GEO_NAME, SHIP_NAME = 'seo-aeo-geo:seo-site-audit', 'seo-aeo-geo:aeo-geo-optimization', 'rhize-devflow:ship'
SECRET_TOKEN = 'sk-ant-abcdefghijklmnop1234'
SECRET_EMAIL = 'jane.doe@example.com'
SENTINEL = 'ZEBRA-SENTINEL-PHRASE'
DESCRIPTIONS = {SEO: 'Audit a website for SEO health.   Uses\nDataForSEO.', GEO: 'Optimize for answer engines.',
                SHIP: 'Ship a release.'}
RECORDS = json.loads((FIX / 'records.json').read_text())['valid']
COHORT_RESERVE = json.loads((FIX / 'cohorts.json').read_text())['valid']['reserve']
COHORT_CONSUMED = json.loads((FIX / 'cohorts.json').read_text())['valid']['consumed']
RESERVE_AT = '2026-10-11T20:00:00Z'


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------- fake runner

def cases_in(prompt):
    return json.loads(prompt.split('# Cases\n\n', 1)[1])


def choose(case, *names, unlisted=False):
    keys = [c['key'] for c in case['candidates'] if c['skill'] in names]
    return {'acceptable': keys, 'bestSkill': keys[0] if keys else 'none', 'unlistedBetter': unlisted,
            'ambiguous': False}


def ambiguous():
    return {'acceptable': [], 'bestSkill': 'none', 'unlistedBetter': False, 'ambiguous': True}


def by_marker(host, case):
    prompt = case['prompt']
    if 'WANT-AMBIG' in prompt:
        return ambiguous()
    if 'WANT-SEO' in prompt:
        return choose(case, SEO_NAME)
    if 'WANT-NONE' in prompt:
        return choose(case)
    return choose(case, GEO_NAME)


def resolve_geo(case):
    return {'verdict': 'resolved', 'reason': 'fixture', 'final': choose(case, GEO_NAME)}


class FakeRunner:
    """Stands in for the two CLIs. annotate(host, case) and review(case) shape each answer."""

    def __init__(self, annotate=None, review=None, auth_error=None, fail=None, observed=None, identity=None):
        self.annotate_fn = annotate or by_marker
        self.review_fn = review or resolve_geo
        self.auth_error, self.fail = auth_error, fail
        self.observed, self.identity = observed or {}, identity
        self.calls, self.preflights = [], []

    def preflight(self, host):
        self.preflights.append(host)
        if self.auth_error:
            raise auto.LabelerError(self.auth_error)
        return {'host': host}

    def call(self, host, model, system, prompt, schema, timeout):
        self.calls.append({'host': host, 'model': model, 'system': system, 'prompt': prompt, 'schema': schema,
                           'timeout': timeout})
        if self.fail:
            raise auto.LabelerError(self.fail)
        cases = cases_in(prompt)
        reviewing = 'reviews' in schema['properties']
        if reviewing:
            answer = {'reviews': [{'caseId': c['caseId'], **self.review_fn(c)} for c in cases]}
        else:
            answer = {'answers': [{'caseId': c['caseId'], **self.annotate_fn(host, c), 'rationale': 'fixture'}
                                  for c in cases]}
        kind = 'review' if reviewing else host
        return {'answer': answer, 'raw': json.dumps(answer), 'requestedModel': model,
                'observedModel': self.observed.get(kind, model),
                'identitySource': self.identity or ('native_model_usage' if host == 'claude' else 'explicit_cli_argument'),
                'usage': {}}

    def prompts(self):
        return '\n'.join(c['prompt'] for c in self.calls)

    def kinds(self):
        return [(c['host'], 'reviews' in c['schema']['properties']) for c in self.calls]


# ---------------------------------------------------------------- world

class LabWorld:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.root = tmp_path / 'root'
        self.transcripts = tmp_path / 'transcripts'
        self.map = tmp_path / 'skill-map.json'
        self.map.write_text(json.dumps({'nodes': [
            {'id': sid, 'kind': 'skill', 'description': text} for sid, text in DESCRIPTIONS.items()
        ] + [{'id': 'agent:x/y', 'kind': 'agent', 'description': 'not a skill'}]}))
        self.count = 0
        self.added = []

    def session(self):
        self.count += 1
        return f'cccccccc-0000-4000-8000-{self.count:012d}'

    def add(self, kind='disagree', marker='', session=None, extra='', minute=None, context=None, shortlist=None,
            write_transcript=True):
        session = session or self.session()
        self.count += 0
        minute = self.count if minute is None else minute
        prompt = f'Please look at this {marker} {extra} {kind} {uuid.uuid4().hex[:8]}'.strip()
        when = f'2026-10-05T12:{minute % 60:02d}:{(len(self.added) % 50):02d}.000Z'
        record = copy.deepcopy(RECORDS['backfill-fired' if kind in ('disagree', 'agree') else 'backfill-silent-laya-pick'])
        if kind == 'skipped':
            record = copy.deepcopy(RECORDS['backfill-silent-skipped'])
        short = list(shortlist or ([SEO, GEO] if kind in ('disagree', 'agree') else [GEO, SEO]))
        if kind != 'skipped':
            record['shortlist'] = short
            choice = {'disagree': GEO, 'agree': SEO, 'silent': GEO, 'silent_none': 'none'}[kind]
            if choice != 'none' and choice not in short:
                choice = short[0]
            record['laya'] = {'status': 'ok', 'choice': choice, 'latencyMs': 40, 'truncated': False,
                              'probabilities': [round(1.0 / (len(short) + 1), 6)] * len(short)
                              + [round(1.0 - round(1.0 / (len(short) + 1), 6) * len(short), 6)]}
            record['incumbent'] = {'skillId': SEO, 'score': 5} if kind in ('disagree', 'agree') else None
            record['sourceStratum'] = 'fired' if kind in ('disagree', 'agree') else 'silent_sample'
        record.update(decisionId=uuid.uuid4().hex, sessionHash=sha(session), promptHash=sha(prompt), ts=when)
        record['occurrenceKey'] = contract.occurrence_key(record['sessionHash'], record['promptHash'], when)
        records.append(self.root, 'skill-fit', 'records', record)
        if write_transcript:
            self.write_transcript(session, prompt, context)
        self.added.append(record)
        return record

    def write_transcript(self, session, prompt, context=None):
        context = context or [f'Earlier I asked about the site, using {SECRET_TOKEN} and mail to {SECRET_EMAIL}.',
                              f'Then we talked about {SENTINEL} for a while.']
        rows, minute = [], 0
        for text in context:
            rows.append({'type': 'user', 'timestamp': f'2026-10-05T11:{minute:02d}:00.000Z',
                         'message': {'role': 'user', 'content': text}})
            rows.append({'type': 'assistant', 'timestamp': f'2026-10-05T11:{minute:02d}:30.000Z',
                         'message': {'role': 'assistant', 'content': 'ok'}})
            minute += 1
        rows.append({'type': 'user', 'timestamp': '2026-10-05T12:00:00.000Z', 'message': {'role': 'user', 'content': prompt}})
        path = self.transcripts / '-proj' / f'{session}.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')

    def reserve(self, recs, target=None, cohort_id=None, **overrides):
        cohort_id = cohort_id or uuid.uuid4().hex
        keys = [r['occurrenceKey'] for r in recs]
        event = {**COHORT_RESERVE, 'cohortId': cohort_id, 'occurrenceKeys': keys, 'target': target or len(keys),
                 'at': RESERVE_AT, **overrides}
        records.append(self.root, 'skill-fit', 'cohorts', event)
        return cohort_id

    def cohort(self, markers, **kwargs):
        recs = [self.add('disagree', marker=m) for m in markers]
        return self.reserve(recs), recs

    def labels(self):
        items, invalid = records.read(self.root, 'skill-fit', 'labels')
        assert invalid == 0
        return items

    def run_cohort(self, cohort_id, runner, **kwargs):
        return sl.label_cohort(self.root, cohort_id, runner=runner, transcript_roots=[self.transcripts],
                               map_path=self.map, **kwargs)

    def run_pool(self, runner, **kwargs):
        return sl.label_pool(self.root, runner=runner, transcript_roots=[self.transcripts], map_path=self.map, **kwargs)


@pytest.fixture
def lab(tmp_path):
    return LabWorld(tmp_path)


def all_text(root):
    return '\n'.join(p.read_text(errors='replace') for p in Path(root).rglob('*') if p.is_file())


# ---------------------------------------------------------------- redaction first, entries blind

def test_text_is_redacted_before_any_model_sees_it_and_entries_are_blind(lab):
    cid, recs = lab.cohort(['WANT-GEO'])
    runner = FakeRunner()
    summary, code = lab.run_cohort(cid, runner)
    assert code == 0 and summary['labelsWritten'] == 1
    seen = runner.prompts()
    assert SECRET_TOKEN not in seen and SECRET_EMAIL not in seen
    assert '[REDACTED_TOKEN]' in seen and '[REDACTED_EMAIL]' in seen
    for call in runner.calls:
        entries = cases_in(call['prompt'])
        for entry in entries:
            assert set(entry) == {'caseId', 'prompt', 'promptTruncated', 'precedingContext', 'candidates'}
            assert [set(c) for c in entry['candidates']] == [{'key', 'skill', 'description'}] * 2
            assert [c['key'] for c in entry['candidates']] == ['s0', 's1']
    rendered = runner.prompts()
    for hidden in (recs[0]['decisionId'], recs[0]['occurrenceKey'], recs[0]['promptHash'], recs[0]['sessionHash'],
                   'incumbent', 'propensity', 'skill:seo-aeo-geo', 'probabilities'):
        assert hidden not in rendered, hidden


def test_descriptions_come_from_the_map_and_are_whitespace_normalized(lab):
    cid, _ = lab.cohort(['WANT-GEO'])
    runner = FakeRunner()
    lab.run_cohort(cid, runner)
    candidates = {c['skill']: c['description'] for c in cases_in(runner.calls[0]['prompt'])[0]['candidates']}
    assert candidates == {SEO_NAME: 'Audit a website for SEO health. Uses DataForSEO.', GEO_NAME: DESCRIPTIONS[GEO]}
    assert sl.load_descriptions(lab.map) == DESCRIPTIONS                        # only skill nodes with descriptions
    assert sl.load_descriptions(lab.tmp / 'missing.json') == {}
    (lab.tmp / 'broken.json').write_text('{not json')
    assert sl.load_descriptions(lab.tmp / 'broken.json') == {}


def test_candidate_order_is_shuffled_per_case_but_stable(lab):
    template = lab.add('disagree', marker='WANT-GEO')
    orders = set()
    for number in range(12):
        record = {**template, 'occurrenceKey': sha(f'fixed-occurrence-{number}')}      # fixed keys: no flakiness
        item = {'record': record, 'cohortId': None, 'stratum': 'disagreement', 'inclusionProbability': 1.0}
        match = {'text': 't', 'prior': [], 'timestamp': record['ts']}
        first = sl.build_case(item, match, DESCRIPTIONS, 'C001')
        again = sl.build_case(item, match, DESCRIPTIONS, 'C009')
        assert first['keyToId'] == again['keyToId'] and first['evidenceSha256'] == again['evidenceSha256']
        assert sorted(first['keyToId'].values()) == sorted(record['shortlist'])
        orders.add(tuple(first['keyToId'].values()))
    assert len(orders) == 2                                                    # both orders occur across the cases


def test_evidence_hash_binds_the_redacted_entry_without_the_case_number(lab):
    cid, _ = lab.cohort(['WANT-GEO'])
    runner = FakeRunner()
    lab.run_cohort(cid, runner)
    entry = cases_in(runner.calls[0]['prompt'])[0]
    expected = sha(instrument.canonical_json({k: v for k, v in entry.items() if k != 'caseId'}))
    assert lab.labels()[0]['evidenceSha256'] == expected


# ---------------------------------------------------------------- annotation, review, ambiguity

def test_identical_answers_are_accepted_without_a_review(lab):
    cid, recs = lab.cohort(['WANT-GEO'])
    runner = FakeRunner()
    summary, code = lab.run_cohort(cid, runner)
    assert code == 0 and summary['status'] == 'completed' and summary['modelCalls'] == 2
    assert runner.kinds() == [('claude', False), ('codex', False)]
    assert runner.calls[0]['model'] == 'claude-sonnet-5-5' and runner.calls[1]['model'] == 'gpt-5.6-sol'
    (label,) = lab.labels()
    contract.validate_label(label)
    assert (label['basis'], label['cohortId'], label['stratum'], label['reviewer']) == (
        'ai_model_reviewed', cid, 'disagreement', None)
    assert label['annotators'] == ['claude-sonnet-5-5', 'gpt-5.6-sol']
    assert label['candidates'] == recs[0]['shortlist']                          # record order, not the shuffled one
    assert label['acceptable'] == [GEO] and label['bestSkill'] == GEO and label['ambiguous'] is False
    assert label['decisionId'] == recs[0]['decisionId'] and label['occurrenceKey'] == recs[0]['occurrenceKey']


def test_a_split_goes_to_the_reviewer_whose_verdict_is_the_label(lab):
    cid, recs = lab.cohort(['WANT-GEO'])
    runner = FakeRunner(annotate=lambda host, case: choose(case, GEO_NAME) if host == 'claude' else choose(case, SEO_NAME),
                        review=lambda case: {'verdict': 'resolved', 'reason': 'r', 'final': choose(case, SEO_NAME, GEO_NAME)})
    summary, code = lab.run_cohort(cid, runner)
    assert code == 0 and summary['modelCalls'] == 3 and summary['reviewed'] == 1
    assert runner.kinds() == [('claude', False), ('codex', False), ('claude', True)]
    assert runner.calls[2]['model'] == 'claude-fable-5-1'
    proposals = cases_in(runner.calls[2]['prompt'])[0]['proposals']
    assert len(proposals) == 2 and all(set(p) == set(sl.FINAL_KEYS) for p in proposals)
    (label,) = lab.labels()
    contract.validate_label(label)
    assert label['reviewer'] == 'claude-fable-5-1' and set(label['acceptable']) == {SEO, GEO}
    assert label['acceptable'] == [s for s in recs[0]['shortlist'] if s in (SEO, GEO)]   # shortlist order


def test_the_annotators_are_the_reviewers_models_never(lab):
    cid, _ = lab.cohort(['WANT-GEO'])
    split = dict(annotate=lambda host, case: choose(case, GEO_NAME) if host == 'claude' else choose(case, SEO_NAME))
    for observed in ({'review': 'claude-sonnet-5-5'}, {'review': 'gpt-5.6-sol'}):
        runner = FakeRunner(observed=observed, **split)
        summary, code = lab.run_cohort(cid, runner)
        assert code == 3 and summary['reviewFailed'] == 1 and summary['labelsWritten'] == 0
    runner = FakeRunner(identity='explicit_cli_argument', **split)        # the reviewer's identity must come from the CLI
    summary, code = lab.run_cohort(cid, runner)
    assert code == 3 and summary['reviewFailed'] == 1
    assert lab.labels() == []
    # a reviewer model configured as one of the annotators is refused before anything runs
    runner = FakeRunner(**split)
    with pytest.raises(auto.LabelerError, match='reviewerModel_must_differ'):
        lab.run_cohort(cid, runner, config={'reviewerModel': 'claude-sonnet-5-5'})
    assert runner.calls == [] and lab.labels() == []


def test_an_unresolved_review_becomes_an_ambiguous_label(lab):
    cid, _ = lab.cohort(['WANT-GEO'])
    runner = FakeRunner(annotate=lambda host, case: choose(case, GEO_NAME) if host == 'claude' else choose(case, SEO_NAME),
                        review=lambda case: {'verdict': 'unresolved', 'reason': 'no single judgement',
                                             'final': choose(case, GEO_NAME)})
    summary, code = lab.run_cohort(cid, runner)
    assert code == 0 and summary['reviewUnresolved'] == 1 and summary['ambiguous'] == 1
    (label,) = lab.labels()
    contract.validate_label(label)
    assert label['ambiguous'] is True and label['acceptable'] == [] and label['bestSkill'] == 'none'
    assert summary['counts'] == {'labeled': 1, 'ambiguous': 1, 'hit': 0, 'notHit': 0}


def test_two_ambiguous_annotators_agree_without_a_reviewer(lab):
    cid, _ = lab.cohort(['WANT-AMBIG'])
    runner = FakeRunner()
    summary, code = lab.run_cohort(cid, runner)
    assert code == 0 and summary['modelCalls'] == 2
    (label,) = lab.labels()
    assert label['ambiguous'] is True and label['reviewer'] is None


@pytest.mark.parametrize('bad', [
    {'acceptable': ['s9'], 'bestSkill': 's9', 'unlistedBetter': False, 'ambiguous': False},          # unknown key
    {'acceptable': ['s0'], 'bestSkill': 's1', 'unlistedBetter': False, 'ambiguous': False},          # best not acceptable
    {'acceptable': [], 'bestSkill': 's0', 'unlistedBetter': False, 'ambiguous': False},              # none required
    {'acceptable': ['s0', 's0'], 'bestSkill': 's0', 'unlistedBetter': False, 'ambiguous': False},    # duplicate
    {'acceptable': ['s0'], 'bestSkill': 's0', 'unlistedBetter': 'no', 'ambiguous': False},           # not a boolean
    {'acceptable': 's0', 'bestSkill': 's0', 'unlistedBetter': False, 'ambiguous': False}])
def test_invalid_annotator_answers_produce_no_label(lab, bad):
    cid, _ = lab.cohort(['WANT-GEO'])
    runner = FakeRunner(annotate=lambda host, case: bad if host == 'codex' else choose(case, GEO_NAME))
    summary, code = lab.run_cohort(cid, runner)
    assert code == 3 and summary['annotationFailed'] == 1 and summary['labelsWritten'] == 0 and summary['unlabeled'] == 1
    assert lab.labels() == [] and runner.kinds() == [('claude', False), ('codex', False)]       # nothing to review


def test_answer_parsers_never_guess():
    expected = {'C001': ['s0', 's1'], 'C002': ['s0']}
    ok = {'caseId': 'C001', 'rationale': 'r', 'acceptable': ['s1', 's0'], 'bestSkill': 's1', 'unlistedBetter': False,
          'ambiguous': False}
    parsed = sl.parse_answers({'answers': [ok, {**ok, 'caseId': 'C002', 'acceptable': ['s9'], 'bestSkill': 's9'}]}, expected)
    assert parsed['C001']['acceptable'] == ['s0', 's1'] and parsed['C002'].startswith('invalid_answer')
    duplicated = sl.parse_answers({'answers': [ok, ok]}, expected)
    assert duplicated == {'C001': 'missing_or_duplicate_answer', 'C002': 'missing_or_duplicate_answer'}
    extra = sl.parse_answers({'answers': [{**ok, 'surprise': 1}]}, expected)
    assert extra['C001'].startswith('invalid_answer')
    ambiguous_wins = sl.normalize_answer({'acceptable': ['s0'], 'bestSkill': 's0', 'unlistedBetter': False,
                                          'ambiguous': True}, ['s0'])
    assert ambiguous_wins == {'acceptable': [], 'bestSkill': 'none', 'unlistedBetter': False, 'ambiguous': True}
    with pytest.raises(auto.LabelerError):
        sl.parse_answers({'nope': []}, expected)
    with pytest.raises(ValueError):
        sl.normalize_answer('not an object', ['s0'])
    review = {'caseId': 'C001', 'verdict': 'resolved', 'reason': 'r', 'final': {
        'acceptable': ['s0'], 'bestSkill': 's0', 'unlistedBetter': False, 'ambiguous': False}}
    reviews = sl.parse_reviews({'reviews': [review, {**review, 'caseId': 'C002', 'verdict': 'maybe'}]}, expected)
    assert reviews['C001']['final']['bestSkill'] == 's0' and reviews['C002'].startswith('invalid_review')
    unresolved = sl.parse_reviews({'reviews': [{**review, 'verdict': 'unresolved', 'final': None}]}, {'C001': ['s0']})
    assert unresolved['C001'] == {'verdict': 'unresolved', 'final': None}
    with pytest.raises(auto.LabelerError):
        sl.parse_reviews('x', expected)


# ---------------------------------------------------------------- cohort plumbing

def test_cohort_counts_report_hit_not_hit_and_ambiguous_against_the_incumbent(lab):
    cid, _ = lab.cohort(['WANT-SEO', 'WANT-GEO', 'WANT-GEO', 'WANT-NONE', 'WANT-AMBIG'])
    summary, code = lab.run_cohort(cid, FakeRunner())
    assert code == 0 and summary['labelsWritten'] == 5
    # incumbent is the seo skill: hit for WANT-SEO; not a hit for GEO-only, none and (excluded) ambiguity
    assert summary['counts'] == {'labeled': 5, 'ambiguous': 1, 'hit': 1, 'notHit': 3}
    assert summary['counts']['labeled'] == sum(summary['counts'][k] for k in ('ambiguous', 'hit', 'notHit'))
    for label in lab.labels():
        contract.validate_label(label)


def test_cohort_inclusion_probability_is_reserved_over_eligible_sessions(lab):
    reserved = [lab.add('disagree', marker='WANT-GEO') for _ in range(3)]
    for _ in range(2):
        lab.add('disagree', marker='WANT-GEO')                         # eligible, not reserved
    shared = lab.session()
    lab.add('disagree', marker='WANT-GEO', session=shared)
    lab.add('disagree', marker='WANT-GEO', session=shared)             # two records, one session
    lab.add('agree', marker='WANT-GEO')                                # not a disagreement: outside the frame
    cid = lab.reserve(reserved)
    summary, code = lab.run_cohort(cid, FakeRunner())
    assert code == 0 and summary['reserved'] == 3
    assert summary['inclusionProbability'] == pytest.approx(3 / 6)     # 3 + 2 + 1 eligible sessions
    assert [l['inclusionProbability'] for l in lab.labels()] == [pytest.approx(0.5)] * 3
    for label in lab.labels():
        contract.validate_label(label)


def test_the_cohort_frame_is_instrument_revision_policy_and_time(lab):
    reserved = [lab.add('disagree', marker='WANT-GEO') for _ in range(2)]
    for _ in range(2):
        lab.add('disagree', marker='WANT-GEO')
    unique = sl.unique_records(lab.root)
    reserve = {**COHORT_RESERVE, 'occurrenceKeys': [r['occurrenceKey'] for r in reserved], 'at': RESERVE_AT}
    assert sl.cohort_inclusion(unique, reserve) == pytest.approx(0.5)
    for other in ({'instrumentSha256': 'f' * 64}, {'layaRevision': 'ffffffffffff'}, {'policySha256': 'e' * 64},
                  {'at': '2026-10-05T11:00:00Z'}):                         # nothing eligible: probability 1
        assert sl.cohort_inclusion(unique, {**reserve, **other}) == 1.0
    sub_second = sl.cohort_inclusion(unique, {**reserve, 'at': '2026-10-05T12:59:59.999Z'})
    assert 0 < sub_second <= 1


def test_inclusion_probability_can_be_overridden(lab):
    cid, _ = lab.cohort(['WANT-GEO', 'WANT-GEO'])
    summary, _ = lab.run_cohort(cid, FakeRunner(), inclusion_probability=0.25)
    assert summary['inclusionProbability'] == 0.25 and {l['inclusionProbability'] for l in lab.labels()} == {0.25}


def test_limit_and_reruns_label_each_occurrence_exactly_once(lab):
    cid, recs = lab.cohort(['WANT-GEO'] * 4)
    runner = FakeRunner()
    first, _ = lab.run_cohort(cid, runner, limit=2)
    assert first['labelsWritten'] == 2 and first['toLabel'] == 4 and first['ready'] == 2 and first['counts']['labeled'] == 2
    second, code = lab.run_cohort(cid, runner)
    assert code == 0 and second['alreadyLabeled'] == 2 and second['toLabel'] == 2 and second['labelsWritten'] == 2
    calls = len(runner.calls)
    third, code = lab.run_cohort(cid, runner)
    assert code == 0 and third['status'] == 'nothing_to_do' and third['modelCalls'] == 0 and len(runner.calls) == calls
    assert sorted(l['occurrenceKey'] for l in lab.labels()) == sorted(r['occurrenceKey'] for r in recs)
    assert third['counts']['labeled'] == 4


def test_a_missing_transcript_gets_no_label_and_costs_no_model_call(lab):
    cid, recs = lab.cohort(['WANT-GEO'])
    ghost = lab.add('disagree', marker='WANT-GEO', write_transcript=False)
    cid = lab.reserve(recs + [ghost])
    runner = FakeRunner()
    summary, code = lab.run_cohort(cid, runner)
    assert code == 0 and summary['labelsWritten'] == 1 and summary['transcript_unavailable'] == 1
    assert cases_in(runner.calls[0]['prompt'])[0]['caseId'] == 'C001' and len(cases_in(runner.calls[0]['prompt'])) == 1
    alone = lab.add('disagree', marker='WANT-GEO', write_transcript=False)
    cid2 = lab.reserve([alone])
    calls = len(runner.calls)
    summary, code = lab.run_cohort(cid2, runner)
    assert code == 0 and summary['status'] == 'nothing_to_do' and summary['modelCalls'] == 0 and len(runner.calls) == calls


def test_an_unknown_or_consumed_cohort_aborts_before_any_call(lab):
    runner = FakeRunner()
    summary, code = lab.run_cohort(uuid.uuid4().hex, runner)
    assert code == 2 and summary['reason'] == 'cohort_not_found' and summary['modelCalls'] == 0
    cid, _ = lab.cohort(['WANT-GEO'])
    records.append(lab.root, 'skill-fit', 'cohorts', {**COHORT_CONSUMED, 'cohortId': cid})
    summary, code = lab.run_cohort(cid, runner)
    assert code == 2 and summary['reason'] == 'cohort_consumed' and runner.calls == [] and runner.preflights == []
    assert lab.labels() == []


def test_reserved_keys_without_records_are_counted_not_guessed(lab):
    cid, recs = lab.cohort(['WANT-GEO'])
    ghost_key = sha('no such occurrence')
    event = {**COHORT_RESERVE, 'cohortId': uuid.uuid4().hex, 'occurrenceKeys': [recs[0]['occurrenceKey'], ghost_key],
             'target': 2, 'at': RESERVE_AT}
    records.append(lab.root, 'skill-fit', 'cohorts', event)
    summary, code = lab.run_cohort(event['cohortId'], FakeRunner())
    assert code == 0 and summary['recordMissing'] == 1 and summary['labelsWritten'] == 1


def test_a_busy_labeler_exits_quietly(lab):
    cid, _ = lab.cohort(['WANT-GEO'])
    runner = FakeRunner()
    with evidence_fs.exclusive_lock(lab.root / 'skill-fit' / 'labeling' / 'run.lock') as held:
        assert held
        summary, code = lab.run_cohort(cid, runner)
    assert (summary, code) == ({'status': 'busy', 'modelCalls': 0}, 0) and runner.calls == []


# ---------------------------------------------------------------- failures and prepare-only

def test_prepare_only_builds_cases_but_makes_no_model_call_or_preflight(lab):
    cid, _ = lab.cohort(['WANT-GEO'] * 3)
    runner = FakeRunner()
    summary, code = lab.run_cohort(cid, runner, prepare_only=True)
    assert code == 0 and summary['status'] == 'prepared' and summary['ready'] == 3 and summary['modelCalls'] == 0
    assert runner.calls == [] and runner.preflights == [] and lab.labels() == []
    assert not list((lab.root / 'skill-fit' / 'labeling').glob('run-*'))
    pool, code = lab.run_pool(runner, prepare_only=True)
    assert code == 0 and pool['modelCalls'] == 0 and runner.calls == [] and runner.preflights == []


def test_prepare_only_through_the_cli_never_constructs_a_backend(lab, monkeypatch, capsys):
    cid, _ = lab.cohort(['WANT-GEO'] * 2)

    class Exploding:
        def __init__(self, *args, **kwargs):
            raise AssertionError('a backend must not be built for --prepare-only')

    monkeypatch.setattr(auto, 'CliBackend', Exploding)
    argv = ['--root', str(lab.root), '--transcripts', str(lab.transcripts), '--map', str(lab.map), '--prepare-only']
    assert sl.main(['label-cohort', '--cohort-id', cid, *argv]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)['status'] == 'prepared' and json.loads(out)['ready'] == 2
    lab.add('agree', marker='x')
    assert sl.main(['label-pool', '--n', '3', *argv]) == 0
    assert json.loads(capsys.readouterr().out)['modelCalls'] == 0


def test_a_failed_login_check_aborts_before_any_label_call(lab):
    cid, _ = lab.cohort(['WANT-GEO'])
    runner = FakeRunner(auth_error='claude_not_logged_in')
    summary, code = lab.run_cohort(cid, runner)
    assert code == 2 and summary['status'] == 'aborted' and summary['reason'] == 'claude_not_logged_in'
    assert runner.calls == [] and lab.labels() == []


def test_model_failures_leave_cases_unlabeled_for_the_next_run(lab):
    cid, _ = lab.cohort(['WANT-GEO', 'WANT-GEO'])
    summary, code = lab.run_cohort(cid, FakeRunner(fail='cli_failed'))
    assert code == 3 and summary['status'] == 'incomplete' and summary['annotationFailed'] == 2
    assert summary['unlabeled'] == 2 and lab.labels() == []
    summary, code = lab.run_cohort(cid, FakeRunner())
    assert code == 0 and summary['labelsWritten'] == 2 and summary['counts']['labeled'] == 2


def test_repeated_failures_stop_the_run_and_the_deadline_is_honoured(lab):
    recs = [lab.add('disagree', marker='WANT-GEO', extra='word ' * 800) for _ in range(6)]
    cid = lab.reserve(recs)
    runner = FakeRunner(fail='cli_failed')
    summary, code = lab.run_cohort(cid, runner, config={'packetBytes': 4096})
    assert code == 3 and summary['aborted'] == 1 and summary['modelCalls'] == auto.MAX_FAILED_CALLS_IN_A_ROW
    assert summary['notAttempted'] >= 1 and lab.labels() == []

    ticks = iter([0.0] + [10 ** 6] * 50)
    runner = FakeRunner()
    summary, code = lab.run_cohort(cid, runner, clock=lambda: next(ticks))
    assert code == 3 and summary['deadline'] >= 1 and summary['modelCalls'] == 0 and runner.calls == []


# ---------------------------------------------------------------- the default backend is private and temporary

def test_default_backend_runs_in_a_private_temp_dir_that_is_removed(lab, monkeypatch, capsys):
    cid, _ = lab.cohort(['WANT-GEO'])
    seen = {}

    class Backend(FakeRunner):
        def __init__(self, claude_bin, codex_bin, effort, workdir):
            super().__init__()
            seen['workdir'] = Path(workdir)
            seen['mode'] = stat.S_IMODE(Path(workdir).stat().st_mode)

    monkeypatch.setattr(auto, 'CliBackend', Backend)
    argv = ['label-cohort', '--cohort-id', cid, '--root', str(lab.root), '--transcripts', str(lab.transcripts),
            '--map', str(lab.map)]
    assert sl.main(argv) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['labelsWritten'] == 1 and summary['modelCalls'] == 2
    assert seen['mode'] == 0o700 and not seen['workdir'].exists()


def test_cli_reports_a_bad_pool_size_without_a_traceback(lab, capsys):
    assert sl.main(['label-pool', '--n', '-1', '--root', str(lab.root), '--transcripts', str(lab.transcripts)]) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'refused'


# ---------------------------------------------------------------- nothing sensitive is stored

def test_no_prompt_or_transcript_text_is_persisted_and_files_are_private(lab, capsys):
    cid, _ = lab.cohort(['WANT-GEO', 'WANT-SEO'])
    runner = FakeRunner(annotate=lambda host, case: choose(case, GEO_NAME) if host == 'claude' else choose(case, SEO_NAME))
    summary, code = lab.run_cohort(cid, runner)
    assert code == 0 and summary['labelsWritten'] == 2
    stored = all_text(lab.root)
    for needle in (SENTINEL, SECRET_TOKEN, SECRET_EMAIL, 'Please look at this', 'REDACTED', 'fixture', 'no single'):
        assert needle not in stored.replace('fixtures', ''), needle
    for path in (lab.root / 'skill-fit').rglob('*'):
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == (0o700 if path.is_dir() else 0o600), (path, oct(mode))
    printed = json.dumps(summary)
    assert SENTINEL not in printed and 'Please look' not in printed


# ---------------------------------------------------------------- the scoreboard pool

def pool_world(lab, per_stratum=5):
    for _ in range(per_stratum):
        lab.add('disagree', marker='WANT-GEO')
        lab.add('agree', marker='WANT-SEO')
        lab.add('silent', marker='WANT-GEO')
    return lab


def test_pool_stratum_rules(lab):
    expectations = {'disagree': 'disagreement', 'agree': 'agreement', 'silent': 'silent_laya_pick',
                    'silent_none': None, 'skipped': None}
    for kind, stratum in expectations.items():
        assert sl.pool_stratum(lab.add(kind, marker='x')) == stratum, kind
    unavailable = copy.deepcopy(RECORDS['backfill-fired'])
    unavailable['laya'] = {'status': 'timeout', 'choice': None, 'latencyMs': None, 'truncated': None, 'probabilities': None}
    assert sl.pool_stratum(unavailable) is None


def test_allocation_spreads_evenly_and_moves_surplus_to_larger_strata():
    assert sl.allocate(12, {'disagreement': 100, 'agreement': 100, 'silent_laya_pick': 100}) == {
        'disagreement': 4, 'agreement': 4, 'silent_laya_pick': 4}
    assert sl.allocate(12, {'disagreement': 2, 'agreement': 100, 'silent_laya_pick': 100}) == {
        'disagreement': 2, 'agreement': 5, 'silent_laya_pick': 5}
    assert sl.allocate(12, {'disagreement': 1, 'agreement': 0, 'silent_laya_pick': 3}) == {
        'disagreement': 1, 'agreement': 0, 'silent_laya_pick': 3}
    assert sl.allocate(0, {'disagreement': 5}) == {'disagreement': 0, 'agreement': 0, 'silent_laya_pick': 0}


def test_pool_samples_each_stratum_with_one_case_per_session_and_valid_labels(lab):
    pool_world(lab)
    # two extra cases in one disagreement session make its inclusion probability smaller
    crowded = lab.session()
    for _ in range(3):
        lab.add('disagree', marker='WANT-GEO', session=crowded)
    runner = FakeRunner()
    summary, code = lab.run_pool(runner, n=6, seed='fixed')
    assert code == 0 and summary['sampled'] == {'disagreement': 2, 'agreement': 2, 'silent_laya_pick': 2}
    labels = lab.labels()
    assert len(labels) == 6 and summary['labelsWritten'] == 6
    by_key = {r['occurrenceKey']: r for r in sl.unique_records(lab.root)}
    assert len({by_key[l['occurrenceKey']]['sessionHash'] for l in labels}) == 6           # at most one per session
    assert {l['stratum'] for l in labels} == set(sl.POOL_STRATA)
    assert all(l['cohortId'] is None and l['basis'] == 'ai_model_reviewed' for l in labels)
    for label in labels:
        contract.validate_label(label)
        stratum = label['stratum']
        sessions = {}
        for record in by_key.values():
            if sl.pool_stratum(record) == stratum:
                sessions.setdefault(record['sessionHash'], []).append(record)
        in_session = len(sessions[by_key[label['occurrenceKey']]['sessionHash']])
        assert label['inclusionProbability'] == pytest.approx((2 / len(sessions)) * (1 / in_session))
        assert label['inclusionProbability'] <= 1
    assert summary['eligibleSessions'] == {'disagreement': 6, 'agreement': 5, 'silent_laya_pick': 5}


def test_pool_is_deterministic_for_a_seed_and_never_a_cohort_label(lab):
    pool_world(lab)
    first, _ = lab.run_pool(FakeRunner(), n=6, seed='abc', prepare_only=True)
    second, _ = lab.run_pool(FakeRunner(), n=6, seed='abc', prepare_only=True)
    assert first == second
    items_a, _ = sl.sample_pool(sl.unique_records(lab.root), set(), [], 6, 'abc')
    items_b, _ = sl.sample_pool(sl.unique_records(lab.root), set(), [], 6, 'abc')
    items_c, _ = sl.sample_pool(sl.unique_records(lab.root), set(), [], 6, 'other')
    keys = lambda items: [i['record']['occurrenceKey'] for i in items]       # noqa: E731
    assert keys(items_a) == keys(items_b) and keys(items_a) != keys(items_c)
    assert all(i['cohortId'] is None for i in items_a)


def test_the_same_day_pool_run_spends_nothing_and_top_ups_add_only_the_difference(lab):
    pool_world(lab)
    runner = FakeRunner()
    first, _ = lab.run_pool(runner, n=6, seed='s')
    assert first['labelsWritten'] == 6
    calls = len(runner.calls)
    again, code = lab.run_pool(runner, n=6, seed='s')
    assert code == 0 and again['status'] == 'nothing_to_do' and again['modelCalls'] == 0 and len(runner.calls) == calls
    assert again['labeledToday'] == 6 and again['sampled'] == {}
    top_up, code = lab.run_pool(runner, n=9, seed='s')
    assert code == 0 and top_up['sampled'] == {'disagreement': 1, 'agreement': 1, 'silent_laya_pick': 1}
    labels = lab.labels()
    by_key = {r['occurrenceKey']: r for r in sl.unique_records(lab.root)}
    assert len(labels) == 9 and len({l['occurrenceKey'] for l in labels}) == 9
    assert len({by_key[l['occurrenceKey']]['sessionHash'] for l in labels}) == 9           # new sessions only


def test_the_pool_never_relabels_an_occurrence_on_a_later_day(lab):
    pool_world(lab, per_stratum=3)
    runner = FakeRunner()
    lab.run_pool(runner, n=3, seed='s')
    first_keys = {l['occurrenceKey'] for l in lab.labels()}
    assert len(first_keys) == 3
    summary, code = lab.run_pool(runner, n=3, seed='s', today='2099-01-01')       # a later UTC day
    assert code == 0 and summary['labeledToday'] == 0 and summary['labelsWritten'] == 3
    second_keys = {l['occurrenceKey'] for l in lab.labels()} - first_keys
    assert len(second_keys) == 3 and not (second_keys & first_keys)


def test_cohort_labels_exclude_those_occurrences_from_the_pool(lab):
    cid, recs = lab.cohort(['WANT-GEO'] * 3)
    lab.run_cohort(cid, FakeRunner())
    summary, _ = lab.run_pool(FakeRunner(), n=6, prepare_only=True)
    assert summary['eligibleSessions']['disagreement'] == 0 and summary['sampled'] == {}


def test_pool_size_must_be_a_non_negative_integer(lab):
    for bad in (-1, 1.5, True, '3'):
        with pytest.raises(sl.LabelError):
            lab.run_pool(FakeRunner(), n=bad)
    summary, code = lab.run_pool(FakeRunner(), n=0)
    assert code == 0 and summary['status'] == 'nothing_to_do'


def test_failed_skillfit_call_reports_reason_and_keeps_only_failure_evidence(lab, monkeypatch):
    cid, _ = lab.cohort(['WANT-GEO'])
    seen = {}
    class Backend(FakeRunner):
        def __init__(self, claude_bin, codex_bin, effort, workdir):
            super().__init__(fail='claude_exit_1')
            seen['workdir'] = Path(workdir)
            call = seen['workdir'] / 'call-001-claude'
            call.mkdir(mode=0o700)
            auto.write_json(call / 'failure.json', {'error': 'claude_exit_1'})
            (call / 'auth.json').write_text('TRANSIENT-CREDENTIAL')
    monkeypatch.setattr(auto, 'CliBackend', Backend)
    summary, code = lab.run_cohort(cid, runner=None)
    assert code == 3 and summary['callFailures'] == {'claude_exit_1': 1}
    assert not seen['workdir'].exists()
    archived = list((seen['workdir'].parent / 'failed').rglob('failure.json'))
    assert len(archived) == 1 and json.loads(archived[0].read_text()) == {'error': 'claude_exit_1'}
    assert not list((seen['workdir'].parent / 'failed').rglob('auth.json'))


def test_failure_archive_refuses_symlink_without_copying_or_destroying_it(tmp_path):
    backend, cleanup = sl.start_runner(None, {'claudeBin': None, 'codexBin': None, 'effort': 'high'}, tmp_path)
    call = backend.workdir / 'call-001-claude'
    call.mkdir()
    secret = tmp_path / 'private-credential'
    secret.write_text('PRIVATE-CREDENTIAL')
    (call / 'failure.json').symlink_to(secret)
    with pytest.raises(sl.LabelError, match='unsafe_failure_evidence'):
        cleanup()
    assert (call / 'failure.json').is_symlink() and secret.read_text() == 'PRIVATE-CREDENTIAL'
    assert not (backend.workdir.parent / 'failed').exists()
