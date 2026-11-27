import hashlib
import json
from pathlib import Path
import sys

import pytest

EVAL = Path(__file__).resolve().parents[2] / "evals/typed-decision"
sys.path.insert(0, str(EVAL))
import receipt_snapshot as reader
import skill_filter_comparison as study
from typed_decision_testkit import INC, make_label, make_record
from decision_pilot import inventory


def test_real_inventory_boundaries_and_independent_oracle(tmp_path):
    root = tmp_path / "receipts"
    root.mkdir()
    for i in reversed(range(9999)):
        (root / f"{i:064x}.json").write_text(json.dumps({"i": i}))
    for i in (9999, 10000, 10001, 10807):
        start = len(list(root.iterdir()))
        for j in range(start, i):
            (root / f"{j:064x}.json").write_text(json.dumps({"i": j}))
        members = reader.scan(root)
        rows = reader.scan(root, members)
        assert list(members) == sorted(members)
        assert members == {p.stem: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
        if i <= 10000:
            assert rows == inventory(root)
        else:
            assert rows == [(f"{j:064x}", {"i": j}) for j in range(i)]


def test_manifest_integrity_arrival_mutation_and_refusals(tmp_path, monkeypatch):
    root = tmp_path / "receipts"
    root.mkdir()
    p = root / ("a" * 64 + ".json")
    q = root / ("b" * 64 + ".json")
    p.write_text("{}")
    out = tmp_path / "manifest"
    digest = reader.seal(root, out)
    members = reader.open_manifest(out, digest, root)
    q.write_text("{}")
    assert reader.scan(root, members) == [(p.stem, {})]
    assert q.stem in reader.scan(root)
    with pytest.raises(FileExistsError):
        reader.seal(root, out)
    p.write_text('{"updated":1}')
    with pytest.raises(ValueError, match="changed"):
        reader.scan(root, members)
    p.unlink()
    with pytest.raises(FileNotFoundError):
        reader.scan(root, members)
    p.symlink_to(q)
    with pytest.raises(OSError):
        reader.scan(root)
    p.unlink()
    with pytest.raises(ValueError, match="digest mismatch"):
        reader.open_manifest(out, "0" * 64, root)
    monkeypatch.setattr(reader, "LIMIT", 1)
    assert len(reader.scan(root)) == 1
    p.write_text("{}")
    with pytest.raises(ValueError, match="resource limit"):
        reader.scan(root)


def test_prospective_frame_and_deferred_decision():
    ts = "2026-11-28T12:00:00Z"
    rows = [make_record(j, ts=ts, laya_revision=study.KEY[2]) for j in range(6)]
    for row in rows:
        row.update(
            policySha256=study.KEY[0],
            instrumentSha256=study.KEY[1],
            host="claude",
            routerSourceSha256=study.ROUTER,
            indexSha256=study.INDEX,
        )
    prior = dict(rows[0], ts="2026-11-25T12:00:00Z")
    rows[2]["host"] = "codex"
    rows[3]["basis"] = "backfill"
    labels = [dict(make_label(r, acceptable=[INC], labeled_at=ts), basis="ai_model_reviewed") for r in rows]
    excluded = {rows[1]["occurrenceKey"]}
    data = study.compare([prior, *rows], labels, excluded, study.END)
    assert data["capturedEligible"] == data["reviewed"] == 2
    assert data["policies"]["incumbent"]["rawHits"] == 2
    assert data["result"] == "inconclusive" and not data["qualifyingCandidates"]
    assert study.compare(rows, labels, set(), study.START)["result"] == "collecting"


def test_retention_and_noise_gates_use_paired_cases_and_unknowns():
    ts = "2026-11-28T12:00:00Z"
    rows, labels = [], []
    for i in range(120):
        good = i < 70
        rec = make_record(
            i, score=5 if good else 2, choice=INC if good else "none", ts=ts, laya_revision=study.KEY[2]
        )
        rec.update(
            policySha256=study.KEY[0],
            instrumentSha256=study.KEY[1],
            host="claude",
            routerSourceSha256=study.ROUTER,
            indexSha256=study.INDEX,
        )
        rows.append(rec)
        labels.append(
            dict(make_label(rec, acceptable=[INC] if good else [], labeled_at=ts), basis="ai_model_reviewed")
        )
    result = study.compare(rows, labels, set(), study.END)
    assert result["result"] == "review_rules_only"
    assert result["policies"]["floor@3"]["retentionLower95"] == 1
    # Unknown outcomes on suppressed suggestions can erase the apparent advantage.
    assert study.compare(rows, labels[:-1], set(), study.END)["result"] == "inconclusive"


def test_rollout_requires_two_distinct_launches_same_release(tmp_path):
    from operational_rollout import Rollout, digest, publish

    cfg = {
        "release": "pinned",
        "releaseRoot": str(EVAL.parents[1]),
        "readerSha256": digest(EVAL / "receipt_snapshot.py"),
        "auditRoot": str(tmp_path),
        "pins": [],
    }
    rollout = Rollout(cfg)
    assert not rollout.active()
    mark = {"release": cfg["release"], "readerSha256": cfg["readerSha256"], "launch": "a"}
    for name in ("a", "duplicate"):
        publish(tmp_path / ("qualified-" + name + ".json"), mark)
    assert not rollout.active()
    publish(tmp_path / "qualified-other.json", dict(mark, release="old", launch="b"))
    assert not rollout.active()
    publish(tmp_path / "qualified-b.json", dict(mark, launch="b"))
    assert rollout.active()
    with pytest.raises(ValueError, match="unreviewed"):
        rollout.command(EVAL / "pilot_cycle.py", ["--shadow-only"])
