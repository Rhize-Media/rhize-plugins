"""Redaction and truncation of what the labeler sends to a model. Invented, obviously fake secrets only."""
import re
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
import pilot_autolabel as auto


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
    assert time.monotonic() - started < 2.0, payload[:12]


def test_a_secret_block_before_the_cut_is_redacted_not_cut_in_half():
    body = '\n'.join('MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC%02d' % n for n in range(60))
    text = '-----BEGIN PRIVATE KEY-----\n' + body + '\n-----END PRIVATE KEY-----\ndone'
    for tail in (False, True):
        out, cut = auto.sanitize(text, 100, tail=tail)
        assert 'MIIEvQIBADAN' not in out and 'BEGIN' not in out.replace('[REDACTED_PRIVATE_KEY]', '')
    assert auto.sanitize(text, 100, tail=True)[0].endswith('done')
    # A credential straddling the old 4x pre-slice boundary is redacted before any bound applies.
    token = fake('AKIA', '0123456789ABCDEF')
    text = 'w ' * 195 + token + ' tail ' * 3
    assert token not in auto.sanitize(text, 400)[0] and token not in auto.sanitize(text, 100, tail=True)[0]


def test_truncation_trims_a_partial_token_at_the_cut():
    out, cut = auto.sanitize('alpha beta gamma delta', 12)
    assert cut is True and out.startswith('alpha beta') and ' g' not in out and 'gamma' not in out
    out, cut = auto.sanitize('alpha beta gamma delta', 10, tail=True)
    assert cut is True and out.endswith('\n delta') and 'amma' not in out
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
    assert auto.detection_view(text) == (text, None, None)
    many = '\\u0041' * (auto.MAX_ESCAPES + 500)
    started = time.monotonic()
    view, starts, ends = auto.detection_view(many)
    assert time.monotonic() - started < 2 and len(view) == len(many) - 5 * auto.MAX_ESCAPES
    assert ends[0] == 6 and starts[0] == 0


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
    assert cut is True and time.monotonic() - started < 3
    view = 'x\u200b' * 100000
    started = time.monotonic()
    auto.redact(view)
    assert time.monotonic() - started < 3
