"""typed_advice: input hygiene, mode resolution, holdback, write-once records and the choice() status map."""
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'rhize-context-manager/scripts'))
import typed_advice as ta  # noqa: E402
from test_laya_transport_conformance import FakeLaya  # noqa: E402  (real loopback server)

QUESTION = 'Which skill should handle the request?'
POLICY = {'candidates': ['a', 'b']}
CANDIDATES = [{'id': 'a', 'criterion': 'use a for small tasks'}, {'id': 'b', 'criterion': 'use b for large tasks'}]
SECRET_REQUEST = 'Please deploy it. password=hunter2hunter2 and token: abcdef123456 now'


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def write_state(store, decision='skill-fit', mode='advise', policy=None, instrument=None, revision=None,
                question=QUESTION, policy_value=POLICY, **extra):
    entry = {'mode': mode,
             'policySha256': policy or ta.policy_sha256(decision, question, policy_value),
             'instrumentSha256': instrument or ta.INSTRUMENT_SHA256, 'layaRevision': revision}
    entry.update(extra)
    (Path(store) / 'registry-state.json').write_text(json.dumps({'decisions': {decision: entry}}))


def key_for(decision, held, prefix='k'):
    for i in range(10000):
        key = f'{prefix}{i}'
        if ta.holdback(decision, key) is held:
            return key
    raise AssertionError('no key found')


class Laya:
    """A fake `call=` that records its invocations."""

    def __init__(self, status='ok', choice='a', probabilities=None):
        self.answer = {'status': status, 'choice': choice, 'probabilities': probabilities or {'a': 0.8, 'b': 0.2},
                       'latencyMs': 1.0}
        self.calls = []

    def __call__(self, request, files, question, candidates, **kwargs):
        self.calls.append({'request': request, 'files': files, 'question': question, 'kwargs': kwargs})
        return dict(self.answer)


def run(store, call, *, decision='skill-fit', key=None, request='Fix the sign-in page', candidates=None, **kwargs):
    kwargs.setdefault('critical_if_wrong', False)
    return ta.advise(decision, request, candidates or CANDIDATES, key or key_for(decision, False),
                     question=QUESTION, policy=POLICY, store=store, call=call, **kwargs)


# ------------------------------------------------------------------ scrub / clean_files

def test_scrub_collapses_whitespace_and_leaves_clean_text_alone():
    assert ta.scrub('  Fix\n\tthe   login\r\npage  ') == 'Fix the login page'
    assert ta.scrub(None) == '' and ta.scrub(['x']) == ''


@pytest.mark.parametrize('text,secret', [
    ('password=hunter2xyz', 'hunter2xyz'),
    ('use PASSWORD: s3cretvalue please', 's3cretvalue'),
    ('API_KEY: abc123def', 'abc123def'),
    ('api-key = abc123def', 'abc123def'),
    ('Authorization Bearer tok3nvalue', 'tok3nvalue'),
    ('Authorization: Bearer tok3nvalue', 'tok3nvalue'),
    ('PGPASSWORD=pg-pass-1 psql', 'pg-pass-1'),
    ('password="my pass phrase"', 'pass phrase'),
    ("secret='two words'", 'two words'),
    ('{"password": "abc def"}', 'abc def'),
    ('client_secret=zzz999', 'zzz999'),
])
def test_scrub_masks_credential_assignments(text, secret):
    out = ta.scrub(text)
    assert secret not in out and '<redacted>' in out, out


def test_scrub_masks_long_opaque_runs_but_not_ordinary_words():
    assert ta.scrub('key ' + 'x' * 40 + ' end') == 'key <redacted> end'
    assert ta.scrub('x' * 31) == 'x' * 31
    assert ta.scrub('sk-' + 'A1b2' * 12) == '<redacted>'
    assert ta.scrub('Fix the login page layout') == 'Fix the login page layout'


def test_scrub_caps_at_1500_characters():
    assert len(ta.scrub('word ' * 2000)) == ta.REQUEST_CHARS == 1500


@pytest.mark.parametrize('bad', [
    '/etc/passwd', '~/notes.md', 'C:\\Users\\x\\a.txt', 'c:/x', '../up.py', 'a/../b.py', '.env', '.env.local',
    'config/.env.production', 'server.pem', 'keys/tls.key', 'id_rsa', 'home/id_ed25519', 'my-credentials.json',
    'client_secret.json', 'a\x00b.py', 'a\tb.py', 'x' * 201, '', '   '])
def test_clean_files_drops_unsafe_names(bad):
    assert ta.clean_files([bad, 'src/ok.py']) == ['src/ok.py']


def test_clean_files_keeps_plain_relative_paths_dedupes_and_caps():
    assert ta.clean_files(['src/a.py', ' src/a.py ', 'src\\b.py', 'docs/env.md', None, 3]) == [
        'src/a.py', 'src/b.py', 'docs/env.md']
    assert ta.clean_files(None) == [] and ta.clean_files([]) == []
    assert ta.clean_files([f'f{i}.py' for i in range(25)]) == [f'f{i}.py' for i in range(20)]


# ------------------------------------------------------------------ effective_mode

def test_missing_and_corrupt_state_read_as_shadow(tmp_path):
    assert ta.effective_mode('skill-fit', 'p', tmp_path) == 'shadow'
    (tmp_path / 'registry-state.json').write_text('{not json')
    assert ta.effective_mode('skill-fit', 'p', tmp_path) == 'shadow'
    (tmp_path / 'registry-state.json').write_text('{"decisions": ["x"]}')
    assert ta.effective_mode('skill-fit', 'p', tmp_path) == 'shadow'
    write_state(tmp_path, mode='bogus')
    assert ta.effective_mode('skill-fit', 'p', tmp_path) == 'shadow'
    write_state(tmp_path, decision='workflow-fit')  # no entry for the decision asked about
    assert ta.effective_mode('skill-fit', 'p', tmp_path) == 'shadow'


@pytest.mark.parametrize('mode,expected', [('off', 'off'), ('shadow', 'shadow'), ('cosign', 'shadow'),
                                           ('advise', 'advise')])
def test_mode_matrix_with_a_matching_binding(tmp_path, mode, expected):
    write_state(tmp_path, mode=mode)
    assert ta.effective_mode('skill-fit', ta.policy_sha256('skill-fit', QUESTION, POLICY), tmp_path) == expected


def test_advise_requires_every_binding_to_match(tmp_path):
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    write_state(tmp_path)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'advise'  # control: the matching state advises
    assert ta.effective_mode('skill-fit', 'f' * 64, tmp_path) == 'shadow'  # policy differs
    write_state(tmp_path, policy='0' * 64)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'
    write_state(tmp_path, instrument='0' * 64)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'
    write_state(tmp_path, revision='abc123')  # state binds a revision, laya-runtime.json absent -> 'unknown'
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'
    (tmp_path / 'laya-runtime.json').write_text('{"revision": "abc123"}')
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'advise'
    (tmp_path / 'laya-runtime.json').write_text('{"revision": "def456"}')  # Laya moved on
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'
    write_state(tmp_path, revision=None)  # a null revision binds nothing
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'advise'


def test_a_symlinked_state_file_reads_as_shadow(tmp_path):
    store = tmp_path / 'store'
    store.mkdir()
    write_state(tmp_path)  # real state elsewhere
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    (store / 'registry-state.json').write_text((tmp_path / 'registry-state.json').read_text())
    assert ta.effective_mode('skill-fit', good, store) == 'advise'  # control: a regular file works
    (store / 'registry-state.json').unlink()
    (store / 'registry-state.json').symlink_to(tmp_path / 'registry-state.json')
    assert ta.effective_mode('skill-fit', good, store) == 'shadow'


def test_laya_revision_reads_a_valid_revision_only(tmp_path):
    assert ta.laya_revision(tmp_path) == 'unknown'
    (tmp_path / 'laya-runtime.json').write_text('{"revision": "55cf4c4ebb4e"}')
    assert ta.laya_revision(tmp_path) == '55cf4c4ebb4e'
    (tmp_path / 'laya-runtime.json').write_text('{"revision": "bad rev!"}')
    assert ta.laya_revision(tmp_path) == 'unknown'


def test_tiers_agree_with_the_catalog():
    catalog = json.loads((REPO / 'rhize-context-manager/catalog/decision-registry.json').read_text())
    entries = catalog['decisions']
    entries = entries.items() if isinstance(entries, dict) else ((e['id'], e) for e in entries)
    for decision, entry in entries:
        assert ta.TIERS.get(decision) == entry['tier'], decision


# ------------------------------------------------------------------ holdback

def test_holdback_is_deterministic_per_decision_and_key():
    assert [ta.holdback('skill-fit', f'k{i}') for i in range(200)] == [ta.holdback('skill-fit', f'k{i}')
                                                                       for i in range(200)]
    assert ta.holdback('skill-fit', 'k1') == (int(sha('holdback:skill-fit:k1')[:8], 16) / 2 ** 32 < 0.10)


@pytest.mark.parametrize('decision,share', [('devflow-next-action', 0.15), ('check-relaxation', 0.15),
                                            ('skill-fit', 0.10), ('workflow-fit', 0.10)])
def test_holdback_share_matches_the_tier(decision, share):
    held = sum(ta.holdback(decision, f'key-{i}') for i in range(20000)) / 20000
    assert abs(held - share) <= 0.01, held


def test_holdback_is_independent_of_the_split_domain():
    keys = [f'session-{i}' for i in range(30000)]
    held = [k for k in keys if ta.holdback('skill-fit', k)]
    tuning = lambda k: int(sha('split:' + k)[:8], 16) / 2 ** 32 < 2 / 3  # noqa: E731
    assert len(held) > 2000
    assert abs(sum(tuning(k) for k in held) / len(held) - 2 / 3) < 0.05  # holdback does not predict the split
    assert abs(sum(tuning(k) for k in keys) / len(keys) - 2 / 3) < 0.02


# ------------------------------------------------------------------ advise

def test_off_makes_no_call_writes_nothing_and_recommends_nothing(tmp_path):
    write_state(tmp_path, mode='off')
    laya = Laya()
    result = run(tmp_path, laya)
    assert result['mode'] == 'off' and result['recommendation'] is None and laya.calls == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ['registry-state.json']


def test_shadow_records_a_choice_and_snapshot_but_never_recommends(tmp_path):
    write_state(tmp_path, mode='shadow')
    laya = Laya()
    result = run(tmp_path, laya)
    assert result['mode'] == 'shadow' and result['recommendation'] is None and len(laya.calls) == 1
    record = ta.load('skill-fit', result['decisionId'], store=tmp_path)
    assert record['laya']['choice'] == 'a' and record['mode'] == 'shadow'
    assert ta.load('skill-fit', result['decisionId'], kind='snapshot', store=tmp_path)['candidates'] == CANDIDATES


def test_missing_state_behaves_as_shadow(tmp_path):
    laya = Laya()
    result = run(tmp_path, laya)
    assert result['mode'] == 'shadow' and result['recommendation'] is None and len(laya.calls) == 1


def test_advise_treatment_returns_the_recommendation(tmp_path):
    write_state(tmp_path)
    result = run(tmp_path, Laya(probabilities={'a': 0.8123456, 'b': 0.1876544}))
    assert result['mode'] == 'advise' and result['holdback'] is False
    assert result['recommendation'] == {'id': 'a', 'confidence': 0.812}
    assert set(result) == {'decisionId', 'mode', 'holdback', 'recommendation', 'policySha256'}


def test_advise_holdback_calls_laya_and_records_but_never_recommends(tmp_path):
    write_state(tmp_path)
    laya = Laya()
    result = run(tmp_path, laya, key=key_for('skill-fit', True))
    assert result['holdback'] is True and result['recommendation'] is None and len(laya.calls) == 1
    record = ta.load('skill-fit', result['decisionId'], store=tmp_path)
    assert record['arm'] == 'holdback' and record['laya']['status'] == 'ok'


def test_a_repeat_returns_the_stored_answer_without_calling_laya_again(tmp_path):
    write_state(tmp_path)
    key = key_for('skill-fit', False)
    first_laya, second_laya = Laya(choice='a'), Laya(choice='b', probabilities={'a': 0.1, 'b': 0.9})
    first = run(tmp_path, first_laya, key=key)
    second = run(tmp_path, second_laya, key=key)
    assert second_laya.calls == [] and second == first and second['recommendation']['id'] == 'a'


def test_a_stored_record_for_another_policy_is_not_shown_as_advice(tmp_path):
    write_state(tmp_path)
    key = key_for('skill-fit', False)
    first = run(tmp_path, Laya(), key=key)
    record_path = tmp_path / 'skill-fit' / 'choice' / f"{first['decisionId']}.json"
    record = json.loads(record_path.read_text())
    record['policySha256'] = '0' * 64
    record_path.write_text(json.dumps(record))
    assert run(tmp_path, Laya(), key=key)['recommendation'] is None


@pytest.mark.parametrize('broken', ['file', 'readonly'])
def test_a_failed_write_means_no_recommendation(tmp_path, broken):
    if broken == 'readonly' and os.geteuid() == 0:
        pytest.skip('root ignores directory permissions')
    store = tmp_path / 'store'
    store.mkdir()
    write_state(store)
    if broken == 'file':
        (store / 'skill-fit').write_text('not a directory')
    else:
        store.chmod(0o500)
    try:
        laya = Laya()
        result = run(store, laya)
    finally:
        store.chmod(0o700)
    assert result['mode'] == 'advise' and result['recommendation'] is None and len(laya.calls) == 1
    assert ta.load('skill-fit', result['decisionId'], store=store) is None


@pytest.mark.parametrize('answer', [Laya('timeout', None, None), Laya('invalid', None, None),
                                    Laya('unavailable', None, None), Laya('ok', 'not-a-candidate')])
def test_a_laya_failure_or_unknown_pick_means_no_recommendation(tmp_path, answer):
    write_state(tmp_path)
    result = run(tmp_path, answer)
    assert result['recommendation'] is None
    assert ta.load('skill-fit', result['decisionId'], store=tmp_path)['laya']['status'] == answer.answer['status']


@pytest.mark.parametrize('candidates', [
    [CANDIDATES[0]],
    [{'id': f'c{i}', 'criterion': 'x'} for i in range(17)],
    [CANDIDATES[0], CANDIDATES[0]],
    [CANDIDATES[0], {'id': 'bad id!', 'criterion': 'x'}],
    [CANDIDATES[0], {'id': '-lead', 'criterion': 'x'}],
    [CANDIDATES[0], {'id': 'b', 'criterion': 'x', 'extra': 1}],
    [CANDIDATES[0], {'id': 'b'}],
    [CANDIDATES[0], {'id': 'b', 'criterion': '   '}],
    [CANDIDATES[0], {'id': 3, 'criterion': 'x'}],
    [CANDIDATES[0], 'b'],
    None, 'ab'])
def test_invalid_candidates_raise_before_any_call(tmp_path, candidates):
    laya = Laya()
    with pytest.raises(ValueError):
        ta.advise('skill-fit', 'req', candidates, 'k', critical_if_wrong=False, question=QUESTION, policy=POLICY,
                  store=tmp_path, call=laya)
    assert laya.calls == []


def test_sixteen_candidates_are_allowed(tmp_path):
    write_state(tmp_path, mode='shadow')
    assert run(tmp_path, Laya(), candidates=[{'id': f'c{i}', 'criterion': 'x'} for i in range(16)])


def test_unknown_decision_and_empty_key_raise(tmp_path):
    with pytest.raises(ValueError, match='unknown decision'):
        ta.advise('nope', 'req', CANDIDATES, 'k', critical_if_wrong=False, question=QUESTION, policy=POLICY,
                  store=tmp_path, call=Laya())
    for key in ('', None, 5):
        with pytest.raises(ValueError, match='key'):
            ta.advise('skill-fit', 'req', CANDIDATES, key, critical_if_wrong=False, question=QUESTION,
                      policy=POLICY, store=tmp_path, call=Laya())


def test_record_has_the_documented_fields_and_no_raw_request_text(tmp_path):
    write_state(tmp_path)
    laya = Laya()
    result = run(tmp_path, laya, request=SECRET_REQUEST, files=['src/a.py', '/etc/passwd'], critical_if_wrong=True)
    path = tmp_path / 'skill-fit' / 'choice' / f"{result['decisionId']}.json"
    record = json.loads(path.read_text())
    assert set(record) == {'schema', 'decision', 'decisionId', 'ts', 'mode', 'arm', 'tier', 'policySha256',
                           'instrumentSha256', 'layaRevision', 'candidates', 'criticalIfWrong', 'requestSha256',
                           'files', 'laya'}
    assert record['schema'] == 'rhize-typed-choice-record-v1' and record['decision'] == 'skill-fit'
    assert record['tier'] == 'advisory' and record['arm'] == 'treatment' and record['mode'] == 'advise'
    assert record['candidates'] == ['a', 'b'] and record['criticalIfWrong'] is True and record['files'] == 1
    assert record['requestSha256'] == sha(ta.scrub(SECRET_REQUEST)) and record['layaRevision'] == 'unknown'
    assert record['instrumentSha256'] == ta.INSTRUMENT_SHA256 and record['policySha256'] == result['policySha256']
    assert set(record['laya']) == {'status', 'choice', 'probabilities', 'latencyMs'}
    assert record['decisionId'] == result['decisionId'] == sha('skill-fit:' + key_for('skill-fit', False))[:32]
    text = path.read_text()
    for fragment in ('Please deploy', 'hunter2', 'abcdef123456', 'sign-in', 'use a for small'):
        assert fragment not in text, fragment


def test_snapshot_holds_only_scrubbed_text(tmp_path):
    write_state(tmp_path)
    result = run(tmp_path, Laya(), request=SECRET_REQUEST, files=['src/a.py', '.env', '../x'])
    path = tmp_path / 'skill-fit' / 'snapshot' / f"{result['decisionId']}.json"
    snapshot = json.loads(path.read_text())
    assert snapshot['request'] == ta.scrub(SECRET_REQUEST) and snapshot['files'] == ['src/a.py']
    assert snapshot['scrub'] == ta.SCRUB_VERSION and snapshot['candidates'] == CANDIDATES
    assert 'hunter2' not in path.read_text() and 'abcdef123456' not in path.read_text()


def test_the_scrubbed_request_is_what_laya_is_asked(tmp_path):
    write_state(tmp_path)
    payload, key_map = ta.build_request(SECRET_REQUEST, ['src/a.py', '/abs'], QUESTION, CANDIDATES)
    assert 'hunter2' not in json.dumps(payload) and payload['state']['files'] == ['src/a.py']
    assert key_map == {'c0': 'a', 'c1': 'b'} and set(payload['questions']['pick']['criteria']) == {'c0', 'c1'}


def test_snapshot_can_be_skipped(tmp_path):
    write_state(tmp_path)
    result = run(tmp_path, Laya(), snapshot=False)
    assert ta.load('skill-fit', result['decisionId'], store=tmp_path) is not None
    assert not (tmp_path / 'skill-fit' / 'snapshot').exists()


def test_files_are_private_and_directories_owner_only(tmp_path):
    write_state(tmp_path)
    result = run(tmp_path, Laya())
    record_id = result['decisionId']
    for kind in ('choice', 'snapshot'):
        directory = tmp_path / 'skill-fit' / kind
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE((directory / f'{record_id}.json').stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / 'skill-fit').stat().st_mode) == 0o700
    assert ta.record_outcome('skill-fit', record_id, 'a', store=tmp_path)
    assert stat.S_IMODE((tmp_path / 'skill-fit' / 'outcome' / f'{record_id}.json').stat().st_mode) == 0o600
    assert not [p for p in (tmp_path / 'skill-fit').rglob('.tmp-*')]


def test_a_symlinked_decision_directory_is_refused(tmp_path):
    store = tmp_path / 'store'
    store.mkdir()
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    write_state(store)
    (store / 'skill-fit').symlink_to(elsewhere)
    laya = Laya()
    result = run(store, laya)
    assert result['recommendation'] is None and len(laya.calls) == 1
    assert list(elsewhere.iterdir()) == []


def test_a_symlinked_record_kind_directory_is_refused(tmp_path):
    store = tmp_path / 'store'
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (store / 'skill-fit').mkdir(parents=True)
    write_state(store)
    (store / 'skill-fit' / 'choice').symlink_to(elsewhere)
    result = run(store, Laya())
    assert result['recommendation'] is None and list(elsewhere.iterdir()) == []


def test_critical_decisions_use_the_critical_holdback_and_tier(tmp_path):
    write_state(tmp_path, decision='devflow-next-action')
    key = key_for('devflow-next-action', False)
    result = run(tmp_path, Laya(), decision='devflow-next-action', key=key, critical_if_wrong=True)
    record = ta.load('devflow-next-action', result['decisionId'], store=tmp_path)
    assert record['tier'] == 'critical' and record['criticalIfWrong'] is True
    assert result['recommendation'] == {'id': 'a', 'confidence': 0.8}


# ------------------------------------------------------------------ record_outcome

def test_first_outcome_wins_and_followed_is_computed(tmp_path):
    write_state(tmp_path, mode='shadow')
    result = run(tmp_path, Laya(choice='a'))
    decision_id = result['decisionId']
    assert ta.record_outcome('skill-fit', decision_id, 'b', store=tmp_path) is True
    assert ta.record_outcome('skill-fit', decision_id, 'a', store=tmp_path) is False
    outcome = ta.load('skill-fit', decision_id, kind='outcome', store=tmp_path)
    assert outcome['chosen'] == 'b' and outcome['followed'] is False and outcome['schema'] == ta.OUTCOME_SCHEMA


def test_followed_is_true_when_the_agent_took_the_recommendation(tmp_path):
    write_state(tmp_path, mode='shadow')
    decision_id = run(tmp_path, Laya(choice='a'))['decisionId']
    assert ta.record_outcome('skill-fit', decision_id, 'a', store=tmp_path)
    assert ta.load('skill-fit', decision_id, kind='outcome', store=tmp_path)['followed'] is True


def test_outcome_refuses_unknown_choices_missing_records_and_bad_ids(tmp_path):
    write_state(tmp_path, mode='shadow')
    decision_id = run(tmp_path, Laya())['decisionId']
    assert ta.record_outcome('skill-fit', decision_id, 'zzz', store=tmp_path) is False
    assert ta.record_outcome('skill-fit', 'f' * 32, 'a', store=tmp_path) is False
    assert ta.record_outcome('skill-fit', '../../x', 'a', store=tmp_path) is False
    assert ta.record_outcome('Bad Decision', decision_id, 'a', store=tmp_path) is False
    assert not (tmp_path / 'skill-fit' / 'outcome').exists()


# ------------------------------------------------------------------ advice_line

def test_advice_line_is_empty_without_a_recommendation():
    assert ta.advice_line('skill-fit', {'recommendation': None, 'decisionId': 'x'}, 'skill') == ''
    assert ta.advice_line('skill-fit', {'decisionId': 'x'}, 'skill') == ''


def test_advice_line_names_the_decision_and_stays_advisory():
    result = {'decisionId': 'd' * 32, 'recommendation': {'id': 'beta', 'confidence': 0.7123}}
    line = ta.advice_line('skill-fit', result, 'skill')
    assert 'd' * 32 in line and 'advisory' in line and '`beta`' in line and '0.71' in line and 'override' in line
    unscored = ta.advice_line('skill-fit', {'decisionId': 'e' * 32, 'recommendation': {'id': 'b', 'confidence': None}},
                              'skill')
    assert 'advisory' in unscored and 'confidence' not in unscored


# ------------------------------------------------------------------ choice() against a real server

def ask(url, tmp_path, **kwargs):
    return ta.choice(SECRET_REQUEST, ['src/a.py'], QUESTION, CANDIDATES, endpoint=url, store=tmp_path, **kwargs)


def test_choice_ok_maps_keys_back_to_candidate_ids_and_sends_scrubbed_text(tmp_path):
    with FakeLaya() as fake:
        result = ask(fake.url, tmp_path)
    assert result['status'] == 'ok' and result['choice'] == 'a'
    assert set(result['probabilities']) == {'a', 'b'} and abs(sum(result['probabilities'].values()) - 1) < 1e-9
    assert [h[0] for h in fake.hits] == ['GET', 'POST']
    assert 'hunter2' not in json.dumps(fake.bodies) and fake.bodies[0]['state']['files'] == ['src/a.py']


@pytest.mark.parametrize('health,post,status', [
    ('ok', 'wrong_model', 'invalid'), ('ok', 'bad_probs', 'invalid'), ('ok', 'bad_choice', 'invalid'),
    ('wrong', 'ok', 'identity_failed'), ('redirect', 'ok', 'redirect_refused'),
    ('ok', 'redirect', 'redirect_refused'), ('ok', 'big', 'invalid'), ('ok', 'error', 'unavailable')])
def test_choice_statuses(tmp_path, health, post, status):
    with FakeLaya(health, post) as fake:
        result = ask(fake.url, tmp_path)
    assert result['status'] == status
    assert result['choice'] is None and result['probabilities'] is None
    if status == 'identity_failed':
        assert [h[0] for h in fake.hits] == ['GET']  # request text never left the machine


def test_choice_slow_server_times_out_within_the_budget(tmp_path):
    with FakeLaya('ok', 'slow', delay=1.0) as fake:
        result = ask(fake.url, tmp_path, budget_ms=200)
    assert result['status'] == 'timeout' and result['latencyMs'] < 900


def test_choice_hostname_endpoint_is_unavailable_with_zero_requests(tmp_path):
    with FakeLaya() as fake:
        result = ask(fake.url.replace('127.0.0.1', 'localhost'), tmp_path)
        assert fake.hits == []
    assert result['status'] == 'unavailable'


def test_choice_never_raises_on_bad_input(tmp_path):
    assert ta.choice('req', [], 'q', 'not-a-list', store=tmp_path)['status'] == 'unavailable'
    assert ta.choice(None, None, None, [{'id': 'a'}], store=tmp_path)['status'] == 'unavailable'


def test_choice_nan_budget_is_a_timeout_not_an_exception(tmp_path):
    with FakeLaya() as fake:
        assert ask(fake.url, tmp_path, budget_ms=float('nan'))['status'] == 'timeout' and fake.hits == []


def test_advise_end_to_end_over_a_real_server(tmp_path):
    write_state(tmp_path)
    with FakeLaya() as fake:
        result = ta.advise('skill-fit', 'Fix the sign-in page', CANDIDATES, key_for('skill-fit', False),
                           critical_if_wrong=False, question=QUESTION, policy=POLICY, endpoint=fake.url,
                           store=tmp_path)
    assert result['recommendation']['id'] == 'a'
    assert (tmp_path / 'laya-health-advice.json').exists()
