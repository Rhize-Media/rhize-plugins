"""Integration seams between the parity lanes: keep-warm writer -> scoreboard reader, and Codex
SKILL.md-read outcomes -> separate harvest candidates."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'rhize-context-manager' / 'scripts'))

from typed_decisions import harvest_signals, laya_choice, laya_keepwarm, scoreboard  # noqa: E402


def test_scoreboard_accepts_every_status_the_keepwarm_writer_can_record(tmp_path):
    assert set(laya_choice.STATUSES) <= set(scoreboard.KEEPWARM_STATUSES)
    root = tmp_path / 'td'
    root.mkdir(mode=0o700)
    started = datetime(2026, 10, 11, 23, 0, tzinfo=timezone.utc).timestamp()
    state = laya_keepwarm.initial_state(started, 90, 2)
    for status in laya_choice.STATUSES:
        state.update(lastStatus=status, lastPingAt=state['startedAt'], lastLatencyMs=42.0, pings=1)
        (root / 'laya-keepwarm.json').write_text(json.dumps(state))
        (root / 'laya-keepwarm.json').chmod(0o600)
        info = scoreboard.read_keepwarm(root, datetime(2026, 10, 11, 23, 5, tzinfo=timezone.utc))
        assert info['state'] == 'present' and info['lastStatus'] == status, (status, info)


def test_codex_skill_file_read_outcomes_form_their_own_harvest_candidates(tmp_path, monkeypatch):
    import test_harvest_signals as hs
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    (tmp_path / 'home').mkdir()
    seed = hs.Seeder(tmp_path / 'root')
    for via in ('skill_tool', 'skill_tool', 'skill_tool', 'skill_file_read', 'skill_file_read', 'skill_file_read'):
        rec = seed.record(host='codex')
        row = seed.outcome(rec, 'invoked_unlisted', hs.DASH)
        if via == 'skill_file_read':      # rewrite the appended outcome's via (Codex SKILL.md-read evidence)
            row = dict(row, via='skill_file_read', occurrenceKey=row['occurrenceKey'])
            hs.records.append(seed.root, 'skill-fit', 'outcomes', hs.contract.validate_outcome(row))
    found, counts = harvest_signals.collect(seed.root, hs.NOW_DT)
    patterns = sorted(c['pattern'] for c in found)
    assert len(found) == 2, patterns
    assert any('host codex, SKILL.md-read evidence' in p for p in patterns)
    assert any('host codex)' in p for p in patterns)


def test_bound_hashes_are_unchanged_so_the_live_cosign_binding_survives():
    """I8: a live cosign state is bound to these hashes; changing either one sends every host back to shadow
    and needs a fresh gate cohort. Update this pin only for a deliberate, reviewed instrument/policy change."""
    from typed_decisions import contract, instrument
    assert instrument.instrument_sha256() == '8df42f4f0a89fb13fe696e5dd427e67cce7bd0ee0401ac1acecb027830a7b0ed'
    assert contract.policy_sha256() == '19509e93ee72927d5e46ad62dd4fe69bfd090a31f86ac4f944a0ad89085eb205'
