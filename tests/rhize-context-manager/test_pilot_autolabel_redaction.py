"""Redaction and truncation of what the labeler sends to a model. Invented, obviously fake secrets only."""
import inspect
import re
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
import pilot_autolabel as auto


# A quadratic pattern takes minutes on these inputs; the limit only has to survive a loaded machine.
TIME_LIMIT = 8


def fake(prefix, body):
    """Built at run time so no fixture looks like a real credential in the source."""
    return prefix + body


FAMILIES = {
    'supabase secret': fake('sb_secret_', 'AbC123dEf456GhI789jKl'),
    'supabase publishable': fake('sb_publishable_', 'AbC123dEf456GhI789jKl'),
    'supabase pat': fake('sbp_', '0123456789abcdef0123456789abcdef01234567'),
    'github pat': fake('github_pat_', '11ABCDEFG0abcdefghijklmnopqrstuvwxyz0123'),
    'slack user': fake('xoxc-', '1234567890-1234567890-abcdefABCDEF'),
    'slack cookie': fake('xoxd-', 'abcDEF123456%2Bghi%2Fjkl789'),
    'google api': fake('AIza', 'SyA-1234567890abcdefghijklmnopqrstuv'),
    'npm': fake('npm_', 'abcdefghijklmnopqrstuvwxyz0123456789'),
    'vercel': fake('vcp_', 'abcdefghijklmnopqrstuvwxyz0123456'),
    'sanity': fake('sk', 'AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGhIjKlMnOp'),
    'resend with underscore': fake('re_', 'AbCd1234_efgh5678ijklmnop9012'),
    'anthropic': fake('sk-ant-', 'api03-abcdefghijklmnopqrstuvwxyz0123'),
    'aws': fake('AKIA', '0123456789ABCDEF'),
    'stripe': fake('sk_live_', 'abcdefghij0123456789'),
    'jwt': 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhYmNkZWYifQ.abcdefghijklmnop',
}


@pytest.mark.parametrize('name', sorted(FAMILIES))
def test_every_token_family_is_redacted_standalone_inline_and_boundary_adjacent(name):
    token = FAMILIES[name]
    for text in (token, 'please use ' + token + ' for the call', 'a(' + token + ')b', '"' + token + '"',
                 'first line\n' + token + '\nlast line'):
        out = auto.redact(text)
        assert token not in out and token[6:] not in out, (name, text, out)


def test_webhooks_basic_auth_sshpass_and_phone_numbers():
    hook = 'https://hooks.slack.com/services/' + 'T0123ABCD/B0123ABCD/' + 'abcdefghijklmnopqrstuvwx'
    assert 'abcdefghijklmnopqrstuvwx' not in auto.redact('post to ' + hook + ' now')
    basic = auto.redact('curl -H "Authorization: Basic dXNlcjpwYXNzd29yZA==" https://example.test')
    assert 'dXNlcjpwYXNzd29yZA' not in basic
    ssh = auto.redact('run sshpass -p hunter2hunter ssh ops@host.test')
    assert 'hunter2hunter' not in ssh and 'sshpass -p [REDACTED_PASSWORD]' in ssh
    assert 'hunter2hunter' not in auto.redact("sshpass -p 'hunter2hunter' ssh x")
    phones = auto.redact('call +1 415-555-0134 or (415) 555-0199 or 415.555.0142 or +14155550111')
    assert re.search(r'\d{3}[ .-]\d{4}', phones) is None and '+14155550111' not in phones
    assert auto.redact('build 2026-09-29 v1.2.3 id 12345') == 'build 2026-09-29 v1.2.3 id 12345'


def test_key_name_anywhere_redacts_the_whole_line():
    cases = ['{"password": "hunter2hunter"}', 'SUPABASE_SERVICE_ROLE_KEY=abc123abc123', 'aws_secret_access_key = wJalrXUtnFEMI',
             "  'client_secret': 'q1w2e3r4'  ", 'export GITHUB_TOKEN=abcdefabcdef', 'db.passphrase: correct-horse',
             'x-api-key: ghij5678']
    for text in cases:
        out = auto.redact('before\n' + text + '\nafter')
        assert out == 'before\n[REDACTED_CREDENTIAL_LINE]\nafter', (text, out)
    # Ordinary prose and counters are left alone.
    keep = 'the secret sauce is fine; set max_tokens=4096 and pass the salt; secret santa is on Friday'
    assert auto.redact(keep) == keep


def test_generic_long_mixed_case_digit_run_is_a_secret_but_identifiers_paths_and_hashes_are_not():
    assert auto.redact('key abcdEFGH1234abcdEFGH1234abcdEFGH1234abcd end') == 'key [REDACTED_TOKEN] end'
    for keep in ('feature_delivery_defect_resolution_code_health_platform', 'src/components/VeryLongComponentName/index.tsx',
                 'commit 0123456789abcdef0123456789abcdef01234567', 'short AbC123 run'):
        assert auto.redact(keep) == keep


@pytest.mark.parametrize('payload', ['a.' * 13000, 'ab.' * 9000, 'x@' * 13000, 'a-B1' * 6500, '1 ' * 13000,
                                     'http://' * 4000, 'bearer ' * 4000, 'sk-' * 8000, 'password ' * 3000,
                                     '\\-----BEGIN PRIVATE KEY-----' * 900, 'a' * 26000])
def test_redaction_time_is_linear_on_long_runs(payload):
    started = time.monotonic()
    auto.redact(payload)
    assert time.monotonic() - started < TIME_LIMIT, payload[:12]


def test_a_secret_block_before_the_cut_is_redacted_not_cut_in_half():
    body = '\n'.join('MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC%02d' % n for n in range(60))
    text = '-----BEGIN PRIVATE KEY-----\n' + body + '\n-----END PRIVATE KEY-----\ndone'
    out, cut = auto.sanitize(text, 100)
    assert 'MIIEvQIBADAN' not in out and 'BEGIN' not in out.replace('[REDACTED_PRIVATE_KEY]', '')
    # A credential straddling the old 4x pre-slice boundary is redacted before any bound applies.
    token = fake('AKIA', '0123456789ABCDEF')
    text = 'w ' * 195 + token + ' tail ' * 3
    assert token not in auto.sanitize(text, 400)[0]
    assert 'tail' not in inspect.signature(auto.sanitize).parameters           # only the head of a message is ever kept


def test_truncation_trims_a_partial_token_at_the_cut():
    out, cut = auto.sanitize('alpha beta gamma delta', 12)
    assert cut is True and out.startswith('alpha beta') and ' g' not in out and 'gamma' not in out
    assert auto.sanitize('short text', 100) == ('short text', False)
    # A single unbroken token longer than the bound is dropped rather than half shown.
    out, cut = auto.sanitize('x' * 500, 100)
    assert cut is True and 'xx' not in out
    # An absurdly large message is cut on a token edge before redaction, then still bounded.
    big = ('word ' * (auto.MAX_MESSAGE_CHARS // 5 + 10))
    out, cut = auto.sanitize(big, 100)
    assert cut is True and len(out) < 200


# ---- round 2: obfuscation, wider key names, more token shapes -------------------------------------

def line_redacted(text):
    out = auto.redact('before\n' + text + '\nafter')
    return out == 'before\n[REDACTED_CREDENTIAL_LINE]\nafter'


def test_obfuscated_key_names_are_still_credential_lines():
    zw = '\u200b'
    cases = ['pass' + zw + 'word=hunter2hunter', 'PASS\u2060WORD: hunter2hunter', 'password\u00a0=\u00a0hunter2hunter',
             'password\u3000:\u3000hunter2hunter', 'password\uff1ahunter2hunter', '\uff50assword=hunter2hunter',
             '\u0440\u0430ssword: hunter2hunter',                         # Cyrillic er and a (fail-safe)
             '\u03c1\u03b1ssword: hunter2hunter', '"\\u0070assword": "hunter2hunter"', 'pass\\x77ord=hunter2hunter',
             '"pa\\u0073\\u0073word":"hunter2hunter"', 'API' + zw + '_KEY=abcdefabcdef']
    for text in cases:
        assert line_redacted(text), text
        assert 'hunter2hunter' not in auto.redact(text)


def test_obfuscated_tokens_redact_the_original_span():
    zw = '\u200b'
    token = 'ghp_' + 'AbCdEfGhIjKlMnOpQrStUvWx1234'
    for hidden in (token[:6] + zw + token[6:], 'g' + zw + token[1:], token[:3] + '\\u005f' + token[4:],
                   'gh\\u0070_' + token[4:], token.replace('A', '\uff21', 1)):
        out = auto.redact('use ' + hidden + ' now')
        assert out == 'use [REDACTED_TOKEN] now', (hidden, out)
    assert auto.redact('nbsp\u00a0' + token + '\u00a0x') == 'nbsp\u00a0[REDACTED_TOKEN]\u00a0x'


def test_the_view_is_bounded_and_ascii_text_is_its_own_view():
    text = 'plain ascii text'
    assert auto.detection_view(text) == (text, None, None, None)
    many = '\\u0041' * (auto.MAX_ESCAPES + 500)
    started = time.monotonic()
    view, starts, ends, cutoff = auto.detection_view(many)
    assert time.monotonic() - started < TIME_LIMIT and len(view) == auto.MAX_ESCAPES
    assert ends[0] == 6 and starts[0] == 0 and cutoff == 6 * auto.MAX_ESCAPES


def test_past_the_escape_cap_the_remainder_is_redacted_not_left_literal():
    padding = '\\u0041' * (auto.MAX_ESCAPES + 1)
    text = padding + ' visible tail ' + fake('gh', 'p_AbCdEfGhIjKlMnOpQrStUvWx1234') + ' end'
    out = auto.redact(text)
    assert out.endswith('[REDACTED_UNDECODABLE_REMAINDER]') and 'visible tail' not in out and 'ghp_' not in out
    within = '\\u0041' * (auto.MAX_ESCAPES - 10) + ' ok ' + fake('gh', 'p_AbCdEfGhIjKlMnOpQrStUvWx1234')
    assert 'UNDECODABLE' not in auto.redact(within) and 'ghp_' not in auto.redact(within)          # the control


@pytest.mark.parametrize('text', ['api key: hunter2hunter', 'secret key=hunter2hunter', 'service role key: hunter2hunter',
                                  'access key id: hunter2hunter', 'pw: hunter2hunter', 'pin: 12345678',
                                  'tokens: hunter2hunter', 'my key = hunter2hunter', 'session: abcd', 'cookie: sid=abcd',
                                  'signing key: hunter2hunter', 'anon-key = hunter2hunter', 'auth: hunter2hunter',
                                  'the password is hunter2hunter', 'Her pin was 4242', 'creds: user pass',
                                  'password' + ' ' * 3 + 'x' * 200 + ' = hunter2hunter'])
def test_wider_key_names_and_natural_language_forms_redact_the_line(text):
    assert line_redacted(text), text


def test_a_value_on_the_next_line_or_in_a_block_is_redacted_with_its_key():
    for text, hidden in (('"password":\n  "hunter2hunter",', 'hunter2hunter'), ('password:\n  hunter2hunter', 'hunter2hunter'),
                         ('password=\nhunter2hunter', 'hunter2hunter'), ('token: |\n  line-one-of-body\n  line-two-of-body', 'body'),
                         ('secret: >-\n    folded-secret-value\n    more', 'folded-secret-value')):
        out = auto.redact('top: ok\n' + text + '\nnext: fine')
        assert hidden not in out and out.startswith('top: ok\n[REDACTED_CREDENTIAL_LINE]') and out.endswith('next: fine'), (text, out)
    # A block ends at the first line that is not indented deeper than the key.
    out = auto.redact('a:\n  secret: |\n    body\n    body2\n  other: keep\nend')
    assert 'body' not in out and 'other: keep' in out and out.endswith('end')
    # Ordinary text near a credential word is not swallowed.
    assert auto.redact('author: Jim\nsessions were long\nthe compass points: north') == 'author: Jim\nsessions were long\nthe compass points: north'


NEW_PREFIXES = {
    'resend without digit': fake('re_', 'AbCdEfGh_IjKlMnOp_QrStUvWxYz'),
    'sanity without digit': fake('sk', 'AbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQr'),
    'shopify': fake('shpat_', 'abcdef0123456789abcdef0123456789'),
    'gitlab': fake('glpat-', 'abcdefghij0123456789'),
    'digitalocean': fake('dop_v1_', 'abcdef0123456789abcdef0123456789abcdef01'),
    'stripe webhook': fake('whsec_', 'abcdefghijklmnopqrstuvwx'),
    'huggingface': fake('hf_', 'abcdefghijklmnopqrstuvwxyzABCDEFGH'),
    'notion': fake('ntn_', 'abcdefghijklmnopqrstuvwxyz012345'),
    'aws temporary': fake('ASIA', '0123456789ABCDEF'),
    'vercel legacy': fake('vercel_', 'abcdefghijklmnopqrstuvwx'),
    'hex run': '0123456789abcdef' * 4,
    'base64 run': 'Zm9vYmFyLWJhc2U2NC1zZWNyZXQ+dmFsdWUvd2l0aC9wdW5jdHVhdGlvbj09QUJDZGVm12',
}


@pytest.mark.parametrize('name', sorted(NEW_PREFIXES))
def test_more_token_shapes_are_redacted(name):
    token = NEW_PREFIXES[name]
    out = auto.redact('see ' + token + ' here')
    assert token not in out and out.startswith('see [REDACTED') and out.endswith('here'), (name, out)


def test_credentials_in_commands_urls_and_headers():
    cases = {'curl -u alice:hunter2hunter https://x.test': 'hunter2hunter', 'curl --user "alice:hunter2 hunter" u': 'hunter2',
             'mysql -h db.test -u root -phunter2hunter app': 'hunter2hunter', 'mysql -p"hunter2 hunter" x': 'hunter2',
             'GET https://x.test/api?key=hunter2hunter&a=1': 'hunter2hunter', 'https://x.test/f?sig=abcdef123456&x=1': 'abcdef123456',
             'https://x.test/cb?token=abcdefabcdef': 'abcdefabcdef', 'echo Basic dXNlcjpwYXNzd29yZA== | base64': 'dXNlcjpwYXNzd29yZA',
             'postgres://user:p@ss:w@rd@db.test/app': 'p@ss', 'https://svc.test/hooks/abcdefghijklmnop1234': 'abcdefghijklmnop1234',
             'https://api.test/v1/webhooks/AbCdEf123456GhIj': 'AbCdEf123456GhIj'}
    for text, secret in cases.items():
        out = auto.redact(text)
        assert secret not in out and out != text, (text, out)
    assert auto.redact('ssh -p2222 host -u root') == 'ssh -p2222 host -u root'          # a port is not a password
    assert auto.redact('use basic implementation details') == 'use basic implementation details'


def test_message_bound_is_200k_and_still_linear(tmp_path):
    assert auto.MAX_MESSAGE_CHARS == 200_000
    started = time.monotonic()
    out, cut = auto.sanitize((('ab.' * 1000 + ' ') * 120) + 'tail', 6500)
    assert cut is True and time.monotonic() - started < TIME_LIMIT
    view = 'x\u200b' * 100000
    started = time.monotonic()
    auto.redact(view)
    assert time.monotonic() - started < TIME_LIMIT


# ---- round 3: concatenated names, name/value shapes, containers, caps -----------------------------

def value_gone(text, secret='v1zzsecret'):
    out = auto.redact('top: fine\n' + text.replace('VALUE', secret) + '\nend: fine')
    return secret not in out and out.startswith('top: fine')      # a name-only line may also take the next line


@pytest.mark.parametrize('text', [
    'PGPASSWORD=VALUE', 'MYSQLPASSWORD=VALUE', 'DBPASSWORD=VALUE', 'dbPassword: VALUE', 'userPassword=VALUE',
    'adminPassword: VALUE', 'accessToken: VALUE', 'refreshToken=VALUE', 'authToken: VALUE', 'apiToken=VALUE',
    'sessionToken: VALUE', 'clientSecret: VALUE', 'appSecret=VALUE', 'stripeApiKey=VALUE', 'githubToken=VALUE',
    'GITHUBTOKEN=VALUE', 'MYSECRET=VALUE', 'APISECRET=VALUE', 'mypassword=VALUE', 'dbpass=VALUE', 'userPass: VALUE',
    '{"idToken":"VALUE"}', '"tokens":"VALUE"', '//registry.npmjs.org/:_authToken=VALUE',
    'npm config set //registry.npmjs.org/:_authToken VALUE', 'yarn config set npmAuthToken VALUE', 'dbPin=VALUE'])
def test_concatenated_and_camel_case_credential_names_are_redacted(text):
    assert value_gone(text), text


@pytest.mark.parametrize('text', ['author: Jim', 'authors: A and B', 'max_tokens=4096', 'ssh -p2222 host', 'bypass=true',
                                  'compass: north', 'trespass: no', 'overpass=1', 'passing: 3', 'what a pass through',
                                  'the password manager is fine', 'password reset flow', 'sessions were long',
                                  'The session lasted long', 'spinner: on', 'pinned: 1.2.3', 'cookies were baked',
                                  'tokens are cheap', 'authentication method', 'Author: A. Writer'])
def test_the_false_positive_controls_stay_untouched(text):
    assert auto.redact(text) == text


@pytest.mark.parametrize('text', [
    '{"name":"DB_PASSWORD","value":"VALUE"}', '- name: DB_PASSWORD\n  value: VALUE', '<password>VALUE</password>',
    '<input name="password" value="VALUE">', 'user,password\nalice,VALUE', 'user,password,email\n\nalice,VALUE,a',
    '| user | password |\n|---|---|\n| bob | VALUE |', 'ENV SECRET VALUE', 'ARG DB_PASSWORD VALUE', 'export API_TOKEN VALUE',
    'Set DB_PASSWORD to VALUE', 'the secret should be VALUE', 'password will be VALUE', 'password => VALUE',
    'api key -> VALUE', 'pw=>VALUE', 'password VALUE', 'machine host.test login me password VALUE',
    'password (again): VALUE', 'token (old) = VALUE'])
def test_value_and_tag_shapes_natural_language_and_netrc(text):
    assert value_gone(text), text


def test_a_value_inside_a_container_on_the_next_line_is_redacted_until_it_closes():
    for text in ('"password":\n[\n  "VALUE",\n  "second-VALUE"\n],', '"password":\n{\n "a": "VALUE",\n "b": ["x", "VALUE"]\n}',
                 'password:\n  [VALUE, second-VALUE]', 'secret:\n  - VALUE\n  - second-VALUE', '"token": [\n  "VALUE"\n]',
                 'password: {\n  user: x\n  pass: VALUE\n}'):
        out = auto.redact('top: fine\n' + text.replace('VALUE', 'v1zzsecret') + '\nafter: fine')
        assert 'v1zzsecret' not in out and out.startswith('top: fine') and out.endswith('after: fine'), (text, out)
    # An unclosed container is redacted to the bound (fail closed), and a closed one does not swallow what follows.
    unclosed = '"password":\n[\n' + ''.join('  "v%dzz",\n' % n for n in range(200)) + 'tail: visible'
    out = auto.redact(unclosed)
    assert 'v10zz' not in out and 'v30zz' not in out                                # redacted up to the bound
    assert auto.redact('"password":\n[\n "VALUE"\n]\nnext: kept').endswith('next: kept')


def test_a_yaml_block_still_open_at_the_cap_redacts_the_rest_of_the_message():
    body = 'password: |\n' + ''.join('  padding line %d\n' % n for n in range(auto.MAX_BLOCK_LINES + 20)) + '  the-real-value-v1zz\n'
    out = auto.redact('head: ok\n' + body + 'tail: gone-too')
    assert 'the-real-value-v1zz' not in out and 'tail: gone-too' not in out and out.startswith('head: ok\n')
    short = auto.redact('head: ok\npassword: |\n  short body v1zz\nnext: kept')
    assert 'v1zz' not in short and short.endswith('next: kept')                       # the control: a closed block ends


def test_base64_without_a_digit_is_caught_by_entropy_but_words_and_paths_are_not():
    import random
    rng = random.Random(3)
    run = ''.join(rng.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+/') for _ in range(48))
    assert any(c in run for c in '+/')
    assert not any(c.isdigit() for c in run)
    assert auto.redact('see ' + run + ' now') == 'see [REDACTED_TOKEN] now'
    for keep in ('/usr/local/lib/python/site/packages/setuptools/command/build/extension/modules',
                 'supercalifragilisticexpialidocious/electroencephalograph/counterrevolutionaries',
                 'a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p/q/r/s/t/u/v/w/x/y/z/a/b/c/d/e/f/g/h'):
        assert auto.redact(keep) == keep, keep


@pytest.mark.parametrize('payload', ['password is x ' * 15000, 'login a ' * 25000, '{"name":"password", ' * 9000,
                                     'pin to x ' * 20000, 'machine h login u password ' * 7000, 'token: ' * 25000,
                                     '"password":\n[\n' * 12000])
def test_credential_line_scans_are_linear_on_one_giant_input(payload):
    started = time.monotonic()
    auto.redact(payload[:auto.MAX_MESSAGE_CHARS])
    assert time.monotonic() - started < TIME_LIMIT, payload[:20]


# ---- round 4: pwd, containers, command bounds, headers, npm, natural forms, paths -----------------------

@pytest.mark.parametrize('text', ['pwd=VALUE', 'DB_PWD=VALUE', 'rootpwd=VALUE', 'PWD: VALUE', '"pwd":"VALUE"', 'my pass is VALUE',
                                  'the pass was VALUE', 'password → VALUE', 'token → VALUE'])
def test_pwd_names_and_the_pass_and_unicode_arrow_forms(text):
    assert value_gone(text), text


@pytest.mark.parametrize('text', ['pwd', 'cd /tmp && pwd', 'run pwd first', 'pass to the callback', 'compass is north',
                                  'bypass was closed', 'export PWD_HINT_ONLY', 'echo $PWD'])
def test_the_bare_pwd_command_and_ordinary_pass_words_stay_clean(text):
    assert auto.redact(text) == text


def test_a_container_still_open_at_the_bound_redacts_to_the_end_of_the_message():
    for secret_line in (55, 100):
        rows = ['  "line%d",' % n for n in range(secret_line)] + ['  "v1zzsecret",']
        out = auto.redact('"password": [\n' + '\n'.join(rows) + '\n  "tail"\n]\nafter: gone-too')
        assert 'v1zzsecret' not in out and 'after: gone-too' not in out, secret_line
    # The character bound is counted from where the container started (it used to reset on every line).
    wide = '"password": [\n' + '\n'.join('  "' + 'x' * 900 + '",' for _ in range(6)) + '\n  "v1zzsecret"\n]\nafter: gone-too'
    assert 'v1zzsecret' not in auto.redact(wide) and 'after: gone-too' not in auto.redact(wide)
    closed = auto.redact('"password": [\n  "v1zz"\n]\nafter: kept')
    assert 'v1zz' not in closed and closed.endswith('after: kept')


def test_brackets_inside_strings_do_not_close_a_container_and_the_key_line_may_open_it():
    for text in ('"password": [\n  "x]",\n  "v1zzsecret"\n]', '"password": {\n  "a": "}", "b": "v1zzsecret"\n}',
                 "secret: [\n  'x]', 'v1zzsecret'\n]", 'password: [a,\n  v1zzsecret, b\n]', '"token": {"a": 1,\n  "b": "v1zzsecret"}',
                 'password: [\n  "a\\\\"]", "v1zzsecret"\n]'):
        out = auto.redact('top: fine\n' + text + '\nafter: kept')
        assert 'v1zzsecret' not in out and out.endswith('after: kept'), (text, out)
    assert auto._bracket_depth('["a]", {"b": "}"}', 0) == 1 and auto._bracket_depth('a ] b', 1) == 0


def test_command_secret_has_no_quadratic_backtracking():
    for payload in ('ENV ' + 'password' * 12500, 'ENV ' + 'a' * 60000 + 'token' + 'b' * 60000, ('ENV x' + 'secret' * 30 + ' ') * 500,
                    'SET ' + 'credentials.' * 8000):
        started = time.monotonic()
        auto.redact(payload[:auto.MAX_MESSAGE_CHARS])
        assert time.monotonic() - started < TIME_LIMIT, payload[:20]


@pytest.mark.parametrize('header', ['|', '|2', '>2-', '|+', '| # a comment', '!!binary |', '&anchor |', '!!str &b >-', '>+3 # c'])
def test_yaml_block_scalar_headers_with_indicators_redact_the_body(header):
    out = auto.redact('a: 1\npassword: %s\n  first-body-line\n  the-value-v1zz\nnext: kept' % header)
    assert 'v1zz' not in out and 'first-body-line' not in out and out.startswith('a: 1') and out.endswith('next: kept')


@pytest.mark.parametrize('text', [
    'npm set //registry.npmjs.org/:_authToken VALUE', 'npm config set -g //registry.npmjs.org/:_authToken VALUE',
    'npm config --global set //registry.npmjs.org/:_authToken VALUE', 'npm --userconfig x config set //r/:_authToken VALUE',
    'pnpm set //registry.npmjs.org/:_authToken VALUE', 'yarn config set npmAuthToken VALUE', 'npm publish --otp=VALUE',
    'npm publish --otp VALUE'])
def test_npm_variants(text):
    assert 'v1zzsecret' not in auto.redact(text.replace('VALUE', 'v1zzsecret')), text
    assert auto.redact('npm install left-pad') == 'npm install left-pad'
    assert auto.redact('npm config set loglevel warn') == 'npm config set loglevel warn'


def test_k8s_name_then_value_from_then_value_lines():
    text = 'env:\n  - name: DB_PASSWORD\n    valueFrom:\n      configMapKeyRef:\n    value: v1zzsecret\n  - name: MODE\n    value: prod'
    out = auto.redact(text)
    assert 'v1zzsecret' not in out and 'name: MODE' in out and out.endswith('value: prod')
    plain = auto.redact('env:\n  - name: DB_PASSWORD\n    value: v1zzsecret\n  - name: MODE\n    value: prod')
    assert 'v1zzsecret' not in plain and plain.endswith('value: prod')


def test_real_paths_and_urls_survive_but_random_base64_with_a_slash_does_not():
    for keep in ('/Users/jamesdeola/dev-local/RHIZE/.worktrees/laya-autolabel/rhize-context-manager/scripts/pilot_autolabel',
                 '/Users/jamesdeola/dev-local/RHIZE/rhize-plugins/tests/rhize-context-manager/test_pilot_autolabel_redaction',
                 'https://github.com/Rhize-Media/rhize-plugins/blob/main/rhize-context-manager/scripts/pilot_autolabel.py',
                 'src/components/VeryLongComponentName/SubFolder/AnotherFolder/index/deep/deeper/deepest',
                 'node_modules/@types/node/ts4.8/assert/strict/very-long-package-name-goes-here/index'):
        assert auto.redact(keep) == keep, keep
    import random
    blob = None
    for seed in range(50):
        rng = random.Random(seed)
        candidate = ''.join(rng.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' + '/' * 8) for _ in range(52))
        if candidate.count('/') >= 2 and not any(c.isdigit() for c in candidate) and not auto._path_like(candidate):
            blob = candidate
            break
    assert blob and auto.redact('x ' + blob + ' y') == 'x [REDACTED_TOKEN] y'
    assert auto._path_like('usr/local/lib') and not auto._path_like('aGVs/bG8+V29y')


# ---- round 5: the path check is linear, every regex survives adversarial input, natural `pass`, npm ---------

# Segments that made the old nested-alternation regex run for seconds or forever (time doubled per character).
PATH_HANGERS = ['a' * 60 + 'A', 'observability-' * 8 + 'CAPS',
                'src/components/accountManagementDashboardSettingsPanelUI/index',
                'docs/archive/error-lifecycle-management-ARCHITECTURE-PROPOSAL']


def elapsed(function, *args):
    started = time.monotonic()
    result = function(*args)
    return result, time.monotonic() - started


@pytest.mark.parametrize('text', PATH_HANGERS)
def test_path_segments_that_hung_the_old_regex_finish_fast(text):
    for call in (auto._path_like, auto.redact):
        _, seconds = elapsed(call, text)
        assert seconds < 0.05, (call.__name__, text[:30], seconds)
    sanitized, seconds = elapsed(auto.sanitize, text, 500)
    assert seconds < 0.05 and sanitized[0] == text, (text[:30], seconds)


def test_a_200k_line_of_such_segments_is_linear():
    for text in ('/'.join(PATH_HANGERS)[:1000], 'a' * 60 + 'A', 'observability-' * 8 + 'CAPS'):
        line = '/'.join([text] * (200000 // (len(text) + 1)))[:200000]
        _, seconds = elapsed(auto._path_like, line)
        assert seconds < 1, (text[:30], seconds)
        _, seconds = elapsed(auto.redact, line)
        assert seconds < 1, (text[:30], seconds)
    assert auto._path_like('a' * 100000 + 'A') and auto._path_like('/'.join(['a' * 30 + 'B'] * 6000))


def test_the_old_segment_pattern_is_gone_so_no_regex_can_backtrack_there():
    assert not hasattr(auto, 'PATH_SEGMENT')
    assert not any(isinstance(value, re.Pattern) and '[A-Z]?[a-z][a-z0-9]*' in value.pattern for value in vars(auto).values())


def gate(run):
    """The entropy gate KEY_RUN_B64 applies before asking whether a run is a path (so the next test is not vacuous)."""
    return any(c in run for c in '+/=') and len(set(run)) >= 20 and auto._entropy(run) >= 4.2


@pytest.mark.parametrize('text', [
    'docs/archive/error-lifecycle-management-ARCHITECTURE-PROPOSAL',                   # kebab case + ALLCAPS
    'plugins/rhize-context-manager/skills/SKILL-context-hygiene-v1/references/notes',
    'src/components/accountManagementDashboardSettingsPanelUI/index',                # camelCase + trailing acronym
    'packages/marketplace/src/lib/marketA/workerV2/handlers/index',                   # trailing capital, trailing capital + vN
    'https://github.com/Rhize-Media/rhize-plugins/tree/main/rhize-context-manager/docs/decision-pilot',
    'services/api/v2/error-handler-v2/retry-policy-v3/index',                         # vN suffix shapes
    'docs/plans/observability-hardening-RFC/appendix-B/migration-checklist-FINAL',
    'rhize-context-manager/scripts/context_experiments/providers/typed_relevance_provider'])
def test_real_looking_paths_and_urls_survive(text):
    assert auto.redact(text) == text
    assert '://' in text or auto._path_like(text)
    assert auto.redact('see ' + text + ' for details') == 'see ' + text + ' for details'


def test_the_path_survival_tests_are_not_vacuous(monkeypatch):
    """Control: these shapes reach the path question (the entropy gate) and are redacted when the path check says no."""
    reached = [t for t in ('docs/archive/error-lifecycle-management-ARCHITECTURE-PROPOSAL',
                           'src/components/accountManagementDashboardSettingsPanelUI/index',
                           'packages/marketplace/src/lib/marketA/workerV2/handlers/index') if gate(t)]
    assert len(reached) >= 2, reached
    monkeypatch.setattr(auto, '_path_like', lambda run: False)
    assert all(auto.redact(t) != t for t in reached)


def random_blob(rng, alphabet, with_slash=True):
    length = rng.randint(40, 120)
    run = [rng.choice(alphabet) for _ in range(length)]
    if with_slash:
        for position in rng.sample(range(1, length - 1), rng.randint(1, 3)):
            run[position] = '/'
    return ''.join(run)


@pytest.mark.parametrize('alphabet', ['abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                                      'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'])
def test_random_base64_with_a_slash_still_redacts_with_or_without_digits(alphabet):
    import random
    rng = random.Random(20260930)
    blobs = [random_blob(rng, alphabet) for _ in range(600)]
    leaked = [b for b in blobs if auto.redact('x ' + b + ' y') != 'x [REDACTED_TOKEN] y']
    assert len(blobs) == 600 and not leaked, leaked[:3]
    assert not any(auto._path_like(b) for b in blobs[:300])


def test_segment_shapes_that_are_not_words_are_not_paths():
    for bad in ('aGVs/bG8+V29y', 'aGVsbG8gd29y/xQ3mKz', 'AdMaKqKcyOiWpB/WcXy', 'ab/c+d', 'a=b/c', 'xQ3m', 'rqcp9i8w6ldAzRP'):
        assert not auto._path_like(bad), bad
    for good in ('usr/local/lib', 'marketA', 'workerV2', 'PanelUI', 'SKILL-context-hygiene-v1', 'README', 'a//b', ''):
        assert auto._path_like(good), good


ADVERSARIAL = {'lowercase then bang': 'a' * 5000 + '!', 'alternating case': 'aA' * 2500, 'dashes then x': '-' * 5000 + 'x',
               'dash and case': 'a-' * 2500 + 'A', 'backslash u': '\\u' * 2500, 'path/base64 alternation': 'aA/+' * 1250,
               'slash alternation': 'a/' * 2500, 'spaces': ' ' * 5000 + 'x', 'equals': '=' * 5000, 'digits': '0' * 5000,
               'dots': 'a.' * 2500, 'emails': 'a@' * 2500, 'machine': 'machine ' + 'a' * 5000, 'password words': 'password ' * 550,
               'key prefixes': 'sk-' * 1600, 'private key': '-----BEGIN ' + 'A ' * 2500, 'npm flags': 'npm ' + '--a ' * 1250,
               'newlines': '\n' * 5000, 'open brackets': '(' * 5000, 'pass is': 'pass is ' * 600, 'the pass is': 'the pass is x. ' * 350}


def module_patterns():
    found = {}
    for name, value in vars(auto).items():
        if isinstance(value, re.Pattern):
            found[name] = value
        elif isinstance(value, dict):
            found.update({'%s[%s]' % (name, key): item for key, item in value.items() if isinstance(item, re.Pattern)})
        elif isinstance(value, (tuple, list)):
            found.update({'%s[%d]' % (name, n): entry[0] for n, entry in enumerate(value)
                          if isinstance(entry, tuple) and entry and isinstance(entry[0], re.Pattern)})
    return found


def test_every_module_level_regex_survives_adversarial_5k_strings():
    patterns = module_patterns()
    assert len(patterns) >= 35 and 'REDACTIONS[0]' in patterns and 'CREDENTIAL_WORD' in patterns, sorted(patterns)
    slow = []
    for name, pattern in patterns.items():
        started = time.monotonic()
        for label, text in ADVERSARIAL.items():
            for call in (pattern.search, pattern.fullmatch, pattern.match):
                call(text)
            for _ in pattern.finditer(text):
                pass
        seconds = time.monotonic() - started
        if seconds > 2:                                  # every pattern, all strings, all four calls; ~0.3s worst measured
            slow.append((name, round(seconds, 2)))
    assert not slow, slow


@pytest.mark.parametrize('label', sorted(ADVERSARIAL))
def test_redact_and_the_path_scanner_survive_adversarial_5k_strings(label):
    text = ADVERSARIAL[label]
    _, seconds = elapsed(auto.redact, text)
    assert seconds < 2, (label, seconds)
    _, seconds = elapsed(auto._path_like, text)
    assert seconds < 0.1, (label, seconds)


@pytest.mark.parametrize('text', ['the first pass is done', 'second pass was clean', 'lint pass is green', 'compile pass was slow',
                                  'the first pass is done.\nnext pass was fine, thanks', 'this pass is slow because of the cache',
                                  'one pass is enough to check it', 'the build pass was slow, then faster'])
def test_ordinary_uses_of_pass_is_and_pass_was_stay_clean(text):
    assert auto.redact(text) == text, text


@pytest.mark.parametrize('text', ['my pass is VALUE', 'your pass was VALUE', 'our pass is VALUE', 'the admin pass is VALUE',
                                  'root pass is VALUE', 'db pass was VALUE', 'the user pass is VALUE', 'login pass is VALUE',
                                  'wifi pass is VALUE', 'account pass was VALUE', 'pass is VALUE', 'the pass was VALUE',
                                  'Pass is VALUE.', 'ok, pass is VALUE', 'note: pass was VALUE. Then retry'])
def test_credential_context_and_a_single_ending_token_still_redact_pass(text):
    assert value_gone(text), text
    clean = 'the first pass is done'
    assert auto.redact(clean) == clean                   # control: the same machinery leaves the ordinary sentence alone


@pytest.mark.parametrize('text', [
    'npm config set --location=user //registry.npmjs.org/:_authToken VALUE',
    'npm config set --location user //registry.npmjs.org/:_authToken VALUE',
    'npm config set -L user //registry.npmjs.org/:_authToken VALUE',
    'npm config set --global=true //registry.npmjs.org/:_authToken VALUE',
    'npm config --location=user set //registry.npmjs.org/:_authToken VALUE',
    'npm --location user config set //registry.npmjs.org/:_authToken VALUE',
    'npm --global=true config set //registry.npmjs.org/:_authToken VALUE',
    'npm c set //registry.npmjs.org/:_authToken VALUE', 'npm c set -g //registry.npmjs.org/:_authToken VALUE',
    'bun config set //registry.npmjs.org/:_authToken VALUE', 'pnpm c set //registry.npmjs.org/:_authToken VALUE'])
def test_npm_and_bun_config_set_gaps(text):
    assert 'v1zzsecret' not in auto.redact(text.replace('VALUE', 'v1zzsecret')), text
    for clean in ('npm config set --location=user loglevel warn', 'npm c set loglevel warn', 'bun config set registry https://r.example/',
                  'npm config set -L user cache /tmp/cache', 'bun install left-pad'):
        assert auto.redact(clean) == clean, clean


# ---- round 6: glued `pass` names, escaped quotes, prefixes after an underscore ---------------------------------

BENIGN_PASS = ['the first pass is done', 'second pass was clean', 'lint pass is green', 'compile pass was slow',
               'this pass is slow because of the cache', 'one pass is enough to check it', 'the build pass was slow, then faster',
               'the first pass is done.\nnext pass was fine, thanks', 'compass is north', 'bypass was closed']


@pytest.mark.parametrize('text', ['dbPass is VALUE', 'db_pass is VALUE', 'adminPass is VALUE', 'adminPass was VALUE', 'root_pass was VALUE',
                                  'new pass is VALUE', 'temp pass is VALUE', 'old pass was VALUE', 'current pass is VALUE',
                                  'sudo pass is VALUE', 'mac pass is VALUE', 'laptop pass was VALUE', 'router pass is VALUE',
                                  'gmail pass was VALUE', 'the router pass is VALUE'])
def test_glued_pass_names_and_more_context_words_redact(text):
    assert value_gone(text), text


@pytest.mark.parametrize('text', ['the first pass is hunter2', 'lint pass was P4ssw0rd', 'the build pass is aB', 'the last pass was x_y',
                                  'the first pass is 100%', 'a pass is p@ss', 'the first pass is a#b'])
def test_any_pass_followed_by_a_non_dictionary_token_redacts(text):
    assert auto.redact(text) == '[REDACTED_CREDENTIAL_LINE]', text


@pytest.mark.parametrize('text', BENIGN_PASS)
def test_the_benign_pass_sentences_stay_clean_after_the_widening(text):
    assert auto.redact(text) == text


@pytest.mark.parametrize('text', [
    'curl -d "{\\"password\\":\\"VALUE\\"}" https://x.example/login', 'curl --data-raw "{\\"token\\": \\"VALUE\\"}"',
    'Invoke-RestMethod -Body "{\\"apiKey\\":\\"VALUE\\"}" -Uri https://x.example', 'body: "{\\"secret\\":\\"VALUE\\"}"',
    'x \\\\"password\\\\":\\\\"VALUE\\\\"', 'x \\\\\\"password\\\\\\": \\\\\\"VALUE\\\\\\"', '{\\"pwd\\":\\"VALUE\\"}', '{\\"tokens\\":\\"VALUE\\"}',
    '{\\"name\\":\\"DB_PASSWORD\\",\\"value\\":\\"VALUE\\"}', "curl -d '{\"password\":\"VALUE\"}'", '{\\"client secret\\": \\"VALUE\\"}'])
def test_a_credential_key_next_to_an_escaped_quote_redacts(text):
    assert value_gone(text), text
    plain = auto.redact('{"password": "v1zzsecret"}')
    assert 'v1zzsecret' not in plain                                   # control: the unescaped form always did


def test_json_escaped_codex_output_keeps_no_escaped_credential_in_the_stored_record():
    raw = '{"type":"item.completed","item":{"id":"i","type":"agent_message","text":"{\\"password\\": \\"v1zzsecret\\"}"}}\n' \
          '{"type":"turn.completed","usage":{}}'
    assert '\\"password\\": \\"v1zzsecret\\"' in raw
    stored, _ = auto.sanitize(raw, auto.MAX_STORED_OUTPUT)
    assert 'v1zzsecret' not in stored and '"turn.completed"' in stored


@pytest.mark.parametrize('text', ['a \\"quoted\\" word', '{\\"name\\":\\"alice\\",\\"age\\":3}',
                                  'say \\"hello\\" to the author'])
def test_escaped_quotes_around_ordinary_words_stay_clean(text):
    assert auto.redact(text) == text


PREFIXED = {'aws': fake('AKIA', 'ABCDEFGHIJKLMNOP'), 'jwt': fake('eyJ', 'hbGciOiJIUzI1.eyJzdWIiOiIxMjM0.abcdefghijklmnop'),
            'gitlab': fake('glpat-', 'Ab1' * 8), 'huggingface': fake('hf_', 'aB3' * 8), 'stripe': fake('sk_live_', 'abcdef123456'),
            'hex64': 'ab12' * 16, 'github': fake('ghp_', 'aB3' * 10), 'npm': fake('npm_', 'aB3' * 12)}


@pytest.mark.parametrize('name', sorted(PREFIXED))
@pytest.mark.parametrize('carrier', ['foo_%s', 'credentials_%s.json', 'x_y_%s_z', 'config_%s.txt'])
def test_a_known_token_prefix_glued_after_an_underscore_redacts(name, carrier):
    text = carrier % PREFIXED[name]
    out = auto.redact(text)
    assert PREFIXED[name] not in out and PREFIXED[name][4:16] not in out, (name, carrier, out)
    assert auto.redact(PREFIXED[name]) != PREFIXED[name]                # control: the bare token always redacted


@pytest.mark.parametrize('text', ['run_npm_install_with_legacy_peer_deps_flag', 'test_re_compile_pattern_name_long_suffix',
                                  'my_hf_model_name_for_large_files', 'is_sk_live_thing_here', 'get_ghp_value', 'foo_sntrys_bar',
                                  'some_AKIA_prefix_name', 'sha256_of_the_file', 'user_id_abcdef', 'build_glpat_helper_function',
                                  'load_eyJ_header_parser', 'max_tokens_per_request', 'my_ntn_value_holder_thing_here'])
def test_ordinary_snake_case_names_stay_clean(text):
    assert auto.redact(text) == text


def test_the_unbounded_whitespace_runs_are_only_used_anchored():
    source = inspect.getsource(auto)
    assert 'CREDENTIAL_TAIL.match(' in source and 'NAME_END.match(' in source
    assert 'CREDENTIAL_TAIL.finditer' not in source and 'NAME_END.finditer' not in source
    assert 'every pattern is length-bounded' not in source


def test_suffix_search_guards_preserve_runtime_credential_match_spans():
    # Compare with the pre-fix patterns at the only positions used by the redactor:
    # immediately after a detected credential word, including long whitespace and length boundaries.
    originals = (
        (auto.CREDENTIAL_TAIL, re.compile(r'[\w.-]{0,256}(?:[ \t]{1,3}(?:\([^)\n]{0,40}\)|[\w.-]{1,256})){0,3}'
                                         + auto._Q + r'[ \t]*[:=]')),
        (auto.NAME_END, re.compile(r'''[\w.-]{0,256}[ \t]*(?:\\{0,3}["',|>]|$)''', re.M)),
    )
    suffixes = ('', '=', ':', ' :', '\t' * 5000 + ':', ' ' * 5000 + 'x',
                'a' * 256 + ':', 'a' * 257 + ':', 'a' * 257,
                ' ' + 'a' * 256 + ' =', ' manager', '"', "'", ' (description) =')
    checked = 0
    for word in ('password', 'secret', 'API_KEY', 'cookie', 'userAuth', 'pin', 'dbpass'):
        for suffix in suffixes:
            text = word + suffix
            for credential in auto.CREDENTIAL_WORD.finditer(text):
                for current, original in originals:
                    before = original.match(text, credential.end())
                    after = current.match(text, credential.end())
                    assert (before.span() if before else None) == (after.span() if after else None), (word, suffix[:40])
                    checked += 1
    assert checked > 100
