"""typed_advice: input hygiene, mode resolution, holdback, write-once records and the choice() status map."""
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'rhize-context-manager/scripts'))
import typed_advice as ta  # noqa: E402
from typed_decisions import contract  # noqa: E402
from test_laya_transport_conformance import FakeLaya  # noqa: E402  (real loopback server)

QUESTION = 'Which skill should handle the request?'
POLICY = {'candidates': ['a', 'b']}
CANDIDATES = [{'id': 'a', 'criterion': 'use a for small tasks'}, {'id': 'b', 'criterion': 'use b for large tasks'}]
REV = 'rev-advice-1'
SECRET_REQUEST = 'Please deploy it. password=hunter2hunter2 and token: abcdef123456 now'


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def write_state(store, decision='skill-fit', mode='advise', policy=None, instrument=None, revision=REV,
                question=QUESTION, policy_value=POLICY, state=None, runtime=REV, **extra):
    """A well-formed registry-state.json (as decision_registry writes it) plus the Laya runtime file it binds to."""
    entry = {'mode': mode, 'pinned': False,
             'policySha256': policy or ta.policy_sha256(decision, question, policy_value),
             'instrumentSha256': instrument or ta.INSTRUMENT_SHA256, 'layaRevision': revision}
    entry.update(extra)
    value = {'schemaVersion': 1, 'revision': 1, 'decisions': {decision: entry}}
    value.update(state or {})
    (Path(store) / 'registry-state.json').write_text(json.dumps(value))
    if runtime:
        (Path(store) / 'laya-runtime.json').write_text(json.dumps({'revision': runtime}))


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


ZW = '\u200b'
HEAD = 'A1b2C3d4E5f6G7h8I9j0'
REVIEWER_PROBES = [  # the final reviewers' probes: (text, fragments that must not survive)
    ('the password is hunter2', ['hunter2']),
    ('my password hunter2 for the db', ['hunter2']),
    ('the password was: hunter2', ['hunter2']),
    ('password=foo bar', ['foo', 'bar']),
    ('password = foo bar baz, then retry', ['foo', 'bar', 'baz']),
    ('{\\"password\\": \\"abc def\\"} next', ['abc', 'def']),
    ('{\\"secret\\":\\"s3cr3tval\\"}', ['s3cr3tval']),
    ('{"password": "abc def"}', ['abc def']),
    ('connect to postgres://user:pa55@db:5432/app now', ['pa55', 'user:']),
    ('git clone https://ghp_token123@github.com/x/y', ['ghp_token123']),
    ('curl -u admin:s3cret https://example.test/api', ['s3cret']),
    ('curl --user admin:s3cret https://example.test', ['s3cret']),
    ('curl -H "Cookie: sid=abc123; theme=dark" https://example.test', ['abc123']),
    ('Set-Cookie: session=zzz999; Path=/', ['zzz999']),
    ('Cookie: sid=abc123def456', ['abc123def456']),
    ('key AKIAIOSFODNN7EXAMPLE leaked', ['AKIAIOSFODNN7EXAMPLE']),
    ('temporary ASIAIOSFODNN7EXAMPLE', ['ASIAIOSFODNN7EXAMPLE']),
    ('aws_secret_access_key = wJalrXUtnFEMI', ['wJalrXUtnFEMI']),
    ('access_key=AKIA-not-real-1234 and more', ['AKIA-not-real-1234']),
    ('session=abc123xyz after login', ['abc123xyz']),
    ('sessionid: abc123xyz', ['abc123xyz']),
    (f'sk-{HEAD}{ZW}{HEAD} tail', [HEAD]),  # a zero-width space splits an opaque token below the run threshold
    (f'pass{ZW}word=hunter2', ['hunter2']),
    ('\uff50\uff41\uff53\uff53\uff57\uff4f\uff52\uff44\uff1dhunter2', ['hunter2']),  # fullwidth "password="
    ('password\u2060=hunter2', ['hunter2']),  # word joiner
]


@pytest.mark.parametrize('text,fragments', REVIEWER_PROBES, ids=[t[:28] for t, _ in REVIEWER_PROBES])
def test_scrub_masks_the_reviewer_probes(text, fragments):
    out = ta.scrub(text)
    assert '<redacted>' in out, out
    for fragment in fragments:
        assert fragment not in out, (fragment, out)


def test_scrub_keeps_ordinary_text_readable():
    for text in ('Fix the login page layout', 'Review the session handling docs', 'Rename the users table migration',
                 'See https://example.test/docs/a?b=1 for details', 'Run tests in src/auth_test.py please'):
        out = ta.scrub(text)
        assert out == text, (text, out)
    assert ta.scrub('See https://example.test/docs/a?b=1') == 'See https://example.test/docs/a?b=1'


def test_scrub_redacts_before_truncating(tmp_path):
    out = ta.scrub('a ' * 745 + 'Z' * 40 + ' tail')  # the opaque run straddles the 1500 character cut
    assert 'ZZZ' not in out and out.endswith('<redacted>') and len(out) <= ta.REQUEST_CHARS
    out = ta.scrub('a ' * 745 + 'token=abcdefghijklmnop rest')
    assert 'abcdef' not in out and len(out) <= ta.REQUEST_CHARS


def test_scrub_is_bounded_in_time_on_adversarial_input():
    start = time.monotonic()
    for text in ('password' * 8000, 'a' * 100000, 'password=a ' * 6000, 'a://b' * 16000, 'is ' * 30000 + 'password',
                 'Cookie: a=b; ' * 5000, '{\\"password\\": ' * 5000):
        assert len(ta.scrub(text)) <= ta.REQUEST_CHARS
    assert time.monotonic() - start < 5


def test_criteria_are_scrubbed_in_the_request_and_the_snapshot(tmp_path):
    leaky = [{'id': 'a', 'criterion': 'use a when token=abcd1234efgh is set'},
             {'id': 'b', 'criterion': 'use b for postgres://u:pa55@db jobs'}]
    payload, _ = ta.build_request('Fix it', [], QUESTION, leaky)
    text = json.dumps(payload)
    assert 'abcd1234efgh' not in text and 'pa55' not in text and '<redacted>' in text
    write_state(tmp_path)
    result = run(tmp_path, Laya(), candidates=leaky)
    snapshot = (tmp_path / 'skill-fit' / 'snapshot' / f"{result['decisionId']}.json").read_text()
    assert 'abcd1234efgh' not in snapshot and 'pa55' not in snapshot
    assert [c['id'] for c in json.loads(snapshot)['candidates']] == ['a', 'b']


@pytest.mark.parametrize('bad', [
    'secrets/prod.txt', 'app/secret/key.txt', 'a/secrets/b/c.txt', '.netrc', 'home/.netrc', '_netrc', '.npmrc', 'web/.npmrc',
    '.pypirc', 'kubeconfig', 'deploy/kubeconfig.yaml', '.kube/config', '.ssh/config', '.aws/config',
    'sa/service-account.json', 'gcp/service-account-prod.json', 'token.json', 'cfg/token.json', 'infra/prod.tfvars',
    'infra/prod.auto.tfvars', 'a/b.tfvars.json', 'config/.env/anything.txt', 'config/.env.local/x.txt',
    f'.env{ZW}', f'.n{ZW}etrc', 'a/credentials/x.json', 'keys/server.pem/readme.txt'])
def test_clean_files_checks_every_component(bad):
    assert ta.clean_files([bad, 'src/ok.py']) == ['src/ok.py'], bad


def test_clean_files_still_keeps_ordinary_names():
    assert ta.clean_files(['docs/env.md', 'src/token_bucket.py', 'src/secretary.py'.replace('secretary', 'sec'),
                           'infra/main.tf', 'README.md']) == ['docs/env.md', 'src/token_bucket.py', 'src/sec.py',
                                                              'infra/main.tf', 'README.md']


# ------------------------------------------------------------------ effective_mode

def test_missing_and_corrupt_state_read_as_shadow(tmp_path):
    assert ta.effective_mode('skill-fit', 'p', tmp_path) == 'shadow'
    (tmp_path / 'registry-state.json').write_text('{not json')
    assert ta.effective_mode('skill-fit', 'p', tmp_path) == 'shadow'
    (tmp_path / 'registry-state.json').write_text('{"decisions": ["x"]}')
    assert ta.effective_mode('skill-fit', 'p', tmp_path) == 'shadow'
    (tmp_path / 'registry-state.json').write_text('{"decisions": {}}')
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
    write_state(tmp_path, revision='abc123', runtime=None)  # state binds a revision, laya-runtime.json absent
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'
    (tmp_path / 'laya-runtime.json').write_text('{"revision": "abc123"}')
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'advise'
    (tmp_path / 'laya-runtime.json').write_text('{"revision": "def456"}')  # Laya moved on
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'


@pytest.mark.parametrize('revision', [None, 'unknown', 5, ''], ids=['null', 'unknown', 'int', 'empty'])
def test_an_advise_entry_without_a_real_laya_revision_is_shadow(tmp_path, revision):
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    write_state(tmp_path)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'advise'  # control
    write_state(tmp_path, revision=revision)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'


def test_an_advise_entry_missing_its_revision_key_is_shadow(tmp_path):
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    write_state(tmp_path)
    value = json.loads((tmp_path / 'registry-state.json').read_text())
    del value['decisions']['skill-fit']['layaRevision']
    (tmp_path / 'registry-state.json').write_text(json.dumps(value))
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'


def test_unknown_runtime_never_matches_an_unknown_binding(tmp_path):
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    write_state(tmp_path, revision='unknown', runtime=None)  # both sides 'unknown' must not read as a match
    assert ta.laya_revision(tmp_path) == 'unknown' and ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'


@pytest.mark.parametrize('state', [
    {'schemaVersion': 2}, {'schemaVersion': True}, {'schemaVersion': '1'}, {'schemaVersion': None},
    {'revision': 0}, {'revision': -1}, {'revision': '3'}, {'revision': True}, {'revision': 1.5}, {'revision': None},
], ids=lambda v: json.dumps(v))
def test_a_malformed_state_envelope_is_shadow(tmp_path, state):
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    write_state(tmp_path)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'advise'  # control
    write_state(tmp_path, state=state)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'
    write_state(tmp_path, mode='off', state=state)  # an unreadable envelope cannot even switch things off
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'


@pytest.mark.parametrize('field', ['schemaVersion', 'revision'])
def test_a_state_missing_an_envelope_field_is_shadow(tmp_path, field):
    write_state(tmp_path)
    value = json.loads((tmp_path / 'registry-state.json').read_text())
    del value[field]
    (tmp_path / 'registry-state.json').write_text(json.dumps(value))
    assert ta.effective_mode('skill-fit', ta.policy_sha256('skill-fit', QUESTION, POLICY), tmp_path) == 'shadow'


@pytest.mark.parametrize('pinned', ['yes', 1, None], ids=['string', 'int', 'null'])
def test_an_entry_whose_pinned_is_not_a_bool_is_shadow(tmp_path, pinned):
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    write_state(tmp_path, pinned=pinned)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'
    write_state(tmp_path, pinned=True)  # a pin is a valid bool; the mode it pins still applies
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'advise'
    write_state(tmp_path, mode='off', pinned=pinned)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'


@pytest.mark.parametrize('bits', [0o664, 0o620, 0o602, 0o666])
def test_a_group_or_world_writable_state_file_is_shadow(tmp_path, bits):
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    write_state(tmp_path)
    state = tmp_path / 'registry-state.json'
    state.chmod(0o640)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'advise'  # control: read-only for others is fine
    state.chmod(bits)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'
    state.chmod(0o600)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'advise'


@pytest.mark.parametrize('bits', [0o770, 0o707, 0o777])
def test_a_group_or_world_writable_store_root_is_shadow(tmp_path, bits):
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    store = tmp_path / 'store'
    store.mkdir(mode=0o700)
    write_state(store)
    assert ta.effective_mode('skill-fit', good, store) == 'advise'  # control
    try:
        store.chmod(bits)
        assert ta.effective_mode('skill-fit', good, store) == 'shadow'
    finally:
        store.chmod(0o700)


def test_state_or_root_owned_by_someone_else_is_shadow(tmp_path, monkeypatch):
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    write_state(tmp_path)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'advise'  # control
    monkeypatch.setattr(ta.os, 'geteuid', lambda: os.stat(tmp_path).st_uid + 1)
    assert ta.effective_mode('skill-fit', good, tmp_path) == 'shadow'


def test_off_still_wins_over_a_stale_binding(tmp_path):
    write_state(tmp_path, mode='off', policy='0' * 64, instrument='0' * 64, revision=None)
    assert ta.effective_mode('skill-fit', 'x' * 64, tmp_path) == 'off'


def test_a_symlinked_state_file_reads_as_shadow(tmp_path):
    store = tmp_path / 'store'
    store.mkdir()
    write_state(tmp_path)  # real state elsewhere
    good = ta.policy_sha256('skill-fit', QUESTION, POLICY)
    (store / 'registry-state.json').write_text((tmp_path / 'registry-state.json').read_text())
    (store / 'laya-runtime.json').write_text((tmp_path / 'laya-runtime.json').read_text())
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
    assert sorted(p.name for p in tmp_path.iterdir()) == ['laya-runtime.json', 'registry-state.json']


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


def test_group_is_stored_hashed(tmp_path):
    write_state(tmp_path)
    result = run(tmp_path, Laya(), group='session-7')
    assert ta.load('skill-fit', result['decisionId'], store=tmp_path)['groupSha256'] == ta.sha256('session-7')


@pytest.fixture
def no_session_env(monkeypatch):
    for name in ta.SESSION_ENV:
        monkeypatch.delenv(name, raising=False)


def group_of(tmp_path, key):
    result = run(tmp_path, Laya(), key=key)
    return ta.load('skill-fit', result['decisionId'], store=tmp_path)['groupSha256']


def test_default_group_is_the_host_session_id(tmp_path, monkeypatch, no_session_env):
    write_state(tmp_path)
    monkeypatch.setenv('CODEX_THREAD_ID', 'thread-9')
    assert group_of(tmp_path, 'k-1') == ta.sha256('session:thread-9')
    assert group_of(tmp_path, 'k-2') == ta.sha256('session:thread-9')  # same session, different occurrence
    monkeypatch.setenv('CLAUDE_SESSION_ID', 'claude-1')  # earlier names in SESSION_ENV win
    assert group_of(tmp_path, 'k-3') == ta.sha256('session:claude-1')


def test_default_group_falls_back_to_cwd_and_utc_date_never_the_key(tmp_path, no_session_env):
    write_state(tmp_path)
    expected = ta.sha256(ta.sha256(os.path.realpath(os.getcwd()) + time.strftime('%Y-%m-%d', time.gmtime())))
    first, second = group_of(tmp_path, 'k-1'), group_of(tmp_path, 'k-2')
    assert first == second == expected
    assert first not in (ta.sha256('k-1'), ta.sha256('k-2'))


def test_record_has_the_documented_fields_and_no_raw_request_text(tmp_path, no_session_env):
    write_state(tmp_path)
    laya = Laya()
    result = run(tmp_path, laya, request=SECRET_REQUEST, files=['src/a.py', '/etc/passwd'], critical_if_wrong=True)
    path = tmp_path / 'skill-fit' / 'choice' / f"{result['decisionId']}.json"
    record = json.loads(path.read_text())
    assert set(record) == {'schema', 'decision', 'decisionId', 'ts', 'mode', 'arm', 'tier', 'policySha256',
                           'instrumentSha256', 'layaRevision', 'candidates', 'criticalIfWrong', 'requestSha256',
                           'files', 'groupSha256', 'laya'}
    assert record['groupSha256'] != ta.sha256(key_for('skill-fit', False))  # the key is never the group
    assert record['schema'] == 'rhize-typed-choice-record-v1' and record['decision'] == 'skill-fit'
    assert record['tier'] == 'advisory' and record['arm'] == 'treatment' and record['mode'] == 'advise'
    assert record['candidates'] == ['a', 'b'] and record['criticalIfWrong'] is True and record['files'] == 1
    assert record['requestSha256'] == sha(ta.scrub(SECRET_REQUEST)) and record['layaRevision'] == REV
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


# ------------------------------------------------------------------ kinds, reuse and the shown marker

@pytest.mark.parametrize('kind', ['../x', 'x/../choice', '', 'Choice', 'choice/', 'labels', 'tmp', '.', 'shown2'])
def test_write_once_and_load_accept_only_the_known_kinds(tmp_path, kind):
    decision_id = 'a' * 32
    with pytest.raises(ValueError):
        ta.write_once(tmp_path, 'skill-fit', kind, decision_id, {'x': 1})
    assert not (tmp_path / 'x').exists() and not (tmp_path / 'skill-fit').exists()
    planted = tmp_path / 'x'
    planted.mkdir()
    (planted / f'{decision_id}.json').write_text('{"planted": true}')
    (tmp_path / 'skill-fit').mkdir()
    assert ta.load('skill-fit', decision_id, kind=kind, store=tmp_path) is None


def test_every_known_kind_round_trips(tmp_path):
    assert ta.KINDS == ('choice', 'snapshot', 'outcome', 'label', 'shown')
    for kind in ta.KINDS:
        assert ta.write_once(tmp_path, 'skill-fit', kind, 'b' * 32, {'kind': kind}) is True
        assert ta.write_once(tmp_path, 'skill-fit', kind, 'b' * 32, {'kind': 'other'}) is False
        assert ta.load('skill-fit', 'b' * 32, kind=kind, store=tmp_path) == {'kind': kind}


def shown_path(store, result, decision='skill-fit'):
    return store / decision / 'shown' / f"{result['decisionId']}.json"


def test_a_shown_marker_is_written_when_and_only_when_a_recommendation_is_returned(tmp_path):
    write_state(tmp_path)
    key = key_for('skill-fit', False)
    result = run(tmp_path, Laya(probabilities={'a': 0.8, 'b': 0.2}), key=key)
    assert result['recommendation']['id'] == 'a'
    marker = json.loads(shown_path(tmp_path, result).read_text())
    assert marker == {'schema': ta.SHOWN_SCHEMA, 'decision': 'skill-fit', 'decisionId': result['decisionId'],
                      'recommendation': 'a', 'policySha256': result['policySha256'], 'ts': marker['ts']}
    assert contract.validate_choice_shown(marker) == marker
    assert stat.S_IMODE(shown_path(tmp_path, result).stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / 'skill-fit' / 'shown').stat().st_mode) == 0o700
    before = shown_path(tmp_path, result).read_text()
    again = run(tmp_path, Laya(), key=key)  # a repeat reuses the record and the write-once marker
    assert again['recommendation']['id'] == 'a' and shown_path(tmp_path, result).read_text() == before


@pytest.mark.parametrize('case', ['holdback', 'shadow', 'off', 'timeout', 'unknown-pick'])
def test_no_shown_marker_without_a_returned_recommendation(tmp_path, case):
    write_state(tmp_path, mode={'shadow': 'shadow', 'off': 'off'}.get(case, 'advise'))
    laya = {'timeout': Laya('timeout', None, None), 'unknown-pick': Laya('ok', 'not-a-candidate')}.get(case, Laya())
    result = run(tmp_path, laya, key=key_for('skill-fit', case == 'holdback'))
    assert result['recommendation'] is None
    assert not (tmp_path / 'skill-fit' / 'shown').exists()


def test_a_failed_marker_write_means_no_recommendation(tmp_path):
    write_state(tmp_path)
    (tmp_path / 'skill-fit').mkdir()
    (tmp_path / 'skill-fit' / 'shown').write_text('not a directory')
    laya = Laya()
    result = run(tmp_path, laya)
    assert result['mode'] == 'advise' and result['recommendation'] is None and len(laya.calls) == 1
    assert ta.load('skill-fit', result['decisionId'], store=tmp_path) is not None  # the choice record itself exists


def test_a_record_written_under_an_older_laya_revision_is_not_shown(tmp_path):
    write_state(tmp_path)
    key = key_for('skill-fit', False)
    first = run(tmp_path, Laya(), key=key)
    assert first['recommendation']['id'] == 'a' and shown_path(tmp_path, first).exists()  # control
    shown_path(tmp_path, first).unlink()
    write_state(tmp_path, revision='rev-advice-2', runtime='rev-advice-2')  # Laya was upgraded and re-earned
    laya = Laya(choice='b', probabilities={'a': 0.1, 'b': 0.9})
    second = run(tmp_path, laya, key=key)
    assert second['mode'] == 'advise' and second['recommendation'] is None
    assert laya.calls == [] and not shown_path(tmp_path, second).exists()
    assert ta.load('skill-fit', first['decisionId'], store=tmp_path)['layaRevision'] == REV  # the old record stands


def test_a_record_written_under_another_instrument_is_not_shown(tmp_path):
    write_state(tmp_path)
    key = key_for('skill-fit', False)
    first = run(tmp_path, Laya(), key=key)
    shown_path(tmp_path, first).unlink()
    path = tmp_path / 'skill-fit' / 'choice' / f"{first['decisionId']}.json"
    record = json.loads(path.read_text())
    record['instrumentSha256'] = '0' * 64
    path.write_text(json.dumps(record))
    assert run(tmp_path, Laya(), key=key)['recommendation'] is None and not shown_path(tmp_path, first).exists()


@pytest.mark.parametrize('change', [{'schema': 'x'}, {'decision': 'nope'}, {'decisionId': 'xyz'},
                                    {'recommendation': 'bad id!'}, {'recommendation': None}, {'policySha256': 'A' * 64},
                                    {'ts': 'yesterday'}, {'extra': 1}])
def test_the_shown_marker_validator_rejects_malformed_markers(tmp_path, change):
    write_state(tmp_path)
    result = run(tmp_path, Laya())
    marker = json.loads(shown_path(tmp_path, result).read_text())
    assert contract.validate_choice_shown(dict(marker)) == marker  # control
    with pytest.raises(ValueError):
        contract.validate_choice_shown({**marker, **change})
    with pytest.raises(ValueError):
        contract.validate_choice_shown({k: v for k, v in marker.items() if k != 'recommendation'})


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
