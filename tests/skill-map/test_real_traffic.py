"""Weekly router-candidate evaluator on real traffic (evals/skill-map-routing/real_traffic.py; plan §7 F7/F8, A3).

Synthetic records, labels, outcomes and transcripts in tmp dirs, tiny git repos and tiny router indexes. Every
prompt carries the token below so the privacy tests can scan all outputs for it. Nothing here touches a real data
root, a real transcript or the network.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from fractions import Fraction
from math import comb
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tests' / 'rhize-context-manager'))
sys.path.insert(0, str(REPO / 'rhize-context-manager' / 'scripts'))

from _util import load_module  # noqa: E402
import typed_decision_testkit as kit  # noqa: E402
from typed_decisions import contract, records, transcripts  # noqa: E402

rt = load_module(REPO / 'evals' / 'skill-map-routing' / 'real_traffic.py', 'real_traffic_under_test')

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node is required for the router replay')
needs_git = pytest.mark.skipif(shutil.which('git') is None, reason='git is required')
pytestmark = [needs_node, needs_git]

SENTINEL = 'sentinelprompttext'
DESC_SENTINEL = 'skilldescriptionsentinel'
FREEZE = '2026-10-11T12:00:00Z'
AFTER = '2026-10-12T09:00:00.000Z'

A, B, C = 'skill:demo/alpha-audit', 'skill:demo/beta-ship', 'skill:demo/gamma-seo'
D, E = 'skill:demo/delta-crm', 'skill:demo/epsilon-ops'


def sig(name, *phrases):
    return [{'kind': 'name', 'label': name, 'weight': 1}] + [{'kind': 'phrase', 'label': p, 'weight': 2} for p in phrases]


BASE_SIGNALS = {A: sig('alpha-audit', 'zebra ledger', 'quartz margin'), B: sig('beta-ship', 'walrus harbor', 'cobalt ferry'),
                D: sig('delta-crm', 'delta crm', 'pipeline sync'), E: sig('epsilon-ops', 'epsilon ops', 'sigma gate')}
# The candidate teaches the router gamma-seo and forgets the delta-crm and epsilon-ops phrases.
CAND_SIGNALS = {A: BASE_SIGNALS[A], B: BASE_SIGNALS[B], C: sig('gamma-seo', 'gamma seo', 'nimbus audit'),
                D: sig('delta-crm'), E: sig('epsilon-ops')}


def index_doc(signals):
    return {'router': {'signals': signals, 'extendsBases': {}}}


def map_doc(signals):
    return {'nodes': [{'id': skill, 'kind': 'skill', 'description': f'{DESC_SENTINEL} for {skill}'} for skill in signals]}


# ------------------------------------------------------------------ git, arms, manifest

def git(cwd, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null')
    done = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', '-c', 'commit.gpgsign=false',
                           '-c', 'core.excludesFile=/dev/null', *args], cwd=cwd, env=env, capture_output=True,
                          text=True, check=True)
    return done.stdout.strip()


def make_repos(tmp_path, base_files=None, candidate_files=None):
    base, cand = tmp_path / 'baseline', tmp_path / 'candidate'
    base.mkdir()
    git(base, 'init', '-q')
    for name, text in {'catalog/tags.json': '{"v":1}', **(base_files or {})}.items():
        (base / name).parent.mkdir(parents=True, exist_ok=True)
        (base / name).write_text(text)
    git(base, 'add', '-A')
    git(base, 'commit', '-q', '-m', 'baseline')
    git(tmp_path, 'clone', '-q', str(base), str(cand))
    for name, text in {'catalog/tags.json': '{"v":2}', **(candidate_files or {})}.items():
        (cand / name).parent.mkdir(parents=True, exist_ok=True)
        (cand / name).write_text(text)
    git(cand, 'add', '-A')
    git(cand, 'commit', '-q', '-m', 'candidate')
    return base, cand


@pytest.fixture
def repos(tmp_path):
    return make_repos(tmp_path)


@pytest.fixture
def arms(tmp_path):
    folder = tmp_path / 'arms-src'
    folder.mkdir()
    paths = {}
    for name, signals in (('baseline', BASE_SIGNALS), ('candidate', CAND_SIGNALS)):
        paths[f'{name}_index'] = folder / f'{name}-index.json'
        paths[f'{name}_map'] = folder / f'{name}-map.json'
        paths[f'{name}_index'].write_text(json.dumps(index_doc(signals)))
        paths[f'{name}_map'].write_text(json.dumps(map_doc(signals)))
    return paths


def do_freeze(tmp_path, repos, arms, root, now=FREEZE, name='cand.manifest.json', **kwargs):
    out = tmp_path / 'frozen' / name
    manifest = rt.freeze(repos[0], repos[1], out, root=root, now=now, **arms, **kwargs)
    return out, manifest


# ------------------------------------------------------------------ the synthetic world

class World:
    """Records, labels, outcomes and transcripts for synthetic router traffic, written under tmp_path."""

    def __init__(self, tmp_path):
        self.root = tmp_path / 'root'
        self.tx = tmp_path / 'transcripts'
        self.counter = 0
        self.recs, self.labels, self.outs = [], [], []
        self.sessions = []
        self.prompts = []

    def prompt(self, text):
        full = f'{text} {SENTINEL}{self.counter}'
        self.prompts.append(full)
        return full

    def add(self, text, shortlist, *, acceptable=None, ambiguous=False, outcome=None, stratum='fired', ts=AFTER,
            host='claude', thread_source='user', rollout=None, session=None, exact=False):
        """One record (plus label / outcome / transcript). Returns the record."""
        self.counter += 1
        i = self.counter
        prompt = text if exact else self.prompt(text)
        session_id = session or str(uuid.UUID(int=i))
        if session is None:
            self.sessions.append(session_id)
        if rollout is None:
            rollout = host == 'codex'
        self.write_transcript(session_id, prompt, rollout, thread_source)
        if stratum == 'silent_sample':
            rec = kit.make_record(i, basis='backfill', incumbent=None, shortlist=shortlist, status='skipped', ts=ts,
                                  stratum='silent_sample')
        else:
            rec = kit.make_record(i, incumbent=shortlist[0], choice=shortlist[0], shortlist=shortlist, ts=ts)
        rec['sessionHash'] = transcripts.sha256_text(session_id)
        rec['promptHash'] = transcripts.sha256_text(prompt)
        rec['host'] = host
        rec['occurrenceKey'] = contract.occurrence_key(rec['sessionHash'], rec['promptHash'], rec['ts'])
        rec = contract.validate_record(rec)
        self.recs.append(rec)
        if acceptable is not None or ambiguous:
            self.labels.append(kit.make_label(rec, acceptable=acceptable or [], ambiguous=ambiguous))
        if outcome is not None:
            kind, skill, *rest = outcome
            via, latency = (rest + ['skill_tool', 0][len(rest):])[:2] if rest else ('skill_tool', 0)
            self.outs.append(contract.validate_outcome({
                'schema': contract.OUTCOME_SCHEMA, 'decisionId': rec['decisionId'], 'occurrenceKey': rec['occurrenceKey'],
                'outcome': kind, 'skillInvoked': skill, 'via': via, 'latencyTurns': latency,
                'joinedAt': '2026-10-13T00:00:00Z', 'transcriptSha256': 'a' * 64}))
        return rec

    def write_transcript(self, session_id, prompt, rollout, thread_source):
        if rollout:
            path = self.tx / 'codex' / f'rollout-2026-10-12T09-00-00-{session_id}.jsonl'
            lines = []
            if thread_source is not False:
                meta = {'id': session_id}
                if thread_source is not None:
                    meta['thread_source'] = thread_source
                lines.append({'type': 'session_meta', 'payload': meta})
            lines.append({'type': 'response_item', 'timestamp': AFTER,
                          'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': prompt}]}})
        else:
            path = self.tx / 'claude' / f'{session_id}.jsonl'
            lines = [{'type': 'user', 'timestamp': AFTER, 'message': {'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}}]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a', encoding='utf-8') as stream:
            for line in lines:
                stream.write(json.dumps(line) + '\n')

    def flush(self):
        kit.write_records(self.root, self.recs)
        kit.write_labels(self.root, self.labels)
        for outcome in self.outs:
            records.append(self.root, 'skill-fit', 'outcomes', outcome)
        self.recs, self.labels, self.outs = [], [], []
        return self.root


def mixed_world(tmp_path):
    """The hand-computed scenario. Candidate wins: 2, 4, 7, 10. Baseline wins: 3, 8, 11. Not comparable: 5."""
    w = World(tmp_path)
    w.add('zebra ledger quartz margin report', [A, B], acceptable=[A])                 # 1 hit / hit
    w.add('gamma seo nimbus audit', [C, A], acceptable=[C])                            # 2 miss / hit: candidate wins
    w.add('delta crm pipeline sync', [D, A], acceptable=[D])                           # 3 hit / miss: baseline wins
    w.add('epsilon ops sigma gate', [E, A], acceptable=[])                             # 4 false fire / silent: candidate wins
    w.add('gamma seo nimbus audit again', [A, B], acceptable=[A])                      # 5 miss / unscorable: not comparable
    w.add('walrus harbor cobalt ferry', [A, B], acceptable=[A])                        # 6 wrong / wrong
    w.add('gamma seo nimbus audit weekly', [A, B], outcome=('invoked_unlisted', 'demo:gamma-seo'))          # 7 candidate wins
    w.add('delta crm pipeline sync weekly', [D, A], outcome=('invoked_other_shortlisted', 'demo:delta-crm'))  # 8 baseline wins
    w.add('walrus harbor cobalt ferry weekly', [A, B], outcome=('invoked_unlisted', 'demo:gamma-seo'))       # 9 wrong / wrong
    w.add('epsilon ops sigma gate maybe', [E, A], stratum='silent_sample')             # 10 fire / quiet: candidate wins
    w.add('gamma seo nimbus audit sample', [C, A], stratum='silent_sample')            # 11 quiet / fire: baseline wins
    w.add('nothing relevant at all', [A, B], stratum='silent_sample')                  # 12 quiet / quiet
    return w


def scaled_world(tmp_path, wins, losses):
    w = World(tmp_path)
    for n in range(wins):
        w.add(f'gamma seo nimbus audit run {n}', [C, A], acceptable=[C])
    for n in range(losses):
        w.add(f'delta crm pipeline sync run {n}', [D, A], acceptable=[D])
    return w


@pytest.fixture
def frozen_mixed(tmp_path, repos, arms):
    w = mixed_world(tmp_path)
    out, manifest = do_freeze(tmp_path, repos, arms, w.root)          # frozen before any record exists
    w.flush()
    return w, out, manifest


def run_eval(w, out, harness_status='pass', tmp_path=None, **kwargs):
    result = (tmp_path or out.parent) / 'harness.json'
    result.write_text(json.dumps({'exitCode': 0 if harness_status == 'pass' else 1}))
    return rt.evaluate(out, w.root, [w.tx], harness_result=result, **kwargs)


# ------------------------------------------------------------------ the exact sign test

@pytest.mark.parametrize('wins,losses,numerator,denominator', [
    (0, 0, 1, 1),
    (10, 0, 1, 1024),
    (9, 1, 11, 1024),
    (8, 2, 56, 1024),
    (7, 3, 176, 1024),
    (15, 5, 21700, 1048576),
    (9, 2, 67, 2048),
    (8, 3, 232, 2048),
    (8, 4, 794, 4096),
    (0, 5, 32, 32),
])
def test_sign_test_is_exact(wins, losses, numerator, denominator):
    result = rt.sign_test(wins, losses)
    assert Fraction(result['tail'], 2 ** result['n']) == Fraction(numerator, denominator)
    assert result['pValue'] == pytest.approx(numerator / denominator)
    assert result['n'] == wins + losses


def test_sign_test_matches_binomial_definition_for_many_values():
    for n in range(0, 25):
        for wins in range(0, n + 1):
            tail = sum(comb(n, k) for k in range(wins, n + 1))
            assert rt.sign_test(wins, n - wins)['tail'] == tail


def test_nine_of_ten_is_significant_but_eight_of_ten_is_not():
    rule = rt.default_rule()
    base = dict(harness_status='pass', baseline_fires=0, candidate_fires=0, candidate_unscorable=0,
                candidate_labeled=10, rule=rule)
    assert rt.decide(discordant=10, wins=9, losses=1, **base)['verdict'] == 'keep'
    eight = rt.decide(discordant=10, wins=8, losses=2, **base)         # p = 56/1024 = 0.0547 > 0.05
    assert eight['verdict'] == 'discard' and eight['blockers'] == ['signTest']


# ------------------------------------------------------------------ the keep rule, branch by branch

KEEP_BASE = dict(harness_status='pass', discordant=12, wins=11, losses=1, baseline_fires=3, candidate_fires=3,
                 candidate_unscorable=2, candidate_labeled=10)


def decide(**override):
    return rt.decide(**{**KEEP_BASE, **override}, rule=rt.default_rule())


def test_keep_requires_every_condition():
    keep = decide()
    assert keep['verdict'] == 'keep' and keep['blockers'] == []
    assert keep['signTest']['n'] == 12 and keep['signTest']['pValue'] == pytest.approx(13 / 4096)


@pytest.mark.parametrize('status,verdict', [('fail', 'discard'), ('not_run', 'blocked'), ('invalid_result', 'blocked'),
                                            ('candidate_mismatch', 'blocked'), ('unavailable', 'blocked')])
def test_harness_must_pass(status, verdict):
    # only a real harness failure is a final discard; an infrastructure gap is a non-final `blocked`
    result = decide(harness_status=status)
    assert result['verdict'] == verdict and result['blockers'] == ['harness']
    assert decide(harness_status=status, discordant=9, wins=9, losses=0)['verdict'] == (
        'insufficient' if status == 'fail' else 'blocked')


def test_fewer_than_ten_discordant_is_insufficient_even_when_one_sided():
    result = decide(discordant=9, wins=9, losses=0)                    # p = 1/512, still not enough cases
    assert result['verdict'] == 'insufficient' and result['blockers'] == ['minDiscordant']
    assert decide(discordant=10, wins=10, losses=0)['verdict'] == 'keep'


def test_a_non_significant_split_is_discarded():
    result = decide(discordant=12, wins=8, losses=4)                   # 794/4096 = 0.194
    assert result['verdict'] == 'discard' and result['blockers'] == ['signTest']
    assert decide(discordant=12, wins=4, losses=8)['verdict'] == 'discard'


def test_silence_fire_count_may_not_rise():
    assert decide(candidate_fires=4)['blockers'] == ['silenceFireCount']
    assert decide(candidate_fires=4)['verdict'] == 'discard'
    assert decide(candidate_fires=2)['verdict'] == 'keep'              # a drop is fine
    assert decide(baseline_fires=0, candidate_fires=0)['verdict'] == 'keep'


def test_unscorable_share_boundary():
    assert decide(candidate_labeled=10, candidate_unscorable=2)['verdict'] == 'keep'          # exactly 0.20
    over = decide(candidate_labeled=10, candidate_unscorable=3)
    assert over['verdict'] == 'discard' and over['blockers'] == ['unscorableShare']
    assert decide(candidate_labeled=0, candidate_unscorable=0)['verdict'] == 'keep'          # nothing labeled, nothing unscorable


def test_every_failed_condition_is_listed():
    result = decide(harness_status='fail', discordant=12, wins=6, losses=6, candidate_fires=9, candidate_unscorable=9)
    assert result['verdict'] == 'discard'
    assert result['blockers'] == ['harness', 'signTest', 'silenceFireCount', 'unscorableShare']


# ------------------------------------------------------------------ scoring of one case

@pytest.mark.parametrize('route,shortlist,acceptable,status,correct', [
    (A, [A, B], [A], 'hit', True),
    (A, [A, B], [A, B], 'hit', True),
    (B, [A, B], [A], 'wrong', False),
    (A, [A, B], [], 'falseFire', False),
    (None, [A, B], [], 'silentCorrect', True),
    (None, [A, B], [A], 'miss', False),
    (C, [A, B], [A], 'unscorable', None),
    (C, [A, B], [], 'unscorable', None),      # outside the shortlist wins over "fired on a no-fit case"
])
def test_labeled_scoring(route, shortlist, acceptable, status, correct):
    case = {'type': 'labeled', 'shortlist': tuple(shortlist), 'acceptable': frozenset(acceptable)}
    assert rt.score_case(case, route) == (status, correct)


def test_weak_and_silence_scoring():
    weak = {'type': 'weak', 'invoked': 'demo:gamma-seo'}
    assert rt.score_case(weak, C) == ('recalled', True)
    assert rt.score_case(weak, A) == ('wrong', False)
    assert rt.score_case(weak, None) == ('silent', False)
    assert rt.score_case({'type': 'weak', 'invoked': 'gamma-seo'}, C) == ('recalled', True)        # bare name
    assert rt.score_case({'type': 'weak', 'invoked': '/Demo:Gamma-SEO'}, C) == ('recalled', True)
    assert rt.score_case({'type': 'weak', 'invoked': 'gamma-seo'}, 'skill:market/demo/gamma-seo') == ('recalled', True)
    assert rt.score_case({'type': 'silence'}, A) == ('fire', False)
    assert rt.score_case({'type': 'silence'}, None) == ('quiet', True)


# ------------------------------------------------------------------ weak positive rules

@pytest.mark.parametrize('outcome,expected', [
    ({'outcome': 'invoked_unlisted', 'via': 'skill_tool', 'latencyTurns': 0, 'skillInvoked': 'demo:x'}, 'demo:x'),
    ({'outcome': 'invoked_other_shortlisted', 'via': 'slash_command', 'latencyTurns': 0, 'skillInvoked': '/demo:x'}, 'demo:x'),
    ({'outcome': 'invoked_unlisted', 'via': 'skill_file_read', 'latencyTurns': 0, 'skillInvoked': 'demo:x'}, None),
    ({'outcome': 'invoked_unlisted', 'via': 'skill_tool', 'latencyTurns': 1, 'skillInvoked': 'demo:x'}, None),
    ({'outcome': 'invoked_unlisted', 'via': 'skill_tool', 'latencyTurns': None, 'skillInvoked': 'demo:x'}, None),
    ({'outcome': 'invoked_emitted', 'via': 'skill_tool', 'latencyTurns': 0, 'skillInvoked': 'demo:x'}, 'demo:x'),
    ({'outcome': 'none_invoked', 'via': None, 'latencyTurns': None, 'skillInvoked': None}, None),
    ({'outcome': 'invoked_unlisted', 'via': 'skill_tool', 'latencyTurns': 0,
      'skillInvoked': 'rhize-ops:parallel-agent-optimization'}, None),
    ({'outcome': 'invoked_unlisted', 'via': 'slash_command', 'latencyTurns': 0,
      'skillInvoked': 'Rhize-Ops:Parallel-Agent-Optimization'}, None),
    (None, None),
])
def test_weak_ref_rules(outcome, expected):
    assert rt.weak_ref(outcome, rt.DEFAULT_MANDATED) == expected


def test_the_mandated_list_is_configurable():
    outcome = {'outcome': 'invoked_unlisted', 'via': 'skill_tool', 'latencyTurns': 0, 'skillInvoked': 'demo:x'}
    assert rt.weak_ref(outcome, ['demo:x']) is None
    assert rt.weak_ref(outcome, []) == 'demo:x'
    bare = dict(outcome, skillInvoked='parallel-agent-optimization')
    assert rt.weak_ref(bare, rt.DEFAULT_MANDATED) is None


def test_case_selection_precedence_and_weak_rules(tmp_path):
    w = World(tmp_path)
    labeled = w.add('labeled one', [A, B], acceptable=[A], outcome=('invoked_unlisted', 'demo:x'))
    ambiguous = w.add('ambiguous one', [A, B], ambiguous=True, outcome=('invoked_unlisted', 'demo:x'))
    weak = w.add('weak one', [A, B], outcome=('invoked_unlisted', 'demo:x'))
    slow = w.add('weak but slow', [A, B], outcome=('invoked_unlisted', 'demo:x', 'skill_tool', 1))
    emitted = w.add('followed the router', [A, B], outcome=('invoked_emitted', 'demo:alpha-audit'))
    mandated = w.add('mandated skill', [A, B], outcome=('invoked_unlisted', 'rhize-ops:parallel-agent-optimization'))
    mandated_silent = w.add('mandated and silent', [A, B], stratum='silent_sample',
                            outcome=('invoked_unlisted', 'rhize-ops:parallel-agent-optimization'))
    silent_weak = w.add('silent but invoked', [A, B], stratum='silent_sample', outcome=('invoked_unlisted', 'demo:y'))
    silent = w.add('plain silent sample', [A, B], stratum='silent_sample')
    plain = w.add('plain fired record', [A, B])
    root = w.flush()
    cases, counts = rt.select_cases(root)
    kinds = {c['key']: c['type'] for c in cases}
    # a prompt where the user followed the router's own suggestion is a weak case too (the candidate can lose it)
    assert kinds == {labeled['occurrenceKey']: 'labeled', weak['occurrenceKey']: 'weak',
                     emitted['occurrenceKey']: 'weak',
                     silent_weak['occurrenceKey']: 'weak', mandated_silent['occurrenceKey']: 'silence',
                     silent['occurrenceKey']: 'silence'}
    assert counts['records'] == 10 and counts['ambiguousLabel'] == 1 and counts['notACase'] == 3
    assert ambiguous['occurrenceKey'] not in kinds and slow['occurrenceKey'] not in kinds
    assert mandated['occurrenceKey'] not in kinds
    assert plain['occurrenceKey'] not in kinds


def test_the_same_turn_recorded_twice_is_one_weak_case_the_nearest_record(tmp_path):
    w = World(tmp_path)
    first = w.add('weak twice', [A, B], outcome=('invoked_unlisted', 'demo:x'), ts='2026-10-12T09:00:10.000Z')
    second = w.add(w.prompts[0], [A, B], outcome=('invoked_unlisted', 'demo:x'), session=w.sessions[0], exact=True,
                   ts='2026-10-12T09:02:10.000Z')
    other = w.add('a different weak turn', [A, B], outcome=('invoked_unlisted', 'demo:x'))
    cases, counts = rt.select_cases(w.flush())
    assert {c['key'] for c in cases} == {second['occurrenceKey'], other['occurrenceKey']}
    assert counts['weakDuplicate'] == 1 and first['occurrenceKey'] not in {c['key'] for c in cases}


def test_the_latest_label_wins_with_human_labels_preferred(tmp_path):
    w = World(tmp_path)
    rec = w.add('relabelled', [A, B], acceptable=[A])
    later = kit.make_label(rec, acceptable=[B], labeled_at='2026-10-13T00:00:00Z')
    w.labels.append(later)
    cases, _ = rt.select_cases(w.flush())
    assert cases[0]['acceptable'] == frozenset({B})


def test_selection_is_deterministic_whatever_the_write_order(tmp_path):
    w = mixed_world(tmp_path)
    recs, labels, outs = list(w.recs), list(w.labels), list(w.outs)
    first_root = w.flush()
    second_root = tmp_path / 'second-root'
    kit.write_records(second_root, recs[::-1])
    kit.write_labels(second_root, labels[::-1])
    for outcome in outs[::-1]:
        records.append(second_root, 'skill-fit', 'outcomes', outcome)
    one, counts_one = rt.select_cases(first_root)
    two, counts_two = rt.select_cases(second_root)
    assert one == two and counts_one == counts_two and len(one) == 12
    assert [(c['session'], c['ts']) for c in one] == sorted((c['session'], c['ts']) for c in one)


# ------------------------------------------------------------------ the prospective filter

def test_only_records_strictly_after_the_freeze_are_confirmatory(tmp_path):
    w = World(tmp_path)
    before = w.add('before', [A, B], stratum='silent_sample', ts='2026-10-11T11:59:59.999Z')
    equal = w.add('equal', [A, B], stratum='silent_sample', ts='2026-10-11T12:00:00.000Z')
    equal_z = w.add('equal without millis', [A, B], stratum='silent_sample', ts='2026-10-11T12:00:00Z')
    after = w.add('after', [A, B], stratum='silent_sample', ts='2026-10-11T12:00:00.001Z')
    later = w.add('later', [A, B], stratum='silent_sample')
    root = w.flush()
    freeze_at = rt.parse_record_ts(FREEZE)
    cases, counts = rt.select_cases(root, after=freeze_at)
    assert {c['key'] for c in cases} == {after['occurrenceKey'], later['occurrenceKey']}
    assert counts['records'] == 2
    everything, _ = rt.select_cases(root)                                  # the dev view has no filter
    assert len(everything) == 5
    assert before['occurrenceKey'] not in {c['key'] for c in cases}
    assert equal['occurrenceKey'] not in {c['key'] for c in cases} and equal_z['occurrenceKey'] not in {c['key'] for c in cases}


@pytest.mark.parametrize('text,expected', [
    ('2026-10-11T12:00:00Z', (2026, 10, 11, 12, 0, 0, 0)),
    ('2026-10-11T12:00:00.5Z', (2026, 10, 11, 12, 0, 0, 500000)),
    ('2026-10-11T12:00:00.123456Z', (2026, 10, 11, 12, 0, 0, 123456)),
])
def test_record_timestamps_parse_with_any_fraction(text, expected):
    moment = rt.parse_record_ts(text)
    assert (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second, moment.microsecond) == expected
    with pytest.raises(ValueError):
        rt.parse_record_ts('2026-10-11 12:00:00')


def test_a_freeze_before_existing_records_is_refused(tmp_path, repos, arms):
    w = World(tmp_path)
    w.add('already there', [A, B], stratum='silent_sample', ts='2026-10-11T13:00:00.000Z')
    w.flush()
    with pytest.raises(rt.RealTrafficError) as caught:
        do_freeze(tmp_path, repos, arms, w.root)
    assert caught.value.code == rt.EXIT_REFUSED
    assert not (tmp_path / 'frozen' / 'cand.manifest.json').exists()
    assert not (tmp_path / 'frozen' / 'cand.manifest.json.arms').exists()


# ------------------------------------------------------------------ Codex machine traffic

@pytest.mark.parametrize('source,reason', [
    ('subagent', 'codex_non_user'), ('guardian_review', 'codex_non_user'), ('automation', 'codex_non_user'),
    ('agent_created_thread', 'codex_non_user'), (None, 'codex_unverified'), (False, 'codex_unverified'),
])
def test_codex_threads_that_are_not_user_threads_are_excluded(tmp_path, source, reason):
    w = World(tmp_path)
    rec = w.add('codex prompt', [A, B], stratum='silent_sample', host='codex', thread_source=source)
    w.flush()
    scanner = transcripts.TranscriptScanner([w.tx])
    case = rt.select_cases(w.root)[0][0]
    assert rt.recover_text(case, scanner) == (None, reason)
    assert case['key'] == rec['occurrenceKey']


def test_a_codex_user_thread_is_recovered(tmp_path):
    w = World(tmp_path)
    w.add('codex user prompt', [A, B], stratum='silent_sample', host='codex')
    w.flush()
    case = rt.select_cases(w.root)[0][0]
    text, reason = rt.recover_text(case, transcripts.TranscriptScanner([w.tx]))
    assert reason is None and text.startswith('codex user prompt')


def test_codex_first_line_is_bounded_and_symlinks_are_not_followed(tmp_path):
    big = tmp_path / 'rollout-big.jsonl'
    big.write_text(json.dumps({'type': 'session_meta', 'payload': {'thread_source': 'user', 'pad': 'x' * (600 * 1024)}}) + '\n')
    assert rt.codex_thread_source(big) is None
    small = tmp_path / 'rollout-small.jsonl'
    small.write_text(json.dumps({'type': 'session_meta', 'payload': {'thread_source': 'user'}}))     # no trailing newline
    assert rt.codex_thread_source(small) == 'user'
    wrong_type = tmp_path / 'rollout-wrong.jsonl'
    wrong_type.write_text(json.dumps({'type': 'event_msg', 'payload': {'thread_source': 'user'}}) + '\n')
    assert rt.codex_thread_source(wrong_type) is None
    link = tmp_path / 'rollout-link.jsonl'
    link.symlink_to(small)
    assert rt.codex_thread_source(link) is None
    assert rt.codex_thread_source(tmp_path / 'missing.jsonl') is None
    junk = tmp_path / 'rollout-junk.jsonl'
    junk.write_text('not json\n')
    assert rt.codex_thread_source(junk) is None


def test_a_codex_record_with_only_a_claude_transcript_is_unverified(tmp_path):
    w = World(tmp_path)
    w.add('claims codex', [A, B], stratum='silent_sample', host='codex', rollout=False)
    w.flush()
    case = rt.select_cases(w.root)[0][0]
    assert rt.recover_text(case, transcripts.TranscriptScanner([w.tx])) == (None, 'codex_unverified')


def test_missing_transcripts_are_counted_not_guessed(tmp_path):
    w = World(tmp_path)
    w.add('unrecoverable', [A, B], stratum='silent_sample')
    w.flush()
    shutil.rmtree(w.tx)
    w.tx.mkdir()
    case = rt.select_cases(w.root)[0][0]
    assert rt.recover_text(case, transcripts.TranscriptScanner([w.tx])) == (None, 'transcript_unavailable')


# ------------------------------------------------------------------ freeze

def git_sha(path):
    return git(path, 'rev-parse', 'HEAD')


def test_freeze_records_identity_hashes_and_rules(tmp_path, repos, arms):
    root = tmp_path / 'root'
    out, manifest = do_freeze(tmp_path, repos, arms, root)
    base, cand = repos
    assert manifest['freezeAt'] == '2026-10-11T12:00:00.000Z'
    assert manifest['baseline']['head'] == git_sha(base) and manifest['candidate']['head'] == git_sha(cand)
    assert manifest['baseline']['head'] != manifest['candidate']['head']
    assert manifest['baseline']['dirty'] is False and manifest['candidate']['dirty'] is False
    expected_diff = subprocess.run(
        ['git', '-C', str(cand), 'diff', '--no-ext-diff', '--no-textconv', '--no-color', '--no-renames', '--binary',
         '--full-index', '--src-prefix=a/', '--dst-prefix=b/', git_sha(base), '--'], capture_output=True, check=True).stdout
    assert manifest['diffSha256'] == rt.sha256_bytes(expected_diff) and manifest['diffFiles'] == 1
    for name in ('baseline', 'candidate'):
        assert manifest[name]['mapSha256'] == rt.sha256_bytes(arms[f'{name}_map'].read_bytes())
        copy_index = out.parent / (out.name + '.arms') / name / 'index.json'
        assert copy_index.read_bytes() == arms[f'{name}_index'].read_bytes()
    assert manifest['baseline']['indexSha256'] != manifest['candidate']['indexSha256']
    assert manifest['rule']['split']['confirmatory'] == 'record ts strictly after freezeAt'
    assert manifest['rule']['weakPositive']['mandatedSkills'] == ['rhize-ops:parallel-agent-optimization']
    assert manifest['rule']['keep']['minDiscordant'] == 10 and manifest['rule']['keep']['alpha'] == 0.05
    assert manifest['corpusAtFreeze'] == {'records': 0, 'labels': 0, 'outcomes': 0}
    assert json.loads(out.read_text()) == manifest
    assert rt.load_manifest(out) == manifest


def test_the_manifest_and_frozen_copies_are_private_and_hold_no_prompt_text(tmp_path, repos, arms):
    w = mixed_world(tmp_path)
    out, manifest = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    arms_dir = out.parent / (out.name + '.arms')
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert stat.S_IMODE(arms_dir.stat().st_mode) == 0o700
    for path in arms_dir.rglob('*'):
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
    for path in [out, *[p for p in arms_dir.rglob('*') if p.is_file()]]:
        assert SENTINEL not in path.read_text().lower()


def test_freeze_never_overwrites_a_manifest(tmp_path, repos, arms):
    out, first = do_freeze(tmp_path, repos, arms, tmp_path / 'root')
    before = out.read_bytes()
    with pytest.raises(rt.RealTrafficError) as caught:
        do_freeze(tmp_path, repos, arms, tmp_path / 'root', now='2026-10-12T00:00:00Z')
    assert caught.value.code == rt.EXIT_REFUSED and out.read_bytes() == before


def test_freeze_refuses_uncommitted_changes_unless_allowed(tmp_path, repos, arms):
    (repos[1] / 'catalog' / 'tags.json').write_text('{"v":3}')
    with pytest.raises(rt.RealTrafficError, match='uncommitted'):
        do_freeze(tmp_path, repos, arms, tmp_path / 'root')
    _, manifest = do_freeze(tmp_path, repos, arms, tmp_path / 'root', allow_dirty=True, name='dirty.manifest.json')
    assert manifest['candidate']['dirty'] is True


def test_freeze_needs_both_files_of_an_explicit_arm(tmp_path, repos, arms):
    arms = dict(arms)
    arms['candidate_map'] = None
    with pytest.raises(rt.RealTrafficError, match='both the candidate index'):
        do_freeze(tmp_path, repos, arms, tmp_path / 'root')


def test_freeze_refuses_a_candidate_that_changes_router_code(tmp_path, arms):
    files = {name: '// router\n' for name in rt.ROUTER_CODE_FILES}
    base, cand = make_repos(tmp_path, base_files=files, candidate_files={rt.ROUTER_CODE_FILES[0]: '// changed\n'})
    with pytest.raises(rt.RealTrafficError, match='router code') as caught:
        do_freeze(tmp_path, (base, cand), arms, tmp_path / 'root')
    assert caught.value.code == rt.EXIT_REFUSED
    same = tmp_path / 'same'
    same.mkdir()
    base2, cand2 = make_repos(same, base_files=files, candidate_files={'catalog/tags.json': '{"v":9}'})
    _, manifest = do_freeze(same, (base2, cand2), arms, same / 'root')
    assert manifest['baseline']['routerCodeSha256'] == manifest['candidate']['routerCodeSha256'] is not None


def test_a_missing_baseline_commit_in_the_candidate_checkout_is_refused(tmp_path, arms):
    base = tmp_path / 'b'
    base.mkdir()
    git(base, 'init', '-q')
    (base / 'f').write_text('1')
    git(base, 'add', '-A')
    git(base, 'commit', '-q', '-m', 'one')
    other = tmp_path / 'o'
    other.mkdir()
    git(other, 'init', '-q')
    (other / 'f').write_text('2')
    git(other, 'add', '-A')
    git(other, 'commit', '-q', '-m', 'two')
    with pytest.raises(rt.RealTrafficError, match='git could not read'):
        do_freeze(tmp_path, (base, other), arms, tmp_path / 'root')


HERMETIC = ('--installed-plugins', 'none-1.json', '--stack-config', 'none-2.json', '--global-settings', 'none-3.json',
            '--local-settings', 'none-4.json', '--cooccurrence', 'none-5.json', '--synced-skills-root', 'none')


def hermetic(tmp_path):
    return [arg if not arg.endswith('.json') else str(tmp_path / arg) for arg in HERMETIC]


def test_build_arm_artifacts_runs_the_checkouts_own_build_script(tmp_path):
    index, skill_map = rt.build_arm_artifacts(REPO, tmp_path / 'built', extra_args=hermetic(tmp_path))
    assert index.name == 'skill-map.indexes.resolved.json' and skill_map.name == 'skill-map.resolved.json'
    assert 'router' in json.loads(index.read_text()) and json.loads(skill_map.read_text())['nodes']
    with pytest.raises(rt.RealTrafficError, match='no build_local_skill_map'):
        rt.build_arm_artifacts(tmp_path, tmp_path / 'nowhere')


def test_freeze_builds_each_arm_from_its_own_checkout_when_no_paths_are_given(tmp_path):
    out = tmp_path / 'frozen' / 'aa.manifest.json'
    before = set(Path(tempfile.gettempdir()).glob('rt-freeze-*'))
    manifest = rt.freeze(REPO, REPO, out, root=tmp_path / 'root', now=FREEZE, allow_dirty=True,
                         build_args=hermetic(tmp_path))
    assert manifest['baseline']['indexSha256'] == manifest['candidate']['indexSha256']       # an A/A freeze
    assert manifest['baseline']['mapSha256'] == manifest['candidate']['mapSha256']
    assert manifest['baseline']['head'] == manifest['candidate']['head']
    assert set(Path(tempfile.gettempdir()).glob('rt-freeze-*')) == before                  # the build dir is removed


# ------------------------------------------------------------------ evaluate: exact numbers

def test_evaluate_scores_both_arms_exactly(tmp_path, frozen_mixed):
    w, out, _ = frozen_mixed
    report, line = run_eval(w, out)
    base, cand = report['counts']['baseline'], report['counts']['candidate']
    assert base['labeled'] == {'total': 6, 'hit': 2, 'silentCorrect': 0, 'falseFire': 1, 'wrong': 1, 'miss': 2,
                               'unscorable': 0, 'noFit': 1}
    assert cand['labeled'] == {'total': 6, 'hit': 2, 'silentCorrect': 1, 'falseFire': 0, 'wrong': 1, 'miss': 1,
                               'unscorable': 1, 'noFit': 1}
    assert base['weak'] == {'total': 3, 'recalled': 1, 'wrong': 1, 'silent': 1}
    assert cand['weak'] == {'total': 3, 'recalled': 1, 'wrong': 1, 'silent': 1}
    assert base['silence'] == {'total': 3, 'fire': 1, 'quiet': 2} and cand['silence'] == {'total': 3, 'fire': 1, 'quiet': 2}
    assert report['discordant'] == {'total': 7, 'candidateWins': 4, 'baselineWins': 3,
                                    'byType': {'labeled': {'candidateWins': 2, 'baselineWins': 1},
                                               'weak': {'candidateWins': 1, 'baselineWins': 1},
                                               'silence': {'candidateWins': 1, 'baselineWins': 1}}}
    assert report['cases']['notComparable'] == 1 and report['cases']['scored'] == 12
    assert report['cases']['byType'] == {'labeled': 6, 'weak': 3, 'silence': 3}
    assert report['signTest']['n'] == 7 and report['signTest']['wins'] == 4
    assert report['signTest']['pValue'] == pytest.approx(sum(comb(7, k) for k in range(4, 8)) / 128)
    assert report['verdict'] == 'insufficient' and report['blockers'] == ['minDiscordant', 'signTest']
    assert report['harness'] == {'status': 'pass'}
    assert report['metrics']['candidate']['labeled']['unscorableShare'] == pytest.approx(1 / 6, abs=1e-6)
    assert report['metrics']['baseline']['labeled']['falseFireRate'] == 1.0
    assert report['metrics']['candidate']['silence']['fireRate'] == pytest.approx(1 / 3, abs=1e-6)
    assert {item['winner'] for item in report['discordantCases']} == {'candidate', 'baseline'}
    assert len(report['discordantCases']) == 7
    assert line['verdict'] == report['verdict'] and 'discordantCases' not in line and 'metrics' not in line


def test_evaluate_keeps_a_candidate_that_wins_on_unseen_traffic(tmp_path, repos, arms):
    w = scaled_world(tmp_path, wins=11, losses=1)
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    report, line = run_eval(w, out)
    assert report['discordant']['candidateWins'] == 11 and report['discordant']['baselineWins'] == 1
    assert report['signTest']['pValue'] == pytest.approx(13 / 4096)
    assert report['verdict'] == 'keep' and report['blockers'] == []


def test_evaluate_discards_when_the_harness_fails_even_with_a_clear_win(tmp_path, repos, arms):
    w = scaled_world(tmp_path, wins=12, losses=0)
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    report, _ = run_eval(w, out, harness_status='fail')
    assert report['discordant']['total'] == 12 and report['harness'] == {'status': 'fail'}
    assert report['verdict'] == 'discard' and report['blockers'] == ['harness']


def test_evaluate_without_a_harness_result_cannot_keep(tmp_path, repos, arms):
    w = scaled_world(tmp_path, wins=12, losses=0)
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    report, _ = rt.evaluate(out, w.root, [w.tx])
    assert report['harness'] == {'status': 'not_run'} and report['verdict'] == 'blocked'


def test_evaluate_is_insufficient_with_few_discordant_cases(tmp_path, repos, arms):
    w = scaled_world(tmp_path, wins=9, losses=0)
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    report, _ = run_eval(w, out)
    assert report['verdict'] == 'insufficient' and report['blockers'] == ['minDiscordant']


def test_evaluate_discards_when_the_silence_fire_count_rises(tmp_path, repos, arms):
    w = scaled_world(tmp_path, wins=12, losses=0)
    w.add('gamma seo nimbus audit sample one', [C, A], stratum='silent_sample')
    w.add('gamma seo nimbus audit sample two', [C, A], stratum='silent_sample')
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    report, _ = run_eval(w, out)
    assert report['counts']['baseline']['silence']['fire'] == 0 and report['counts']['candidate']['silence']['fire'] == 2
    assert report['discordant']['baselineWins'] == 2 and report['discordant']['candidateWins'] == 12
    assert report['verdict'] == 'discard' and 'silenceFireCount' in report['blockers']


def test_evaluate_discards_when_too_many_candidate_routes_are_unscorable(tmp_path, repos, arms):
    w = scaled_world(tmp_path, wins=12, losses=0)
    for n in range(4):              # the candidate routes to gamma-seo, which these records never shortlisted
        w.add(f'gamma seo nimbus audit outside {n}', [A, B], acceptable=[A])
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    report, _ = run_eval(w, out)
    assert report['counts']['candidate']['labeled']['unscorable'] == 4 and report['counts']['candidate']['labeled']['total'] == 16
    assert report['cases']['notComparable'] == 4                       # unscorable cases are never discordant
    assert report['discordant']['total'] == 12
    assert report['verdict'] == 'discard' and report['blockers'] == ['unscorableShare']


def test_evaluate_ignores_traffic_recorded_before_the_freeze(tmp_path, repos, arms):
    w = World(tmp_path)
    for n in range(12):             # twelve would-be wins, all recorded at or before the freeze
        w.add(f'gamma seo nimbus audit old {n}', [C, A], acceptable=[C], ts='2026-10-11T12:00:00.000Z')
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    report, _ = run_eval(w, out)
    assert report['cases']['recordsAfterFreeze'] == 0 and report['discordant']['total'] == 0
    assert report['verdict'] == 'insufficient'


def test_evaluate_excludes_codex_machine_traffic_and_counts_why(tmp_path, repos, arms):
    w = World(tmp_path)
    w.add('gamma seo nimbus audit user thread', [C, A], acceptable=[C], host='codex')
    w.add('gamma seo nimbus audit subagent', [C, A], acceptable=[C], host='codex', thread_source='subagent')
    w.add('gamma seo nimbus audit guardian', [C, A], acceptable=[C], host='codex', thread_source='guardian_review')
    w.add('gamma seo nimbus audit unverified', [C, A], acceptable=[C], host='codex', thread_source=None)
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    report, _ = run_eval(w, out)
    assert report['cases']['scored'] == 1
    assert report['cases']['excluded'] == {'codexNonUser': 2, 'codexUnverified': 1}


def test_unrecoverable_prompts_are_excluded_and_counted(tmp_path, repos, arms):
    w = scaled_world(tmp_path, wins=2, losses=0)
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    shutil.rmtree(w.tx / 'claude' / f'{w.sessions[0]}.jsonl', ignore_errors=True)
    (w.tx / 'claude' / f'{w.sessions[0]}.jsonl').unlink()
    report, _ = run_eval(w, out)
    assert report['cases']['scored'] == 1 and report['cases']['excluded'] == {'transcriptUnavailable': 1}


def test_a_replay_error_excludes_the_case(tmp_path, repos, arms):
    w = scaled_world(tmp_path, wins=3, losses=0)
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()

    class Flaky:
        def __init__(self, fail):
            self.fail, self.seen = fail, 0

        def replay(self, text):
            self.seen += 1
            if self.fail and self.seen == 1:
                return {'id': 1, 'error': 'invalid_request'}
            return {'incumbent': None}

    @contextmanager
    def factory(arm_files, node):
        yield {'baseline': Flaky(False), 'candidate': Flaky(True)}

    report, _ = rt.evaluate(out, w.root, [w.tx], replay_factory=factory)
    assert report['cases']['scored'] == 2 and report['cases']['excluded'] == {'replayError': 1}


# ------------------------------------------------------------------ frozen files cannot drift

def test_a_modified_frozen_arm_is_refused(tmp_path, frozen_mixed):
    w, out, _ = frozen_mixed
    frozen_index = out.parent / (out.name + '.arms') / 'candidate' / 'index.json'
    doc = json.loads(frozen_index.read_text())
    doc['router']['signals'][A].append({'kind': 'phrase', 'label': 'tampered phrase', 'weight': 2})
    frozen_index.write_text(json.dumps(doc))
    with pytest.raises(rt.RealTrafficError, match='was modified') as caught:
        run_eval(w, out)
    assert caught.value.code == rt.EXIT_REFUSED
    ledger = w.root / 'skill-fit' / 'improvement' / 'ledger.jsonl'
    assert not ledger.exists()


def test_a_modified_frozen_map_is_refused(tmp_path, frozen_mixed):
    w, out, _ = frozen_mixed
    frozen_map = out.parent / (out.name + '.arms') / 'baseline' / 'map.json'
    frozen_map.write_text(frozen_map.read_text() + ' ')
    with pytest.raises(rt.RealTrafficError, match='was modified'):
        run_eval(w, out)


def test_a_missing_or_malformed_manifest_is_refused(tmp_path, frozen_mixed):
    w, out, manifest = frozen_mixed
    with pytest.raises(rt.RealTrafficError) as missing:
        rt.evaluate(tmp_path / 'nowhere.json', w.root, [w.tx])
    assert missing.value.code == rt.EXIT_REFUSED
    for broken in ({}, {**manifest, 'schema': 'other'}, {**manifest, 'extra': 1},
                   {**manifest, 'freezeAt': 'yesterday'}, {**manifest, 'arms': {'dir': '../elsewhere'}},
                   {**manifest, 'rule': {**manifest['rule'], 'codexThreadSource': 'any'}},
                   {**manifest, 'rule': {**manifest['rule'], 'keep': {**manifest['rule']['keep'], 'harnessMustPass': False}}},
                   {**manifest, 'rule': {**manifest['rule'], 'keep': {**manifest['rule']['keep'], 'minDiscordant': 0}}},
                   {**manifest, 'candidate': {**manifest['candidate'], 'head': 'abc'}}):
        bad = tmp_path / 'bad.json'
        bad.write_text(json.dumps(broken))
        with pytest.raises(rt.RealTrafficError) as caught:
            rt.evaluate(bad, w.root, [w.tx])
        assert caught.value.code == rt.EXIT_REFUSED


def test_a_changed_router_source_since_the_freeze_is_refused(tmp_path, frozen_mixed):
    w, out, manifest = frozen_mixed
    altered = dict(manifest, replay={'routerSourceSha256': '0' * 64})
    path = tmp_path / 'altered.json'
    path.write_text(json.dumps(altered))
    shutil.copytree(out.parent / (out.name + '.arms'), tmp_path / 'altered.json.arms')
    altered['arms'] = {'dir': 'altered.json.arms'}
    path.write_text(json.dumps(altered))
    with pytest.raises(rt.RealTrafficError, match='router source changed'):
        rt.evaluate(path, w.root, [w.tx])


# ------------------------------------------------------------------ the harness gate

def harness_file(tmp_path, content):
    path = tmp_path / 'h.json'
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


@pytest.mark.parametrize('content,status', [
    ({'exitCode': 0}, 'pass'), ({'exit_code': 0}, 'pass'), ({'exitCode': 1}, 'fail'), ({'exitCode': 2}, 'fail'),
    ({'passed': True}, 'pass'), ({'passed': False}, 'fail'), ({'status': 'pass'}, 'pass'), ({'status': 'fail'}, 'fail'),
    ({'exitCode': True}, 'invalid_result'), ({'status': 'maybe'}, 'invalid_result'), ({}, 'invalid_result'),
    ([0], 'invalid_result'), ('not json', 'invalid_result'),
])
def test_harness_result_shapes(tmp_path, frozen_mixed, content, status):
    _, _, manifest = frozen_mixed
    assert rt.harness_from_result(harness_file(tmp_path, content), manifest) == status


def test_harness_result_bound_to_another_candidate_is_a_mismatch(tmp_path, frozen_mixed):
    _, _, manifest = frozen_mixed
    assert rt.harness_from_result(harness_file(tmp_path, {'exitCode': 0, 'candidateDiffSha256': 'f' * 64}), manifest) == 'candidate_mismatch'
    ok = {'exitCode': 0, 'candidateDiffSha256': manifest['diffSha256']}
    assert rt.harness_from_result(harness_file(tmp_path, ok), manifest) == 'pass'
    assert rt.harness_from_result(tmp_path / 'absent.json', manifest) == 'invalid_result'


def test_run_harness_uses_the_documented_command(tmp_path, monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen['command'], seen['kwargs'] = command, kwargs
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(rt.subprocess, 'run', fake_run)
    assert rt.run_harness(tmp_path / 'cand') == 'pass'
    command = seen['command']
    assert command[1].endswith('evals/skill-map-routing/run.py')
    assert command[command.index('--checkout') + 1] == str(tmp_path / 'cand')
    assert command[command.index('--check') + 1].endswith('evals/skill-map-routing/baseline.json')
    assert '--out' in command and seen['kwargs']['cwd'] == str(rt.REPO)
    monkeypatch.setattr(rt.subprocess, 'run', lambda command, **kw: subprocess.CompletedProcess(command, 1, b'', b''))
    assert rt.run_harness(tmp_path / 'cand') == 'fail'

    def boom(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(rt.subprocess, 'run', boom)
    assert rt.run_harness(tmp_path / 'cand') == 'unavailable'
    assert not list(Path(tempfile.gettempdir()).glob('rt-harness-*'))


def test_run_harness_flag_checks_the_frozen_candidate_first(tmp_path, repos, arms):
    out, manifest = do_freeze(tmp_path, repos, arms, tmp_path / 'root')
    calls = []

    def runner(checkout):
        calls.append(Path(checkout))
        return 'pass'

    assert rt.resolve_harness(manifest, None, True, None, runner) == 'pass' and calls == [repos[1].resolve()]
    assert rt.resolve_harness(manifest, None, False, None, runner) == 'not_run'
    with pytest.raises(rt.RealTrafficError):
        rt.resolve_harness(manifest, tmp_path / 'x.json', True, None, runner)
    (repos[1] / 'catalog' / 'tags.json').write_text('{"v":99}')              # the candidate moved on after the freeze
    git(repos[1], 'commit', '-q', '-am', 'drift')
    assert rt.resolve_harness(manifest, None, True, None, runner) == 'candidate_mismatch' and len(calls) == 1
    assert rt.resolve_harness(manifest, None, True, tmp_path / 'not-a-repo', runner) == 'unavailable'


def test_run_harness_through_evaluate(tmp_path, repos, arms):
    w = scaled_world(tmp_path, wins=11, losses=0)
    out, _ = do_freeze(tmp_path, repos, arms, w.root)
    w.flush()
    report, _ = rt.evaluate(out, w.root, [w.tx], run_harness_flag=True, harness_runner=lambda checkout: 'pass')
    assert report['harness'] == {'status': 'pass'} and report['verdict'] == 'keep'
    report, _ = rt.evaluate(out, w.root, [w.tx], run_harness_flag=True, harness_runner=lambda checkout: 'fail')
    assert report['verdict'] == 'discard'


# ------------------------------------------------------------------ the ledger and the report

def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_the_ledger_is_append_only_private_and_counts_only(tmp_path, frozen_mixed):
    w, out, manifest = frozen_mixed
    ledger = w.root / 'skill-fit' / 'improvement' / 'ledger.jsonl'
    report, line = run_eval(w, out)
    rt.append_ledger(w.root, line)
    first = ledger.read_bytes()
    assert stat.S_IMODE(ledger.stat().st_mode) == 0o600
    assert stat.S_IMODE(ledger.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE((w.root / 'skill-fit').stat().st_mode) == 0o700
    report2, line2 = run_eval(w, out, harness_status='fail')
    rt.append_ledger(w.root, line2)
    second = ledger.read_bytes()
    assert second.startswith(first) and len(second) > len(first)         # append-only: the old line is untouched
    rows = read_lines(ledger)
    assert [row['harness']['status'] for row in rows] == ['pass', 'fail']
    assert {row['manifestSha256'] for row in rows} == {rt.manifest_hash(manifest)}
    assert set(rows[0]) == {'schema', 'manifestSha256', 'freezeAt', 'evaluatedAt', 'cases', 'counts', 'discordant',
                            'signTest', 'harness', 'blockers', 'verdict'}
    assert rows[0]['schema'] == rt.LEDGER_SCHEMA and rows[0]['discordant']['candidateWins'] == 4
    assert stat.S_IMODE(ledger.stat().st_mode) == 0o600


def test_the_cli_appends_one_ledger_line_per_run_and_writes_a_private_report(tmp_path, frozen_mixed, capsys):
    w, out, _ = frozen_mixed
    result = harness_file(tmp_path, {'exitCode': 0})
    report_path = tmp_path / 'reports' / 'week.json'
    argv = ['evaluate', '--manifest', str(out), '--root', str(w.root), '--transcripts', str(w.tx),
            '--harness-result', str(result), '--out', str(report_path), '--now', '2026-10-18T18:30:00Z']
    assert rt.main(argv) == 0
    assert rt.main(argv) == 0
    summary = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert summary['status'] == 'completed' and summary['verdict'] == 'insufficient' and summary['discordant'] == 7
    ledger = w.root / 'skill-fit' / 'improvement' / 'ledger.jsonl'
    rows = read_lines(ledger)
    assert len(rows) == 2 and rows[0] == rows[1] and rows[0]['evaluatedAt'] == '2026-10-18T18:30:00.000Z'
    report = json.loads(report_path.read_text())
    assert report['schema'] == rt.REPORT_SCHEMA and report['verdict'] == 'insufficient'
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    assert {k: v for k, v in report.items() if k in rows[0]} == {k: v for k, v in rows[0].items() if k != 'schema'} | {'schema': report['schema']}


def test_the_first_ledger_line_creates_a_private_chain(tmp_path):
    root = tmp_path / 'fresh' / 'root'
    rt.append_ledger(root, {'a': 1})
    for directory in (root, root / 'skill-fit', root / 'skill-fit' / 'improvement'):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE((root / 'skill-fit' / 'improvement' / 'ledger.jsonl').stat().st_mode) == 0o600


def test_a_symlinked_ledger_is_refused_and_its_target_untouched(tmp_path, frozen_mixed):
    w, out, _ = frozen_mixed
    improvement = w.root / 'skill-fit' / 'improvement'
    improvement.mkdir(parents=True)
    target = tmp_path / 'elsewhere.jsonl'
    target.write_text('keep\n')
    (improvement / 'ledger.jsonl').symlink_to(target)
    with pytest.raises(rt.RealTrafficError) as caught:
        rt.append_ledger(w.root, {'a': 1})
    assert caught.value.code == rt.EXIT_REFUSED and target.read_text() == 'keep\n'


def test_a_symlinked_ledger_directory_is_refused(tmp_path):
    root = tmp_path / 'root'
    (root / 'skill-fit').mkdir(parents=True)
    real = tmp_path / 'real'
    real.mkdir()
    (root / 'skill-fit' / 'improvement').symlink_to(real)
    with pytest.raises(rt.RealTrafficError) as caught:
        rt.append_ledger(root, {'a': 1})
    assert caught.value.code == rt.EXIT_REFUSED and not list(real.iterdir())


def test_a_loose_or_torn_ledger_is_repaired_without_losing_lines(tmp_path):
    root = tmp_path / 'root'
    improvement = root / 'skill-fit' / 'improvement'
    improvement.mkdir(parents=True)
    ledger = improvement / 'ledger.jsonl'
    ledger.write_text('{"old":1}\n{"torn":')
    os.chmod(ledger, 0o644)
    rt.append_ledger(root, {'new': 2})
    assert stat.S_IMODE(ledger.stat().st_mode) == 0o600
    lines = ledger.read_text().splitlines()
    assert lines[0] == '{"old":1}' and lines[1] == '{"torn":' and json.loads(lines[2]) == {'new': 2}


def test_a_symlinked_report_path_is_refused(tmp_path):
    target = tmp_path / 't.json'
    target.write_text('x')
    link = tmp_path / 'link.json'
    link.symlink_to(target)
    with pytest.raises(rt.RealTrafficError):
        rt.write_report(link, {'a': 1})
    assert target.read_text() == 'x'


# ------------------------------------------------------------------ privacy

def all_files(*bases):
    for base in bases:
        base = Path(base)
        if base.is_file():
            yield base
        elif base.is_dir():
            yield from (p for p in base.rglob('*') if p.is_file())


def test_no_prompt_text_session_id_path_or_description_reaches_any_output(tmp_path, frozen_mixed, capsys):
    w, out, _ = frozen_mixed
    result = harness_file(tmp_path, {'exitCode': 0})
    report_path = tmp_path / 'reports' / 'week.json'
    assert rt.main(['evaluate', '--manifest', str(out), '--root', str(w.root), '--transcripts', str(w.tx),
                    '--harness-result', str(result), '--out', str(report_path)]) == 0
    dev_path = tmp_path / 'reports' / 'dev.json'
    assert rt.main(['dev-report', '--root', str(w.root), '--baseline-checkout', str(tmp_path),
                    '--baseline-index', str(out.parent / (out.name + '.arms') / 'baseline' / 'index.json'),
                    '--baseline-map', str(out.parent / (out.name + '.arms') / 'baseline' / 'map.json'),
                    '--transcripts', str(w.tx), '--out', str(dev_path)]) == 0
    stdout = capsys.readouterr().out
    outputs = {'stdout': stdout.lower()}
    for path in all_files(report_path, dev_path, w.root / 'skill-fit' / 'improvement'):
        outputs[path.name] = path.read_text().lower()
    assert len(outputs) >= 4
    for name, text in outputs.items():
        assert SENTINEL not in text, name
        assert DESC_SENTINEL not in text, name
        assert str(tmp_path).lower() not in text, name
        for session in w.sessions:
            assert session.lower() not in text, name
        for prompt in w.prompts:
            assert prompt.lower() not in text, name
    # the frozen manifest and its copies hold no prompt text either (descriptions live in the frozen map by design)
    for path in all_files(out, out.parent / (out.name + '.arms')):
        assert SENTINEL not in path.read_text().lower()
    # opaque occurrence keys are in the private report only
    assert 'occurrenceKey' in report_path.read_text()
    assert 'occurrencekey' not in (w.root / 'skill-fit' / 'improvement' / 'ledger.jsonl').read_text().lower()


def test_nothing_is_written_beside_the_replay_and_temp_dirs_are_removed(tmp_path, frozen_mixed):
    w, out, _ = frozen_mixed
    before = set(Path(tempfile.gettempdir()).glob('rt-*'))
    run_eval(w, out)
    assert set(Path(tempfile.gettempdir()).glob('rt-*')) == before
    assert not (w.root / 'skill-fit' / 'records' / 'rt').exists()
    assert sorted(p.name for p in (w.root / 'skill-fit').iterdir()) == ['labels', 'outcomes', 'records']   # evaluate() alone writes none


def test_errors_print_only_safe_reasons(tmp_path, capsys, monkeypatch):
    secret = 'prompt text with: secrets; and /private/path'
    assert rt.contract.safe_reason(RuntimeError(secret)) is None
    assert rt.contract.safe_reason(rt.RealTrafficError('the manifest is missing or unreadable')) is not None

    def explode(args):
        raise ValueError(secret)

    monkeypatch.setattr(rt, 'run_dev_report', explode)
    code = rt.main(['dev-report', '--root', str(tmp_path), '--baseline-checkout', str(tmp_path),
                    '--out', str(tmp_path / 'r.json')])
    assert code == rt.EXIT_FAILED
    assert json.loads(capsys.readouterr().out) == {'status': 'failed', 'error': 'ValueError', 'reason': None}


def test_refusals_print_safe_reasons(tmp_path, capsys):
    code = rt.main(['evaluate', '--manifest', str(tmp_path / 'nowhere.json'), '--root', str(tmp_path),
                    '--out', str(tmp_path / 'r.json')])
    printed = json.loads(capsys.readouterr().out)
    assert code == rt.EXIT_REFUSED and printed['status'] == 'refused'
    assert str(tmp_path) not in json.dumps(printed) and printed['reason'] == 'the manifest is missing or unreadable'


# ------------------------------------------------------------------ replay isolation (F8)

class Spy:
    """Records every child process started: argv, environment, cwd and the state of its temp dirs at spawn time."""

    TEMP_KEYS = ('RHIZE_TYPED_DECISIONS_ROOT', 'XDG_DATA_HOME', 'RHIZE_CONTEXT_MANAGER_DIR')

    def __init__(self, monkeypatch):
        self.calls = []
        original = subprocess.Popen

        def popen(args, *a, **kw):
            env = dict(kw.get('env') or {})
            fresh = {key: Path(env[key]).is_dir() and not any(Path(env[key]).iterdir()) for key in self.TEMP_KEYS
                     if key in env}
            self.calls.append({'args': [str(x) for x in args], 'env': env, 'cwd': kw.get('cwd'), 'fresh': fresh})
            return original(args, *a, **kw)

        monkeypatch.setattr(subprocess, 'Popen', popen)

    def replays(self):
        return [c for c in self.calls if any(a.endswith('route_replay.js') for a in c['args']) and '--hashes' not in c['args']]


def test_prompts_reach_node_through_stdin_only_in_an_isolated_environment(tmp_path, monkeypatch, frozen_mixed):
    w, out, _ = frozen_mixed
    spy = Spy(monkeypatch)
    report, _ = run_eval(w, out)
    assert report['discordant']['candidateWins'] == 4                              # the prompts really arrived (stdin)
    replays = spy.replays()
    assert len(replays) == 2
    temp = Path(tempfile.gettempdir())
    for call in replays:
        env = call['env']
        blob = ' '.join(call['args']) + ' ' + ' '.join(f'{k}={v}' for k, v in env.items())
        assert SENTINEL not in blob.lower()
        assert not any(prompt.lower() in blob.lower() for prompt in w.prompts)
        assert env['HOME'] == os.environ['HOME']                                   # HOME is unchanged
        assert env['RHIZE_TYPED_DECISIONS_ROOT'] != env['XDG_DATA_HOME']
        assert str(w.root) not in ' '.join(env.values())
        for key in (*Spy.TEMP_KEYS, 'RHIZE_SUGGESTION_LOG'):
            assert Path(env[key]).is_relative_to(temp), key                          # fresh temp dirs
        assert call['fresh'] == {key: True for key in Spy.TEMP_KEYS}                 # created empty for this run
        assert set(env) <= set(rt.CHILD_ENV_ALLOWLIST) | set(Spy.TEMP_KEYS) | {'RHIZE_SUGGESTION_LOG'}
        assert '--require' in call['args'] and call['args'][call['args'].index('--require') + 1].endswith('network-guard.js')
        assert call['args'].count(str(rt.backfill.REPLAY_SCRIPT)) == 1 and len(call['args']) == 6   # node --require g s i m
        assert Path(env['RHIZE_TYPED_DECISIONS_ROOT']).parent == Path(call['cwd'])
    for call in replays:
        for key in Spy.TEMP_KEYS:
            assert not Path(call['env'][key]).exists()                              # removed after the run


def test_credentials_in_the_parent_environment_do_not_reach_the_replay_child(tmp_path, monkeypatch, frozen_mixed):
    w, out, _ = frozen_mixed
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'secret-key-value')
    monkeypatch.setenv('NODE_OPTIONS', '--require /nonexistent.js')
    spy = Spy(monkeypatch)
    run_eval(w, out)
    for call in spy.replays():
        assert 'ANTHROPIC_API_KEY' not in call['env'] and 'NODE_OPTIONS' not in call['env']


def test_the_network_guard_aborts_any_socket_or_name_lookup(tmp_path):
    guard = tmp_path / 'guard.js'
    guard.write_text(rt.NETWORK_GUARD)
    for snippet in ("require('net').connect(9, '127.0.0.1')", "require('net').createConnection(9)",
                    "require('dns').lookup('example.com', () => {})", "require('dgram').createSocket('udp4')",
                    "fetch('http://127.0.0.1:9/')", "require('http').get('http://127.0.0.1:9/')",
                    "require('https').request('https://127.0.0.1:9/')", "require('tls').connect(9)"):
        done = subprocess.run([NODE, '--require', str(guard), '-e', snippet], capture_output=True, text=True, timeout=30)
        assert done.returncode == rt.GUARD_EXIT, snippet
        assert 'network_use_denied' in done.stderr
    quiet = subprocess.run([NODE, '--require', str(guard), '-e', "process.stdout.write('ok')"], capture_output=True,
                           text=True, timeout=30)
    assert quiet.returncode == 0 and quiet.stdout == 'ok'


def test_a_replay_child_that_touches_the_network_fails_the_run(tmp_path, monkeypatch, frozen_mixed):
    w, out, _ = frozen_mixed
    original = rt.NETWORK_GUARD
    monkeypatch.setattr(rt, 'NETWORK_GUARD', original + "\nrequire('net').connect(9, '127.0.0.1');\n")
    with pytest.raises(rt.RealTrafficError, match='could not read an index|replay process failed'):
        run_eval(w, out)


# ------------------------------------------------------------------ dev report

def test_dev_report_lists_baseline_misses_by_skill_and_makes_no_keep_decision(tmp_path, arms):
    w = mixed_world(tmp_path)
    w.add('gamma seo nimbus audit way before', [C, A], acceptable=[C], ts='2026-01-01T00:00:00.000Z')      # dev sees old data
    w.flush()
    report = rt.dev_report(w.root, tmp_path, [w.tx], baseline_index=arms['baseline_index'],
                           baseline_map=arms['baseline_map'], now='2026-10-12T00:00:00Z')
    assert 'verdict' not in report and 'signTest' not in report and report['schema'] == rt.DEV_REPORT_SCHEMA
    assert report['cases']['scored'] == 13 and report['cases']['byType'] == {'labeled': 7, 'weak': 3, 'silence': 3}
    assert report['counts']['labeled']['miss'] == 3 and report['counts']['labeled']['falseFire'] == 1
    misses = {m['skill']: m for m in report['topMisses']}
    assert misses['demo:gamma-seo'] == {'skill': 'demo:gamma-seo', 'total': 4, 'silent': 3, 'misrouted': 1}
    assert misses['demo:alpha-audit'] == {'skill': 'demo:alpha-audit', 'total': 2, 'silent': 1, 'misrouted': 1}
    assert [m['total'] for m in report['topMisses']] == sorted((m['total'] for m in report['topMisses']), reverse=True)
    assert report['topFalseFires'] == [{'skill': 'demo:epsilon-ops', 'total': 2, 'fires': 2}]
    assert report['baseline']['mapSha256'] == rt.sha256_bytes(arms['baseline_map'].read_bytes())
    assert report['metrics']['labeled']['falseFireRate'] == 1.0


def test_dev_report_top_limits_the_lists(tmp_path, arms):
    w = mixed_world(tmp_path)
    w.flush()
    report = rt.dev_report(w.root, tmp_path, [w.tx], baseline_index=arms['baseline_index'],
                           baseline_map=arms['baseline_map'], top=1)
    assert len(report['topMisses']) == 1


def test_dev_report_builds_the_baseline_from_its_checkout_when_no_paths_are_given(tmp_path):
    w = World(tmp_path)
    w.add('nothing relevant at all', [A, B], stratum='silent_sample')
    w.flush()
    before = set(Path(tempfile.gettempdir()).glob('rt-dev-*'))
    report = rt.dev_report(w.root, REPO, [w.tx], build_args=hermetic(tmp_path))
    assert report['cases']['scored'] == 1 and report['counts']['silence'] == {'total': 1, 'fire': 0, 'quiet': 1}
    assert set(Path(tempfile.gettempdir()).glob('rt-dev-*')) == before


# ------------------------------------------------------------------ the command line, end to end

def test_freeze_then_evaluate_through_the_command_line(tmp_path, repos, arms, capsys):
    w = scaled_world(tmp_path, wins=11, losses=1)
    out = tmp_path / 'week' / 'cand-1.manifest.json'
    freeze_argv = ['freeze', '--baseline-checkout', str(repos[0]), '--candidate-checkout', str(repos[1]),
                   '--out', str(out), '--root', str(w.root), '--now', FREEZE,
                   '--baseline-index', str(arms['baseline_index']), '--baseline-map', str(arms['baseline_map']),
                   '--candidate-index', str(arms['candidate_index']), '--candidate-map', str(arms['candidate_map'])]
    assert rt.main(freeze_argv) == 0
    frozen = json.loads(capsys.readouterr().out)
    assert frozen['status'] == 'frozen' and frozen['manifestSha256'] == rt.manifest_hash(json.loads(out.read_text()))
    assert rt.main(freeze_argv) == rt.EXIT_REFUSED                                  # a frozen manifest is never replaced
    assert json.loads(capsys.readouterr().out)['status'] == 'refused'
    w.flush()
    result = harness_file(tmp_path, {'exitCode': 0, 'candidateDiffSha256': json.loads(out.read_text())['diffSha256']})
    assert rt.main(['evaluate', '--manifest', str(out), '--root', str(w.root), '--transcripts', str(w.tx),
                    '--harness-result', str(result), '--out', str(tmp_path / 'week' / 'eval.json')]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['verdict'] == 'keep' and summary['discordant'] == 12 and summary['harness'] == 'pass'
    assert summary['manifestSha256'] == frozen['manifestSha256']
    assert len(read_lines(w.root / 'skill-fit' / 'improvement' / 'ledger.jsonl')) == 1


def test_the_mandated_list_is_frozen_with_the_candidate(tmp_path, repos, arms):
    w = World(tmp_path)
    out, manifest = do_freeze(tmp_path, repos, arms, w.root, mandated=['Demo:Gamma-SEO'])
    empty_out, empty = do_freeze(tmp_path, repos, arms, w.root, mandated=[], name='none.manifest.json')
    assert manifest['rule']['weakPositive']['mandatedSkills'] == ['demo:gamma-seo']
    assert empty['rule']['weakPositive']['mandatedSkills'] == []
    w.add('gamma seo nimbus audit mandated', [C, A], outcome=('invoked_unlisted', 'demo:gamma-seo'))
    w.add('gamma seo nimbus audit chosen', [C, A], outcome=('invoked_unlisted', 'demo:other'))
    w.flush()
    report, _ = run_eval(w, out)
    assert report['cases']['byType']['weak'] == 1 and report['cases']['excluded']['notACase'] == 1
    report, _ = run_eval(w, empty_out)
    assert report['cases']['byType']['weak'] == 2


# ------------------------------------------------------------------ misc

def test_parse_instant_forms():
    assert rt.iso(rt.parse_instant('2026-10-11')) == '2026-10-11T00:00:00.000Z'
    assert rt.iso(rt.parse_instant('2026-10-11T12:00:00+02:00')) == '2026-10-11T10:00:00.000Z'
    with pytest.raises(rt.RealTrafficError):
        rt.parse_instant('2026-10-11T12:00:00')
    with pytest.raises(rt.RealTrafficError):
        rt.parse_instant('tomorrow')


def test_evaluate_and_run_harness_are_mutually_exclusive_on_the_command_line(tmp_path):
    with pytest.raises(SystemExit):
        rt.build_parser().parse_args(['evaluate', '--manifest', 'm', '--root', 'r', '--out', 'o',
                                      '--harness-result', 'h.json', '--run-harness'])


def test_the_evaluator_never_imports_or_calls_a_gate_registry_or_network_client():
    import ast
    tree = ast.parse((REPO / 'evals' / 'skill-map-routing' / 'real_traffic.py').read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split('.')[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {node.module.split('.')[0]} | {alias.name for alias in node.names}
    assert not imported & {'socket', 'urllib', 'http', 'requests', 'decision_registry', 'laya_choice', 'cohorts_gate'}
    literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert not literals & {'push', 'merge', 'set-mode', 'pr', 'reserve', 'evaluate_cohort'}
    assert 'registry-state.json' not in literals
