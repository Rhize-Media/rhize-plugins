"""test_refinement_backlog.py — the read-only refinement-queue backlog report."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / "rhize-context-manager" / "scripts"
          / "refinement_backlog.py")
NOW = "2026-11-15T00:00:00Z"
MARK = "SECRET-MARKER-XYZ"


def run(queue, *extra, as_json=True):
    cmd = [sys.executable, str(SCRIPT), "report", "--queue", str(queue), "--now", NOW, *extra]
    if as_json:
        cmd.append("--json")
    return subprocess.run(cmd, capture_output=True, text=True)


def write(path, rows, raw=()):
    lines = [json.dumps(r) for r in rows] + list(raw)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def ent(i, **kw):
    base = {"id": i, "ts": "2026-11-10T00:00:00Z", "source": "s", "repo": "r", "status": "pending"}
    base.update(kw)
    return base


def test_ranking_and_tiebreak(tmp_path):
    q = write(tmp_path / "q.jsonl", [
        ent("b"), ent("a"),
        ent("c", count=5, ts="2026-01-01T00:00:00Z"),
        ent("d", ts="2026-11-14T00:00:00Z"),
        ent("e", evidence={"generated_at": "2026-11-15T00:00:00Z"}),
    ])
    rep = json.loads(run(q).stdout)
    assert [r["id"] for r in rep["top"]] == ["c", "e", "d", "a", "b"]
    assert rep["ranking"]["sessions"] == "not available"


def test_stale_and_ts_handling(tmp_path):
    q = write(tmp_path / "q.jsonl", [
        ent("old", ts="2026-10-01T00:00:00+00:00"),
        ent("new", ts="2026-11-10T00:00:00Z"),
        ent("none", ts=None), ent("bad", ts="not-a-date"),
    ])
    rep = json.loads(run(q, "--stale-days", "30").stdout)
    rows = {r["id"]: r for r in rep["top"]}
    assert rows["old"]["stale"] and rows["old"]["age_days"] == 45.0
    assert not rows["new"]["stale"]
    for k in ("none", "bad"):
        assert rows[k]["age_days"] is None and rows[k]["stale"] is False
        assert rows[k]["age_unknown"] is True
    assert rep["stale"] == 1


def test_non_pending_counted_not_ranked_and_unparsable(tmp_path):
    q = write(tmp_path / "q.jsonl",
              [ent("p"), ent("t", status="triaged"), ent("x", status="rejected")],
              raw=["{broken", "[1,2]", ""])
    rep = json.loads(run(q).stdout)
    assert [r["id"] for r in rep["top"]] == ["p"]
    assert rep["totals_by_status"] == {"pending": 1, "triaged": 1, "rejected": 1}
    assert rep["unparsable"] == 2 and rep["pending"] == 1


def test_supersession(tmp_path):
    kw = dict(target_skill="foo", signal_type="t", subtype="u")
    q = write(tmp_path / "q.jsonl", [
        ent("o1", ts="2026-11-01T00:00:00Z", **kw),
        ent("new", ts="2026-11-09T00:00:00Z", **kw),
        ent("o2", ts="2026-11-05T00:00:00Z", **kw),
        ent("other", ts="2026-11-02T00:00:00Z", target_skill="foo", signal_type="z", subtype="u"),
        ent("noskill", ts="2026-11-02T00:00:00Z", **{**kw, "target_skill": ""}),
    ])
    rep = json.loads(run(q).stdout)
    assert rep["supersession_candidates"] == [
        {"older_id": "o1", "newer_id": "new"}, {"older_id": "o2", "newer_id": "new"}]


def test_target_outcomes(tmp_path):
    root = tmp_path / "skills"
    (root / "here").mkdir(parents=True)
    q = write(tmp_path / "q.jsonl", [
        ent("p", target_skill="here"),
        ent("m", target_skill="gone"),
        ent("esc", target_skill="../x"),
    ])
    rep = json.loads(run(q, "--root", str(root)).stdout)
    loss = {c["id"]: c for c in rep["target_loss_candidates"]}
    assert "p" not in loss
    assert loss["m"]["status"] == "target_missing" and loss["m"]["checked"]
    assert loss["esc"]["status"] == "lookup_failed"
    rep = json.loads(run(q, "--root", str(tmp_path / "absent")).stdout)
    assert {c["status"] for c in rep["target_loss_candidates"]} == {"lookup_failed"}


def test_top_and_json_shape(tmp_path):
    q = write(tmp_path / "q.jsonl", [ent("a%d" % i) for i in range(5)])
    rep = json.loads(run(q, "--top", "2").stdout)
    assert len(rep["top"]) == 2
    assert set(rep) == {"totals_by_status", "pending", "stale", "unparsable", "stale_days",
                        "ranking", "top", "supersession_candidates", "target_loss_candidates"}
    text = run(q, "--top", "2", as_json=False).stdout
    assert "pending: 5" in text and "Supersession" in text


def test_missing_queue_exit_2(tmp_path):
    r = run(tmp_path / "nope.jsonl")
    assert r.returncode == 2 and r.stderr


def test_privacy(tmp_path):
    q = write(tmp_path / "q.jsonl", [ent(
        "p", pattern=MARK, note=MARK, filter_note=MARK, triage_reason=MARK, harvest_log=MARK,
        disposition=MARK, evidence={"kind": MARK, "generated_at": "2026-11-01T00:00:00Z"},
        target_skill="skill-" + "a", est_savings="~" + MARK)])
    for as_json in (True, False):
        r = run(q, as_json=as_json)
        assert r.returncode == 0 and MARK not in r.stdout + r.stderr


def test_no_write(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    q = write(d / "q.jsonl", [ent("a"), ent("b", target_skill="x")])
    before = (q.read_bytes(), q.stat().st_mtime_ns, sorted(os.listdir(d)))
    assert run(q, "--root", str(tmp_path)).returncode == 0
    assert run(q, as_json=False).returncode == 0
    assert (q.read_bytes(), q.stat().st_mtime_ns, sorted(os.listdir(d))) == before
