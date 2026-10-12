"""harvest_signals.py emit: skill-fit decision evidence -> learn-harvest review candidates (plan §7 F10, A2).

Synthetic records and outcomes in a tmp root only. Nothing here reads or writes the real data root, the live
refinement queue or any transcript.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))

from typed_decision_testkit import ALT1, ALT2, INC, SCRIPTS, make_record, sha  # noqa: E402

from typed_decisions import contract, harvest_signals, records  # noqa: E402

SCRIPT = SCRIPTS / 'typed_decisions' / 'harvest_signals.py'
NOW = '2026-10-12T12:00:00Z'
NOW_DT = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)
SOURCE = 'skill-fit-decisions'
SEO_REF, GEO_REF, TEST_REF = 'seo-aeo-geo:seo-site-audit', 'seo-aeo-geo:aeo-geo-optimization', 'rhize-devflow:test-evidence'
DASH = 'rhize-ops:skill-dashboard'

NOT_SHORTLISTED = ('routing-miss (not-shortlisted, host {host}): {skill} was invoked soon after prompts where the '
                   'router suggested another skill or none and did not shortlist it, repeatedly within the '
                   'trailing window — review its tags and trigger phrases.')
IGNORED = ('routing-miss (suggested-but-ignored, host {host}): the router suggested {skill} but the user invoked a '
           'different shortlisted skill instead, repeatedly within the trailing window — review its tags and '
           'trigger phrases, and whether the suggestion fires on the wrong prompts.')
SUPPRESSED = ('decision-layer (cosign-suppressed-then-invoked, host {host}): the co-sign withheld the router '
              'suggestion {skill} (Laya disagreed or was unavailable) and the user invoked it within one turn '
              'anyway, repeatedly within the trailing window — review whether the co-sign path suppresses '
              'good suggestions for this skill.')
TIMEOUTS = ('decision-layer (laya-timeouts, host {host}): the Laya co-sign call timed out on an elevated share of '
            'live decisions in the trailing window — review keep-warm health and the latency budget.')
TEMPLATES = (NOT_SHORTLISTED, IGNORED, SUPPRESSED, TIMEOUTS)


def eid(pattern):
    return hashlib.sha1((SOURCE + pattern).encode('utf-8')).hexdigest()[:12]


class Seeder:
    """Writes valid records (and outcomes) into one tmp root with unique ids."""

    def __init__(self, root):
        self.root = Path(root)
        self.n = 0

    def ts(self, days_ago=1.0, base=NOW_DT):
        return (base - timedelta(days=days_ago)).strftime('%Y-%m-%dT%H:%M:%S.000Z')

    def record(self, *, host='claude', days_ago=1.0, outcome=None, skill=None, turns=0, join_after_hours=1.0,
               **kwargs):
        self.n += 1
        rec = make_record(self.n, ts=self.ts(days_ago), **kwargs)
        rec['host'] = host
        records.append(self.root, 'skill-fit', 'records', contract.validate_record(rec))
        if outcome:
            self.outcome(rec, outcome, skill, turns, join_after_hours)
        return rec

    def outcome(self, rec, kind, skill=None, turns=0, join_after_hours=1.0):
        invoked = kind.startswith('invoked')
        joined = (datetime.fromisoformat(rec['ts'].replace('Z', '+00:00'))
                  + timedelta(hours=join_after_hours)).strftime('%Y-%m-%dT%H:%M:%SZ')
        row = {'schema': contract.OUTCOME_SCHEMA, 'decisionId': rec['decisionId'],
               'occurrenceKey': rec['occurrenceKey'], 'outcome': kind, 'skillInvoked': skill if invoked else None,
               'via': 'skill_tool' if invoked else None, 'latencyTurns': turns if invoked else None,
               'joinedAt': joined, 'transcriptSha256': None if kind == 'transcript_unavailable' else sha('t' + rec['decisionId'])}
        records.append(self.root, 'skill-fit', 'outcomes', contract.validate_outcome(row))
        return row


@pytest.fixture
def home(tmp_path, monkeypatch):
    fake = tmp_path / 'home'
    fake.mkdir()
    monkeypatch.setenv('HOME', str(fake))
    monkeypatch.delenv('RHIZE_TYPED_DECISIONS_ROOT', raising=False)
    return fake


@pytest.fixture
def seed(tmp_path, home):
    return Seeder(tmp_path / 'root')


def run_emit(seed, tmp_path, name='queue.jsonl', **flags):
    queue = tmp_path / 'out' / name
    argv = ['emit', '--queue', str(queue), '--root', str(seed.root), '--now', flags.pop('now', NOW)]
    for key, value in flags.items():
        argv += [f'--{key.replace("_", "-")}', str(value)]
    code = harvest_signals.main(argv)
    return code, queue


def read_queue(queue):
    return [json.loads(line) for line in Path(queue).read_text(encoding='utf-8').splitlines()]


def by_pattern(rows):
    return {row['pattern']: row for row in rows}


# ---------------------------------------------------------------- the four signals, exact ids

def seed_all_signals(seed):
    for _ in range(3):                      # 1. not-shortlisted: an unlisted skill invoked after a miss
        seed.record(outcome='invoked_unlisted', skill=DASH)
    for _ in range(2):                      # below the threshold: stays out
        seed.record(outcome='invoked_unlisted', skill='other:skill')
    for _ in range(3):                      # 2. suggested-but-ignored: INC shown, a different shortlisted skill used
        seed.record(outcome='invoked_other_shortlisted', skill=GEO_REF, host='codex')
    for _ in range(3):                      # 3. cosign withheld INC, the user invoked it within one turn
        seed.record(mode='cosign', outcome='invoked_other_shortlisted', skill=SEO_REF, turns=1)
    for _ in range(4):                      # 4. timeouts, no outcome needed (host unknown)
        seed.record(host='unknown', status='timeout', choice=None)
    for _ in range(16):
        seed.record(host='unknown')


def test_the_four_signals_with_exact_ids_and_schema(seed, tmp_path, capsys):
    seed_all_signals(seed)
    code, queue = run_emit(seed, tmp_path)
    rows = read_queue(queue)
    assert code == 0 and len(rows) == 4
    expected = [
        ('routing-miss', NOT_SHORTLISTED.format(host='claude', skill='skill:rhize-ops/skill-dashboard'),
         'rhize-ops/skill-dashboard'),
        ('routing-miss', IGNORED.format(host='codex', skill=INC), 'seo-aeo-geo/seo-site-audit'),
        ('decision-layer', SUPPRESSED.format(host='claude', skill=INC), 'seo-aeo-geo/seo-site-audit'),
        ('decision-layer', TIMEOUTS.format(host='unknown', skill=None), None),
    ]
    found = by_pattern(rows)
    assert set(found) == {pattern for _, pattern, _ in expected}
    for signal_type, pattern, target in expected:
        row = found[pattern]
        assert list(row) == ['id', 'ts', 'source', 'repo', 'pattern', 'est_savings', 'target_skill', 'status',
                             'signal_type']
        assert row == {'id': eid(pattern), 'ts': NOW, 'source': SOURCE, 'repo': 'rhize-plugins', 'pattern': pattern,
                       'est_savings': None, 'target_skill': target, 'status': 'pending', 'signal_type': signal_type}
    # the ids are pinned literally too: any wording change to a pattern is a deliberate, reviewed event
    assert sorted(row['id'] for row in rows) == sorted(PINNED_IDS)
    summary = json.loads(capsys.readouterr().out)
    assert summary['candidates'] == 4 and summary['groupsBelowThreshold'] == 1
    assert summary['bySignal'] == {'decision-layer/cosign-suppressed-then-invoked': 1,
                                   'decision-layer/laya-timeouts': 1, 'routing-miss/not-shortlisted': 1,
                                   'routing-miss/suggested-but-ignored': 1}


PINNED_IDS = ['c36e943da15d', 'b46a5e1ce66d', 'e5dc97545893', '9a6b8882746e']     # independent sha1sum values


def test_queue_file_is_private_and_new(seed, tmp_path):
    seed_all_signals(seed)
    _, queue = run_emit(seed, tmp_path)
    assert stat.S_IMODE(os.stat(queue).st_mode) == 0o600
    assert not [p for p in queue.parent.iterdir() if p != queue]          # no temp files left behind


def test_repo_and_target_forms(seed, tmp_path):
    for _ in range(3):
        seed.record(outcome='invoked_unlisted', skill='learned-thing')    # a bare (user-level) skill name
    code, queue = run_emit(seed, tmp_path, repo='some-repo')
    [row] = read_queue(queue)
    assert code == 0 and row['repo'] == 'some-repo' and row['target_skill'] == 'learned-thing'
    assert row['pattern'] == NOT_SHORTLISTED.format(host='claude', skill='skill:learned-thing')


# ---------------------------------------------------------------- threshold behavior

@pytest.mark.parametrize('min_events,count,expected', [(3, 2, 0), (3, 3, 1), (3, 5, 1), (5, 4, 0), (5, 5, 1), (1, 1, 1)])
def test_min_events_threshold(seed, tmp_path, min_events, count, expected):
    for _ in range(count):
        seed.record(outcome='invoked_unlisted', skill=DASH)
    _, queue = run_emit(seed, tmp_path, min_events=min_events)
    assert len(read_queue(queue)) == expected


def test_groups_are_per_skill_and_per_host(seed, tmp_path):
    for _ in range(2):
        seed.record(outcome='invoked_unlisted', skill=DASH, host='claude')
        seed.record(outcome='invoked_unlisted', skill=DASH, host='codex')
        seed.record(outcome='invoked_unlisted', skill='a:b', host='claude')
    _, queue = run_emit(seed, tmp_path)
    assert read_queue(queue) == []            # 2 + 2 + 2: no single (skill, host) group reaches 3
    seed.record(outcome='invoked_unlisted', skill=DASH, host='claude')
    _, queue = run_emit(seed, tmp_path, name='second.jsonl')
    [row] = read_queue(queue)
    assert row['pattern'] == NOT_SHORTLISTED.format(host='claude', skill='skill:rhize-ops/skill-dashboard')


def test_only_the_defined_outcomes_and_conditions_count(seed, tmp_path):
    for _ in range(3):
        seed.record(outcome='invoked_emitted', skill=SEO_REF)                 # the suggestion worked
        seed.record(outcome='none_invoked')
        seed.record(outcome='transcript_unavailable')
        seed.record()                                                          # no outcome yet: not finalized
        seed.record(emitted=None, outcome='invoked_other_shortlisted', skill=GEO_REF)   # nothing was shown
        # cosign suppressed but too slow, wrong arm, or a different skill invoked: none of these is signal 3
        seed.record(mode='cosign', outcome='invoked_other_shortlisted', skill=SEO_REF, turns=2)
        seed.record(mode='cosign', arm='holdback', emitted=None, outcome='invoked_other_shortlisted', skill=SEO_REF,
                    turns=0)
        seed.record(mode='cosign', outcome='invoked_other_shortlisted', skill=GEO_REF, turns=0, incumbent=ALT2,
                    shortlist=[ALT2, INC, ALT1])
    _, queue = run_emit(seed, tmp_path)
    assert read_queue(queue) == []


def test_cosign_suppressed_boundary_turn_and_arm(seed, tmp_path):
    for turns in (0, 1, 1):
        seed.record(mode='cosign', outcome='invoked_other_shortlisted', skill=SEO_REF, turns=turns)
    _, queue = run_emit(seed, tmp_path)
    [row] = read_queue(queue)
    assert row['signal_type'] == 'decision-layer' and row['target_skill'] == 'seo-aeo-geo/seo-site-audit'
    assert 'cosign-suppressed-then-invoked' in row['pattern']


def test_suppressed_also_covers_a_laya_timeout_with_emitted_null(seed, tmp_path):
    # cosign-v1 emits nothing unless Laya answered and agreed, so a timeout withholds the suggestion too
    for _ in range(3):
        seed.record(mode='cosign', status='timeout', choice=None, emitted=None,
                    outcome='invoked_other_shortlisted', skill=SEO_REF, turns=0)
    _, queue = run_emit(seed, tmp_path)
    assert [row['pattern'] for row in read_queue(queue)] == [SUPPRESSED.format(host='claude', skill=INC)]


# ---------------------------------------------------------------- laya-timeouts

@pytest.mark.parametrize('calls,timeouts,skipped,expected', [
    (20, 2, 0, True),        # 10% of 20 calls
    (20, 1, 0, False),       # exactly 5% is not above 5%
    (40, 3, 0, True),        # 7.5%
    (40, 2, 0, False),       # exactly 5%
    (19, 19, 0, False),      # fewer than 20 calls
    (19, 5, 7, False),       # 26 records but 7 were skipped: only 19 calls
    (20, 3, 9, True),        # skipped records do not count as calls (or as timeouts)
])
def test_laya_timeout_signal_thresholds(seed, tmp_path, calls, timeouts, skipped, expected):
    for index in range(calls):
        timed_out = index < timeouts
        seed.record(host='codex', status='timeout' if timed_out else 'ok', choice=None if timed_out else ALT1)
    for _ in range(skipped):
        seed.record(host='codex', status='skipped', choice=None)
    _, queue = run_emit(seed, tmp_path)
    rows = read_queue(queue)
    assert [r['pattern'] for r in rows] == ([TIMEOUTS.format(host='codex', skill=None)] if expected else [])
    if expected:
        assert rows[0]['target_skill'] is None and rows[0]['signal_type'] == 'decision-layer'


def test_laya_timeouts_are_per_host_and_ignore_backfill(seed, tmp_path):
    for index in range(20):
        seed.record(host='claude', status='timeout' if index < 4 else 'ok', choice=None if index < 4 else ALT1)
        seed.record(host='codex', status='ok')
    for _ in range(25):
        seed.record(host='unknown', basis='backfill', status='timeout', choice=None, incumbent=INC)
    _, queue = run_emit(seed, tmp_path)
    assert [r['pattern'] for r in read_queue(queue)] == [TIMEOUTS.format(host='claude', skill=None)]


# ---------------------------------------------------------------- window

def test_window_excludes_old_and_future_records(seed, tmp_path):
    for _ in range(3):
        seed.record(days_ago=15, outcome='invoked_unlisted', skill='old:skill')
        seed.record(days_ago=-1, outcome='invoked_unlisted', skill='future:skill')
        seed.record(days_ago=13, outcome='invoked_unlisted', skill='fresh:skill')
    _, queue = run_emit(seed, tmp_path)
    assert [r['target_skill'] for r in read_queue(queue)] == ['fresh/skill']
    _, wide = run_emit(seed, tmp_path, name='wide.jsonl', window_days=20)
    assert sorted(r['target_skill'] for r in read_queue(wide)) == ['fresh/skill', 'old/skill']


def test_window_edges_are_inclusive_of_the_start_and_of_now(seed, tmp_path):
    for _ in range(2):
        seed.record(days_ago=14, outcome='invoked_unlisted', skill='edge:skill')     # exactly the window start
    seed.record(days_ago=0, outcome='invoked_unlisted', skill='edge:skill', join_after_hours=0)  # exactly now
    _, queue = run_emit(seed, tmp_path)
    assert [r['target_skill'] for r in read_queue(queue)] == ['edge/skill']


def test_outcomes_joined_after_now_are_not_evidence(seed, tmp_path):
    for _ in range(3):                                           # records in the window, outcomes joined later
        seed.record(days_ago=0.01, outcome='invoked_unlisted', skill='late:skill', join_after_hours=1)
    _, queue = run_emit(seed, tmp_path)
    assert read_queue(queue) == []
    for _ in range(3):
        seed.record(days_ago=0.01, outcome='invoked_unlisted', skill='late:skill', join_after_hours=0.001)
    _, queue2 = run_emit(seed, tmp_path, name='queue2.jsonl')
    assert [r['target_skill'] for r in read_queue(queue2)] == ['late/skill']


def test_the_newest_join_at_or_before_now_wins(seed, tmp_path):
    for _ in range(3):
        rec = seed.record(days_ago=2, outcome='none_invoked')    # first join: nothing invoked
        seed.outcome(rec, 'invoked_unlisted', 'rejoin:skill', join_after_hours=5)    # a later re-join
        seed.outcome(rec, 'none_invoked', join_after_hours=72)   # a "re-join" dated after now: ignored
    _, queue = run_emit(seed, tmp_path)
    assert [r['target_skill'] for r in read_queue(queue)] == ['rejoin/skill']


def test_timeout_signal_also_respects_the_window(seed, tmp_path):
    for _ in range(25):
        seed.record(days_ago=20, status='timeout', choice=None)
    _, queue = run_emit(seed, tmp_path)
    assert read_queue(queue) == []


def test_duplicate_occurrences_count_once_and_live_beats_backfill(seed, tmp_path):
    first = seed.record(outcome='invoked_unlisted', skill=DASH)
    for _ in range(5):                                           # the same router run recorded again
        records.append(seed.root, 'skill-fit', 'records', copy.deepcopy(first))
    _, queue = run_emit(seed, tmp_path)
    assert read_queue(queue) == []                               # one event, not six


def test_live_record_wins_over_a_backfill_replay_of_the_same_prompt(seed, tmp_path):
    for _ in range(3):
        seed.n += 1
        ts = seed.ts(2)
        replay = make_record(seed.n, ts=ts, basis='backfill', incumbent=INC)
        replay['host'] = 'claude'
        live = make_record(seed.n, ts=ts)
        live['host'] = 'codex'
        assert replay['occurrenceKey'] == live['occurrenceKey']
        records.append(seed.root, 'skill-fit', 'records', contract.validate_record(replay))
        records.append(seed.root, 'skill-fit', 'records', contract.validate_record(live))
        seed.outcome(live, 'invoked_unlisted', DASH)
    _, queue = run_emit(seed, tmp_path)
    assert [r['pattern'] for r in read_queue(queue)] == [
        NOT_SHORTLISTED.format(host='codex', skill='skill:rhize-ops/skill-dashboard')]


# ---------------------------------------------------------------- idempotence

def test_second_run_yields_identical_ids_and_bytes(seed, tmp_path):
    seed_all_signals(seed)
    _, first = run_emit(seed, tmp_path, name='a.jsonl')
    _, second = run_emit(seed, tmp_path, name='b.jsonl')
    assert first.read_bytes() == second.read_bytes() and first.read_bytes()
    later = (NOW_DT + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    _, third = run_emit(seed, tmp_path, name='c.jsonl', now=later)
    assert [r['id'] for r in read_queue(third)] == [r['id'] for r in read_queue(first)]
    assert {r['ts'] for r in read_queue(third)} == {later}


def test_ids_do_not_depend_on_counts(seed, tmp_path):
    for _ in range(3):
        seed.record(outcome='invoked_unlisted', skill=DASH)
    _, small = run_emit(seed, tmp_path, name='small.jsonl')
    for _ in range(4):
        seed.record(outcome='invoked_unlisted', skill=DASH)
    _, large = run_emit(seed, tmp_path, name='large.jsonl')
    assert read_queue(small)[0]['id'] == read_queue(large)[0]['id']
    assert not re.search(r'\d', read_queue(large)[0]['pattern'])           # no counts, no dates in the pattern


def test_empty_root_writes_an_empty_private_file(home, tmp_path, capsys):
    code = harvest_signals.main(['emit', '--queue', str(tmp_path / 'q.jsonl'), '--root', str(tmp_path / 'nothing'),
                                 '--now', NOW])
    assert code == 0 and (tmp_path / 'q.jsonl').read_bytes() == b''
    assert json.loads(capsys.readouterr().out)['candidates'] == 0
    assert stat.S_IMODE(os.stat(tmp_path / 'q.jsonl').st_mode) == 0o600


# ---------------------------------------------------------------- refusals

def test_live_queue_path_is_refused_and_never_opened(seed, tmp_path, home, capsys):
    live = home / '.claude' / 'context-manager' / 'refinement-queue.jsonl'
    for target in (live, home / '.claude' / 'context-manager' / '..' / 'context-manager' / 'refinement-queue.jsonl'):
        code = harvest_signals.main(['emit', '--queue', str(target), '--root', str(seed.root), '--now', NOW])
        assert code == 2 and json.loads(capsys.readouterr().out)['status'] == 'refused'
    assert not live.exists() and not (home / '.claude').exists()
    # an existing live queue is left byte-for-byte alone
    live.parent.mkdir(parents=True)
    live.write_text('{"id":"x"}\n')
    assert harvest_signals.main(['emit', '--queue', str(live), '--root', str(seed.root), '--now', NOW]) == 2
    assert live.read_text() == '{"id":"x"}\n'


def test_live_queue_reached_through_symlinks_is_refused(seed, tmp_path, home):
    live_dir = home / '.claude' / 'context-manager'
    live_dir.mkdir(parents=True)
    alias = tmp_path / 'alias'
    alias.symlink_to(live_dir, target_is_directory=True)
    assert harvest_signals.main(['emit', '--queue', str(alias / 'refinement-queue.jsonl'), '--root', str(seed.root),
                                 '--now', NOW]) == 2
    link = tmp_path / 'link.jsonl'
    link.symlink_to(live_dir / 'refinement-queue.jsonl')
    assert harvest_signals.main(['emit', '--queue', str(link), '--root', str(seed.root), '--now', NOW]) == 2
    assert not (live_dir / 'refinement-queue.jsonl').exists()


def test_existing_file_and_symlinks_are_refused(seed, tmp_path, capsys):
    existing = tmp_path / 'existing.jsonl'
    existing.write_text('keep me\n')
    assert harvest_signals.main(['emit', '--queue', str(existing), '--root', str(seed.root), '--now', NOW]) == 2
    assert existing.read_text() == 'keep me\n'
    target = tmp_path / 'target.jsonl'
    link = tmp_path / 'dangling.jsonl'
    link.symlink_to(target)
    assert harvest_signals.main(['emit', '--queue', str(link), '--root', str(seed.root), '--now', NOW]) == 2
    assert 'symlinked queue path refused' in capsys.readouterr().out and not target.exists()
    # a second emit to the file the first one created is refused as well
    queue = tmp_path / 'fresh.jsonl'
    assert harvest_signals.main(['emit', '--queue', str(queue), '--root', str(seed.root), '--now', NOW]) == 0
    assert harvest_signals.main(['emit', '--queue', str(queue), '--root', str(seed.root), '--now', NOW]) == 2


@pytest.mark.parametrize('flags', [['--window-days', '0'], ['--min-events', '0'], ['--now', 'not-a-time'],
                                   ['--now', '2026-10-12T12:00:00'], ['--repo', ' ']])
def test_bad_arguments_are_refused_without_writing(seed, tmp_path, flags):
    queue = tmp_path / 'q.jsonl'
    argv = ['emit', '--queue', str(queue), '--root', str(seed.root)]
    if '--now' not in flags:
        argv += ['--now', NOW]
    assert harvest_signals.main(argv + flags) == 2
    assert not queue.exists()


def test_invalid_lines_are_counted_not_repaired(seed, tmp_path, capsys):
    seed.record(outcome='invoked_unlisted', skill=DASH)
    day_file = next((seed.root / 'skill-fit' / 'records').glob('*.jsonl'))
    with open(day_file, 'a', encoding='utf-8') as handle:
        handle.write('{not json}\n{"schema":"wrong"}\n')
    before = day_file.read_bytes()
    code, _ = run_emit(seed, tmp_path)
    assert code == 0 and json.loads(capsys.readouterr().out)['invalidLines'] == 2
    assert day_file.read_bytes() == before


# ---------------------------------------------------------------- no prompt text, nothing else written

def test_output_is_only_template_text_and_counts_only_summary(seed, tmp_path, capsys):
    seed_all_signals(seed)
    sentinel = 'ZEBRA-SENTINEL-PHRASE'
    (seed.root / 'unrelated.txt').write_text(sentinel)            # evidence-adjacent text must stay unread
    _, queue = run_emit(seed, tmp_path)
    text = queue.read_text(encoding='utf-8')
    assert sentinel not in text and sentinel not in capsys.readouterr().out
    regexes = [re.compile('\\A' + re.escape(t).replace(r'\{host\}', r'(claude|codex|unknown)')
                          .replace(r'\{skill\}', r'(skill:[A-Za-z0-9_.:/-]+|None)') + '\\Z') for t in TEMPLATES]
    for row in read_queue(queue):
        assert any(rx.match(row['pattern']) for rx in regexes), row['pattern']
        assert set(row) == set(harvest_signals.QUEUE_KEYS)
        assert row['est_savings'] is None and row['status'] == 'pending' and row['source'] == SOURCE
    # nothing but the new queue file and the seeded evidence exists
    assert sorted(p.name for p in seed.root.iterdir()) == ['skill-fit', 'unrelated.txt']


def test_emit_writes_nothing_under_the_evidence_store(seed, tmp_path):
    seed_all_signals(seed)
    before = sorted(str(p.relative_to(seed.root)) for p in seed.root.rglob('*'))
    snapshot = {p: p.read_bytes() for p in seed.root.rglob('*') if p.is_file()}
    run_emit(seed, tmp_path)
    assert sorted(str(p.relative_to(seed.root)) for p in seed.root.rglob('*')) == before
    assert {p: p.read_bytes() for p in seed.root.rglob('*') if p.is_file()} == snapshot


def test_cli_subprocess_prints_counts_only_json(seed, tmp_path, home):
    seed_all_signals(seed)
    queue = tmp_path / 'cli' / 'queue.jsonl'
    env = {**os.environ, 'HOME': str(home), 'PYTHONDONTWRITEBYTECODE': '1'}
    done = subprocess.run([sys.executable, str(SCRIPT), 'emit', '--queue', str(queue), '--root', str(seed.root),
                           '--now', NOW], capture_output=True, text=True, env=env, timeout=60)
    assert done.returncode == 0 and done.stderr == ''
    summary = json.loads(done.stdout)
    assert summary['status'] == 'ok' and summary['candidates'] == 4
    assert all(isinstance(v, (int, dict)) or k == 'status' for k, v in summary.items())
    refused = subprocess.run([sys.executable, str(SCRIPT), 'emit', '--queue', str(queue), '--root', str(seed.root)],
                             capture_output=True, text=True, env=env, timeout=60)
    assert refused.returncode == 2 and json.loads(refused.stdout)['status'] == 'refused'
