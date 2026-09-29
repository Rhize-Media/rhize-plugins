"""Daily AI labeler: invented fixtures, fake backends and temp directories only.

No test starts a real model CLI, touches the network or writes below ~/.local/share/rhize.
"""
import fcntl
import json
import os
from pathlib import Path
import stat
import sys

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
        self.calls, self.preflights = [], []

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
            answer = {'answers': [{'caseId': c['caseId'], **self.annotate_fn(host, c), 'rationale': 'fixture'}
                                  for c in cases]}
        else:
            answer = {'reviews': [{'caseId': c['caseId'], **self.review_fn(c)} for c in cases]}
        return {'answer': answer, 'raw': json.dumps(answer), 'requestedModel': model, 'observedModel': model,
                'identitySource': 'fake', 'usage': {}}

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
        ('user', 'turn one'), ('assistant', 'turn two'), ('user', 'turn three'), ('assistant', 'turn four'),
        ('assistant', 'Arm A chose the content family for this one'), ('user', 'turn six'),
        ('assistant', 'turn seven'), ('user', prompt), ('assistant', 'the later answer is never included')],
        codex=True)
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
    # At most four prior turns, most recent last, and the turn that discussed an arm is dropped whole.
    assert [t['text'] for t in packet['precedingContext']] == ['turn three', 'turn four', 'turn six', 'turn seven']
    assert all(set(t) == {'role', 'text', 'truncated'} for t in packet['precedingContext'])
    assert 'later answer' not in json.dumps(packet)


def test_claude_layout_and_long_text_are_bounded(tmp_path):
    prompt = 'Explain this: ' + 'x' * 8000
    root, receipts, receipt = make(tmp_path, prompt[:15000])
    transcript(tmp_path, SESSION, [('assistant', 'z' * 9000), ('user', prompt[:15000])])
    config = config_for(tmp_path)
    cases, _ = auto.prepare_cases(root, receipts, lambda w: auto.TranscriptIndex(config['transcriptRoots'], w),
                                  {}, 'f' * 64, {**config, 'force': False})
    packet = cases[0]['packet']
    assert packet['promptTruncated'] is True and len(packet['prompt']) < auto.PROMPT_LIMIT + 100
    assert packet['precedingContext'][0]['truncated'] is True
    assert packet['precedingContext'][0]['text'].startswith('[TRUNCATED')   # assistant turns keep their tail


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
    transcript(tmp_path, SESSION, [('assistant', 'new earlier turn'), ('user', 'do the thing')])
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
open(home + '/codex-call.json', 'w').write(json.dumps({'argv': args, 'env': dict(os.environ), 'prompt': prompt,
                                                        'schema': open(args[args.index('--output-schema') + 1]).read()}))
print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps({'answers': []})}}))
print(json.dumps({'type': 'turn.completed', 'usage': {}}))
'''


@pytest.fixture
def cli(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    (home / 'auth-mode').write_text('claude.ai')
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
    assert set(env) == {'HOME', 'USER', 'PATH', 'RHIZE_AUTOLABEL_CHILD', 'DISABLE_AUTOUPDATER', 'NO_COLOR'}


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
    assert auto.main(['--state', str(tmp_path / 'state'), 'status']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'prepared'
    assert auto.main(['--root', str(root), '--receipts', str(receipts), '--state', str(tmp_path / 'state'),
                      'run', '--reviewer-model', 'gpt-5']) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'unavailable'
