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
    keep = 'the secret sauce is fine; set max_tokens=4096 and tokens: 12; secret santa is on Friday'
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
