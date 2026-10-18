"""Scoreboard per-host breakdown and the keep-warm line (plan §7 F6, §8; acceptance test A6)."""
from __future__ import annotations

import copy
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from typed_decision_testkit import (  # noqa: E402
    ALT1, INC, LAYA_REV, SCRIPTS, fixture, make_record, write_records)
from typed_decisions import contract, records, scoreboard  # noqa: E402

SKILL = 'skill-fit'
CLI = SCRIPTS / 'typed_decisions' / 'scoreboard.py'
NOW = '2026-10-12T12:00:00Z'


@pytest.fixture(autouse=True)
def _runtime_pin(monkeypatch):
    real = records.laya_revision

    def pinned(root=None):
        value = real(root)
        base = Path(root) if root is not None else records.default_root()
        return LAYA_REV if value == 'unknown' and not (base / 'laya-runtime.json').exists() else value

    monkeypatch.setattr(records, 'laya_revision', pinned)


@pytest.fixture
def root(tmp_path):
    path = tmp_path / 'typed-decisions'
    path.mkdir(mode=0o700)
    (path / 'laya-runtime.json').write_text(json.dumps({'revision': LAYA_REV}))
    return path


def codex(rec):
    rec = copy.deepcopy(rec)
    rec['host'] = 'codex'
    return contract.validate_record(rec)


def outcome_for(rec, kind, via='skill_tool'):
    base = fixture('outcomes.json')['valid']
    outcome = copy.deepcopy(base[{'invoked_emitted': 'invoked-emitted', 'none_invoked': 'none-invoked',
                                  'transcript_unavailable': 'transcript-unavailable'}[kind]])
    outcome.update({'decisionId': rec['decisionId'], 'occurrenceKey': rec['occurrenceKey']})
    if kind == 'invoked_emitted':
        outcome['via'] = via
    return contract.validate_outcome(outcome)


def two_host_world(root):
    """Claude: 6 treatment (4 agree, 2 disagree), 2 holdback, 1 timeout, 3 backfill. Codex: 5 shadow treatment
    (1 agree, 4 disagree), 2 holdback, 2 unavailable. One unknown-host row."""
    claude_treatment = ([make_record(i, arm='treatment', choice=INC, latency=50.0 + i) for i in range(4)]
                        + [make_record(10 + i, arm='treatment', choice=ALT1, latency=70.0) for i in range(2)])
    claude_holdback = [make_record(20 + i, arm='holdback', choice=INC) for i in range(2)]
    claude_timeout = [make_record(30, status='timeout', latency=800.0)]
    claude_backfill = [make_record(40 + i, basis='backfill', choice=ALT1) for i in range(3)]
    codex_treatment = ([codex(make_record(100, arm='treatment', choice=INC, latency=120.0))]
                       + [codex(make_record(101 + i, arm='treatment', choice=ALT1, latency=200.0 + i)) for i in range(4)])
    codex_holdback = [codex(make_record(110 + i, arm='holdback', choice=INC)) for i in range(2)]
    codex_down = [codex(make_record(120 + i, status='unavailable', latency=None)) for i in range(2)]
    unknown = copy.deepcopy(make_record(200))
    unknown['host'] = 'unknown'
    unknown = contract.validate_record(unknown)
    everything = (claude_treatment + claude_holdback + claude_timeout + claude_backfill
                  + codex_treatment + codex_holdback + codex_down + [unknown])
    write_records(root, everything)
    # outcomes: claude 4 invoked_emitted (skill_tool) + 1 none; codex 3 invoked_emitted (skill_file_read) + 1 none
    # + 1 unavailable; holdback and unknown rows have none.
    for rec in claude_treatment[:4]:
        records.append(root, SKILL, 'outcomes', outcome_for(rec, 'invoked_emitted'))
    records.append(root, SKILL, 'outcomes', outcome_for(claude_treatment[4], 'none_invoked'))
    for rec in codex_treatment[:3]:
        records.append(root, SKILL, 'outcomes', outcome_for(rec, 'invoked_emitted', via='skill_file_read'))
    records.append(root, SKILL, 'outcomes', outcome_for(codex_treatment[3], 'none_invoked'))
    records.append(root, SKILL, 'outcomes', outcome_for(codex_treatment[4], 'transcript_unavailable'))
    return everything


# ---------------------------------------------------------------- per host

def test_every_metric_is_reported_per_host(root):
    two_host_world(root)
    data = scoreboard.build(root, NOW)
    assert data['gateHosts'] == ['claude'] and list(data['hosts']) == ['claude', 'codex', 'unknown']
    claude, other, unknown = data['hosts']['claude'], data['hosts']['codex'], data['hosts']['unknown']
    assert (claude['gate'], other['gate'], unknown['gate']) == (True, False, False)

    assert claude['records'] == 12 and claude['byBasis'] == {'live': 9, 'backfill': 3}
    assert other['records'] == 9 and other['byBasis'] == {'live': 9}
    assert unknown['records'] == 1 and unknown['byBasis'] == {'live': 1}

    assert claude['liveArms'] == {'treatment': 7, 'holdback': 2} and claude['liveModes'] == {'shadow': 9}
    assert other['liveArms'] == {'treatment': 7, 'holdback': 2} and other['liveModes'] == {'shadow': 9}

    assert claude['layaStatuses'] == {'live': {'ok': 8, 'timeout': 1}, 'backfill': {'ok': 3}}
    assert other['layaStatuses'] == {'live': {'ok': 7, 'unavailable': 2}, 'backfill': {}}

    # disagreement prevalence among fired records (incumbent present and Laya ok), per host and basis
    assert claude['prevalence']['live'] == {'fired': 8, 'disagreements': 2, 'share': 2 / 8}
    assert claude['prevalence']['backfill']['fired'] == 3
    assert other['prevalence']['live'] == {'fired': 7, 'disagreements': 4, 'share': 4 / 7}
    assert other['prevalence']['backfill'] == {'fired': 0, 'disagreements': 0, 'share': None}

    assert claude['timeouts'] == {'calls': 9, 'timeouts': 1, 'share': 1 / 9}
    assert other['timeouts'] == {'calls': 9, 'timeouts': 0, 'share': 0.0}
    assert claude['latency']['n'] == 8 and other['latency']['n'] == 7
    assert (claude['latency']['p50'], claude['latency']['p90']) == (53.0, 70.0)     # nearest rank over ok calls
    assert (other['latency']['p50'], other['latency']['p90']) == (200.0, 203.0)

    assert claude['outcomes'] == {'joined': 5, 'counts': {'invoked_emitted': 4, 'none_invoked': 1},
                                  'byArm': {'treatment': {'emitted': 5, 'invokedEmitted': 4, 'rate': 4 / 5}}}
    assert other['outcomes']['joined'] == 5
    assert other['outcomes']['counts'] == {'invoked_emitted': 3, 'none_invoked': 1, 'transcript_unavailable': 1}
    assert other['outcomes']['byArm'] == {'treatment': {'emitted': 4, 'invokedEmitted': 3, 'rate': 3 / 4}}   # unavailable excluded
    assert unknown['outcomes'] == {'joined': 0, 'counts': {}, 'byArm': {}}


def test_per_host_figures_add_up_to_the_totals(root):
    two_host_world(root)
    data = scoreboard.build(root, NOW)
    hosts = data['hosts'].values()
    assert sum(h['records'] for h in hosts) == data['records']['total']
    for basis, count in data['records']['byBasis'].items():
        assert sum(h['byBasis'].get(basis, 0) for h in hosts) == count
    for arm, count in data['records']['liveArms'].items():
        assert sum(h['liveArms'].get(arm, 0) for h in hosts) == count
    for kind, count in data['acceptance']['outcomes'].items():
        assert sum(h['outcomes']['counts'].get(kind, 0) for h in hosts) == count
    assert sum(h['outcomes']['joined'] for h in hosts) == data['acceptance']['joined']
    json.dumps(data)


def test_the_existing_top_level_sections_are_unchanged_by_the_split(root):
    two_host_world(root)
    data = scoreboard.build(root, NOW)
    assert data['records']['byBasis'] == {'live': 19, 'backfill': 3}
    assert data['prevalence']['live']['fired'] == 16            # 8 claude + 7 codex + 1 unknown


def test_markdown_renders_the_per_host_table(root):
    two_host_world(root)
    text = scoreboard.render_md(scoreboard.build(root, NOW))
    assert '### Per host (gate hosts: claude; other hosts are shadow evidence only)' in text
    rows = {line.split('|')[1].strip(): line for line in text.splitlines() if line.startswith('| claude') or
            line.startswith('| codex') or line.startswith('| unknown')}
    assert set(rows) == {'claude (gate)', 'codex', 'unknown'}
    claude, other = rows['claude (gate)'], rows['codex']
    assert '12 (live 9, backfill 3)' in claude and 'holdback 2, treatment 7' in claude
    assert 'ok 8, timeout 1' in claude and '2/8 (25.0%)' in claude and '11.1%' in claude
    assert '5: invoked_emitted 4, none_invoked 1' in claude
    assert '9 (live 9, backfill 0)' in other and 'ok 7, unavailable 2' in other and '4/7 (57.1%)' in other
    assert '5: invoked_emitted 3, none_invoked 1, transcript_unavailable 1' in other
    assert '| 1 (live 1, backfill 0)' in rows['unknown']


def test_a_quiet_host_shows_zeros_and_an_unused_unknown_host_is_hidden(root):
    write_records(root, [make_record(i) for i in range(3)])
    data = scoreboard.build(root, NOW)
    assert data['hosts']['codex'] == {
        'gate': False, 'records': 0, 'byBasis': {}, 'liveArms': {}, 'liveModes': {},
        'layaStatuses': {'live': {}, 'backfill': {}},
        'prevalence': {'live': {'fired': 0, 'disagreements': 0, 'share': None},
                       'backfill': {'fired': 0, 'disagreements': 0, 'share': None}},
        'latency': {'n': 0, 'p50': None, 'p90': None}, 'timeouts': {'calls': 0, 'timeouts': 0, 'share': None},
        'outcomes': {'joined': 0, 'counts': {}, 'byArm': {}}}
    text = scoreboard.render_md(data)
    assert '| codex | 0 (live 0, backfill 0)' in text and '| unknown |' not in text


def test_outcome_via_skill_file_read_is_counted_like_any_other(root):
    rec = codex(make_record(1, choice=INC))
    write_records(root, [rec])
    records.append(root, SKILL, 'outcomes', outcome_for(rec, 'invoked_emitted', via='skill_file_read'))
    assert scoreboard.build(root, NOW)['hosts']['codex']['outcomes']['counts'] == {'invoked_emitted': 1}


# ---------------------------------------------------------------- an empty root

def test_an_empty_root_renders_both_formats_with_the_per_host_and_keep_warm_sections(root, tmp_path):
    data = scoreboard.build(root, NOW)
    text = scoreboard.render_md(data)
    assert 'Mode: **shadow**' in text and 'No cohort reserved yet.' in text and '- keep-warm: not running' in text
    assert '### Per host' in text and '| claude (gate) | 0 (live 0, backfill 0)' in text
    assert data['keepWarm'] == {'state': 'missing'} and data['hosts']['claude']['records'] == 0
    json.dumps(data)
    env = {**os.environ, 'HOME': str(tmp_path / 'home')}
    md = subprocess.run([sys.executable, str(CLI), 'render', '--root', str(root), '--now', NOW],
                        capture_output=True, text=True, timeout=120, env=env)
    assert md.returncode == 0 and 'keep-warm: not running' in md.stdout and '### Per host' in md.stdout
    js = subprocess.run([sys.executable, str(CLI), 'render', '--root', str(root), '--format', 'json', '--now', NOW],
                        capture_output=True, text=True, timeout=120, env=env)
    parsed = json.loads(js.stdout)
    assert js.returncode == 0 and parsed['keepWarm'] == {'state': 'missing'} and parsed['gateHosts'] == ['claude']
    assert set(parsed['hosts']) == {'claude', 'codex', 'unknown'}


def test_a_root_that_does_not_exist_still_renders(tmp_path):
    data = scoreboard.build(tmp_path / 'never-created', NOW)
    assert data['keepWarm'] == {'state': 'missing'}
    assert '- keep-warm: not running' in scoreboard.render_md(data)


# ---------------------------------------------------------------- keep-warm

def keepwarm(**overrides):
    state = {'schema': 'rhize-laya-keepwarm-v1', 'startedAt': '2026-10-12T08:00:00Z',
             'lastPingAt': '2026-10-12T11:59:00Z', 'lastStatus': 'ok', 'lastLatencyMs': 41.5,
             'consecutiveFailures': 0, 'pings': 100, 'ok': 99, 'skippedIdle': 3, 'skippedWarm': 9,
             'intervalSeconds': 90, 'activeWindowHours': 2, 'lastActivityAt': '2026-10-12T11:50:00Z'}
    state.update(overrides)
    return state


def write_keepwarm(root, state, mode=0o600):
    path = root / 'laya-keepwarm.json'
    path.write_text(state if isinstance(state, str) else json.dumps(state))
    os.chmod(path, mode)
    return path


def test_a_missing_keepwarm_file_reads_as_not_running(root):
    data = scoreboard.build(root, NOW)
    assert data['keepWarm'] == {'state': 'missing'}
    assert '- keep-warm: not running' in scoreboard.render_md(data).splitlines()


def test_a_valid_keepwarm_file_shows_age_status_latency_and_failures(root):
    write_keepwarm(root, keepwarm(consecutiveFailures=2, lastStatus='timeout', lastLatencyMs=800))
    data = scoreboard.build(root, NOW)
    info = data['keepWarm']
    assert info['state'] == 'present' and info['lastPingAgeSeconds'] == 60.0 and info['lastActivityAgeSeconds'] == 600.0
    assert (info['lastStatus'], info['lastLatencyMs'], info['consecutiveFailures']) == ('timeout', 800, 2)
    assert (info['pings'], info['ok'], info['skippedIdle'], info['skippedWarm']) == (100, 99, 3, 9)
    assert (info['intervalSeconds'], info['activeWindowHours']) == (90, 2)
    line = next(item for item in scoreboard.render_md(data).splitlines() if item.startswith('- keep-warm:'))
    assert line.startswith('- keep-warm: last ping 60s ago, status timeout, latency 800 ms, consecutive failures 2;')
    assert 'pings 100 (ok 99, skipped idle 3, skipped warm 9)' in line and 'last activity 10m ago' in line
    json.dumps(data)


@pytest.mark.parametrize('ping,expected', [
    ('2026-10-12T11:59:30Z', '30s'), ('2026-10-12T11:50:00Z', '10m'), ('2026-10-12T09:00:00Z', '3.0h'),
    ('2026-10-09T12:00:00Z', '3.0d'), ('2026-10-12T12:30:00Z', '0s')])      # the last one is in the future: clamped
def test_the_ping_age_is_human_readable(root, ping, expected):
    write_keepwarm(root, keepwarm(lastPingAt=ping))
    line = next(item for item in scoreboard.render_md(scoreboard.build(root, NOW)).splitlines()
                if item.startswith('- keep-warm:'))
    assert f'last ping {expected} ago' in line


def test_a_keepwarm_file_that_has_not_pinged_yet_is_valid(root):
    write_keepwarm(root, keepwarm(lastPingAt=None, lastStatus=None, lastLatencyMs=None, lastActivityAt=None, pings=0, ok=0))
    info = scoreboard.build(root, NOW)['keepWarm']
    assert info['state'] == 'present' and info['lastPingAgeSeconds'] is None and info['lastStatus'] is None
    line = next(item for item in scoreboard.render_md(scoreboard.build(root, NOW)).splitlines()
                if item.startswith('- keep-warm:'))
    assert 'last ping - ago, status -, latency -' in line


INVALID_STATES = {
    'not json': '{not json',
    'empty file': '',
    'a list': '[1, 2]',
    'a string': '"keep-warm"',
    'binary': b'\xff\xfe\x00'.decode('latin-1'),
    'wrong schema': keepwarm(schema='rhize-laya-keepwarm-v2'),
    'no schema': {k: v for k, v in keepwarm().items() if k != 'schema'},
    'unknown status': keepwarm(lastStatus='exploded'),
    'status of the wrong type': keepwarm(lastStatus=1),
    'negative failures': keepwarm(consecutiveFailures=-1),
    'boolean counter': keepwarm(pings=True),
    'string counter': keepwarm(ok='99'),
    'missing counter': {k: v for k, v in keepwarm().items() if k != 'skippedWarm'},
    'negative latency': keepwarm(lastLatencyMs=-5),
    'string latency': keepwarm(lastLatencyMs='fast'),
    'zero interval': keepwarm(intervalSeconds=0),
    'missing window': {k: v for k, v in keepwarm().items() if k != 'activeWindowHours'},
    'naive timestamp': keepwarm(lastPingAt='2026-10-12T11:59:00'),
    'garbage timestamp': keepwarm(lastActivityAt='yesterday'),
    'numeric timestamp': keepwarm(startedAt=12345),
    'missing startedAt': {k: v for k, v in keepwarm().items() if k != 'startedAt'},
    'null startedAt': keepwarm(startedAt=None),
}


@pytest.mark.parametrize('state', list(INVALID_STATES.values()), ids=list(INVALID_STATES))
def test_content_that_does_not_validate_reads_as_invalid(root, state):
    write_keepwarm(root, state)
    data = scoreboard.build(root, NOW)
    assert data['keepWarm'] == {'state': 'invalid'}
    assert '- keep-warm: invalid state file (laya-keepwarm.json)' in scoreboard.render_md(data).splitlines()


def test_nan_and_infinity_are_invalid(root):
    for text in ('{"schema": "rhize-laya-keepwarm-v1", "lastLatencyMs": NaN}',
                 json.dumps(keepwarm()).replace('41.5', 'Infinity')):
        write_keepwarm(root, text)
        assert scoreboard.build(root, NOW)['keepWarm'] == {'state': 'invalid'}


def test_unsafe_files_read_as_invalid_without_following_or_reading_them(root, tmp_path):
    path = root / 'laya-keepwarm.json'
    target = tmp_path / 'elsewhere.json'
    target.write_text(json.dumps(keepwarm()))
    path.symlink_to(target)                                                     # a symlink to a valid file
    assert scoreboard.read_keepwarm(root, NOW) == {'state': 'invalid'}
    path.unlink()
    path.mkdir()                                                                # a directory
    assert scoreboard.read_keepwarm(root, NOW) == {'state': 'invalid'}
    path.rmdir()
    os.mkfifo(path)                                                             # a fifo would block a naive open
    assert scoreboard.read_keepwarm(root, NOW) == {'state': 'invalid'}
    path.unlink()
    big = write_keepwarm(root, json.dumps(keepwarm(note='x' * (scoreboard.MAX_KEEPWARM_BYTES + 1))))
    assert big.stat().st_size > scoreboard.MAX_KEEPWARM_BYTES
    assert scoreboard.read_keepwarm(root, NOW) == {'state': 'invalid'}
    big.unlink()
    write_keepwarm(root, '[' * 100000)                                           # deep nesting must not raise
    assert scoreboard.read_keepwarm(root, NOW) == {'state': 'invalid'}


def test_extra_keys_are_tolerated_and_not_echoed(root):
    write_keepwarm(root, keepwarm(futureField='new', host='mac'))
    info = scoreboard.read_keepwarm(root, NOW)
    assert info['state'] == 'present' and 'futureField' not in info and 'host' not in info


def test_reading_keepwarm_never_writes(root):
    write_keepwarm(root, keepwarm())
    before = sorted((str(p), p.stat().st_mtime_ns) for p in root.rglob('*'))
    scoreboard.build(root, NOW)
    scoreboard.render_md(scoreboard.build(root, NOW))
    assert sorted((str(p), p.stat().st_mtime_ns) for p in root.rglob('*')) == before
    assert stat.S_IMODE((root / 'laya-keepwarm.json').stat().st_mode) == 0o600


def test_the_cli_shows_the_keepwarm_line(root, tmp_path):
    write_keepwarm(root, keepwarm())
    env = {**os.environ, 'HOME': str(tmp_path / 'home')}
    out = subprocess.run([sys.executable, str(CLI), 'render', '--root', str(root), '--now', NOW],
                         capture_output=True, text=True, timeout=120, env=env)
    assert out.returncode == 0 and '- keep-warm: last ping 60s ago, status ok, latency 41.5 ms' in out.stdout


def test_epoch_metrics_keep_history_and_exclude_backfill_and_future_records(root):
    rows = [make_record(1, status='timeout', latency=800.0), make_record(2),
            codex(make_record(3, status='timeout', latency=800.0)),
            make_record(4, basis='backfill'), make_record(5)]
    for row, stamp in zip(rows, ['2026-10-12T07:59:00Z', '2026-10-12T08:00:00Z',
                                '2026-10-12T09:00:00Z', '2026-10-12T10:00:00Z',
                                '2026-10-12T12:01:00Z']):
        row['ts'] = stamp
        row['occurrenceKey'] = contract.occurrence_key(row['sessionHash'], row['promptHash'], stamp)
    write_records(root, rows)
    write_keepwarm(root, keepwarm())
    data = scoreboard.build(root, NOW)
    epoch = data['sinceKeepWarmStart']
    assert epoch['startedAt'] == '2026-10-12T08:00:00Z'
    assert epoch['hosts']['claude']['timeouts'] == {'calls': 1, 'timeouts': 0, 'share': 0.0}
    assert epoch['hosts']['codex']['timeouts'] == {'calls': 1, 'timeouts': 1, 'share': 1.0}
    assert data['hosts']['claude']['timeouts']['calls'] == 3
    assert 'Since keep-warm epoch' in scoreboard.render_md(data)
    assert 'not a causal recovery claim' in scoreboard.render_md(data)


def test_epoch_metrics_are_unavailable_without_a_valid_epoch(root):
    assert scoreboard.build(root, NOW)['sinceKeepWarmStart'] is None
    write_keepwarm(root, keepwarm(startedAt='not-a-time'))
    assert scoreboard.build(root, NOW)['sinceKeepWarmStart'] is None
