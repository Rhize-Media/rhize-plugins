"""Daily skill-fit scoreboard: counts and hashes only, built from the cycle receipt, records, labels and outcomes."""
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
    ALT1, INC, LAYA_REV, SCRIPTS, disagreements, fixture, label_cohort, load_cycle_module, make_label,
    make_record, min_pass_x, small_registry, write_labels, write_records)
from typed_decisions import cohorts, contract, decision_registry as reg, records, scoreboard  # noqa: E402

SKILL = 'skill-fit'
CLI = SCRIPTS / 'typed_decisions' / 'scoreboard.py'
CYCLE = load_cycle_module()
NOW = '2026-10-12T12:00:00Z'


@pytest.fixture(autouse=True)
def _runtime_pin(monkeypatch):
    """Roots without a laya-runtime.json read as running the fixtures' checkpoint (LAYA_REV); a real pin file wins."""
    real = records.laya_revision

    def pinned(root=None):
        value = real(root)
        base = Path(root) if root is not None else records.default_root()
        return LAYA_REV if value == 'unknown' and not (base / 'laya-runtime.json').exists() else value

    monkeypatch.setattr(records, 'laya_revision', pinned)


@pytest.fixture
def root(tmp_path):
    # The Laya runtime pin the fixtures' records and bindings were produced under (activation writes it).
    path = tmp_path / 'typed-decisions'
    path.mkdir(mode=0o700)
    (path / 'laya-runtime.json').write_text(json.dumps({'revision': LAYA_REV}))
    return path


def outcome_for(rec, kind):
    outcome = copy.deepcopy(fixture('outcomes.json')['valid'][
        {'invoked_emitted': 'invoked-emitted', 'none_invoked': 'none-invoked',
         'transcript_unavailable': 'transcript-unavailable'}[kind]])
    outcome.update({'decisionId': rec['decisionId'], 'occurrenceKey': rec['occurrenceKey']})
    return contract.validate_outcome(outcome)


def populated(root):
    registry = small_registry()
    treatment = [make_record(i, arm='treatment', choice=INC, bucket='lt200', latency=10.0 * (i + 1)) for i in range(10)]
    holdback = [make_record(100 + i, arm='holdback', choice=INC, bucket='600-1200', latency=100.0) for i in range(5)]
    timeout = [make_record(200, status='timeout', bucket='lt200', latency=800.0)]
    disagree = disagreements(45, start=300)
    backfill = [make_record(500 + i, basis='backfill', bucket='gt1200', latency=70.0) for i in range(4)]
    everything = treatment + holdback + timeout + disagree + backfill
    write_records(root, everything)
    kinds = ['invoked_emitted'] * 6 + ['none_invoked'] * 3 + ['transcript_unavailable']
    for rec, kind in zip(treatment, kinds):
        records.append(root, SKILL, 'outcomes', outcome_for(rec, kind))
    for rec, kind in zip(holdback, ['invoked_emitted'] * 4 + ['none_invoked']):
        records.append(root, SKILL, 'outcomes', outcome_for(rec, kind))
    pool = [make_label(treatment[0], acceptable=[INC], stratum='agreement', inclusion=0.5),
            make_label(disagree[0], acceptable=[ALT1], stratum='disagreement', inclusion=0.25)]
    write_labels(root, pool)
    reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0, now='2026-10-09T00:00:00Z',
               registry=registry)
    reg.mutate(root, SKILL, 'shadow', actor='cli', reason='back_to_shadow', expected_revision=1,
               now='2026-10-10T00:00:00Z', registry=registry)
    first = CYCLE.run_cycle(root, '2026-10-11T00:00:00Z', registry=registry, seed=1)
    event = cohorts.cohort_ledger(root)[first['cohorts'][0]['cohortId']]['reserve']
    by_key = {r['occurrenceKey']: r for r in everything}
    label_cohort(root, event, by_key, not_hit=min_pass_x(20) - 1)
    CYCLE.run_cycle(root, '2026-10-11T06:00:00Z', registry=registry, seed=1)       # fails, reserves attempt 2
    return registry


def test_empty_root_renders_both_formats_without_crashing(root):
    data = scoreboard.build(root, NOW)
    text = scoreboard.render_md(data)
    assert 'Mode: **shadow**' in text and 'No cohort reserved yet.' in text and 'No Laya calls recorded yet.' in text
    assert data['alternatives'] is None and data['lastCycle'] is None and data['cohorts'] == []
    json.dumps(data)                                                       # serializable


def test_populated_scoreboard_reports_counts_gate_and_laya_latency(root):
    populated(root)
    data = scoreboard.build(root, NOW)
    assert data['mode']['effective'] == 'shadow' and data['mode']['revision'] == 2 and not data['mode']['pinned']
    assert data['lastModeChange'] == {'at': '2026-10-10T00:00:00Z', 'actor': 'cli', 'fromMode': 'off',
                                      'toMode': 'shadow', 'reason': 'back_to_shadow', 'revision': 2}
    assert data['records']['byBasis'] == {'live': 61, 'backfill': 4}
    assert data['records']['liveArms'] == {'treatment': 56, 'holdback': 5}
    assert data['prevalence']['live'] == {'fired': 60, 'disagreements': 45, 'share': 45 / 60}
    assert [(c['attempt'], c['status'], c['verdict']) for c in data['cohorts']] == [
        (1, 'consumed', 'fail'), (2, 'awaiting_labels', None)]
    assert data['lastVerdict']['statistic']['x'] == min_pass_x(20) - 1 and data['lastVerdict']['verdict'] == 'fail'
    short = data['laya']['live']['lt200']
    assert short['calls'] == 56 and short['statuses'] == {'ok': 55, 'timeout': 1}
    assert data['laya']['live']['600-1200'] == {'calls': 5, 'statuses': {'ok': 5}, 'p50': 100.0, 'p90': 100.0}
    assert data['laya']['backfill']['gt1200']['p90'] == 70.0
    assert data['lastCycle']['actions'] == ['evaluate', 'reserve'] and len(data['lastCycle']['versions']['policySha256']) == 64
    assert data['alternatives']['status'] == 'ok'
    names = [a['name'] for a in data['alternatives']['alternatives']]
    assert 'incumbent' in names and 'cosign-v1' in names and 'swap' in names


def test_acceptance_is_a_labelled_secondary_signal_split_by_arm(root):
    populated(root)
    acceptance = scoreboard.build(root, NOW)['acceptance']
    assert 'secondary' in acceptance['note']
    assert acceptance['byArm']['treatment'] == {'emitted': 9, 'invokedEmitted': 6, 'rate': 6 / 9}   # unavailable excluded
    assert acceptance['byArm']['holdback'] == {'emitted': 5, 'invokedEmitted': 4, 'rate': 0.8}
    assert acceptance['outcomes'] == {'invoked_emitted': 10, 'none_invoked': 4, 'transcript_unavailable': 1}


def test_markdown_has_every_section_and_leaks_nothing_textual(root):
    populated(root)
    data = scoreboard.build(root, NOW)
    text = scoreboard.render_md(data)
    for heading in ('## Laya skill-fit scoreboard', '### Gate', '### Report-only alternatives', '### Acceptance',
                    '### Laya latency and status by prompt length', '### Last verdict'):
        assert heading in text
    assert 'Disagreement prevalence among fired (live): 45/60 (75.0%)' in text
    assert 'secondary' in text and 'never deployed' in text and 'Last mode change: off -> shadow' in text
    assert '| cosign-v1 | deployable |' in text and '| floor@3 | alternative |' in text
    assert len(text.splitlines()) < 120                                            # short enough for the daily summary

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, str):
            yield value
    strings = list(walk(data))
    assert all(len(text_) < 400 for text_ in strings)
    assert not any(text_.startswith('skill:') or ' ' in text_ and len(text_) > 120 for text_ in strings if text_ != data['alternatives']['caveat'])


def test_a_pinned_cosign_shows_the_pin_and_the_demotion_watch(root):
    registry = small_registry()
    entry = reg.load_registry()['decisions'][SKILL]
    policy_hash, instrument_hash = cohorts.deployable_hashes(entry)
    reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_override', expected_revision=0, pinned=True,
               binding={'policySha256': policy_hash, 'instrumentSha256': instrument_hash, 'layaRevision': LAYA_REV,
                        'cohortId': None}, now='2026-10-01T00:00:00Z', registry=registry)
    write_records(root, [make_record(i, mode='cosign', ts=f'2026-10-11T10:{i:02d}:05.000Z') for i in range(25)])
    CYCLE.run_cycle(root, NOW, registry=registry, seed=1)
    text = scoreboard.render_md(scoreboard.build(root, NOW))
    assert 'Mode: **cosign**, pinned (automation suspended)' in text
    assert 'Demotion watch: quality n=0' in text and '(report-only)' in text


def test_cli_renders_md_json_and_a_private_out_file(root, tmp_path):
    populated(root)
    env = {**os.environ, 'HOME': str(tmp_path / 'home')}
    md = subprocess.run([sys.executable, str(CLI), 'render', '--root', str(root), '--now', NOW],
                        capture_output=True, text=True, timeout=120, env=env)
    assert md.returncode == 0 and md.stdout.startswith('## Laya skill-fit scoreboard (2026-10-12T12:00:00Z)')
    js = subprocess.run([sys.executable, str(CLI), 'render', '--root', str(root), '--format', 'json', '--now', NOW],
                        capture_output=True, text=True, timeout=120, env=env)
    assert js.returncode == 0 and json.loads(js.stdout)['schema'] == 'rhize-typed-decision-scoreboard-v1'
    out = tmp_path / 'out' / 'scoreboard.md'
    saved = subprocess.run([sys.executable, str(CLI), 'render', '--root', str(root), '--out', str(out), '--now', NOW],
                           capture_output=True, text=True, timeout=120, env=env)
    assert saved.returncode == 0 and json.loads(saved.stdout)['out'] == str(out)
    assert out.read_text() == md.stdout and stat.S_IMODE(out.stat().st_mode) == 0o600
    assert not (tmp_path / 'home').exists()


def test_the_scoreboard_never_writes_into_the_data_root(root):
    populated(root)
    before = sorted(str(p) for p in root.rglob('*'))
    scoreboard.build(root, NOW)
    assert sorted(str(p) for p in root.rglob('*')) == before


# ---------------------------------------------------------------- advise rows

def test_every_advise_decision_has_a_row_even_on_an_empty_root(root):
    data = scoreboard.build(root, NOW)
    rows = {r['decision']: r for r in data['advise']}
    expected = {d for d, e in reg.load_registry()['decisions'].items() if e['advise']}
    assert set(rows) == expected and 'credential-procedure' not in rows
    assert all(r['mode'] == 'shadow' and r['attempts'] == 0 and r['nextAlpha'] == 0.1 and r['lastVerdict'] is None
               for r in rows.values())
    assert rows['workflow-fit']['labelled'] is None and rows['model-routing']['labelled'] == 0
    assert '### Advise (majority-baseline gate' in scoreboard.render_md(data)


def test_advise_rows_report_the_ledger_receipt_and_labels(root):
    from typed_decision_testkit import CHOICE_IDS, write_choice, write_choice_label
    for i in range(120):
        result = write_choice(root, 'devflow-next-action', i, laya=CHOICE_IDS[i % 3], critical=True)
        write_choice_label(root, 'devflow-next-action', result['decisionId'], CHOICE_IDS[i % 3], ambiguous=i < 5)
    out = CYCLE.run_cycle(root, NOW, seed=1, probe=lambda: None)
    assert out['advise']['devflow-next-action']['verdict'] == 'pass'
    before = {str(p): p.stat().st_mtime_ns for p in root.rglob('*') if p.is_file()}
    data = scoreboard.build(root, NOW)
    assert before == {str(p): p.stat().st_mtime_ns for p in root.rglob('*') if p.is_file()}   # read-only
    row = {r['decision']: r for r in data['advise']}['devflow-next-action']
    assert row['mode'] == 'advise' and row['labelled'] == 115 and row['lastVerdict'] == 'pass' and row['attempts'] == 1
    assert row['accuracy'] == 1.0 and row['baselineAccuracy'] < 0.5 and row['cpLower'] > 0.5 and row['coverage'] == 1.0
    assert row['criticalCases'] >= 10 and row['criticalMisses'] == 0 and row['nextAlpha'] == 0.05
    md = scoreboard.render_md(data)
    assert '| devflow-next-action | advise | 115 | pass | 100.0% /' in md and '| 1 | 0.05 |' in md


def test_a_corrupt_advise_ledger_is_flagged_not_fatal(root):
    (root / 'model-routing').mkdir()
    (root / 'model-routing' / 'advise-cohorts.jsonl').write_text('{"event": "reserve", "decision": "model-routing"}\n')
    row = {r['decision']: r for r in scoreboard.build(root, NOW)['advise']}['model-routing']
    assert row['ledger'] == 'invalid'
    assert 'ledger invalid' in scoreboard.render_md(scoreboard.build(root, NOW))
