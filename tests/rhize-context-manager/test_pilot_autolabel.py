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
import workflow_context_packet as request_context

DIGEST_FILES = ('decision_pilot_v2.py', 'decision_pilot.py', 'workflow_selection.py', 'workflow_task_context.py',
                'workflow_context_packet.py', 'pilot_redaction.py', 'pilot_routing.py',
                'context_experiments/typed_relevance.py')
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
    cases, skipped = auto.prepare_cases(root, receipts, lambda w, b: auto.TranscriptIndex(config['transcriptRoots'], w, b),
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
    cases, _ = auto.prepare_cases(root, receipts, lambda w, b: auto.TranscriptIndex(config['transcriptRoots'], w, b),
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
        return auto.prepare_cases(root, receipts, lambda w, b: auto.TranscriptIndex(config['transcriptRoots'], w, b),
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


def captured_fixture(receipt, text):
    """Invented API response; the shared sidecar loader has its own binding/immutability tests."""
    sanitized, truncated = auto.sanitize(text, auto.PROMPT_LIMIT)
    return {'opportunityId': receipt['opportunityId'], 'sessionHash': receipt['sessionHash'],
            'promptHash': receipt['promptHash'], 'receiptObservedAt': receipt['observedAt'],
            'capturedAt': receipt['observedAt'], 'originalRequest': sanitized, 'requestTruncated': truncated,
            'snapshotSha256': 'c' * 64}


def capture_api(monkeypatch, snapshots, links=None):
    links = links or {}
    monkeypatch.setattr(auto, 'load_request_context', lambda receipts, identity: {
        'current': snapshots.get(identity), 'preceding': links.get(identity, []),
        'contextSha256': 'd' * 64 if links.get(identity) else None})


def native_rows(tmp_path, requests):
    raw_transcript(tmp_path, SESSION, [{**line('user', text, receipt['observedAt'], False), 'sessionId': SESSION}
                                     for receipt, text in requests])


def prepared_cases(tmp_path, root, receipts):
    config = config_for(tmp_path)
    return auto.prepare_cases(root, receipts, lambda wanted, bounds: auto.TranscriptIndex(
        config['transcriptRoots'], wanted, bounds), {}, 'f' * 64, config)[0]


def test_explicit_captured_context_recovers_later_short_request_without_widening_history(tmp_path, monkeypatch):
    initial = 'Implement the backend invoice validation; preserve authorization constraints.'
    root, receipts, initiating = make(tmp_path, initial, kind='new_task')
    _, _, approval = make(tmp_path, 'Proceed with implementation', kind='changed_intent')
    first, current = captured_fixture(initiating, initial), captured_fixture(approval, 'Proceed with implementation')
    capture_api(monkeypatch, {initiating['opportunityId']: first, approval['opportunityId']: current},
                {approval['opportunityId']: [first]})
    native_rows(tmp_path, [(initiating, initial), (approval, 'Proceed with implementation')])
    cases = prepared_cases(tmp_path, root, receipts)
    case = next(c for c in cases if c['opportunityId'] == approval['opportunityId'])
    assert case['contextStatus'] == 'ok'
    assert [c['text'] for c in case['packet']['precedingContext']] == [initial]
    assert case['contextProvenance']['exposure'] == 'unknown'
    assert len(case['contextProvenance']['requests']) == 2
    # Raw request snapshots and their private provenance never enter Laya scoring inputs.
    observation = workflow.read_json(root / 'v2/observations' / (approval['opportunityId'] + '.json'))
    assert initial not in json.dumps(observation) and 'originalRequest' not in json.dumps(observation)


def test_captured_changed_intent_does_not_implicitly_mix_an_earlier_task_root(tmp_path, monkeypatch):
    root, receipts, first = make(tmp_path, 'Create a front end invoice form')
    _, _, changed = make(tmp_path, 'Investigate the database deadlock', kind='changed_intent', action='investigate')
    snapshots = {r['opportunityId']: captured_fixture(r, text) for r, text in [
        (first, 'Create a front end invoice form'), (changed, 'Investigate the database deadlock')]}
    capture_api(monkeypatch, snapshots)
    native_rows(tmp_path, [(first, 'Create a front end invoice form'), (changed, 'Investigate the database deadlock')])
    case = next(c for c in prepared_cases(tmp_path, root, receipts) if c['opportunityId'] == changed['opportunityId'])
    assert case['contextStatus'] == 'ok' and case['packet']['precedingContext'] == []


@pytest.mark.parametrize('failure,status', [(ValueError('request_snapshot_binding_mismatch'), 'context_binding_mismatch'),
                                         (KeyError('createdAt'), 'context_binding_mismatch'),
                                         (TypeError('invalid private context timestamp'), 'context_binding_mismatch'),
                                         (ValueError('request_snapshot_late'), 'context_snapshot_late'),
                                         (OSError('private path must not appear'), 'context_unavailable')])
def test_invalid_captured_context_never_falls_back_or_calls_models(tmp_path, monkeypatch, failure, status):
    root, receipts, receipt = make(tmp_path, 'Implement the approved backend change')
    transcript(tmp_path, SESSION, [('user', 'Implement the approved backend change')])
    def unavailable(*args):
        raise failure
    monkeypatch.setattr(auto, 'load_request_context', unavailable)
    backend = FakeBackend(auth_error='must_not_be_asked')
    summary, code = go(tmp_path, backend)
    assert code == 0 and summary['outcomes'] == {status: 1}
    assert summary['contextDiagnostics'] == {status: 1} and summary['warnings'] == [status]
    assert backend.calls == [] and backend.preflights == []
    annotation = read_run_file(summary, 'annotations.json')[0]
    assert annotation['status'] == 'insufficient_context' and annotation['detail'] == status
    assert 'private path' not in json.dumps(summary) and labels.load_labels(root) == []


def test_captured_context_filters_assistant_answers_routing_disclosures_and_private_provenance(tmp_path, monkeypatch):
    root, receipts, request = make(tmp_path, 'Keep the existing backend authorization')
    _, _, disclosed = make(tmp_path, 'Arm B chose general for this task')
    _, _, current = make(tmp_path, 'Proceed', kind='changed_intent')
    rows = [(request, 'Keep the existing backend authorization'), (disclosed, 'Arm B chose general for this task'),
            (current, 'Proceed')]
    snapshots = {r['opportunityId']: captured_fixture(r, text) for r, text in rows}
    capture_api(monkeypatch, snapshots, {current['opportunityId']: [snapshots[request['opportunityId']],
                                                                  snapshots[disclosed['opportunityId']]]})
    native_rows(tmp_path, rows)
    backend = FakeBackend()
    summary, _ = go(tmp_path, backend, no_import=True)
    target = next(c for c in read_run_file(summary, 'manifest.json')['cases']
                  if c['opportunityId'] == current['opportunityId'])
    assert target['contextProvenance']['withheldLinkedRequests'] == 1
    target_number = target['caseId']
    for call in backend.calls:
        model_case = next(c for c in cases_in(call['prompt']) if c['caseId'] == target_number)
        assert [c['text'] for c in model_case['precedingContext']] == ['Keep the existing backend authorization']
        assert not {'contextProvenance', 'snapshotSha256', 'opportunityId', 'transcriptRef'}.intersection(model_case)


def test_snapshot_requires_an_actual_user_turn_and_sanitized_binding(tmp_path, monkeypatch):
    text = 'Implement the email notification; contact user@example.test'
    root, receipts, receipt = make(tmp_path, text)
    snapshot = captured_fixture(receipt, text)
    capture_api(monkeypatch, {receipt['opportunityId']: snapshot})
    raw_transcript(tmp_path, SESSION, [line('assistant', text, receipt['observedAt'], False)])
    assert prepared_cases(tmp_path, root, receipts)[0]['contextStatus'] == 'context_missing'
    native_rows(tmp_path, [(receipt, text)])
    case = prepared_cases(tmp_path, root, receipts)[0]
    assert case['contextStatus'] == 'ok' and 'user@example.test' not in json.dumps(case['packet'])
    snapshot['originalRequest'] += ' tampered'
    assert prepared_cases(tmp_path, root, receipts)[0]['contextStatus'] == 'context_binding_mismatch'


def test_snapshot_transcript_matching_rejects_wrong_session_and_outside_window_requests(tmp_path, monkeypatch):
    text = 'Implement the email notification'
    root, receipts, receipt = make(tmp_path, text)
    capture_api(monkeypatch, {receipt['opportunityId']: captured_fixture(receipt, text)})
    raw_transcript(tmp_path, OTHER_SESSION, [line('user', text, receipt['observedAt'], False)])
    assert prepared_cases(tmp_path, root, receipts)[0]['contextStatus'] == 'context_missing'
    raw_transcript(tmp_path, SESSION, [{**line('user', text, stamped(120), False), 'sessionId': SESSION}])
    assert prepared_cases(tmp_path, root, receipts)[0]['contextStatus'] == 'context_binding_mismatch'


def native_request(tmp_path, prompt, *, kind='new_task', context_ids=()):
    receipts, root = tmp_path / 'receipts', tmp_path / 'pilot'
    payload = {'prompt': prompt, 'session_id': SESSION, 'turn_id': prompt}
    receipt, _ = workflow.opportunity(payload, 'codex', receipts,
                                     {'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}})
    request_context.capture_request_snapshot(receipts, receipt, payload)
    request_context.capture_request_context(receipts, receipt['opportunityId'], context_ids)
    value = {'schemaVersion': context.SCHEMA, 'opportunityId': receipt['opportunityId'],
             'promptHash': receipt['promptHash'], 'sessionHash': receipt['sessionHash'],
             'eventKind': kind, 'action': 'implement', 'domain': 'software', 'exclusions': [],
             'parentOpportunityId': None, 'preboundFamily': None}
    context.capture_context(receipts, receipt['opportunityId'], value,
                            seal=lambda c, r: pilot.enqueue_v2(c, r, root, spawn=False, receipts=receipts))
    return root, receipts, receipt


@pytest.mark.parametrize('publication_lag,status', [(15.512, 'ok'), (60, 'ok'),
                                                   (60.001, 'context_binding_mismatch')])
def test_codex_snapshot_accepts_bounded_post_hook_transcript_publication(tmp_path, publication_lag, status):
    from datetime import datetime, timedelta
    text = 'Implement the backend notification; contact user@example.test'
    root, receipts, receipt = native_request(tmp_path, text)
    snapshot = request_context.load_request_snapshot(receipts, receipt['opportunityId'])
    published = (datetime.fromisoformat(receipt['observedAt']) + timedelta(seconds=publication_lag)).isoformat()
    assert auto._timestamp(published) > auto._timestamp(snapshot['capturedAt'])
    path = transcript(tmp_path, SESSION, [], codex=True)
    rows = [{'type': 'session_meta', 'payload': {'id': SESSION}}, line('user', text, published, True)]
    path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
    case = prepared_cases(tmp_path, root, receipts)[0]
    assert case['contextStatus'] == status
    if status == 'ok':
        assert '[REDACTED_EMAIL]' in case['packet']['prompt']
        assert case['packet']['precedingContext'] == []
        assert case['contextProvenance']['requests'][0]['transcriptIdentity'] == 'verified'
    else:
        assert case['packet'] is None
    # Publication lag never changes the sealed pre-decision snapshot or its bindings.
    assert request_context.load_request_snapshot(receipts, receipt['opportunityId']) == snapshot


def test_native_snapshot_link_integration_and_tampered_sidecar_never_falls_back(tmp_path):
    original = 'Implement the backend authorization constraints; email user@example.test'
    root, receipts, initiating = native_request(tmp_path, original)
    _, _, current = native_request(tmp_path, 'Proceed with this change', kind='changed_intent',
                                   context_ids=[initiating['opportunityId']])
    native_rows(tmp_path, [(initiating, original), (current, 'Proceed with this change')])
    case = next(c for c in prepared_cases(tmp_path, root, receipts) if c['opportunityId'] == current['opportunityId'])
    assert case['contextStatus'] == 'ok'
    assert '[REDACTED_EMAIL]' in case['packet']['precedingContext'][0]['text']
    assert 'user@example.test' not in json.dumps(case)
    assert case['contextProvenance']['contextSha256'] is not None
    path = receipts.parent / 'request-snapshots' / (current['opportunityId'] + '.json')
    stored = json.loads(path.read_text())
    stored['sessionHash'] = 'e' * 64
    path.write_text(json.dumps(stored))
    bad = next(c for c in prepared_cases(tmp_path, root, receipts) if c['opportunityId'] == current['opportunityId'])
    assert bad['contextStatus'] == 'context_binding_mismatch' and bad['packet'] is None


def test_native_snapshot_captured_after_context_is_deferred_with_a_typed_diagnostic(tmp_path):
    root, receipts, receipt = native_request(tmp_path, 'Implement this exact backend change')
    native_rows(tmp_path, [(receipt, 'Implement this exact backend change')])
    path = receipts.parent / 'request-snapshots' / (receipt['opportunityId'] + '.json')
    stored = json.loads(path.read_text())
    stored['capturedAt'] = stamped(60)
    stored['snapshotSha256'] = request_context._sha(stored, 'snapshotSha256')
    path.write_text(json.dumps(stored))
    case = prepared_cases(tmp_path, root, receipts)[0]
    assert case['contextStatus'] == 'context_snapshot_late' and case['packet'] is None


def test_missing_observation_timestamp_defers_only_that_snapshot_case(tmp_path):
    root, receipts, malformed = native_request(tmp_path, 'Implement the malformed-timestamp database change')
    _, _, valid = native_request(tmp_path, 'Implement the valid-session backend change')
    native_rows(tmp_path, [(malformed, 'Implement the malformed-timestamp database change'),
                          (valid, 'Implement the valid-session backend change')])
    path = root / 'v2/observations' / (malformed['opportunityId'] + '.json')
    observation = json.loads(path.read_text())
    del observation['createdAt']
    path.write_text(json.dumps(observation))
    backend = FakeBackend()
    summary, code = go(tmp_path, backend, no_import=True)
    assert code == 0 and summary['status'] == 'completed'
    assert summary['outcomes'] == {'context_binding_mismatch': 1, 'labeled': 1}
    manifest = read_run_file(summary, 'manifest.json')['cases']
    bad_id = next(c['caseId'] for c in manifest if c['opportunityId'] == malformed['opportunityId'])
    good_id = next(c['caseId'] for c in manifest if c['opportunityId'] == valid['opportunityId'])
    assert backend.calls and all({c['caseId'] for c in cases_in(call['prompt'])} == {good_id}
                                 for call in backend.calls)
    assert all(bad_id not in {c['caseId'] for c in cases_in(call['prompt'])} for call in backend.calls)
    assert summary['warnings'] == ['context_binding_mismatch']


def test_transcript_scan_refuses_nonregular_sources_and_tracks_unavailability(tmp_path):
    fifo = tmp_path / 'blocked.jsonl'
    os.mkfifo(fifo)
    issues = []
    started = time.monotonic()
    assert auto.TranscriptIndex._scan([fifo], {'a' * 64}, issues=issues) == {}
    assert time.monotonic() - started < 2 and issues == ['transcript_not_regular']
    regular = tmp_path / 'regular.jsonl'
    regular.write_text('{}\n')
    linked = tmp_path / 'link.jsonl'
    linked.symlink_to(regular)
    issues = []
    assert auto.TranscriptIndex._scan([linked], {'a' * 64}, issues=issues) == {}
    assert issues == ['transcript_unavailable']


@pytest.mark.parametrize('codex', [False, True])
@pytest.mark.parametrize('native_id', [OTHER_SESSION, None])
def test_new_snapshot_requires_native_session_identity_despite_matching_filename(tmp_path, codex, native_id):
    text = 'Implement the verified-session database change'
    root, receipts, receipt = native_request(tmp_path, text)
    if codex:
        path = transcript(tmp_path, SESSION, [], codex=True)
        rows = ([{'type': 'session_meta', 'payload': {'id': native_id}}] if native_id else [])
        rows.append(line('user', text, receipt['observedAt'], True))
    else:
        path = raw_transcript(tmp_path, SESSION, [])
        rows = [line('user', text, receipt['observedAt'], False)]
        if native_id:
            rows[0]['sessionId'] = native_id
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    case = prepared_cases(tmp_path, root, receipts)[0]
    assert case['contextStatus'] == 'context_binding_mismatch' and case['packet'] is None
    if codex:
        rows.insert(0, {'type': 'session_meta', 'payload': {'id': SESSION}})
        rows = [r for r in rows if r.get('type') != 'session_meta' or r['payload']['id'] == SESSION]
    else:
        rows[0]['sessionId'] = SESSION
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    valid = prepared_cases(tmp_path, root, receipts)[0]
    assert valid['contextStatus'] == 'ok'
    assert valid['contextProvenance']['requests'][0]['transcriptIdentity'] == 'verified'


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
elif behavior == 'payload':
    open(codex_home + '/auth.json', 'w').write(open(home + '/codex-payload').read())
elif behavior == 'noise':
    import time
    open(home + '/codex-noise.pid', 'w').write(str(os.getpid()))
    print('this line is not json', flush=True)
    time.sleep(60)
elif behavior == 'events':
    import time
    if os.path.exists(home + '/codex-events-sleep'):
        with open(home + '/codex-events.pid', 'w') as pid_file:
            pid_file.write(str(os.getpid()))
    for event_line in open(home + '/codex-events').read().splitlines():
        print(event_line, flush=True)
    if os.path.exists(home + '/codex-events-sleep'):
        time.sleep(60)
    sys.exit(0)
elif behavior == 'newkey':
    open(codex_home + '/auth.json', 'w').write(json.dumps({'tokens': {'access': 'X'}, 'brand_new_top_level_key': 1}))
elif behavior == 'tool':
    import time
    open(home + '/codex-tool.pid', 'w').write(str(os.getpid()))
    print(json.dumps({'type': 'item.started', 'item': {'type': 'command_execution', 'command': 'pwd'}}), flush=True)
    time.sleep(60)
    open(home + '/tool-kept-running', 'w').write('yes')
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
    cases, _ = auto.prepare_cases(root, receipts, lambda w, b: auto.TranscriptIndex(config['transcriptRoots'], w, b),
                                  {}, 'f' * 64, {**config, 'force': False})
    return cases[0]['packet']


# ---- item 3: prior context is what the user typed, nothing an agent wrote --------------------------

def test_prior_context_skips_sidechain_compact_boilerplate_anywhere_and_widened_leaks(tmp_path):
    root, receipts, receipt = make(tmp_path, 'final request')

    ticks = iter(range(100))

    def row(text, **flags):
        return {'type': 'user', 'timestamp': '2026-09-29T14:00:%02dZ' % next(ticks),
                'message': {'role': 'user', 'content': text}, **flags}
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
    assert sorted(p.name for p in (home / '.codex').iterdir()) == ['.laya-auth.lock', 'AGENTS.md', 'auth.json', 'config.toml']  # no temp left
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
    rows = [{'type': 'user', 'timestamp': '2026-09-29T14:00:01Z', 'message': {'role': 'user', 'content': 'earlier \ud83d question \ude00'}},
            {'type': 'user', 'timestamp': '2026-09-29T14:00:02Z', 'message': {'role': 'user', 'content': [{'type': 'text', 'text': 'and \udc00 this'}, {'type': 'text', 'text': 5}]}},
            {'type': 'user', 'timestamp': '2026-09-29T14:00:03Z', 'message': {'role': 'user', 'content': 'add a report filter'}}]
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
        (runs / name / 'summary.json').write_text(json.dumps({'schema': auto.SUMMARY_SCHEMA, 'runId': name,
                                                            'status': 'completed', 'exitCode': 0}))
        (runs / name / 'manifest.json').write_text(json.dumps({'schema': auto.RUN_SCHEMA, 'runId': name, 'cases': []}))
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


def test_pruning_preserves_every_failed_interrupted_and_unverifiable_run(tmp_path):
    runs = tmp_path / 'runs'
    runs.mkdir()
    statuses = ['failed', 'unavailable', 'terminated', 'incomplete', 'interrupted', 'started',
                'missing_summary', 'malformed_summary', 'missing_manifest', 'malformed_manifest', 'wrong_run_id',
                'completed_with_warning', 'fifo_summary']
    names = []
    for number, status in enumerate(statuses, 1):
        name = '202609%02dT000000Z-%08x' % (number, number)
        names.append(name)
        path = runs / name
        path.mkdir()
        summary = {'schema': auto.SUMMARY_SCHEMA, 'runId': name, 'status': status, 'exitCode': 1}
        manifest = {'schema': auto.RUN_SCHEMA, 'runId': name, 'cases': []}
        if status in {'missing_manifest', 'malformed_manifest', 'wrong_run_id', 'completed_with_warning'}:
            summary.update(status='completed', exitCode=0)
        if status == 'wrong_run_id':
            manifest['runId'] = 'different'
        if status == 'completed_with_warning':
            summary['warnings'] = ['context_unavailable']
        if status != 'missing_summary':
            (path / 'summary.json').write_text('broken {' if status == 'malformed_summary' else json.dumps(summary))
        if status != 'missing_manifest':
            (path / 'manifest.json').write_text('broken {' if status == 'malformed_manifest' else json.dumps(manifest))
        if status == 'fifo_summary':
            (path / 'summary.json').unlink()
            os.mkfifo(path / 'summary.json')
    started = time.monotonic()
    assert auto.prune_runs(tmp_path, 1, names[-1]) == 0
    assert time.monotonic() - started < 2
    assert sorted(p.name for p in runs.iterdir()) == sorted(names)


RUN_ID_LIKE = __import__('re').compile(r'\d{8}T\d{6}Z-[0-9a-f]{8}')


def test_the_output_schema_file_is_private(cli):
    backend, home, claude, codex = cli
    backend.call('claude', 'claude-fable-5-1', auto.REVIEW_SYSTEM, 'BODY', auto.REVIEW_SCHEMA, 30)
    codex_call(backend)
    schemas = list(backend.workdir.glob('call-*/schema.json'))
    assert len(schemas) == 2 and all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in schemas)


# ---- structural boundary for prior context -----------------------------------------------------------

def stamped(offset_seconds):
    """An ISO timestamp relative to now (the receipts of a test are created now)."""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def stamped_rows(turns):
    return [{'type': 'user', 'timestamp': when, 'message': {'role': 'user', 'content': text}} for when, text in turns]


def test_prior_context_stops_at_the_first_pilot_artifact_of_the_session(tmp_path):
    root, receipts, receipt = make(tmp_path, 'final request')
    raw_transcript(tmp_path, SESSION, stamped_rows([
        (stamped(-7200), 'typed long before the pilot existed'), (stamped(-3600), 'typed an hour before'),
        (stamped(3600), 'typed after outputs could have been surfaced'), (stamped(7200), 'final request')]))
    packet = packet_for(tmp_path, root, receipts)
    assert [t['text'] for t in packet['precedingContext']] == ['typed long before the pilot existed', 'typed an hour before']
    # The bound is the earlier of the prompt and the first artifact: a prompt sent before it also bounds the context.
    raw_transcript(tmp_path, SESSION, stamped_rows([
        (stamped(-7200), 'early'), (stamped(-1800), 'late but still before'), (stamped(-600), 'final request')]))
    assert [t['text'] for t in packet_for(tmp_path, root, receipts)['precedingContext']] == ['early', 'late but still before']


def test_prior_context_is_omitted_when_the_boundary_or_a_timestamp_cannot_be_established(tmp_path):
    root, receipts, receipt = make(tmp_path, 'final request')
    session = receipt['sessionHash']
    rows = stamped_rows([(stamped(-7200), 'early one'), (stamped(-3600), 'early two'), (stamped(-60), 'final request')])
    raw_transcript(tmp_path, SESSION, rows)

    def scan(boundaries, transcript_rows=None):
        if transcript_rows:
            raw_transcript(tmp_path, SESSION, transcript_rows)
        index = auto.TranscriptIndex(config_for(tmp_path)['transcriptRoots'], {session: {receipt['promptHash']}}, boundaries)
        return index.matches(session, receipt['promptHash'])[0]['prior']
    assert [t['text'] for t in scan({session: 4102444800.0})] == ['early one', 'early two']    # year 2100: a control
    assert scan(None) == [] and scan({}) == [] and scan({session: None}) == []             # unknown boundary
    # The prompt's own record has no usable timestamp: the limit cannot be established.
    broken = stamped_rows([(stamped(-7200), 'early one'), (stamped(-3600), 'early two')]) + [
        {'type': 'user', 'message': {'role': 'user', 'content': 'final request'}}]
    assert scan({session: 4102444800.0}, broken) == []
    # A prior turn without a timestamp is left out; its neighbours stay.
    mixed = [{'type': 'user', 'message': {'role': 'user', 'content': 'undated'}}] + stamped_rows([
        (stamped(-3600), 'dated'), (stamped(-60), 'final request')])
    assert [t['text'] for t in scan({session: 4102444800.0}, mixed)] == ['dated']


def test_session_boundaries_take_the_earliest_artifact_and_fail_closed(tmp_path):
    root, receipts, first = make(tmp_path, 'first request', turn='a')
    _, _, second = make(tmp_path, 'second request', turn='b')
    rows = v2.joined(root, receipts)
    bounds = auto.session_boundaries(rows)
    earliest = min(auto._timestamp(r['receipt']['observedAt']) for r in rows)
    assert bounds == {first['sessionHash']: min(earliest, *[r['observation']['createdAt'] for r in rows])}
    broken = [{**row, 'receipt': {**row['receipt'], 'observedAt': 'garbage'}} if row['id'] == second['opportunityId'] else row
              for row in rows]
    assert auto.session_boundaries(broken) == {first['sessionHash']: None}
    assert auto.session_boundaries(list(reversed(broken))) == {first['sessionHash']: None}


# ---- round 2: Codex login handling and the early tool kill -------------------------------------------

def test_a_refresh_with_new_top_level_keys_or_without_the_lock_is_skipped_and_counted(cli):
    backend, home, claude, codex = cli
    real = home / '.codex/auth.json'
    original = real.read_text()
    (home / 'codex-behavior').write_text('newkey')
    codex_call(backend)
    assert real.read_text() == original and backend.auth_writebacks == 0 and backend.auth_writeback_skips == 1
    (home / 'codex-behavior').write_text('refresh')
    with open(home / '.codex/.laya-auth.lock', 'w') as held:                  # another labeler is between copy and write-back
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = codex_call(backend)
    assert result['answer'] == {'answers': []} and real.read_text() == original
    assert backend.auth_writebacks == 0 and backend.auth_writeback_skips == 2
    codex_call(backend)                                                       # the lock is free again: the refresh lands
    assert json.loads(real.read_text())['tokens']['access'] == 'REFRESHED-TOKEN-VALUE' and backend.auth_writebacks == 1


def test_the_real_login_is_opened_without_following_symlinks_and_must_be_ours(cli, tmp_path):
    backend, home, claude, codex = cli
    real = home / '.codex/auth.json'
    target = tmp_path / 'elsewhere.json'
    target.write_text(real.read_text())
    real.unlink()
    real.symlink_to(target)
    for action in (lambda: codex_call(backend), lambda: backend.preflight('codex')):
        with pytest.raises(auto.LabelerError, match='codex_auth_unavailable'):
            action()
    real.unlink()
    real.mkdir()                                                              # not a regular file
    with pytest.raises(auto.LabelerError, match='codex_auth_unavailable'):
        codex_call(backend)
    assert not (home / 'codex-call.json').exists()


def test_writeback_and_skip_counts_reach_the_run_summary(cli, tmp_path):
    backend, home, claude, codex = cli
    make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    (home / 'codex-behavior').write_text('refresh')
    summary, _ = auto.execute(config_for(tmp_path), backend=backend, clock=Clock())
    assert summary['codexAuthWritebacks'] == 1 and 'codexAuthWritebackSkipped' not in summary
    assert 'REFRESHED-TOKEN-VALUE' not in json.dumps(summary)
    (home / 'codex-behavior').write_text('newkey')
    summary, _ = auto.execute(config_for(tmp_path), backend=backend, clock=Clock(), force=True)
    assert summary['codexAuthWritebackSkipped'] == 1


def test_stale_private_codex_homes_from_a_killed_run_are_swept_at_start(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    runs = tmp_path / 'state/runs'
    old = runs / '20260901T000000Z-aaaaaaaa'
    (old / 'call-001-codex/codex-home').mkdir(parents=True)
    (old / 'call-001-codex/codex-home/auth.json').write_text('{"tokens": {"a": "b"}}')
    keep = tmp_path / 'outside-codex-home'
    keep.mkdir()
    (keep / 'auth.json').write_text('untouched')
    (runs / '20260902T000000Z-bbbbbbbb/call-001-codex').mkdir(parents=True)
    (runs / '20260902T000000Z-bbbbbbbb/call-001-codex/codex-home').symlink_to(keep)
    go(tmp_path, FakeBackend(), no_import=True)
    assert not (old / 'call-001-codex/codex-home').exists() and (old / 'call-001-codex').is_dir()
    assert (keep / 'auth.json').read_text() == 'untouched'                    # a symlink is never followed


def test_a_codex_tool_item_is_killed_on_the_first_line_and_recorded_as_a_failure(cli):
    backend, home, claude, codex = cli
    (home / 'codex-behavior').write_text('tool')
    started = time.monotonic()
    with pytest.raises(auto.LabelerError, match='codex_attempted_a_tool_or_item'):
        codex_call(backend)
    assert time.monotonic() - started < 15                                    # not the 30 s call timeout, let alone 60 s
    pid = int((home / 'codex-tool.pid').read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        raise AssertionError('the Codex process outlived its tool attempt')
    assert not (home / 'tool-kept-running').exists() and not list(backend.workdir.glob('call-*/codex-home'))
    # The guard alone: reasoning and messages pass, anything else (or a malformed item) raises, noise is ignored.
    for fine in ({'type': 'item.completed', 'item': {'type': 'reasoning'}}, {'type': 'turn.started'}):
        auto.codex_line_guard(json.dumps(fine).encode())
    auto.codex_line_guard(b'   ')
    for bad in ({'type': 'item.started', 'item': {'type': 'file_change'}}, {'type': 'item.completed'},
                {'type': 'item.started', 'item': 'text'}, {'type': 'item.updated', 'item': {'type': 'command_execution'}},
                {'type': 'item.whatever', 'item': {'type': 'mcp_tool_call'}}):
        with pytest.raises(auto.LabelerError, match='tool_or_item'):
            auto.codex_line_guard(json.dumps(bad).encode())
    auto.codex_line_guard(json.dumps({'type': 'item.updated', 'item': {'type': 'agent_message', 'text': 'x'}}).encode())
    for invalid in (b'not json', b'[1, 2]', b'"text"', b'{"type": "item.completed"'):
        with pytest.raises(auto.LabelerError, match='codex_invalid_output'):
            auto.codex_line_guard(invalid)


# ---- round 2: ledger counting, run-import validation, and confirmations ------------------------------

def test_import_pending_rows_never_use_up_attempts_but_model_failures_still_do(tmp_path, monkeypatch):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    real = labels.import_batch
    # Lock contention and I/O errors raise from import_batch; they are recorded as import_failed and never count.
    monkeypatch.setattr(labels, 'import_batch', lambda *a, **k: (_ for _ in ()).throw(BlockingIOError(11, 'busy')))
    for _ in range(auto.MAX_ATTEMPTS + 1):
        assert go(tmp_path, FakeBackend())[0]['reason'] == 'import_failed'
    assert list(auto.load_ledger(tmp_path / 'state').values()) == [{'terminal': False, 'failures': 0, 'deterministicSkips': 0}]
    monkeypatch.setattr(labels, 'import_batch', real)
    assert go(tmp_path, FakeBackend())[0]['status'] == 'completed'
    # Control: genuine model failures are still counted and stop after MAX_ATTEMPTS, and deadline cut-offs never count.
    root2 = tmp_path / 'second'
    root2.mkdir()
    make(root2, 'do the thing')
    transcript(root2, SESSION, [('user', 'do the thing')])
    for _ in range(auto.MAX_ATTEMPTS):
        go(root2, FakeBackend(annotate=lambda host, case: {**ANSWER, 'family': 'not_a_family'}))
    assert go(root2, FakeBackend())[0]['skipped'] == {'already_attempted': 1}
    root3 = tmp_path / 'third'
    root3.mkdir()
    make(root3, 'another thing')
    transcript(root3, SESSION, [('user', 'another thing')])

    class Late(FakeBackend):
        def call(self, host, model, system, prompt, schema, timeout):
            raise auto.LabelerError('timed_out')
    for _ in range(auto.MAX_ATTEMPTS + 2):
        summary, _ = go(root3, Late(), config={'deadlineSeconds': 200, 'callTimeoutSeconds': 900})
        assert summary['outcomes'] == {'not_attempted': 1} and summary['selected'] == 1
    assert go(root3, FakeBackend())[0]['status'] == 'completed'


def _saved_run(tmp_path):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    summary, _ = go(tmp_path, FakeBackend(), no_import=True)
    path = Path(summary['runDir']) / 'annotations.json'
    return root, receipts, path, json.loads(path.read_text())


def test_import_run_validates_the_saved_records_before_importing_anything(tmp_path):
    root, receipts, path, records = _saved_run(tmp_path)
    record = records[0]
    reviewer_is_annotator = json.loads(json.dumps(record))
    reviewer_is_annotator['review']['observedModel'] = record['annotators'][0]['observedModel']
    self_reported = json.loads(json.dumps(record))
    self_reported['review']['identitySource'] = 'model_self_report'
    unreviewed = {**record, 'review': None}
    one_annotator = {**record, 'annotators': record['annotators'][:1]}
    missing = {k: v for k, v in record.items() if k != 'sourceSha256'}
    human = {**record, 'humanAdjudicated': True}
    bad_id = {**record, 'opportunityId': 'not-a-digest'}
    cases = [([record, record], 'annotations_duplicate_record'),
             ([record, {**record, 'opportunityId': 'f' * 64}], 'annotations_duplicate_record'),      # same caseId, new id
             ([missing], 'annotations_record_incomplete'), ([bad_id], 'annotations_record_incomplete'),
             ([human], 'annotations_record_basis'), ([unreviewed], 'annotations_record_not_reviewed'),
             ([self_reported], 'annotations_reviewer_identity_not_cli_metadata'),
             ([reviewer_is_annotator], 'annotations_reviewer_is_an_annotator_model'),
             ([one_annotator], 'annotations_annotators_incomplete'), ({'not': 'a list'}, 'annotations_malformed'),
             (['junk'], 'annotations_record_incomplete')]
    for altered, reason in cases:
        path.write_text(json.dumps(altered))
        with pytest.raises(auto.LabelerError, match=reason):
            auto.import_run(config_for(tmp_path), path.parent)
        assert labels.load_labels(root) == [] and ledger_rows(tmp_path) == [], reason
    path.write_text(json.dumps(records))                                                        # the control
    assert auto.import_run(config_for(tmp_path), path.parent)[0]['import']['results'] == {'recorded': 1}
    # Non-label records (no reviewer involved) stay valid.
    other = {**record, 'opportunityId': 'e' * 64, 'caseId': 'C002', 'status': 'checker_disagreement', 'review': None}
    auto.validate_run_records([record, other])


def test_review_batches_follow_the_full_prompt_including_proposals(tmp_path, monkeypatch):
    prompts = ['request %d %s' % (n, 'z' * 3000) for n in range(3)]
    for n, prompt in enumerate(prompts):
        make(tmp_path, prompt, turn='t%d' % n)
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])
    big = tmp_path / 'big.md'
    big.write_text('# Taxonomy\n' + 'rule text. ' * 1800)
    monkeypatch.setattr(auto, 'TAXONOMY_DOC', big)
    prepared, _ = go(tmp_path, FakeBackend(), prepare_only=True)
    packets = read_run_file(prepared, 'packets.json')
    sizes = [auto.entry_bytes(p) for p in packets]          # later packets carry the earlier prompts as context
    budget = len(auto.annotation_prompt(big.read_text(), []).encode()) + sizes[0] + sizes[1] + 100
    backend = FakeBackend()
    summary, code = go(tmp_path, backend, config={'packetBytes': budget})
    assert code == 0 and summary['outcomes'] == {'labeled': 3}
    annotate = [c for c in backend.calls if 'answers' in c['schema']['properties']]
    review = [c for c in backend.calls if 'reviews' in c['schema']['properties']]
    assert len(annotate) == 4 and len(review) == 3                       # two annotate batches; the pair splits in review
    assert sorted(len(cases_in(c['prompt'])) for c in annotate) == [1, 1, 2, 2]
    assert all(len(c['prompt'].encode()) <= budget for c in backend.calls if len(cases_in(c['prompt'])) > 1)
    assert sorted(len(cases_in(c['prompt'])) for c in review) == [1, 1, 1]      # proposals push the pair over budget


def test_pruning_never_follows_a_symlinked_runs_directory(tmp_path):
    state = tmp_path / 'state'
    state.mkdir(mode=0o700)
    outside = tmp_path / 'outside'
    victims = [outside / ('2026092%dT000000Z-0000000%d' % (n, n)) for n in range(1, 4)]
    for victim in victims:
        victim.mkdir(parents=True)
        (victim / 'keep.txt').write_text('mine')
    (state / 'runs').symlink_to(outside)
    assert auto.prune_runs(state, 1, 'current') == 0 and auto.sweep_codex_homes(state, 'current') == 0
    assert all((v / 'keep.txt').read_text() == 'mine' for v in victims)


def test_a_deterministic_import_skip_stops_after_two_runs_with_no_further_model_calls(tmp_path, monkeypatch):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    real = labels.import_batch
    reason = {'value': 'label_contradicts_exclusions'}

    def skipping(*args, **kwargs):
        result = real(*args, dry_run=True, **{k: v for k, v in kwargs.items() if k != 'dry_run'})
        return {**result, 'dispositions': [{**d, 'result': 'skipped', 'reason': reason['value']} for d in result['dispositions']]}
    monkeypatch.setattr(labels, 'import_batch', skipping)
    spent = []
    for attempt in range(auto.MAX_DETERMINISTIC_SKIPS):
        backend = FakeBackend()
        summary, code = go(tmp_path, backend)
        spent.append(len(backend.calls))
        assert code == 3 and summary['importSkipped'] == {reason['value']: 1} and summary['selected'] == 1
    assert spent == [3, 3]                                                   # two annotators and a reviewer each time
    assert all(row['disposition'] == 'skipped' and 'deterministic' not in row for row in ledger_rows(tmp_path))
    for _ in range(3):
        backend = FakeBackend()
        summary, code = go(tmp_path, backend)
        assert code == 0 and summary['status'] == 'nothing_to_do' and backend.calls == [] and backend.preflights == []
        assert summary['skipped'] == {'deterministic_skip_exhausted': 1} and summary['deterministicSkipExhausted'] == 1
    assert list(auto.load_ledger(tmp_path / 'state').values()) == [{'terminal': False, 'failures': 0, 'deterministicSkips': 2}]
    # A changed packet is a different attempt, and --force always overrides the ledger.
    transcript(tmp_path, SESSION, [('user', 'a new earlier turn'), ('user', 'add a report filter')])
    assert go(tmp_path, FakeBackend())[0]['selected'] == 1
    assert go(tmp_path, FakeBackend(), force=True)[0]['selected'] == 1


@pytest.mark.parametrize('reason', ['label_contradicts_exclusions', 'immutable label already exists',
                                    'a brand new validation message nobody has seen'])
def test_every_skip_reason_counts_as_deterministic_including_new_ones(tmp_path, monkeypatch, reason):
    root, receipts, receipt = make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    real = labels.import_batch

    def skipping(*args, **kwargs):
        result = real(*args, dry_run=True, **{k: v for k, v in kwargs.items() if k != 'dry_run'})
        return {**result, 'dispositions': [{**d, 'result': 'skipped', 'reason': reason} for d in result['dispositions']]}
    monkeypatch.setattr(labels, 'import_batch', skipping)
    calls = 0
    for _ in range(auto.MAX_DETERMINISTIC_SKIPS + 2):
        backend = FakeBackend()
        go(tmp_path, backend)
        calls += len(backend.calls)
    assert calls == 3 * auto.MAX_DETERMINISTIC_SKIPS and auto.MAX_ATTEMPTS == 3
    assert not hasattr(auto, 'TRANSIENT_SKIP_REASONS') and not hasattr(auto, 'skip_is_transient')       # no dead constants


# ---- round 3: login refresh rule, FIFO, lock release, guard edges ------------------------------------------

REAL_SHAPE = {'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None, 'last_refresh': 't0',
              'tokens': {'id_token': 'i0', 'access_token': 'a0', 'refresh_token': 'r0', 'account_id': 'acct'}}


def refresh_with(cli, payload, start=REAL_SHAPE):
    backend, home, claude, codex = cli
    real = home / '.codex/auth.json'
    real.write_text(json.dumps(start))
    (home / 'codex-behavior').write_text('payload')
    (home / 'codex-payload').write_text(json.dumps(payload))
    codex_call(backend)
    return backend, real, json.loads(real.read_text())


def tokens(**changes):
    value = dict(REAL_SHAPE['tokens'])
    for key, new in changes.items():
        value.pop(key, None) if new is ... else value.__setitem__(key, new)
    return value


@pytest.mark.parametrize('name,payload', [
    ('emptied tokens', {**REAL_SHAPE, 'tokens': {}}),
    ('tokens removed', {k: v for k, v in REAL_SHAPE.items() if k != 'tokens'}),
    ('a top-level key dropped', {k: v for k, v in REAL_SHAPE.items() if k != 'last_refresh'}),
    ('the null key dropped', {k: v for k, v in REAL_SHAPE.items() if k != 'OPENAI_API_KEY'}),
    ('a token sub-key dropped', {**REAL_SHAPE, 'tokens': tokens(refresh_token=...)}),
    ('a token emptied', {**REAL_SHAPE, 'tokens': tokens(access_token='')}),
    ('a token nulled', {**REAL_SHAPE, 'tokens': tokens(id_token=None)}),
    ('a value nulled', {**REAL_SHAPE, 'auth_mode': None}),
    ('a value emptied', {**REAL_SHAPE, 'auth_mode': ''}),
    ('tokens replaced by a string', {**REAL_SHAPE, 'tokens': 'x'}),
    ('an unknown top-level key', {**REAL_SHAPE, 'extra': 'x'}),
    ('an unknown token key', {**REAL_SHAPE, 'tokens': {**REAL_SHAPE['tokens'], 'extra': 'x'}}),
    ('empty object', {})])
def test_a_refresh_that_removes_or_empties_the_login_is_refused_loudly(cli, capsys, name, payload):
    backend, real, after = refresh_with(cli, payload)
    assert after == REAL_SHAPE, name                                            # the real login is untouched
    assert backend.auth_writebacks == 0 and backend.auth_writeback_skips == 1
    assert 'codex login status' in capsys.readouterr().err and 'codex login status' in backend.warnings[0]


def test_a_rotated_refresh_token_and_known_additions_are_written_back(cli, capsys):
    rotated = {**REAL_SHAPE, 'last_refresh': 't1', 'tokens': tokens(refresh_token='r1', access_token='a1', id_token='i1')}
    backend, real, after = refresh_with(cli, rotated)
    assert after == rotated and backend.auth_writebacks == 1 and backend.auth_writeback_skips == 0
    assert capsys.readouterr().err == '' and stat.S_IMODE(real.stat().st_mode) == 0o600
    original = {k: v for k, v in REAL_SHAPE.items() if k != 'last_refresh'}           # an allowlisted key may be added
    added = {**original, 'last_refresh': 't2', 'tokens': tokens(refresh_token='r2')}
    backend2, real2, after2 = refresh_with(cli, added, start=original)
    assert after2 == added and backend2.auth_writebacks == 2


def test_the_skip_warning_reaches_the_summary_without_changing_the_exit_code(cli, tmp_path):
    backend, home, claude, codex = cli
    make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    (home / '.codex/auth.json').write_text(json.dumps(REAL_SHAPE))
    (home / 'codex-behavior').write_text('payload')
    (home / 'codex-payload').write_text(json.dumps({**REAL_SHAPE, 'tokens': {}}))
    summary, code = auto.execute(config_for(tmp_path), backend=backend, clock=Clock())
    assert summary['codexAuthWritebackSkipped'] == 1 and 'codex login status' in summary['warnings'][0]
    assert code == 3 and json.loads((home / '.codex/auth.json').read_text()) == REAL_SHAPE     # exit 3 is the empty answers, not the warning


def test_a_fifo_named_auth_json_cannot_hang_the_run(cli):
    import threading
    backend, home, claude, codex = cli
    real = home / '.codex/auth.json'
    real.unlink()
    os.mkfifo(real)
    caught = []

    def attempt():
        try:
            backend.preflight('codex')
        except auto.LabelerError as exc:
            caught.append(str(exc))
    thread = threading.Thread(target=attempt, daemon=True)
    thread.start()
    thread.join(10)
    assert not thread.is_alive() and caught == ['codex_auth_unavailable']


def test_the_lock_is_released_when_setup_fails_after_it_was_taken(tmp_path):
    home = tmp_path / 'codex'
    home.mkdir()
    (home / 'auth.json').write_text(json.dumps(REAL_SHAPE))
    blocker = tmp_path / 'not-a-directory'
    blocker.write_text('x')
    with pytest.raises(OSError):
        auto.CodexLogin(home, blocker / 'codex-home').open()
    with open(home / '.laya-auth.lock', 'w') as probe:
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)                      # not held any more
    assert not (blocker / 'codex-home').exists()


def test_codex_output_is_checked_to_the_last_byte_and_noise_fails_closed(cli, tmp_path):
    child = [sys.executable, '-c', 'import sys; sys.stdout.write(\'{"type": "item.started", "item": {"type": "command_execution"}}\'); sys.stdout.flush()']
    env = auto.child_env({'PATH': os.environ.get('PATH', '')})
    with pytest.raises(auto.LabelerError, match='tool_or_item'):                  # the final line has no newline
        auto.run_process(child, b'', tmp_path, 20, env, guard=auto.codex_line_guard)
    fine = [sys.executable, '-c', 'import sys; sys.stdout.write(\'{"type": "turn.completed"}\')']
    assert auto.run_process(fine, b'', tmp_path, 20, env, guard=auto.codex_line_guard)[0] == 0
    backend, home, claude, codex = cli
    (home / 'codex-behavior').write_text('noise')
    started = time.monotonic()
    with pytest.raises(auto.LabelerError, match='codex_invalid_output'):
        codex_call(backend)
    assert time.monotonic() - started < 15
    pid = int((home / 'codex-noise.pid').read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        raise AssertionError('the Codex process outlived its invalid output')


# ---- round 3: saved-run tamper checks and oversized prompts ------------------------------------------------

def test_import_run_rejects_unknown_statuses_other_runs_and_manifest_disagreements(tmp_path):
    root, receipts, path, records = _saved_run(tmp_path)
    record, run_dir = records[0], path.parent
    manifest_path = run_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    other_run = {**record, 'runId': '20260101T000000Z-deadbeef'}
    empty_names = json.loads(json.dumps(record))
    empty_names['annotators'][0]['observedModel'] = ''
    cases = [([{**record, 'status': 'approved'}], 'annotations_record_status_unknown'),
             ([{**record, 'status': 'not_a_label'}], 'annotations_record_status_unknown'),
             ([other_run], 'annotations_record_from_another_run'), ([empty_names], 'annotations_annotators_incomplete'),
             ([{**record, 'caseId': 'C099'}], 'annotations_record_not_in_manifest'),
             ([{**record, 'contextPacketSha256': 'a' * 64}], 'annotations_record_disagrees_with_manifest'),
             ([{**record, 'sourceSha256': 'b' * 64}], 'annotations_record_disagrees_with_manifest'),
             ([{**record, 'opportunityId': 'c' * 64}], 'annotations_record_disagrees_with_manifest')]
    for altered, reason in cases:
        path.write_text(json.dumps(altered))
        with pytest.raises(auto.LabelerError, match=reason):
            auto.import_run(config_for(tmp_path), run_dir)
        assert labels.load_labels(root) == [] and ledger_rows(tmp_path) == [], reason
    path.write_text(json.dumps(records))
    manifest_path.write_text(json.dumps({**manifest, 'cases': []}))
    with pytest.raises(auto.LabelerError, match='annotations_record_not_in_manifest'):
        auto.import_run(config_for(tmp_path), run_dir)
    manifest_path.unlink()
    with pytest.raises(auto.LabelerError, match='run_has_no_manifest'):
        auto.import_run(config_for(tmp_path), run_dir)
    manifest_path.write_text(json.dumps(manifest))                                            # the control
    assert auto.import_run(config_for(tmp_path), run_dir)[0]['import']['results'] == {'recorded': 1}


def test_a_case_too_large_for_the_prompt_ceiling_fails_alone_without_being_sent(tmp_path, monkeypatch):
    prompts = ['small request', 'big request ' + 'z' * 3400, 'another small one']
    for n, prompt in enumerate(prompts):
        make(tmp_path, prompt, turn='t%d' % n)
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])
    taxonomy, _ = auto.load_taxonomy()
    framing = len(auto.annotation_prompt(taxonomy, []).encode())
    # Later packets carry the earlier prompts as context, so the ceiling is set just above the first one and below the rest.
    packets = read_run_file(go(tmp_path, FakeBackend(), prepare_only=True)[0], 'packets.json')
    first = auto.entry_bytes(packets[0])
    ceiling = framing + first + 1500
    monkeypatch.setattr(auto, 'MAX_PROMPT_BYTES', ceiling)
    backend = FakeBackend()
    summary, code = go(tmp_path, backend)
    assert summary['outcomes'] == {'labeled': 1, 'annotation_failed': 2} and code == 3
    sent = ''.join(c['prompt'] for c in backend.calls)
    assert 'big request' not in sent and 'another small one' not in sent and len(cases_in(backend.calls[0]['prompt'])) == 1
    assert all(len(c['prompt'].encode()) <= ceiling for c in backend.calls)
    manifest_failed = [r for r in ledger_rows(tmp_path) if r['outcome'] == 'annotation_failed']
    assert len(manifest_failed) == 2 and all(r['terminal'] is False for r in manifest_failed)
    assert auto.batch_by_size([1, 2], lambda item: 5, -100) == [[1], [2]]                     # a negative budget is clamped


def test_a_review_prompt_that_only_the_proposals_push_over_the_ceiling_fails_that_case(tmp_path, monkeypatch):
    make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    taxonomy, _ = auto.load_taxonomy()
    packets = read_run_file(go(tmp_path, FakeBackend(), prepare_only=True)[0], 'packets.json')
    entry = auto.entry_bytes(packets[0])
    monkeypatch.setattr(auto, 'MAX_PROMPT_BYTES', len(auto.annotation_prompt(taxonomy, []).encode()) + entry + 20)
    backend = FakeBackend()
    summary, code = go(tmp_path, backend)
    assert code == 3 and summary['outcomes'] == {'review_failed': 1}
    assert [c['host'] for c in backend.calls] == ['claude', 'codex']                          # the reviewer was never called
    assert read_run_file(summary, 'summary.json')['outcomes'] == {'review_failed': 1}


# ---- round 4: the canary event sequences (Codex-side warnings are not tools) ---------------------------------

CODE_MODE = 'Code Mode is unavailable because code-mode host is disabled and cannot run tools.'
FALLBACK = 'Falling back from WebSockets to HTTPS transport. stream disconnected before completion'
ANSWER_EVENT = {'type': 'item.completed', 'item': {'id': 'item_1', 'type': 'agent_message', 'text': json.dumps({'answers': []})}}


def error_item(message, kind='item.completed'):
    return {'type': kind, 'item': {'id': 'item_0', 'type': 'error', 'message': message}}


def reconnect(n):
    return {'type': 'error', 'message': 'Reconnecting... %d/5 (stream disconnected before completion)' % n}


def events(*items):
    return [json.dumps(item) for item in items]


SEQ_CODE_MODE = events({'type': 'thread.started', 'thread_id': 't'}, error_item(CODE_MODE), {'type': 'turn.started'},
                       ANSWER_EVENT, {'type': 'turn.completed', 'usage': {'input_tokens': 5, 'output_tokens': 1}})
SEQ_RECONNECT_OK = events({'type': 'thread.started', 'thread_id': 't'}, reconnect(1), reconnect(2), error_item(FALLBACK),
                          {'type': 'turn.started'}, ANSWER_EVENT, {'type': 'turn.completed', 'usage': {}})
SEQ_RECONNECT_FAILED = events({'type': 'thread.started', 'thread_id': 't'}, reconnect(1), reconnect(2), reconnect(3),
                              {'type': 'turn.failed', 'error': {'message': 'stream disconnected'}})
SEQ_ERROR_THEN_TOOL = events({'type': 'thread.started', 'thread_id': 't'}, error_item(CODE_MODE),
                             {'type': 'item.started', 'item': {'id': 'item_2', 'type': 'command_execution', 'command': 'pwd'}})


def run_events(cli, lines, sleep=False):
    backend, home, claude, codex = cli
    (home / 'codex-behavior').write_text('events')
    (home / 'codex-events').write_text('\n'.join(lines) + '\n')
    if sleep:
        (home / 'codex-events-sleep').write_text('1')
    return codex_call(backend)


def test_a_code_mode_warning_before_the_answer_is_recorded_not_fatal(cli):
    result = run_events(cli, SEQ_CODE_MODE)
    assert result['answer'] == {'answers': []} and result['codexWarnings'] == [CODE_MODE]
    assert result['codexTransientErrors'] == 0 and result['identitySource'] == 'explicit_cli_argument'


def test_reconnect_errors_and_a_transport_fallback_before_completion_succeed(cli):
    result = run_events(cli, SEQ_RECONNECT_OK)
    assert result['answer'] == {'answers': []} and result['codexTransientErrors'] == 2
    assert result['codexWarnings'] == [FALLBACK]


def test_reconnect_errors_then_a_failed_turn_is_a_failure(cli):
    with pytest.raises(auto.LabelerError, match='codex_reported_failure'):
        run_events(cli, SEQ_RECONNECT_FAILED)
    with pytest.raises(auto.LabelerError, match='codex_completion_missing'):           # errors and then nothing at all
        run_events(cli, events({'type': 'thread.started'}, reconnect(1), reconnect(2)))


def test_an_error_item_followed_by_a_tool_item_is_killed_at_once(cli):
    backend, home, claude, codex = cli
    started = time.monotonic()
    with pytest.raises(auto.LabelerError, match='codex_attempted_a_tool_or_item'):
        run_events(cli, SEQ_ERROR_THEN_TOOL, sleep=True)
    assert time.monotonic() - started < 15
    pid = int((home / 'codex-events.pid').read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        raise AssertionError('the Codex process outlived its tool attempt')


def test_error_items_never_supply_the_answer_and_their_text_is_bounded_and_redacted():
    smuggled = error_item(json.dumps({'answers': [{'caseId': 'C001'}]}))
    with pytest.raises(auto.LabelerError, match='codex_answer_missing'):              # the error text is not an answer
        auto.parse_native('codex', '\n'.join(events(smuggled, {'type': 'turn.completed', 'usage': {}})), 'gpt-5.6-sol')
    many = [error_item('warning %d ' % n + 'x' * 400) for n in range(9)] + [
        error_item('leaked ' + 'gh' + 'p_AbCdEfGhIjKlMnOpQrStUvWx1234')]
    answer, meta = auto.parse_native('codex', '\n'.join(events(*many, ANSWER_EVENT, {'type': 'turn.completed'})), 'gpt-5.6-sol')
    assert answer == {'answers': []} and len(meta['codexWarnings']) == auto.MAX_CODEX_WARNINGS == 5
    assert all(len(w) <= 200 for w in meta['codexWarnings'])
    late = error_item('leaked ' + 'gh' + 'p_AbCdEfGhIjKlMnOpQrStUvWx1234')
    _, meta = auto.parse_native('codex', '\n'.join(events(late, ANSWER_EVENT, {'type': 'turn.completed'})), 'gpt-5.6-sol')
    assert 'ghp_' not in meta['codexWarnings'][0] and 'REDACTED' in meta['codexWarnings'][0]
    assert {'agent_message', 'reasoning', 'error'} == auto.CODEX_ITEM_TYPES
    for tool in ('command_execution', 'file_change', 'mcp_tool_call', 'web_search', 'todo_list'):
        with pytest.raises(auto.LabelerError, match='tool'):
            auto.parse_native('codex', json.dumps({'type': 'item.completed', 'item': {'type': tool}}), 'gpt-5.6-sol')
        with pytest.raises(auto.LabelerError, match='tool'):
            auto.codex_line_guard(json.dumps({'type': 'item.started', 'item': {'type': tool}}).encode())


def test_codex_warnings_reach_the_call_record(cli, tmp_path):
    backend, home, claude, codex = cli
    make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    (home / 'codex-behavior').write_text('events')
    (home / 'codex-events').write_text('\n'.join(SEQ_RECONNECT_OK) + '\n')
    summary, _ = auto.execute(config_for(tmp_path), backend=backend, clock=Clock())
    record = json.loads(next(Path(summary['runDir'], 'calls').glob('*-codex.json')).read_text())
    assert record['codexWarnings'] == [FALLBACK] and record['codexTransientErrors'] == 2


# ---- round 4: extra pins on what a refresh may change ------------------------------------------------------

@pytest.mark.parametrize('name,payload', [
    ('auth mode changed', {**REAL_SHAPE, 'auth_mode': 'apikey'}),
    ('a null API key becomes a value', {**REAL_SHAPE, 'OPENAI_API_KEY': 'sk-placeholder'}),
    ('last_refresh not a string', {**REAL_SHAPE, 'last_refresh': 12345}),
    ('last_refresh empty', {**REAL_SHAPE, 'last_refresh': ''}),
    ('a token is a number', {**REAL_SHAPE, 'tokens': tokens(account_id=7)}),
    ('a token is an object', {**REAL_SHAPE, 'tokens': tokens(id_token={'x': 'y'})})])
def test_login_pins_hold_for_mode_api_key_and_value_types(cli, capsys, name, payload):
    backend, real, after = refresh_with(cli, payload)
    assert after == REAL_SHAPE and backend.auth_writeback_skips == 1, name
    assert 'codex login status' in capsys.readouterr().err


# ---- round 5: a completed turn with no message, error items that carry more than a warning, stored output ----

def test_a_completed_codex_turn_without_a_message_is_a_failed_call_and_counts_toward_the_cap(cli, tmp_path):
    lines = events({'type': 'thread.started', 'thread_id': 't'}, reconnect(1), {'type': 'turn.started'},
                   {'type': 'turn.completed', 'usage': {'input_tokens': 5, 'output_tokens': 0}})
    with pytest.raises(auto.LabelerError, match='codex_answer_missing'):
        auto.parse_native('codex', '\n'.join(lines), 'gpt-5.6-sol')
    with pytest.raises(auto.LabelerError, match='codex_answer_missing'):              # through the real CLI path as well
        run_events(cli, lines)
    with pytest.raises(auto.LabelerError, match='codex_answer_missing'):              # an agent_message with no text
        auto.parse_native('codex', '\n'.join(events(
            {'type': 'item.completed', 'item': {'id': 'i', 'type': 'agent_message'}}, {'type': 'turn.completed'})), 'gpt-5.6-sol')
    # A reasoning-only turn is the same failure; a message plus completion still succeeds (control).
    with pytest.raises(auto.LabelerError, match='codex_answer_missing'):
        auto.parse_native('codex', '\n'.join(events(
            {'type': 'item.completed', 'item': {'id': 'i', 'type': 'reasoning', 'text': 'hm'}}, {'type': 'turn.completed'})),
            'gpt-5.6-sol')
    answer, _ = auto.parse_native('codex', '\n'.join(events(ANSWER_EVENT, {'type': 'turn.completed'})), 'gpt-5.6-sol')
    assert answer == {'answers': []}

    prompts = ['request %d %s' % (n, 'x' * 3400) for n in range(5)]
    for n, prompt in enumerate(prompts):
        make(tmp_path, prompt, turn='t%d' % n)
    transcript(tmp_path, SESSION, [('user', prompt) for prompt in prompts])

    class NoMessage(FakeBackend):
        def call(self, host, model, system, prompt, schema, timeout):
            self.calls.append({'host': host})
            auto.parse_native('codex', '\n'.join(lines), model)             # raises codex_answer_missing
    backend = NoMessage()
    summary, code = go(tmp_path, backend, config={'packetBytes': 4096})
    assert code == 3 and len(backend.calls) == auto.MAX_FAILED_CALLS_IN_A_ROW
    assert summary['outcomes'] == {'annotation_failed': auto.MAX_FAILED_CALLS_IN_A_ROW, 'not_attempted': 2}


@pytest.mark.parametrize('extra', [{'command': 'pwd'}, {'path': '/etc/passwd'}, {'status': 'completed'}, {'text': 'x'}])
def test_an_error_item_with_keys_beyond_id_type_and_message_is_a_tool_attempt(extra):
    item = {'id': 'item_0', 'type': 'error', 'message': 'Code Mode is unavailable', **extra}
    for kind in ('item.started', 'item.completed'):
        line = json.dumps({'type': kind, 'item': item})
        with pytest.raises(auto.LabelerError, match='codex_attempted_a_tool_or_item'):
            auto.codex_line_guard(line.encode())
        with pytest.raises(auto.LabelerError, match='codex_attempted_a_tool_or_item'):
            auto.parse_native('codex', line, 'gpt-5.6-sol')
    plain = json.dumps({'type': 'item.completed', 'item': {'id': 'item_0', 'type': 'error', 'message': 'ok'}})
    auto.codex_line_guard(plain.encode())                                             # control: the plain warning passes
    bare = json.dumps({'type': 'item.completed', 'item': {'type': 'error', 'message': 'ok'}})
    auto.codex_line_guard(bare.encode())


def test_call_records_store_sanitized_capped_output_and_hash_the_raw_output(cli, tmp_path):
    backend, home, claude, codex = cli
    make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])
    leaked = 'leaked ' + 'gh' + 'p_AbCdEfGhIjKlMnOpQrStUvWx1234'
    lines = events({'type': 'thread.started', 'thread_id': 't'}, error_item(leaked), {'type': 'turn.started'}, ANSWER_EVENT,
                   {'type': 'turn.completed', 'usage': {}})
    (home / 'codex-behavior').write_text('events')
    (home / 'codex-events').write_text('\n'.join(lines) + '\n')
    summary, _ = auto.execute(config_for(tmp_path), backend=backend, clock=Clock())
    record = json.loads(next(Path(summary['runDir'], 'calls').glob('*-codex.json')).read_text())
    assert 'ghp_AbCd' not in json.dumps(record) and 'REDACTED' in record['output']
    assert '"thread.started"' in record['output']                                     # the rest of the output is kept
    assert record['outputSha256'] == auto.digest('\n'.join(lines) + '\n')           # the hash still covers the raw output


def test_stored_output_is_capped_and_none_when_there_is_none(tmp_path):
    make(tmp_path, 'add a report filter')
    transcript(tmp_path, SESSION, [('user', 'add a report filter')])

    class Verbose(FakeBackend):
        def call(self, *args):
            result = super().call(*args)
            return {**result, 'raw': ('word ' * 40000) + json.dumps(result['answer'])}
    summary, _ = go(tmp_path, Verbose())
    records = [json.loads(path.read_text()) for path in Path(summary['runDir'], 'calls').glob('*.json')]
    assert records and all(len(r['output']) <= auto.MAX_STORED_OUTPUT + 100 and 'TRUNCATED' in r['output'] for r in records)
