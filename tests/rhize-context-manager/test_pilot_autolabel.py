"""Daily AI labeler: invented fixtures, fake backends and temp directories only.

No test starts a real model CLI, touches the network or writes below ~/.local/share/rhize.
"""
import errno
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import time

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
import decision_pilot as pilot
import decision_pilot_v2 as v2
import pilot_autolabel as auto
import pilot_labels as labels
import workflow_selection as workflow
import workflow_task_context as context

DIGEST_FILES = ('decision_pilot_v2.py', 'decision_pilot.py', 'workflow_selection.py', 'workflow_task_context.py',
                'pilot_routing.py', 'context_experiments/typed_relevance.py')
SESSION = '0f1e2d3c-4b5a-4968-8778-a1b2c3d4e5f6'
OTHER_SESSION = '9a8b7c6d-5e4f-4321-8fed-cba987654321'
ALLOWED_PACKET_KEYS = {'caseId', 'prompt', 'promptTruncated', 'precedingContext', 'role', 'text', 'truncated'}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make(tmp_path, prompt, *, session=SESSION, turn=None, kind='new_task', domain='software', action='implement',
         exclusions=None):
    receipts, root = tmp_path / 'receipts', tmp_path / 'pilot'
    receipt, _ = workflow.opportunity({'prompt': prompt, 'session_id': session, 'turn_id': turn or prompt[:24]},
        'codex', receipts, {'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}})
    evidence = {'schemaVersion': context.SCHEMA, 'opportunityId': receipt['opportunityId'],
                'promptHash': receipt['promptHash'], 'sessionHash': receipt['sessionHash'],
                'eventKind': kind, 'action': action, 'domain': domain, 'exclusions': exclusions or [],
                'parentOpportunityId': None, 'preboundFamily': None}
    context.capture_context(receipts, receipt['opportunityId'], evidence,
        seal=lambda c, r: pilot.enqueue_v2(c, r, root, spawn=False, receipts=receipts))
    return root, receipts, receipt


def source(root, receipt):
    return workflow.read_json(root / 'v2/observations' / (receipt['opportunityId'] + '.json'))['sourceSha256']


def label_value(root, receipt, **overrides):
    base = {'schema': labels.LABEL_SCHEMA, 'opportunityId': receipt['opportunityId'],
            'sourceSha256': source(root, receipt), 'taxonomyVersion': labels.TAXONOMY_VERSION,
            'basis': labels.AI, 'family': 'feature_delivery', 'phase': 'implement', 'areas': ['backend_api'],
            'stratum': 'routine', 'riskFlags': [], 'choice': 'general', 'choiceBasis': labels.FAMILY_MAP,
            'reviewer': 'ai-review-fixture', 'reviewEvidenceSha256': 'c' * 64}
    return {**base, **overrides}


def line(role, text, when, codex):
    if codex:
        kind = 'input_text' if role == 'user' else 'output_text'
        return {'type': 'response_item', 'timestamp': when,
                'payload': {'type': 'message', 'role': role, 'content': [{'type': kind, 'text': text}]}}
    return {'type': role, 'timestamp': when, 'message': {'role': role, 'content': text}}


def transcript(tmp_path, session, turns, codex=False):
    """turns: (role, text) pairs in order. Claude and Codex layouts differ; both are supported."""
    if codex:
        path = tmp_path / 'transcripts/codex/2026/09/29' / ('rollout-2026-09-29T10-00-00-' + session + '.jsonl')
    else:
        path = tmp_path / 'transcripts/claude/-proj' / (session + '.jsonl')
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [line(role, text, '2026-09-29T14:00:%02dZ' % n, codex) for n, (role, text) in enumerate(turns)]
    path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
    return path


ANSWER = {'status': 'labeled', 'family': 'feature_delivery', 'phase': 'implement', 'areas': ['backend_api'],
          'stratum': 'routine', 'riskFlags': [], 'choice': 'general'}
EMPTY = {'status': 'insufficient_context', 'family': None, 'phase': None, 'areas': [], 'stratum': None,
         'riskFlags': [], 'choice': None}


def cases_in(prompt):
    return json.loads(prompt.split('# Cases\n\n', 1)[1])


class FakeBackend:
    """Stands in for the two CLIs. `annotate(host, case)` and `review(case)` shape each answer."""

    def __init__(self, annotate=None, review=None, clock=None, step=0, auth_error=None):
        self.annotate_fn = annotate or (lambda host, case: dict(ANSWER))
        self.review_fn = review or (lambda case: {'verdict': 'accept', 'reason': 'agreed', 'final': dict(ANSWER)})
        self.clock, self.step, self.auth_error = clock, step, auth_error
        self.calls, self.preflights, self.rationale = [], [], 'fixture'

    def preflight(self, host):
        self.preflights.append(host)
        if self.auth_error:
            raise auto.LabelerError(self.auth_error)
        return {'host': host, 'path': '/fake/' + host, 'version': '0.0.0', 'sha256': '0' * 64}

    def call(self, host, model, system, prompt, schema, timeout):
        self.calls.append({'host': host, 'model': model, 'system': system, 'prompt': prompt, 'schema': schema,
                           'timeout': timeout})
        if self.clock:
            self.clock.advance(self.step)
        cases = cases_in(prompt)
        if 'answers' in schema['properties']:
            answer = {'answers': [{'caseId': c['caseId'], **self.annotate_fn(host, c), 'rationale': self.rationale}
                                  for c in cases]}
        else:
            answer = {'reviews': [{'caseId': c['caseId'], **self.review_fn(c)} for c in cases]}
        return {'answer': answer, 'raw': json.dumps(answer), 'requestedModel': model, 'observedModel': model,
                'identitySource': self.identity_for(host), 'usage': {}}

    def identity_for(self, host):
        return 'native_model_usage' if host == 'claude' else 'explicit_cli_argument'

    def kinds(self):
        return [(c['host'], 'answers' in c['schema']['properties']) for c in self.calls]


def config_for(tmp_path, **overrides):
    return auto.merge_config(auto.DEFAULTS, {
        'root': tmp_path / 'pilot', 'receipts': tmp_path / 'receipts', 'state': tmp_path / 'state',
        'transcriptRoots': [tmp_path / 'transcripts/claude', tmp_path / 'transcripts/codex'], **overrides})


def go(tmp_path, backend, clock=None, **options):
    overrides = options.pop('config', {})
    return auto.execute(config_for(tmp_path, **overrides), backend=backend, clock=clock or Clock(), **options)


def stored(root):
    return {label['opportunityId']: label for label in labels.load_labels(root)}


def read_run_file(summary, name):
    return json.loads((Path(summary['runDir']) / name).read_text())


# ---- structure -------------------------------------------------------------------------------

def test_module_stays_outside_collection_source_digest():
    before = v2.source_digest()
    joined = b''.join((SCRIPTS / name).read_bytes() for name in DIGEST_FILES)
    assert before == workflow.digest(joined)
    assert b'pilot_autolabel' not in joined and b'pilot_labels' not in joined


def test_config_is_validated_and_models_are_configurable():
    config = auto.merge_config(auto.DEFAULTS, {})
    assert (config['claudeModel'], config['codexModel'], config['reviewerModel']) == (
        'claude-sonnet-5-5', 'gpt-5.6-sol', 'claude-fable-5-1')
    assert auto.merge_config(auto.DEFAULTS, {'codexModel': 'gpt-6-luna'})['codexModel'] == 'gpt-6-luna'
    for bad in ({'unknown': 1}, {'maxCases': 0}, {'deadlineSeconds': 5}, {'reviewerModel': 'gpt-5'},
                {'codexModel': 'claude-x'}, {'effort': 'extreme'}):
        with pytest.raises(auto.LabelerError):
            auto.merge_config(auto.DEFAULTS, bad)


# ---- selection and context recovery ------------------------------------------------------------

def test_selection_takes_only_eligible_cases_without_an_explicit_label(tmp_path):
    root, receipts, fresh = make(tmp_path, 'fresh request one')
    _, _, derived = make(tmp_path, 'derived label request')
    _, _, explicit = make(tmp_path, 'explicit label request')
    _, _, human = make(tmp_path, 'human label request')
    _, _, status = make(tmp_path, 'status request', kind='status')
    labels.record_label(root, receipts, label_value(root, derived), 'a' * 64)
    labels.record_label(root, receipts, label_value(root, explicit, choiceBasis='explicit'), 'a' * 64)
    labels.record_label(root, receipts, label_value(root, human, basis=labels.HUMAN, reviewer='jim'), 'a' * 64)
    ids = [row['id'] for row in auto.candidates(root, receipts)]
    assert sorted(ids) == sorted([fresh['opportunityId'], derived['opportunityId']])


def test_packets_recover_context_by_hash_and_carry_only_the_redacted_request(tmp_path):
    prompt = 'Write the launch article. Contact me at jim@example.test with key sk-ant-abcdefghijklmnop1234'
    root, receipts, receipt = make(tmp_path, prompt)
    other = 'A different prompt from another session'
    make(tmp_path, other, session=OTHER_SESSION)
    transcript(tmp_path, SESSION, [
        ('user', 'turn one'), ('assistant', 'assistant prose is never context'), ('user', 'turn three'),
        ('user', 'Arm A chose the content family for this one'), ('user', 'turn five'), ('user', 'turn six'),
        ('assistant', 'more assistant prose'), ('user', 'turn eight'), ('user', prompt),
        ('assistant', 'the later answer is never included')], codex=True)
    transcript(tmp_path, OTHER_SESSION, [('user', other)])
    config = config_for(tmp_path)
    cases, skipped = auto.prepare_cases(root, receipts, lambda w: auto.TranscriptIndex(config['transcriptRoots'], w),
                                        {}, 'f' * 64, {**config, 'force': False})
    assert skipped == {} and [c['contextStatus'] for c in cases] == ['ok', 'ok']
    case = next(c for c in cases if c['opportunityId'] == receipt['opportunityId'])
    packet = case['packet']
    assert set(packet) == {'prompt', 'promptTruncated', 'precedingContext'}
    assert 'jim@example.test' not in packet['prompt'] and 'sk-ant-abcdefghijklmnop1234' not in packet['prompt']
    assert '[REDACTED_EMAIL]' in packet['prompt'] and '[REDACTED_TOKEN]' in packet['prompt']
    # At most four prior USER turns, most recent last; the turn that discussed an arm is dropped whole and
    # assistant prose (which restates pilot results) never appears.
    texts = [t['text'] for t in packet['precedingContext']]
    assert texts == ['turn three', 'turn five', 'turn six', 'turn eight']
    assert all(set(t) == {'role', 'text', 'truncated'} and t['role'] == 'user' for t in packet['precedingContext'])
    assert 'later answer' not in json.dumps(packet) and 'assistant prose' not in json.dumps(packet)


def test_claude_layout_and_long_text_are_bounded(tmp_path):
    prompt = 'Explain this: ' + 'x' * 8000
    root, receipts, receipt = make(tmp_path, prompt[:15000])
    transcript(tmp_path, SESSION, [('user', 'z' * 9000), ('user', prompt[:15000])])
    config = config_for(tmp_path)
    cases, _ = auto.prepare_cases(root, receipts, lambda w: auto.TranscriptIndex(config['transcriptRoots'], w),
                                  {}, 'f' * 64, {**config, 'force': False})
    packet = cases[0]['packet']
    assert packet['promptTruncated'] is True and len(packet['prompt']) < auto.PROMPT_LIMIT + 100
    assert packet['precedingContext'][0]['truncated'] is True
    assert packet['precedingContext'][0]['text'].endswith('more source context exists]')


def test_recovery_needs_both_hashes_and_refuses_ambiguous_repeats(tmp_path):
    prompt = 'ship it'
    root, receipts, receipt = make(tmp_path, prompt)
    config = config_for(tmp_path)

    def prepare():
        return auto.prepare_cases(root, receipts, lambda w: auto.TranscriptIndex(config['transcriptRoots'], w),
                                  {}, 'f' * 64, {**config, 'force': False})[0][0]
    assert prepare()['contextStatus'] == 'context_missing'
    transcript(tmp_path, OTHER_SESSION, [('user', prompt)])          # right text, wrong session
    assert prepare()['contextStatus'] == 'context_missing'
    transcript(tmp_path, SESSION, [('user', 'something else')])      # right session, wrong text
    assert prepare()['contextStatus'] == 'context_missing'
    transcript(tmp_path, SESSION, [('user', 'first context'), ('user', prompt), ('user', 'second context'),
                                   ('user', prompt)])
    assert prepare()['contextStatus'] == 'context_ambiguous'         # same prompt twice, different history


def test_missing_context_records_insufficient_context_without_any_model_call(tmp_path):
    root, receipts, receipt = make(tmp_path, 'no transcript exists for this one')
    backend = FakeBackend(auth_error='must_not_be_asked')
    summary, code = go(tmp_path, backend)
    assert code == 0 and summary['status'] == 'completed' and summary['outcomes'] == {'context_missing': 1}
    assert backend.calls == [] and backend.preflights == []
    record = read_run_file(summary, 'annotations.json')[0]
    assert record['status'] == 'insufficient_context' and record['detail'] == 'context_missing'
    assert record['family'] is None and record['areas'] == [] and record['review'] is None
    assert summary['import']['skipped'] == {'status_insufficient_context': 1}
    assert labels.load_labels(root) == []
    again, code = go(tmp_path, backend)
    assert code == 0 and again['status'] == 'nothing_to_do' and again['skipped'] == {'already_attempted': 1}


def test_cap_counts_model_ready_cases_and_orders_oldest_first(tmp_path):
    root, receipts, _ = make(tmp_path, 'request number 0', turn='t0')
    prompts = ['request number %d' % n for n in range(4)]
    for n, prompt in enumerate(prompts[1:], 1):
        make(tmp_path, prompt, turn='t%d' % n)
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])
    summary, code = go(tmp_path, FakeBackend(), no_import=True, config={'maxCases': 2})
    assert code == 0 and summary['selected'] == 2 and summary['skipped'] == {'beyond_cap': 2}


# ---- packets never carry routing artifacts -------------------------------------------------------

def test_annotator_prompts_hold_only_whitelisted_packet_keys_and_no_pilot_artifacts(tmp_path):
    root, receipts, receipt = make(tmp_path, 'Please draft the release notes article')
    # Arm A, a consultation, an Arm B score and a label all exist for this decision.
    observation = workflow.read_json(root / 'v2/observations' / (receipt['opportunityId'] + '.json'))
    result = v2.assess(observation, receipts, lambda url, request: ({
        'routing': {'model': 'typed-decisions'}, 'usage': {'input_tokens': 3, 'output_tokens': 0},
        'answers': {'c%d' % i: {'type': 'noul', 'noul': n} for i, n in enumerate((0.91, 0.05, 0.04))}}, 1.5), root=root)
    pilot.save_once(root / 'v2/results', receipt['opportunityId'], result)
    evidence = tmp_path / 'consult-evidence'
    evidence.write_text('invented lookup result')
    context.capture_consultation(receipts, receipt['opportunityId'], 'content', evidence)
    labels.record_label(root, receipts, label_value(root, receipt), 'a' * 64)
    row = next(r for r in v2.joined(root, receipts) if r['id'] == receipt['opportunityId'])
    assert row['armA'] == 'content' and row['armB'] == 'content' and row['bucket'] == 'eligible'
    transcript(tmp_path, SESSION, [('user', 'Please draft the release notes article')])
    backend = FakeBackend()
    summary, code = go(tmp_path, backend, no_import=True, force=True)
    assert code == 0 and backend.calls
    forbidden = [receipt['opportunityId'], receipt['promptHash'], receipt['sessionHash'], source(root, receipt),
                 'armA', 'armB', 'scores', '0.91', 'consult', 'questions', 'reviewEvidence', 'choiceBasis',
                 'derived:family-map-v1', 'ai-review-fixture']
    for call in backend.calls:
        data = call['prompt'].split('# Cases\n\n', 1)[1]
        for token in forbidden:
            assert token not in data
        def keys(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key
                    yield from keys(item)
            elif isinstance(value, list):
                for item in value:
                    yield from keys(item)
        found = set(keys(json.loads(data)))
        assert found <= ALLOWED_PACKET_KEYS | {'proposals', 'status', 'family', 'phase', 'areas', 'stratum',
                                               'riskFlags', 'choice', 'rationale'}, found
        if 'answers' in call['schema']['properties']:
            assert found <= ALLOWED_PACKET_KEYS
    packets = read_run_file(summary, 'packets.json')
    assert set(packets[0]) == {'caseId', 'prompt', 'promptTruncated', 'precedingContext'}


# ---- annotation, review and import ---------------------------------------------------------------

def three_cases(tmp_path):
    prompts = {'accept': 'add a filter to the reports table', 'revise': 'why does the cron job fail',
               'unresolved': 'improve the thing'}
    made = {name: make(tmp_path, prompt, turn=name) for name, prompt in prompts.items()}
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts.values()])
    root, receipts = made['accept'][0], made['accept'][1]
    return root, receipts, {name: value[2] for name, value in made.items()}, prompts


def test_agreement_review_and_supersession_end_to_end(tmp_path):
    root, receipts, receipts_by, prompts = three_cases(tmp_path)
    old = receipts_by['accept']
    labels.record_label(root, receipts, label_value(root, old), 'a' * 64)     # derived: to be superseded
    labels.set_policy(root, True, 'fixture', 'jim')

    def annotate(host, case):
        if 'improve the thing' in case['prompt']:
            return {**ANSWER, 'choice': 'general' if host == 'claude' else 'none'}
        if 'cron job' in case['prompt']:
            return {**ANSWER, 'family': 'defect_resolution', 'phase': 'triage', 'areas': ['automation_integrations']}
        return dict(ANSWER)

    def review(case):
        if 'cron job' in case['prompt']:
            return {'verdict': 'revise', 'reason': 'elevated: shared cron', 'final': {
                **ANSWER, 'family': 'defect_resolution', 'phase': 'triage', 'areas': ['automation_integrations'],
                'stratum': 'elevated', 'riskFlags': ['production_availability'], 'choice': 'none'}}
        return {'verdict': 'accept', 'reason': 'agreed', 'final': dict(ANSWER)}

    backend = FakeBackend(annotate=annotate, review=review)
    summary, code = go(tmp_path, backend)
    assert code == 0 and summary['status'] == 'completed'
    assert summary['outcomes'] == {'labeled': 2, 'unresolved': 1}
    assert summary['import']['results'] == {'recorded': 1, 'superseded': 1}
    assert summary['import']['skipped'] == {'status_checker_disagreement': 1}
    by_id = stored(root)
    accept, revise = by_id[old['opportunityId']], by_id[receipts_by['revise']['opportunityId']]
    assert accept['choice'] == 'general' and accept['choiceBasis'] == 'explicit' and accept['basis'] == labels.AI
    assert accept['reviewer'] == 'ai-review-claude-fable-5-1'
    assert revise['stratum'] == 'elevated' and revise['choice'] == 'none' and revise['riskFlags'] == ['production_availability']
    assert receipts_by['unresolved']['opportunityId'] not in by_id
    # The derived label was moved, not deleted.
    archived = list((root / labels.SUPERSEDED_DIR).glob('*.json'))
    assert len(archived) == 1 and json.loads(archived[0].read_text())['choiceBasis'] == labels.FAMILY_MAP
    report = labels.report(root)
    assert report['researchUsable'] == 2 and report['superseded'] == 1
    # Two annotators per batch, then one Claude reviewer call, all with the configured models.
    assert backend.kinds() == [('claude', True), ('codex', True), ('claude', False)]
    assert [c['model'] for c in backend.calls] == ['claude-sonnet-5-5', 'gpt-5.6-sol', 'claude-fable-5-1']
    # The compiled records are exactly what the importer consumes.
    records = read_run_file(summary, 'annotations.json')
    assert {r['status'] for r in records} == {'labeled', 'checker_disagreement'}
    for record in records:
        assert record['schema'] == labels.BATCH_SCHEMA and record['humanAdjudicated'] is False
        assert record['basis'] == 'ai_generated_model_reviewed' and record['taxonomySha256'] == summary['taxonomySha256']
        if record['status'] == 'labeled':
            value, reason = labels.batch_label(record)
            assert reason is None and value['choiceBasis'] == 'explicit' and value['basis'] == labels.AI
            assert record['review']['actuallyRan'] is True and record['review']['observedModel'] == 'claude-fable-5-1'
            assert [a['provider'] for a in record['annotators']] == ['claude', 'codex']
    # Human labels are never created by the pipeline and the legacy store is untouched.
    assert all(label['basis'] == labels.AI for label in by_id.values()) and not (root / 'v2/labels').exists()


def test_annotator_disagreement_never_reaches_the_reviewer_or_a_label(tmp_path):
    root, receipts, receipt = make(tmp_path, 'do the thing')
    transcript(tmp_path, SESSION, [('user', 'do the thing')])
    backend = FakeBackend(annotate=lambda host, case: {**ANSWER, 'stratum': 'routine' if host == 'claude' else 'elevated'})
    summary, code = go(tmp_path, backend)
    assert code == 0 and summary['outcomes'] == {'unresolved': 1}
    assert backend.kinds() == [('claude', True), ('codex', True)]
    assert labels.load_labels(root) == []
    assert read_run_file(summary, 'annotations.json')[0]['status'] == 'checker_disagreement'


def test_reviewer_unresolved_and_agreed_non_labels_are_kept_without_labels(tmp_path):
    prompts = ['maybe do something', '<task-notification> background job finished', 'and also that one']
    made = [make(tmp_path, prompt, turn='t%d' % n) for n, prompt in enumerate(prompts)]
    root, receipts = made[0][0], made[0][1]
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])

    def annotate(host, case):
        if 'task-notification' in case['prompt']:
            return {**EMPTY, 'status': 'excluded_operational'}
        return dict(ANSWER)
    backend = FakeBackend(annotate=annotate, review=lambda case: {
        'verdict': 'unresolved', 'reason': 'not enough context', 'final': dict(EMPTY, status='needs_split')})
    summary, code = go(tmp_path, backend)
    assert code == 0 and summary['outcomes'] == {'excluded_operational': 1, 'unresolved': 2}
    assert labels.load_labels(root) == []
    statuses = sorted(r['status'] for r in read_run_file(summary, 'annotations.json'))
    assert statuses == ['checker_disagreement', 'checker_disagreement', 'excluded_operational']


def test_reviewer_accept_must_match_the_agreed_classification(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    backend = FakeBackend(review=lambda case: {'verdict': 'accept', 'reason': 'ok', 'final': {**ANSWER, 'choice': 'none'}})
    summary, code = go(tmp_path, backend)
    assert code == 3 and summary['outcomes'] == {'review_failed': 1} and labels.load_labels(root) == []


def test_no_import_writes_only_the_private_run_directory(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    summary, code = go(tmp_path, FakeBackend(), no_import=True)
    assert code == 0 and 'import' not in summary
    assert not (root / labels.LABEL_DIR).exists() and not (tmp_path / 'state' / auto.LEDGER).exists()
    records = read_run_file(summary, 'annotations.json')
    assert records[0]['status'] == 'labeled' and records[0]['choice'] == 'general'
    # Inspecting a --no-import run and importing that same file later works and supersedes.
    result = labels.import_batch(root, receipts, Path(summary['runDir']) / 'annotations.json', supersede=True)
    assert result['results'] == {'recorded': 1}
    # It did not consume the attempt, so the next pass would select the case again unless labeled.
    assert auto.candidates(root, receipts) == []


def test_run_directory_is_private(tmp_path):
    make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    summary, _ = go(tmp_path, FakeBackend())
    run_dir = Path(summary['runDir'])
    for directory in (tmp_path / 'state', tmp_path / 'state/runs', run_dir, run_dir / 'calls'):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    files = [run_dir / name for name in ('summary.json', 'manifest.json', 'packets.json', 'annotations.json')]
    files += list((run_dir / 'calls').glob('*.json')) + [tmp_path / 'state' / auto.LEDGER, tmp_path / 'state' / auto.LATEST]
    assert len(files) >= 8 and all(stat.S_IMODE(f.stat().st_mode) == 0o600 for f in files)
    assert auto.status(tmp_path / 'state')['runId'] == summary['runId']


# ---- attempt ledger ----------------------------------------------------------------------------

def test_unchanged_packet_is_not_attempted_again_but_changed_packet_and_force_are(tmp_path):
    root, receipts, receipt = make(tmp_path, 'do the thing')
    transcript(tmp_path, SESSION, [('user', 'do the thing')])
    disagree = FakeBackend(annotate=lambda host, case: {**ANSWER, 'choice': 'general' if host == 'claude' else 'none'})
    first, _ = go(tmp_path, disagree)
    assert first['outcomes'] == {'unresolved': 1} and len(disagree.calls) == 2
    second_backend = FakeBackend()
    second, code = go(tmp_path, second_backend)
    assert code == 0 and second['status'] == 'nothing_to_do' and second['skipped'] == {'already_attempted': 1}
    assert second_backend.calls == []
    # Earlier context changed: a different packet is a different attempt.
    transcript(tmp_path, SESSION, [('user', 'new earlier turn'), ('user', 'do the thing')])
    third_backend = FakeBackend(annotate=lambda host, case: {**ANSWER, 'choice': 'general' if host == 'claude' else 'none'})
    third, _ = go(tmp_path, third_backend)
    assert len(third_backend.calls) == 2 and third['outcomes'] == {'unresolved': 1}
    forced_backend = FakeBackend()
    forced, _ = go(tmp_path, forced_backend, force=True)
    assert len(forced_backend.calls) == 3 and forced['outcomes'] == {'labeled': 1}


def test_repeated_malformed_output_is_retried_then_left_alone(tmp_path):
    root, receipts, receipt = make(tmp_path, 'do the thing')
    transcript(tmp_path, SESSION, [('user', 'do the thing')])
    bad = FakeBackend(annotate=lambda host, case: {**ANSWER, 'family': 'not_a_family'})
    for attempt in range(auto.MAX_ATTEMPTS):
        summary, code = go(tmp_path, bad)
        assert code == 3 and summary['status'] == 'incomplete' and summary['outcomes'] == {'annotation_failed': 1}
    assert labels.load_labels(root) == []
    idle, code = go(tmp_path, FakeBackend())
    assert code == 0 and idle['skipped'] == {'already_attempted': 1}


def test_an_overlapping_pass_exits_without_touching_anything(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    (tmp_path / 'state').mkdir()
    with open(tmp_path / 'state' / 'run.lock', 'w') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backend = FakeBackend()
        summary, code = go(tmp_path, backend)
    assert code == 0 and summary['status'] == 'busy' and backend.calls == []
    assert not (tmp_path / 'state' / 'runs').exists() and labels.load_labels(root) == []
    assert go(tmp_path, FakeBackend())[0]['status'] == 'completed'          # the lock is released afterwards


# ---- fail closed ---------------------------------------------------------------------------------

@pytest.mark.parametrize('reason', ['subscription_login_missing:codex', 'binary_missing:claude'])
def test_missing_login_or_binary_aborts_before_any_model_call(tmp_path, reason):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    backend = FakeBackend(auth_error=reason)
    summary, code = go(tmp_path, backend)
    assert code == 2 and summary['status'] == 'aborted' and summary['reason'] == reason
    assert backend.calls == [] and backend.preflights == ['claude']
    assert labels.load_labels(root) == [] and not (tmp_path / 'state' / auto.LEDGER).exists()
    assert not (Path(summary['runDir']) / 'annotations.json').exists()


def test_hard_deadline_stops_new_calls_and_keeps_finished_cases(tmp_path):
    prompts = ['first request ' + 'a' * 3400, 'second request ' + 'b' * 3400, 'third request ' + 'c' * 3400]
    made = [make(tmp_path, prompt, turn='t%d' % n) for n, prompt in enumerate(prompts)]
    root, receipts = made[0][0], made[0][1]
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])
    clock = Clock()
    backend = FakeBackend(clock=clock, step=100)
    summary, code = go(tmp_path, backend, clock=clock,
                       config={'deadlineSeconds': 250, 'packetBytes': 4096})
    # Batch one: two annotators and a reviewer fit; nothing after the wall clock is allowed to start.
    assert code == 3 and summary['status'] == 'incomplete' and len(backend.calls) == 3
    assert summary['outcomes'] == {'labeled': 1, 'not_attempted': 2}
    assert summary['import']['results'] == {'recorded': 1} and len(labels.load_labels(root)) == 1
    assert all(call['timeout'] <= 250 for call in backend.calls)
    entries = [json.loads(x) for x in (tmp_path / 'state' / auto.LEDGER).read_text().splitlines()]
    assert [e['outcome'] for e in entries] == ['labeled']          # unattempted cases are retried tomorrow
    # The next pass resumes with the two that never ran.
    resumed = FakeBackend()
    again, code = go(tmp_path, resumed)
    assert code == 0 and again['selected'] == 2 and len(labels.load_labels(root)) == 3


def test_an_unexpected_backend_error_keeps_finished_cases_and_retries_the_rest(tmp_path):
    prompts = ['first request ' + 'a' * 3400, 'second request ' + 'b' * 3400]
    made = [make(tmp_path, prompt, turn='t%d' % n) for n, prompt in enumerate(prompts)]
    root = made[0][0]
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])

    class Crashing(FakeBackend):
        def call(self, host, model, system, prompt, schema, timeout):
            if len(self.calls) >= 3:
                self.calls.append({})
                raise RuntimeError('boom')
            return super().call(host, model, system, prompt, schema, timeout)
    summary, code = go(tmp_path, Crashing(), config={'packetBytes': 4096})
    assert code == 3 and summary['processingError'] == 'RuntimeError'
    assert summary['outcomes'] == {'labeled': 1, 'not_attempted': 1} and len(labels.load_labels(root)) == 1


def test_repeated_call_failures_stop_the_run(tmp_path):
    prompts = ['request %d %s' % (n, 'x' * 3400) for n in range(5)]
    for n, prompt in enumerate(prompts):
        make(tmp_path, prompt, turn='t%d' % n)
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])

    class Failing(FakeBackend):
        def call(self, host, model, system, prompt, schema, timeout):
            self.calls.append({'host': host})
            raise auto.LabelerError('claude_exit_1')
    backend = Failing()
    summary, code = go(tmp_path, backend, config={'packetBytes': 4096})
    assert code == 3 and len(backend.calls) == auto.MAX_FAILED_CALLS_IN_A_ROW
    assert summary['outcomes'] == {'annotation_failed': auto.MAX_FAILED_CALLS_IN_A_ROW, 'not_attempted': 2}


# ---- the real CLI backend, against fake binaries ------------------------------------------------

def fake_binary(path, body):
    path.write_text('#!%s\n%s\n' % (sys.executable, body))
    path.chmod(0o755)
    return str(path)


CLAUDE_BODY = r'''
import json, os, sys
home = os.environ['HOME']
args = sys.argv[1:]
if args[:2] == ['auth', 'status']:
    print(json.dumps({'loggedIn': True, 'authMethod': open(home + '/auth-mode').read().strip(), 'apiProvider': 'firstParty'}))
    sys.exit(0)
if args == ['--version']:
    print('9.9.9 (fake)')
    sys.exit(0)
prompt = sys.stdin.read()
open(home + '/claude-call.json', 'w').write(json.dumps({'argv': args, 'env': dict(os.environ), 'prompt': prompt}))
model = args[args.index('--model') + 1]
print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'modelUsage': {model: {}},
                  'structured_output': {'answers': []}}))
'''
CODEX_BODY = r'''
import json, os, sys
home = os.environ['HOME']
args = sys.argv[1:]
if args[:2] == ['login', 'status']:
    print('Logged in using ChatGPT')
    sys.exit(0)
if args == ['--version']:
    print('codex-cli 0.0.0-fake')
    sys.exit(0)
prompt = sys.stdin.read()
codex_home = os.environ.get('CODEX_HOME', '')
listing = sorted(os.listdir(codex_home)) if codex_home and os.path.isdir(codex_home) else None
modes = {n: oct(os.stat(os.path.join(codex_home, n)).st_mode & 0o777) for n in listing or []}
mode_dir = oct(os.stat(codex_home).st_mode & 0o777) if listing is not None else None
open(home + '/codex-call.json', 'w').write(json.dumps({'argv': args, 'env': dict(os.environ), 'prompt': prompt,
                                                        'codexHome': codex_home, 'listing': listing, 'modes': modes,
                                                        'homeMode': mode_dir,
                                                        'schema': open(args[args.index('--output-schema') + 1]).read()}))
behavior = open(home + '/codex-behavior').read().strip() if os.path.exists(home + '/codex-behavior') else ''
if behavior == 'refresh':
    open(codex_home + '/auth.json', 'w').write(json.dumps({'tokens': {'access': 'REFRESHED-TOKEN-VALUE'}}))
elif behavior == 'empty':
    open(codex_home + '/auth.json', 'w').write('')
elif behavior == 'garbage':
    open(codex_home + '/auth.json', 'w').write('not json {')
elif behavior == 'fail-refresh':
    open(codex_home + '/auth.json', 'w').write(json.dumps({'tokens': {'access': 'REFRESHED-THEN-FAILED'}}))
    sys.exit(3)
elif behavior == 'concurrent':
    open(codex_home + '/auth.json', 'w').write(json.dumps({'tokens': {'access': 'OURS'}}))
    open(home + '/.codex/auth.json', 'w').write(json.dumps({'tokens': {'access': 'THEIRS'}}))
print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps({'answers': []})}}))
print(json.dumps({'type': 'turn.completed', 'usage': {}}))
'''


@pytest.fixture
def cli(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    (home / 'auth-mode').write_text('claude.ai')
    (home / '.codex').mkdir()
    (home / '.codex/auth.json').write_text(json.dumps({'tokens': {'access': 'ORIGINAL-TOKEN-VALUE'}}))
    (home / '.codex/auth.json').chmod(0o600)
    (home / '.codex/AGENTS.md').write_text('PRIVATE INSTRUCTIONS THAT MUST NOT BE SENT')
    (home / '.codex/config.toml').write_text('model = "x"')
    workdir = tmp_path / 'work'
    workdir.mkdir()
    environ = {'HOME': str(home), 'USER': 'tester', 'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
               'ANTHROPIC_API_KEY': 'sk-ant-must-not-cross', 'OPENAI_API_KEY': 'sk-must-not-cross',
               'ANTHROPIC_BASE_URL': 'https://gateway.invalid', 'OPENAI_BASE_URL': 'https://gateway.invalid',
               'CLAUDE_CODE_USE_BEDROCK': '1', 'AWS_SECRET_ACCESS_KEY': 'secret', 'SOME_API_KEY': 'k'}
    claude, codex = fake_binary(tmp_path / 'claude', CLAUDE_BODY), fake_binary(tmp_path / 'codex', CODEX_BODY)
    backend = auto.CliBackend(claude, codex, 'high', workdir, environ=environ)
    return backend, home, claude, codex


def test_child_env_is_an_allowlist_that_drops_every_api_key():
    env = auto.child_env({'HOME': '/h', 'USER': 'u', 'PATH': '/p', 'ANTHROPIC_API_KEY': 'a', 'OPENAI_API_KEY': 'o',
                          'ANTHROPIC_AUTH_TOKEN': 't', 'OPENAI_BASE_URL': 'b', 'RANDOM_SECRET': 's',
                          'CLAUDE_CODE_USE_VERTEX': '1'})
    assert set(env) == {'HOME', 'USER', 'PATH', 'DISABLE_AUTOUPDATER', 'NO_COLOR'}      # nothing consumed the old child marker
    assert auto.child_env({'HOME': '/h', 'CODEX_HOME': '/real'})['HOME'] == '/h'
    assert 'CODEX_HOME' not in auto.child_env({'HOME': '/h', 'CODEX_HOME': '/real'})     # never inherited
    assert auto.child_env({'HOME': '/h'}, codex_home='/private')['CODEX_HOME'] == '/private'


def test_cli_backend_scrubs_the_environment_and_builds_no_tools_schema_bound_commands(cli):
    backend, home, claude, codex = cli
    provenance = backend.preflight('claude')
    assert provenance['version'] == '9.9.9 (fake)' and provenance['path'] == claude
    assert len(provenance['sha256']) == 64 and provenance['login'] == 'claude.ai/firstParty'
    assert backend.preflight('codex')['version'] == 'codex-cli 0.0.0-fake'
    result = backend.call('claude', 'claude-fable-5-1', auto.REVIEW_SYSTEM, 'PROMPT-BODY', auto.REVIEW_SCHEMA, 30)
    assert result['observedModel'] == 'claude-fable-5-1' and result['identitySource'] == 'native_model_usage'
    seen = json.loads((home / 'claude-call.json').read_text())
    assert 'ANTHROPIC_API_KEY' not in seen['env'] and 'OPENAI_API_KEY' not in seen['env']
    assert not {k for k in seen['env'] if k.startswith(('ANTHROPIC_', 'OPENAI_', 'AWS_', 'CLAUDE_CODE_USE'))}
    assert 'SOME_API_KEY' not in seen['env'] and seen['env']['USER'] == 'tester'
    assert seen['prompt'] == 'PROMPT-BODY' and 'PROMPT-BODY' not in seen['argv']      # prompt is stdin only
    argv = seen['argv']
    assert argv[argv.index('--tools') + 1] == '' and '--safe-mode' in argv and '--no-session-persistence' in argv
    assert argv[argv.index('--model') + 1] == 'claude-fable-5-1' and '--json-schema' in argv
    assert argv[argv.index('--permission-mode') + 1] == 'dontAsk' and not any('api' in a.lower() for a in argv if a.startswith('--'))
    backend.call('codex', 'gpt-5.6-sol', auto.SYSTEM, 'CODEX-BODY', auto.ANNOTATE_SCHEMA, 30)
    seen = json.loads((home / 'codex-call.json').read_text())
    assert 'OPENAI_API_KEY' not in seen['env'] and 'ANTHROPIC_API_KEY' not in seen['env']
    assert seen['argv'][seen['argv'].index('--sandbox') + 1] == 'read-only' and seen['argv'][-1] == '-'
    # Codex ran with a private per-call CODEX_HOME that held only auth.json; the real ~/.codex was not exposed.
    assert seen['codexHome'] != str(home / '.codex') and seen['codexHome'].startswith(str(backend.workdir))
    assert seen['listing'] == ['auth.json'] and seen['modes'] == {'auth.json': '0o600'} and seen['homeMode'] == '0o700'
    assert not Path(seen['codexHome']).exists()                          # removed after the call
    assert 'CODEX-BODY' in seen['prompt'] and 'CODEX-BODY' not in seen['argv']
    assert json.loads(seen['schema']) == auto.ANNOTATE_SCHEMA


def test_cli_backend_fails_closed_without_a_subscription_login(cli):
    backend, home, claude, codex = cli
    (home / 'auth-mode').write_text('apiKey')                      # API-key billing is never acceptable
    with pytest.raises(auto.LabelerError, match='subscription_login_missing:claude'):
        backend.preflight('claude')
    (home / 'auth-mode').write_text('claude.ai')
    fake_binary(Path(codex), 'import sys\nprint("Not logged in")\nsys.exit(1)')
    with pytest.raises(auto.LabelerError, match='subscription_login_missing:codex'):
        backend.preflight('codex')
    missing = auto.CliBackend(str(Path(claude).with_name('nope')), codex, 'high', home)
    with pytest.raises(auto.LabelerError, match='binary_missing:claude'):
        missing.preflight('claude')


def test_model_command_lines_are_pinned(tmp_path):
    claude = auto.model_command('claude', '/bin/claude', 'claude-sonnet-5-5', 'high', tmp_path, 'SYS', {'type': 'object'})
    assert claude[:6] == ['/bin/claude', '--print', '--model', 'claude-sonnet-5-5', '--effort', 'high']
    assert claude[claude.index('--tools'):claude.index('--tools') + 2] == ['--tools', '']
    assert claude[-4:] == ['--system-prompt', 'SYS', '--json-schema', '{"type":"object"}']
    codex = auto.model_command('codex', '/bin/codex', 'gpt-5.6-sol', 'high', tmp_path, 'SYS', {'type': 'object'})
    assert codex[:4] == ['/bin/codex', 'exec', '--model', 'gpt-5.6-sol'] and codex[-1] == '-'
    assert '--ignore-user-config' in codex and 'features.shell_tool=false' in codex and 'mcp_servers={}' in codex
    assert codex[codex.index('--output-schema') + 1] == str(tmp_path / 'schema.json')
    for command in (claude, codex):
        assert not any('key' in part.lower() and part.startswith('--') for part in command)


def test_reviewer_identity_must_come_from_the_claude_report():
    good = json.dumps({'subtype': 'success', 'is_error': False, 'modelUsage': {'claude-fable-5-1': {}},
                       'structured_output': {'reviews': []}})
    assert auto.parse_native('claude', good, 'claude-fable-5-1')[1]['observedModel'] == 'claude-fable-5-1'
    for wrong in ({'modelUsage': {'claude-sonnet-5-5': {}}}, {'modelUsage': {}}, {'is_error': True}):
        payload = json.dumps({'subtype': 'success', 'is_error': False, 'structured_output': {}, **wrong})
        with pytest.raises(auto.LabelerError):
            auto.parse_native('claude', payload, 'claude-fable-5-1')
    tool = json.dumps({'type': 'item.started', 'item': {'type': 'command_execution'}})
    with pytest.raises(auto.LabelerError, match='tool'):
        auto.parse_native('codex', tool, 'gpt-5.6-sol')


def test_process_deadline_kills_a_stuck_child(tmp_path):
    started = os.times().elapsed
    with pytest.raises(auto.LabelerError, match='timed_out'):
        auto.run_process([sys.executable, '-c', 'import time; time.sleep(60)'], b'', tmp_path, 1,
                         auto.child_env({'PATH': os.environ.get('PATH', '')}))
    assert os.times().elapsed - started < 15


# ---- command line ------------------------------------------------------------------------------

def test_command_line_prepares_packets_without_any_model_or_state_change(tmp_path, capsys):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    argv = ['--root', str(root), '--receipts', str(receipts), '--state', str(tmp_path / 'state'),
            'run', '--prepare-only', '--transcript-root', str(tmp_path / 'transcripts/claude'),
            '--max-cases', '3', '--codex-model', 'gpt-6-luna']
    assert auto.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['status'] == 'prepared' and out['selected'] == 1 and out['models']['annotators']['codex'] == 'gpt-6-luna'
    assert out['calls'] == 0 and 'tools' not in out and labels.load_labels(root) == []
    # An inspection never replaces what the daily status shows.
    assert auto.main(['--state', str(tmp_path / 'state'), 'status']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'none'
    inspection = json.loads((tmp_path / 'state' / auto.LATEST_INSPECTION).read_text())
    assert inspection['status'] == 'prepared' and not (tmp_path / 'state' / auto.LATEST).exists()
    assert auto.main(['--root', str(root), '--receipts', str(receipts), '--state', str(tmp_path / 'state'),
                      'run', '--reviewer-model', 'gpt-5']) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'unavailable'


# ==== review fixes 1-9 ===========================================================================

def raw_transcript(tmp_path, session, rows):
    path = tmp_path / 'transcripts/claude/-proj' / (session + '.jsonl')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
    return path


def packet_for(tmp_path, root, receipts):
    config = config_for(tmp_path)
    cases, _ = auto.prepare_cases(root, receipts, lambda w: auto.TranscriptIndex(config['transcriptRoots'], w),
                                  {}, 'f' * 64, {**config, 'force': False})
    return cases[0]['packet']


# ---- item 3: prior context is what the user typed, nothing an agent wrote --------------------------

def test_prior_context_skips_sidechain_compact_boilerplate_anywhere_and_widened_leaks(tmp_path):
    root, receipts, receipt = make(tmp_path, 'final request')

    def row(text, **flags):
        return {'type': 'user', 'timestamp': '2026-09-29T14:00:00Z', 'message': {'role': 'user', 'content': text}, **flags}
    rows = [row('kept first'),
            row('sub-agent brief', isSidechain=True),
            row('compact summary of the session', isCompactSummary=True),
            row('x' * 2500 + ' <system-reminder>buried injected block</system-reminder>'),   # marker after char 900
            row('the consultation recommends the general workflow'),
            row('option A scored higher for this one'),
            row('the laya score said 0.9'),
            row('kept second'),
            {'type': 'assistant', 'message': {'role': 'assistant', 'content': 'Arm B chose content'}},
            {'type': 'user', 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'content': 'tool text'}]}},
            row('final request')]
    raw_transcript(tmp_path, SESSION, rows)
    packet = packet_for(tmp_path, root, receipts)
    assert [t['text'] for t in packet['precedingContext']] == ['kept first', 'kept second']
    blob = json.dumps(packet)
    for banned in ('sub-agent', 'compact summary', 'buried', 'consultation', 'laya', 'Arm B', 'tool text'):
        assert banned not in blob


# ---- item 4: Codex gets a private CODEX_HOME, and a refreshed token is written back safely -----------

def codex_call(backend):
    return backend.call('codex', 'gpt-5.6-sol', auto.SYSTEM, 'BODY', auto.ANNOTATE_SCHEMA, 30)


def test_codex_refreshed_login_is_written_back_atomically_and_never_logged(cli):
    backend, home, claude, codex = cli
    real = home / '.codex/auth.json'
    (home / 'codex-behavior').write_text('refresh')
    result = codex_call(backend)
    assert json.loads(real.read_text()) == {'tokens': {'access': 'REFRESHED-TOKEN-VALUE'}}
    assert stat.S_IMODE(real.stat().st_mode) == 0o600 and backend.auth_writebacks == 1
    assert sorted(p.name for p in (home / '.codex').iterdir()) == ['AGENTS.md', 'auth.json', 'config.toml']  # no temp left
    assert 'REFRESHED-TOKEN-VALUE' not in json.dumps(result) and 'ORIGINAL-TOKEN-VALUE' not in json.dumps(result)
    assert not list(backend.workdir.glob('call-*/codex-home'))            # the private copy is gone


def test_codex_login_is_untouched_when_nothing_changed_or_the_new_content_is_unusable(cli):
    backend, home, claude, codex = cli
    real = home / '.codex/auth.json'
    original = real.read_text()
    inode = real.stat().st_ino
    codex_call(backend)
    assert real.read_text() == original and real.stat().st_ino == inode and backend.auth_writebacks == 0
    for behavior in ('empty', 'garbage'):
        (home / 'codex-behavior').write_text(behavior)
        codex_call(backend)
        assert real.read_text() == original and backend.auth_writebacks == 0
    (home / 'codex-behavior').write_text('concurrent')      # someone else refreshed meanwhile: theirs wins
    codex_call(backend)
    assert json.loads(real.read_text()) == {'tokens': {'access': 'THEIRS'}} and backend.auth_writebacks == 0


def test_codex_failure_still_writes_back_a_refresh_and_removes_the_private_home(cli):
    backend, home, claude, codex = cli
    (home / 'codex-behavior').write_text('fail-refresh')
    with pytest.raises(auto.LabelerError, match='codex_exit_3'):
        codex_call(backend)
    assert json.loads((home / '.codex/auth.json').read_text())['tokens']['access'] == 'REFRESHED-THEN-FAILED'
    assert not list(backend.workdir.glob('call-*/codex-home'))


def test_codex_needs_a_usable_login_file_before_anything_runs(cli):
    backend, home, claude, codex = cli
    (home / '.codex/auth.json').write_text('')
    with pytest.raises(auto.LabelerError, match='codex_auth_unavailable'):
        codex_call(backend)
    (home / '.codex/auth.json').unlink()
    with pytest.raises(auto.LabelerError, match='codex_auth_unavailable'):
        codex_call(backend)
    assert not (home / 'codex-call.json').exists()                        # no process was started


def test_a_missing_codex_login_file_aborts_at_preflight_before_any_call(cli):
    backend, home, claude, codex = cli
    (home / '.codex/auth.json').unlink()
    assert backend.preflight('claude')['host'] == 'claude'
    with pytest.raises(auto.LabelerError, match='codex_auth_unavailable'):
        backend.preflight('codex')


def test_an_explicit_codex_home_is_the_one_whose_login_is_copied(cli, tmp_path):
    backend, home, claude, codex = cli
    other = tmp_path / 'other-codex'
    other.mkdir()
    (other / 'auth.json').write_text(json.dumps({'tokens': {'access': 'OTHER'}}))
    backend.environ = {**backend.environ, 'CODEX_HOME': str(other)}
    codex_call(backend)
    seen = json.loads((home / 'codex-call.json').read_text())
    assert seen['codexHome'] != str(other) and seen['listing'] == ['auth.json']


# ---- item 5: Codex tool lockdown ------------------------------------------------------------------

def test_codex_lockdown_disables_every_verified_tool_feature(tmp_path):
    command = auto.model_command('codex', '/bin/codex', 'gpt-5.6-sol', 'high', tmp_path, 'SYS', {'type': 'object'})
    settings = {command[i + 1] for i, part in enumerate(command) if part == '-c'}
    wanted = {'shell_tool', 'unified_exec', 'unified_exec_tty', 'view_image', 'code_mode_host', 'plugins', 'remote_plugin',
              'tool_suggest', 'js_repl', 'multi_agent_v2'}
    assert wanted <= set(auto.CODEX_DISABLED_FEATURES)
    for name in auto.CODEX_DISABLED_FEATURES:
        assert 'features.%s=false' % name in settings
    assert 'apply_patch_freeform' not in ' '.join(command)                 # removed from the CLI
    assert {'approval_policy="never"', 'web_search="disabled"', 'mcp_servers={}'} <= settings


@pytest.mark.skipif(not shutil.which('codex'), reason='codex CLI not installed')
def test_disabled_feature_names_exist_in_the_installed_codex_cli(tmp_path):
    (tmp_path / 'ch').mkdir()
    env = {'HOME': str(tmp_path), 'CODEX_HOME': str(tmp_path / 'ch'), 'PATH': os.environ.get('PATH', '')}
    try:
        done = subprocess.run([shutil.which('codex'), 'features', 'list'], capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.SubprocessError):
        pytest.skip('codex features list unavailable')
    if done.returncode != 0:
        pytest.skip('codex features list failed')
    known = {line.split()[0] for line in done.stdout.splitlines() if line.strip()}
    assert set(auto.CODEX_DISABLED_FEATURES) <= known


# ---- item 6: the ledger mirrors what the import really did ------------------------------------------

def ledger_rows(tmp_path):
    path = tmp_path / 'state' / auto.LEDGER
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_a_skipped_import_is_counted_surfaced_and_not_remembered_as_settled(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])

    class Racing(FakeBackend):
        def call(self, host, model, system, prompt, schema, timeout):
            if host == 'codex' and 'answers' in schema['properties'] and not labels.load_labels(root):
                # Someone judged the routing choice directly while this pass was running.
                labels.record_label(root, receipts, label_value(root, receipt, choice='none', choiceBasis='explicit',
                                                                reviewEvidenceSha256='d' * 64), 'd' * 64)
            return super().call(host, model, system, prompt, schema, timeout)
    summary, code = go(tmp_path, Racing())
    assert code == 3 and summary['status'] == 'incomplete'
    assert summary['importSkipped'] == {'immutable label already exists': 1} and summary['outcomes'] == {'labeled': 1}
    assert stored(root)[receipt['opportunityId']]['choice'] == 'none'         # the direct judgment stayed
    row = ledger_rows(tmp_path)[0]
    assert row['terminal'] is False and row['disposition'] == 'skipped' and row['importReason'] == 'immutable label already exists'
    assert read_run_file(summary, 'import.json')['dispositions'][0]['result'] == 'skipped'


def test_a_failed_import_still_writes_the_ledger_and_import_run_settles_it_later(tmp_path, monkeypatch):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    real = labels.import_batch
    monkeypatch.setattr(labels, 'import_batch', lambda *a, **k: (_ for _ in ()).throw(BlockingIOError(11, 'label lock busy')))
    summary, code = go(tmp_path, FakeBackend())
    assert code == 1 and summary['status'] == 'unavailable' and summary['reason'] == 'import_failed'
    assert summary['import']['reason'] == 'BlockingIOError'
    rows = ledger_rows(tmp_path)
    assert len(rows) == 1 and rows[0]['terminal'] is False and rows[0]['disposition'] == 'import_failed'
    assert (Path(summary['runDir']) / 'annotations.json').is_file() and labels.load_labels(root) == []
    monkeypatch.setattr(labels, 'import_batch', real)
    settled, code = auto.import_run(config_for(tmp_path), Path(summary['runDir']))
    assert code == 0 and settled['status'] == 'imported' and settled['import']['results'] == {'recorded': 1}
    assert stored(root)[receipt['opportunityId']]['choiceBasis'] == 'explicit'
    last = ledger_rows(tmp_path)[-1]
    assert last['terminal'] is True and last['disposition'] == 'recorded' and last['via'] == 'import-run'
    latest = auto.status(tmp_path / 'state')
    assert latest['status'] == 'completed' and latest['importedBy'] == 'import-run' and 'reason' not in latest
    assert go(tmp_path, FakeBackend())[0]['status'] == 'nothing_to_do'


def test_import_run_imports_an_inspected_no_import_run_and_is_idempotent(tmp_path, capsys):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    summary, _ = go(tmp_path, FakeBackend(), no_import=True)
    assert labels.load_labels(root) == [] and ledger_rows(tmp_path) == []
    argv = ['--root', str(root), '--receipts', str(receipts), '--state', str(tmp_path / 'state'),
            'import-run', summary['runDir']]
    assert auto.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['status'] == 'imported' and out['import']['results'] == {'recorded': 1} and 'dispositions' not in out['import']
    assert stored(root)[receipt['opportunityId']]['basis'] == labels.AI
    assert auto.main(argv) == 0 and json.loads(capsys.readouterr().out)['import']['results'] == {'already_recorded': 1}
    assert len(list(Path(summary['runDir']).glob('import-*.json'))) == 2
    assert all(row['terminal'] for row in ledger_rows(tmp_path))
    # The inspection never replaced the daily status, and importing did not invent one either.
    assert auto.status(tmp_path / 'state') == {'status': 'none'}


def test_import_run_refuses_foreign_directories_and_a_changed_taxonomy(tmp_path, monkeypatch):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    summary, _ = go(tmp_path, FakeBackend(), no_import=True)
    config = config_for(tmp_path)
    outside = tmp_path / 'elsewhere' / '20260929T000000Z-deadbeef'
    outside.mkdir(parents=True)
    shutil.copy(Path(summary['runDir']) / 'annotations.json', outside)
    for bad in (outside, Path(summary['runDir']) / 'calls', tmp_path / 'state'):
        with pytest.raises(auto.LabelerError, match='run_dir_must_be_a_run_in_the_state_directory'):
            auto.import_run(config, bad)
    link = tmp_path / 'state/runs/20260929T000000Z-cafebabe'
    link.symlink_to(summary['runDir'])
    with pytest.raises(auto.LabelerError, match='run_dir_must_be_a_run'):
        auto.import_run(config, link)
    changed = tmp_path / 'taxonomy.md'
    changed.write_text(auto.TAXONOMY_DOC.read_text() + '\nA new rule.\n')
    monkeypatch.setattr(auto, 'TAXONOMY_DOC', changed)
    with pytest.raises(auto.LabelerError, match='taxonomy_changed_since_the_run'):
        auto.import_run(config, Path(summary['runDir']))
    assert labels.load_labels(root) == []


# ---- item 7: robustness ---------------------------------------------------------------------------------

def test_lone_surrogates_in_a_transcript_never_crash_the_run(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    path = tmp_path / 'transcripts/claude/-proj' / (SESSION + '.jsonl')
    path.parent.mkdir(parents=True)
    rows = [{'type': 'user', 'message': {'role': 'user', 'content': 'earlier \ud83d question \ude00'}},
            {'type': 'user', 'message': {'role': 'user', 'content': [{'type': 'text', 'text': 'and \udc00 this'}, {'type': 'text', 'text': 5}]}},
            {'type': 'user', 'message': {'role': 'user', 'content': 'add a report filter'}}]
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    assert '\\ud83d' in path.read_text()
    summary, code = go(tmp_path, FakeBackend())
    assert code == 0 and summary['outcomes'] == {'labeled': 1}
    packets = read_run_file(summary, 'packets.json')
    assert [t['text'] for t in packets[0]['precedingContext']] == ['earlier ? question ?', 'and ? this']
    assert auto.transcript_message({'type': 'user', 'message': {'role': 'user', 'content': 'a\ud800b'}})[1] == 'a?b'


def test_malformed_answer_types_spoil_only_their_own_case(tmp_path):
    prompts = ['first report request', 'second report request']
    for n, prompt in enumerate(prompts):
        make(tmp_path, prompt, turn='t%d' % n)
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])

    def annotate(host, case):
        return {**ANSWER, 'areas': [['unhashable']], 'riskFlags': 'x'} if 'first' in case['prompt'] else dict(ANSWER)
    summary, code = go(tmp_path, FakeBackend(annotate=annotate))
    assert code == 3 and summary['outcomes'] == {'annotation_failed': 1, 'labeled': 1}
    assert 'TypeError' in json.dumps(read_run_file(summary, 'summary.json')) or summary['outcomes']
    # The same protection for review answers.
    root2 = tmp_path / 'second'
    root2.mkdir()
    for n, prompt in enumerate(prompts):
        make(root2, prompt, turn='t%d' % n)
    transcript(root2, SESSION, [('user', prompt) for prompt in prompts])

    def review(case):
        final = {**ANSWER, 'areas': [['x']]} if 'first' in case['prompt'] else dict(ANSWER)
        return {'verdict': 'accept', 'reason': 'ok', 'final': final}
    summary2, code2 = go(root2, FakeBackend(review=review))
    assert code2 == 3 and summary2['outcomes'] == {'labeled': 1, 'review_failed': 1}


def test_unhashable_case_ids_and_verdicts_are_ignored_not_fatal():
    answers = {'answers': [{'caseId': ['C001']}, {'caseId': {'a': 1}}, 'junk', None, {'caseId': 'C001', 'x': 1}]}
    parsed = auto.parse_answers(answers, ['C001'])
    assert parsed == {'C001': 'invalid_answer: answer keys'}
    reviews = {'reviews': [{'caseId': ['C001']}, {'caseId': 'C001', 'verdict': [], 'reason': 'r', 'final': None}]}
    assert auto.parse_reviews(reviews, ['C001']) == {'C001': 'invalid_review: review keys'}


def test_only_a_contended_lock_is_busy_any_other_lock_error_is_reported(tmp_path, monkeypatch):
    make(tmp_path, 'add a report filter')

    def failing(code):
        def flock(handle, operation):
            raise OSError(code, os.strerror(code))
        return flock
    for code in (errno.EAGAIN, errno.EACCES):
        monkeypatch.setattr(auto.fcntl, 'flock', failing(code))
        summary, exit_code = go(tmp_path, FakeBackend())
        assert summary['status'] == 'busy' and exit_code == 0
    monkeypatch.setattr(auto.fcntl, 'flock', failing(errno.EINTR))
    summary, exit_code = go(tmp_path, FakeBackend())
    assert summary['status'] == 'unavailable' and exit_code == 1 and summary['reason'] == 'lock_error:EINTR'


def test_taxonomy_size_is_capped_and_batches_follow_the_full_prompt(tmp_path, monkeypatch):
    prompts = ['request %d %s' % (n, 'z' * 3000) for n in range(3)]
    for n, prompt in enumerate(prompts):
        make(tmp_path, prompt, turn='t%d' % n)
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])
    huge = tmp_path / 'huge.md'
    huge.write_bytes(b'x' * (auto.MAX_TAXONOMY_BYTES + 1))
    monkeypatch.setattr(auto, 'TAXONOMY_DOC', huge)
    backend = FakeBackend()
    summary, code = go(tmp_path, backend)
    assert code == 2 and summary['reason'] == 'taxonomy_document_too_large' and backend.calls == []
    big = tmp_path / 'big.md'
    big.write_text('# Taxonomy\n' + 'rule text. ' * 1800)                       # about 20 KB
    monkeypatch.setattr(auto, 'TAXONOMY_DOC', big)
    backend = FakeBackend()
    summary, code = go(tmp_path, backend, config={'packetBytes': 30000})
    assert code == 0 and summary['outcomes'] == {'labeled': 3}
    annotate_calls = [c for c in backend.calls if 'answers' in c['schema']['properties']]
    assert len(annotate_calls) == 4                                          # two batches x two annotators
    assert all(len(c['prompt'].encode()) <= 30000 for c in backend.calls)
    # The packets alone (about 10 KB) would have fit one batch; the taxonomy made the difference.
    assert len(json.dumps([c for c in read_run_file(summary, 'packets.json')]).encode()) < 30000


def test_a_call_cut_short_by_the_deadline_is_not_attempted_but_a_plain_timeout_is_a_failure(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])

    class TimesOut(FakeBackend):
        def call(self, host, model, system, prompt, schema, timeout):
            self.calls.append({'host': host, 'timeout': timeout})
            raise auto.LabelerError('timed_out')
    # The remaining wall time (200 s) is shorter than the per-call limit (900 s): the deadline ended the call.
    summary, code = go(tmp_path, TimesOut(), config={'deadlineSeconds': 200, 'callTimeoutSeconds': 900})
    assert code == 3 and summary['outcomes'] == {'not_attempted': 1} and ledger_rows(tmp_path) == []
    summary, code = go(tmp_path, TimesOut(), config={'deadlineSeconds': 14400, 'callTimeoutSeconds': 30})
    assert code == 3 and summary['outcomes'] == {'annotation_failed': 1}
    assert [r['terminal'] for r in ledger_rows(tmp_path)] == [False]


def test_sigterm_finishes_a_summary_keeps_finished_cases_and_import_run_recovers_them(tmp_path):
    prompts = ['first request ' + 'a' * 3400, 'second request ' + 'b' * 3400]
    made = [make(tmp_path, prompt, turn='t%d' % n) for n, prompt in enumerate(prompts)]
    root = made[0][0]
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])

    class Interrupted(FakeBackend):
        def call(self, host, model, system, prompt, schema, timeout):
            if len(self.calls) >= 3:
                raise auto.Terminated()
            return super().call(host, model, system, prompt, schema, timeout)
    summary, code = go(tmp_path, Interrupted(), config={'packetBytes': 4096})
    assert code == 4 and summary['status'] == 'terminated' and summary['outcomes'] == {'labeled': 1, 'not_attempted': 1}
    assert read_run_file(summary, 'summary.json')['status'] == 'terminated'
    assert labels.load_labels(root) == [] and ledger_rows(tmp_path) == []        # nothing half-imported
    settled, code = auto.import_run(config_for(tmp_path), Path(summary['runDir']))
    assert code == 0 and settled['import']['results'] == {'recorded': 1}


def test_a_real_sigterm_stops_the_child_and_leaves_a_terminated_summary(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    home = tmp_path / 'home'
    (home / '.codex').mkdir(parents=True)
    (home / '.codex/auth.json').write_text(json.dumps({'tokens': {'a': 'b'}}))
    (home / 'auth-mode').write_text('claude.ai')
    slow = CLAUDE_BODY.replace("prompt = sys.stdin.read()", "prompt = sys.stdin.read()\nimport time\nopen(home + '/child.pid', 'w').write(str(os.getpid()))\ntime.sleep(120)")
    claude, codex = fake_binary(tmp_path / 'claude', slow), fake_binary(tmp_path / 'codex', CODEX_BODY)
    env = {'HOME': str(home), 'USER': 'tester', 'PATH': os.environ.get('PATH', '/usr/bin:/bin')}
    process = subprocess.Popen([sys.executable, str(SCRIPTS / 'pilot_autolabel.py'), '--root', str(root),
                                '--receipts', str(receipts), '--state', str(tmp_path / 'state'), 'run', '--claude-bin', claude,
                                '--codex-bin', codex, '--transcript-root', str(tmp_path / 'transcripts/claude')],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(200):
            if (home / 'child.pid').exists() and (home / 'child.pid').read_text():
                break
            time.sleep(0.1)
        child = int((home / 'child.pid').read_text())
        process.send_signal(signal.SIGTERM)
        out, _ = process.communicate(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()
    assert process.returncode == 4 and json.loads(out.strip().splitlines()[-1])['status'] == 'terminated'
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        raise AssertionError('the model child outlived its parent')
    runs = list((tmp_path / 'state/runs').iterdir())
    assert json.loads((runs[0] / 'summary.json').read_text())['status'] == 'terminated'
    with open(tmp_path / 'state/run.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)                      # the lock was released


def test_an_unexpected_failure_still_leaves_a_failure_summary(tmp_path, monkeypatch):
    make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    monkeypatch.setattr(auto, 'compile_records', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    summary, code = go(tmp_path, FakeBackend())
    assert code == 1 and summary['status'] == 'failed' and summary['reason'] == 'unexpected:RuntimeError'
    assert read_run_file(summary, 'summary.json')['status'] == 'failed'
    assert auto.status(tmp_path / 'state')['status'] == 'failed'


# ---- item 8: integrity --------------------------------------------------------------------------------

def test_reviewer_identity_must_be_cli_metadata_and_differ_from_the_annotators(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])

    class SelfReported(FakeBackend):
        def identity_for(self, host):
            return 'model_self_report' if host == 'claude' else 'explicit_cli_argument'
    summary, code = go(tmp_path, SelfReported())
    assert code == 3 and summary['outcomes'] == {'review_failed': 1} and labels.load_labels(root) == []
    assert read_run_file(summary, 'summary.json')['outcomes'] == {'review_failed': 1}

    class SameModel(FakeBackend):
        def call(self, host, model, system, prompt, schema, timeout):
            result = super().call(host, model, system, prompt, schema, timeout)
            if 'reviews' in schema['properties']:
                result['observedModel'] = 'claude-sonnet-5-5'                # reports an annotator's model
            return result
    summary, code = go(tmp_path, SameModel(), force=True)
    assert code == 3 and summary['outcomes'] == {'review_failed': 1}
    assert json.dumps(read_run_file(summary, 'annotations.json')) and labels.load_labels(root) == []
    for same in ({'reviewerModel': 'claude-sonnet-5-5'}, {'claudeModel': 'claude-fable-5-1'}):
        with pytest.raises(auto.LabelerError, match='must_differ'):
            auto.merge_config(auto.DEFAULTS, same)


def test_annotator_rationales_never_reach_the_reviewer(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    backend = FakeBackend()
    backend.rationale = 'RATIONALE-MARKER-XYZ persuasive argument'
    summary, code = go(tmp_path, backend)
    assert code == 0 and summary['outcomes'] == {'labeled': 1}
    review = next(c for c in backend.calls if 'reviews' in c['schema']['properties'])
    assert 'RATIONALE-MARKER' not in review['prompt'] and 'rationale' not in review['prompt']
    proposals = cases_in(review['prompt'])[0]['proposals']
    assert len(proposals) == 2 and all(set(p) == {'status', 'family', 'phase', 'areas', 'stratum', 'riskFlags', 'choice'}
                                       for p in proposals)
    # The audit copy on the record keeps the rationale; only the reviewer's view drops it.
    assert 'RATIONALE-MARKER' in json.dumps(read_run_file(summary, 'annotations.json'))


# ---- item 9: operations -------------------------------------------------------------------------------

def test_inspection_runs_never_overwrite_the_daily_status(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    daily, _ = go(tmp_path, FakeBackend())
    latest = (tmp_path / 'state' / auto.LATEST).read_bytes()
    assert daily['status'] == 'completed'
    make(tmp_path, 'another request', turn='t2')
    transcript(tmp_path, SESSION, [('user', 'add a report filter'), ('user', 'another request')])
    for options in ({'no_import': True}, {'prepare_only': True}):
        inspected, _ = go(tmp_path, FakeBackend(), **options)
        assert (tmp_path / 'state' / auto.LATEST).read_bytes() == latest
        assert json.loads((tmp_path / 'state' / auto.LATEST_INSPECTION).read_text())['runId'] == inspected['runId']
    assert auto.status(tmp_path / 'state')['runId'] == daily['runId']


def test_binaries_must_be_absolute_and_a_mise_shim_is_refused(tmp_path):
    for key in ('claudeBin', 'codexBin'):
        with pytest.raises(auto.LabelerError, match='absolute'):
            auto.merge_config(auto.DEFAULTS, {key: 'claude'})
    assert auto.merge_config(auto.DEFAULTS, {'claudeBin': '/usr/bin/true'})['claudeBin'] == '/usr/bin/true'
    real = fake_binary(tmp_path / 'mise', 'print(1)')
    shim = tmp_path / 'shims' / 'claude'
    shim.parent.mkdir()
    shim.symlink_to(real)
    backend = auto.CliBackend(str(shim), str(shim), 'high', tmp_path)
    for host in ('claude', 'codex'):
        with pytest.raises(auto.LabelerError, match='binary_is_mise_shim:' + host):
            backend.preflight(host)


def test_old_run_directories_are_pruned_but_never_the_current_or_foreign_ones(tmp_path):
    runs = tmp_path / 'state' / 'runs'
    runs.mkdir(parents=True, mode=0o700)
    names = ['2026092%dT000000Z-0000000%d' % (n, n) for n in range(1, 6)]
    for name in names:
        (runs / name).mkdir()
        (runs / name / 'summary.json').write_text('{}')
    (runs / 'notes').mkdir()
    link = runs / '20260901T000000Z-abcdef01'
    link.symlink_to(runs / names[-1])
    assert auto.prune_runs(tmp_path / 'state', 2, names[-1]) == 3
    assert sorted(p.name for p in runs.iterdir() if p.is_dir() and not p.is_symlink()) == sorted(names[-2:] + ['notes'])
    assert link.is_symlink() and (runs / names[-1] / 'summary.json').exists()
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    for name in names[-2:]:
        assert (runs / name).exists()
    summary, _ = go(tmp_path, FakeBackend(), config={'retainRuns': 1})
    assert [p.name for p in runs.iterdir() if RUN_ID_LIKE.fullmatch(p.name) and p.is_dir() and not p.is_symlink()] == [summary['runId']]
    with pytest.raises(auto.LabelerError):
        auto.merge_config(auto.DEFAULTS, {'retainRuns': 0})


RUN_ID_LIKE = __import__('re').compile(r'\d{8}T\d{6}Z-[0-9a-f]{8}')


def test_the_output_schema_file_is_private(cli):
    backend, home, claude, codex = cli
    backend.call('claude', 'claude-fable-5-1', auto.REVIEW_SYSTEM, 'BODY', auto.REVIEW_SCHEMA, 30)
    codex_call(backend)
    schemas = list(backend.workdir.glob('call-*/schema.json'))
    assert len(schemas) == 2 and all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in schemas)
